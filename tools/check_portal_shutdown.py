# -*- coding: utf-8 -*-
"""门户自退（POST /_api/shutdown）控制检验。

为什么要有这条通路：
  插件（DSH 宿主）派生出来的子进程与门户进程在某些环境里不在同一个作业/
  沙箱内 —— taskkill 回「找不到进程」(128)，而门户明明还在应答；那个子进程
  连 `runs/portal_state.json` 都写不进去（Errno 13）。于是「点停止」报成功、
  实际什么都没停。让门户**自己退**才可靠。

本检验打的是真门户上的真实行为：
  ① 本机 POST /_api/shutdown → 200，且端口随后真的松掉；
  ② 非本机来源（用本机网卡地址访问，门户看到的是内网地址）→ 403，门户不动；
  ③ 反例控制：GET 不接受（只认 POST）；
  ④ 收尾：进程真的退出了（端口没了才算）。

运行：python -X utf8 tools/check_portal_shutdown.py
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable
SCRIPT = os.path.join(HERE, "portal_run.py")

results = []


def check(name, ok, detail=""):
    results.append((bool(ok), name, detail))
    print(("PASS  " if ok else "FAIL  ") + name + ((" —— " + detail) if detail else ""))


def free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def port_open(port, host="127.0.0.1"):
    sock = socket.socket()
    sock.settimeout(1.5)
    try:
        sock.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def post(port, path, host="127.0.0.1", method="POST"):
    req = urllib.request.Request("http://%s:%d%s" % (host, port, path), data=b"",
                                 method=method)
    try:
        with urllib.request.urlopen(req, timeout=6) as res:
            return res.status, res.read(600).decode("utf-8", "replace")
    except urllib.error.HTTPError as err:
        return err.code, err.read(600).decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        return None, repr(exc)


def lan_ip():
    """本机一个非回环地址（用于模拟"来自局域网"的请求）。"""
    sys.path.insert(0, HERE)
    try:
        import lan_address
        ips = lan_address.detect_lan_ips()
        return ips[0] if ips else None
    except Exception:
        return None


def main():
    runs = tempfile.mkdtemp(prefix="portal-shutdown-")
    port = free_port()
    log = open(os.path.join(tempfile.gettempdir(), "portal-shutdown.log"), "wb")
    proc = subprocess.Popen(
        [PY, "-X", "utf8", SCRIPT, "--port", str(port),
         "--password", "shutdown-check-password", "--lan-only"],
        cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
        env=dict(os.environ, PORTAL_RUNS_DIR=runs))
    try:
        ready = False
        for _ in range(60):
            if post(port, "/_auth/health", method="GET")[0] == 200:
                ready = True
                break
            time.sleep(0.5)
        check("门户起来了（前提）", ready, "port=%d" % port)
        if not ready:
            return 1

        # ---- ③ 反例控制：GET 不能被当成"关掉我" ----
        status, _ = post(port, "/_api/shutdown", method="GET")
        time.sleep(0.5)
        check("GET /_api/shutdown 不生效（只认 POST）",
              status != 200 and port_open(port),
              "HTTP %s" % status)

        # ---- ② 非本机来源必须被拒 ----
        ip = lan_ip()
        if ip:
            status_lan, body_lan = post(port, "/_api/shutdown", host=ip)
            time.sleep(0.5)
            check("从局域网地址来的停止请求被拒（403），门户不动",
                  status_lan == 403 and port_open(port),
                  "HTTP %s body=%r" % (status_lan, body_lan[:80]))
        else:
            check("从局域网地址来的停止请求被拒（403），门户不动",
                  False, "这台机器没探测到内网地址，跳过不算过")

        # ---- ① 本机 POST 必须真的让它退 ----
        status_ok, body_ok = post(port, "/_api/shutdown")
        check("本机 POST /_api/shutdown 返回 200",
              status_ok == 200, "HTTP %s body=%r" % (status_ok, body_ok[:80]))
        gone = False
        for _ in range(40):
            if not port_open(port):
                gone = True
                break
            time.sleep(0.25)
        check("端口随后真的松开（不是只有响应好看）", gone, "port=%d" % port)
        check("进程也真的退出了", proc.poll() is not None,
              "poll=%r" % (proc.poll(),))

        passed = sum(1 for ok, _, _ in results if ok)
        print("\n门户自退控制检验：%d/%d" % (passed, len(results)))
        return 0 if passed == len(results) else 1
    finally:
        if proc.poll() is None:
            proc.kill()
        try:
            log.close()
        except Exception:
            pass
        import shutil
        shutil.rmtree(runs, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
