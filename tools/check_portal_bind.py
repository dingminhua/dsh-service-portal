# -*- coding: utf-8 -*-
"""绑定与控制检验：listen 地址 + 独占绑定 + 端口自适应。

拦的 bug（都是真踩到的）：
  1. **只绑 127.0.0.1** -> 同一 WiFi 的手机永远连不上，扫码打不开。
     门户必须绑 0.0.0.0（认证层按 Host 分类豁免，暴露到局域网是安全的）。
  2. **Windows 上 SO_REUSEADDR 允许重复绑定** -> 端口被占也会「绑定成功」，
     流量被内核随机分到两个进程，表现为「有时能开、有时打不开」。
     必须用 SO_EXCLUSIVEADDRUSE 独占。
  3. 端口被占时能**自动往后试**（用户不必为「上个门户没停干净」手动换端口）。
"""
import os
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))


def listening_addrs(port):
    """netstat 里该端口的监听地址集合。"""
    try:
        raw = subprocess.run(["netstat", "-ano", "-p", "TCP"],
                             capture_output=True, timeout=20).stdout or b""
    except Exception:
        return set()
    out = set()
    for line in raw.decode("utf-8", "replace").splitlines():
        if "LISTENING" not in line or (":%d " % port) not in line:
            continue
        parts = line.split()
        for part in parts:
            if part.endswith(":%d" % port):
                out.add(part.rsplit(":", 1)[0])
    return out


def http_ok(port, host_header=None, timeout=4):
    req = urllib.request.Request("http://127.0.0.1:%d/_auth/health" % port)
    if host_header:
        req.add_header("Host", host_header)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status == 200
    except Exception:
        return False


def wait_ready(port, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if http_ok(port):
            return True
        time.sleep(0.4)
    return False


def main():
    results = []

    def check(label, cond, detail=""):
        results.append(bool(cond))
        print("%s  %s %s" % ("PASS" if cond else "FAIL", label, detail))

    # ---- 1. 纯单元：绑 0.0.0.0，且独占 ----
    print("[绑定语义]")
    import portal_proxy
    srv = portal_proxy.make_portal_server(0, {"password": "x" * 16})
    try:
        host = srv.server_address[0]
        port = srv.server_address[1]
        check("默认监听 0.0.0.0（手机能连上）", host == "0.0.0.0",
              "实际 %r" % host)
        # 独占：另一个进程再绑同一端口必须失败
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            probe.bind(("0.0.0.0", port))
            check("同一端口不能被重复绑定（独占生效）", False,
                  "竟然绑上了 —— Windows 上会变成流量随机分流")
        except OSError:
            check("同一端口不能被重复绑定（独占生效）", True)
        finally:
            probe.close()
    finally:
        srv.server_close()

    # ---- 2. 真实进程：手机可达 + 端口自适应 ----
    print("\n[真实进程]")
    runs = os.path.join(ROOT, "runs")
    state = os.path.join(runs, "portal_state.json")
    backup = state + ".bind-check"
    if os.path.exists(state):
        os.replace(state, backup)

    base = 9060
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    blocker.bind(("0.0.0.0", base))
    blocker.listen(1)

    proc = subprocess.Popen(
        [sys.executable, "-X", "utf8", os.path.join(ROOT, "tools", "portal_run.py"),
         "--port", str(base), "--password", "bind-check-password-1", "--lan-only"],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        check("原定端口被占时自动换端口并起来",
              wait_ready(base + 1), "端口 %d 是否就绪" % (base + 1))
        addrs = listening_addrs(base + 1)
        check("监听 0.0.0.0（不是只绑 127.0.0.1）",
              "0.0.0.0" in addrs, "监听地址=%r" % addrs)

        # 关键：模拟**手机**——用本机内网 IP 访问（不是 127.0.0.1）
        import lan_address
        best = lan_address.best_lan_ip()
        if best:
            try:
                with urllib.request.urlopen(
                        "http://%s:%d/_auth/health" % (best, base + 1),
                        timeout=5) as res:
                    ok = res.status == 200
            except Exception as exc:
                ok = False
                print("      （内网 IP 访问失败：%r）" % (exc,))
            check("从内网 IP 能访问（手机可达，这就是扫码能打开的前提）",
                  ok, "用 %s 试的" % best)
        else:
            check("从内网 IP 能访问", False, "没探测到内网 IP")

        # 状态里的地址应是内网可达的那个（不是 198.18.x）
        try:
            req = urllib.request.Request(
                "http://127.0.0.1:%d/_api/state" % (base + 1))
            req.add_header("Host", "127.0.0.1:%d" % (base + 1))
            import json
            with urllib.request.urlopen(req, timeout=5) as res:
                st = json.loads(res.read().decode("utf-8"))
            urls = st.get("lan_urls") or []
            check("状态里的内网地址不含 198.18.x（虚拟网卡段）",
                  not any("198.18." in u for u in urls[:1]),
                  "lan_urls=%r" % urls)
            check("状态里的内网地址是真实网卡",
                  bool(urls) and urls[0].startswith("http://" + (best or "x")),
                  "lan_urls=%r best=%r" % (urls, best))
        except Exception as exc:
            check("能读到状态", False, repr(exc))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        blocker.close()
        for path in (state, state + ".tmp"):
            if os.path.exists(path):
                os.remove(path)
        if os.path.exists(backup):
            os.replace(backup, state)

    passed = sum(1 for ok in results if ok)
    print("\n绑定与端口自适应控制检验：%d/%d" % (passed, len(results)))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
