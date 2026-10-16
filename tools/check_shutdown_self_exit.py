# -*- coding: utf-8 -*-
"""复现 `test_host_buttons` 里「停止走的是门户自退」这条失败。

现象（用户重启 DSH 后从 SKIP 变成 FAIL）：
    FAIL  停止返回 ok=true
    FAIL  停止后端口真的释放
    FAIL  停止走的是「门户自退」  stoppedBy='stop-command'

`stoppedBy='stop-command'` 的意思是：宿主先 POST /_api/shutdown 请门户自退，
**那一请求没成功**（或成功后端口没松开），于是退到兜底的 `--stop`。

本脚本把这两步分开测，定位到底是"请求没通"还是"通了但没退"：
  1. 起一个临时门户；
  2. 用**与宿主完全相同**的请求（POST /_api/shutdown，Content-Length: 0）打它；
  3. 看 HTTP 状态码、再等一会儿看端口是否松开。

运行：python -X utf8 tools/check_shutdown_self_exit.py
"""
import json
import os
import re
import shutil
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

results = []


def check(name, ok, detail=""):
    results.append((bool(ok), name, detail))
    print(("PASS  " if ok else "FAIL  ") + name + ((" —— " + detail) if detail else ""))


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def port_open(port):
    s = socket.socket()
    s.settimeout(0.6)
    try:
        s.connect(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def shutdown_request(port, timeout=5):
    """与 lib/index.js 的 askPortalShutdown 完全同形：POST，Content-Length: 0。"""
    req = urllib.request.Request(
        "http://127.0.0.1:%d/_api/shutdown" % port, data=b"", method="POST",
        headers={"Content-Length": "0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status, res.read(200).decode("utf-8", "replace")
    except urllib.error.HTTPError as err:
        return err.code, err.read(200).decode("utf-8", "replace")
    except Exception as exc:
        return 0, repr(exc)


def main():
    tmp = tempfile.mkdtemp(prefix="shutdown-")
    runs = os.path.join(tmp, "runs")
    os.makedirs(runs, exist_ok=True)
    port = free_port()
    log = open(os.path.join(tmp, "portal.log"), "wb")
    proc = subprocess.Popen(
        [PY, "-X", "utf8", os.path.join(HERE, "portal_run.py"),
         "--port", str(port), "--password", "shutdown-password-1", "--lan-only"],
        cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
        env=dict(os.environ, PORTAL_RUNS_DIR=runs))
    try:
        ready = False
        for _ in range(60):
            if port_open(port):
                ready = True
                break
            time.sleep(0.5)
        check("前提：门户起来了", ready, "port=%d" % port)
        if not ready:
            return 1

        code, body = shutdown_request(port)
        check("POST /_api/shutdown 返回 2xx（宿主据此判'自退成功'）",
              200 <= code < 300, "HTTP %s %r" % (code, body[:120]))

        # 端口要真的松开（宿主最多等 40×250ms = 10s）
        gone = False
        for _ in range(40):
            if not port_open(port):
                gone = True
                break
            time.sleep(0.25)
        check("端口真的松开了（宿主等 10 秒的上限内）", gone,
              "等了 %s" % ("松开" if gone else "10 秒仍未松开"))

        # 进程要退出
        try:
            proc.wait(timeout=10)
            check("门户进程已退出", True, "exit=%s" % proc.returncode)
        except subprocess.TimeoutExpired:
            check("门户进程已退出", False, "10 秒内没退")

        # ---- 竞态：端口一在听，/_api/shutdown 就必须可用 ----
        #
        # 真 bug（用户重启 DSH 后 test_host_buttons 从 SKIP 变 FAIL 才暴露）：
        # `serve_forever` 先起（端口开始监听），而 shutdown 钩子晚得多才装上，
        # 中间夹着隧道建立 + 一次可能重试 ~2 秒的 save_state（沙箱里写 runs/
        # 会 Errno 13）。那个窗口里 POST /_api/shutdown 会回 503「门户还没就绪」，
        # 宿主判 asked=false 退到 --stop 兜底，而兜底在沙箱里杀不掉 —— 表现为
        # **第二次点「停止」失败**：报错、门户还活着。
        #
        # 断言改在**源码顺序**上（比掐时间稳）。
        # 注意：要找**可执行语句**，不能 `find("serve_forever")` —— 那个词在注释里
        # 也出现（说明这段竞态的注释自己就提到它），按裸词判会误报。
        src = open(os.path.join(HERE, "portal_run.py"), encoding="utf-8").read()
        i_hook = src.find('shutdown_holder["fn"] = shutdown')
        m_serve = re.search(
            r"^\s*threading\.Thread\(target=server\.serve_forever", src, re.M)
        i_serve = m_serve.start() if m_serve else -1
        check("关闭钩子在 serve_forever **之前**装上（消除 503 窗口）",
              i_hook != -1 and i_serve != -1 and i_hook < i_serve,
              "hook@%s serve@%s" % (i_hook, i_serve))

        # 再实测一次"刚起来就能自退"：起一个新的，立刻打 shutdown
        proc2 = subprocess.Popen(
            [PY, "-X", "utf8", os.path.join(HERE, "portal_run.py"),
             "--port", str(port), "--password", "shutdown-password-2", "--lan-only"],
            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env=dict(os.environ, PORTAL_RUNS_DIR=runs))
        try:
            ready2 = False
            for _ in range(60):
                if port_open(port):
                    ready2 = True
                    break
                time.sleep(0.25)
            check("（实测）新门户端口已监听", ready2, "port=%d" % port)
            # **端口一在听就立刻打** —— 这正是原来会 503 的时刻
            code2, body2 = shutdown_request(port)
            check("（实测）端口一在听就能自退（不是 503「门户还没就绪」）",
                  200 <= code2 < 300,
                  "HTTP %s %r" % (code2, body2[:100]))
            gone2 = False
            for _ in range(40):
                if not port_open(port):
                    gone2 = True
                    break
                time.sleep(0.25)
            check("（实测）随后端口真的松开", gone2)
        finally:
            if proc2.poll() is None:
                proc2.kill()

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
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
