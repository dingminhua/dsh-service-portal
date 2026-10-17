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
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))


def _make_exclusive(probe):
    """尽量让 probe 独占端口后绑定 —— **跨平台**。

    `SO_EXCLUSIVEADDRUSE` 只有 Windows 有。原来三处都直接引用它，在 macOS/Linux
    上会 AttributeError 把整个检验崩掉（看着像门户坏了，其实只是检验脚本写死了
    Windows）。非 Windows 上不设这个选项即可：门户侧也没有设 SO_REUSEADDR，
    所以第二个 bind 到同一端口依然会被系统拒绝，检验语义不变。
    """
    exclusive = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
    if exclusive is not None:
        probe.setsockopt(socket.SOL_SOCKET, exclusive, 1)
    return probe


def port_free(port):
    """这个端口现在能不能独占绑上（与门户同口径）。"""
    probe = _make_exclusive(socket.socket(socket.AF_INET, socket.SOCK_STREAM))
    try:
        probe.bind(("0.0.0.0", port))
        return True
    except OSError:
        return False
    finally:
        probe.close()


def pick_base_pair():
    """挑一个 base，使 base 和 base+1 都空着。

    为什么要动态挑：这个检验原来是写死 9060 的，然后断言"门户会落到 9061"。
    实测在别的程序（或上一次检验的残留）占着 9061 的机器上，门户会落到 9062，
    断言就失败 —— 那是**检验依赖机器当前状态**，不是产品有问题。
    """
    for base in range(20000, 30000, 2):
        if port_free(base) and port_free(base + 1):
            return base
    return None


def listening_addrs(port):
    """该端口的监听地址集合（**跨平台**）。

    原来只认 Windows 的 `netstat -ano -p TCP`：它用 `LISTENING` 标记监听行。
    macOS/Linux 的 netstat 用 `LISTEN`，且没有 `-p TCP` 这套参数 —— 于是
    在非 Windows 上这里**永远返回空集**，紧接着那条
    「监听 0.0.0.0（不是只绑 127.0.0.1）」断言必然 FAIL。
    那不是门户只绑了 127.0.0.1，而是检验脚本量不出来（同一条检验里
    「从内网 IP 能访问」是通过的 —— 真只绑 127.0.0.1 的话它不可能通过）。

    现在按平台选命令：Windows 沿用 netstat；其余用 `lsof -nP -iTCP:<port> -sTCP:LISTEN`。
    """
    out = set()
    if os.name == "nt":
        try:
            raw = subprocess.run(["netstat", "-ano", "-p", "TCP"],
                                 capture_output=True, timeout=20).stdout or b""
        except Exception:
            return out
        for line in raw.decode("utf-8", "replace").splitlines():
            if "LISTENING" not in line or (":%d " % port) not in line:
                continue
            for part in line.split():
                if part.endswith(":%d" % port):
                    out.add(part.rsplit(":", 1)[0])
        return out
    # POSIX：lsof 的 NAME 形如 `*:8899 (LISTEN)` / `127.0.0.1:8899 (LISTEN)`
    try:
        raw = subprocess.run(["lsof", "-nP", "-iTCP:%d" % port, "-sTCP:LISTEN"],
                             capture_output=True, timeout=20).stdout or b""
    except Exception:
        return out
    for line in raw.decode("utf-8", "replace").splitlines():
        for part in line.split():
            if part.endswith(":%d" % port):
                host = part.rsplit(":", 1)[0]
                # lsof 用 `*` 表示"所有地址"（等价于 0.0.0.0）
                out.add("0.0.0.0" if host in ("*", "[::]") else host)
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
        # 独占：另一个进程再绑同一端口必须失败（跨平台，见 _make_exclusive）。
        probe = _make_exclusive(socket.socket(socket.AF_INET, socket.SOCK_STREAM))
        try:
            probe.bind(("0.0.0.0", port))
            check("同一端口不能被重复绑定（独占生效）", False,
                  "竟然绑上了 —— 流量会被随机分流到两个进程")
        except OSError:
            check("同一端口不能被重复绑定（独占生效）", True)
        finally:
            probe.close()
    finally:
        srv.server_close()

    # ---- 2. 真实进程：手机可达 + 端口自适应 ----
    print("\n[真实进程]")
    # 状态目录隔离到临时目录：不碰用户真实的 runs/（里面存着局域网口令和
    # 用户在控制台注册的服务）。原来这里借用了真实 runs/ 再备份还原，
    # 一旦中途异常，用户的状态文件就悬了。
    runs_tmp = tempfile.mkdtemp(prefix="portal-bind-runs-")

    base = pick_base_pair()
    if base is None:
        print("找不到两个连续空闲端口，跳过真实进程部分")
        return 1
    blocker = _make_exclusive(socket.socket(socket.AF_INET, socket.SOCK_STREAM))
    blocker.bind(("0.0.0.0", base))
    blocker.listen(1)

    proc = subprocess.Popen(
        [sys.executable, "-X", "utf8", os.path.join(ROOT, "tools", "portal_run.py"),
         "--port", str(base), "--password", "bind-check-password-1", "--lan-only"],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env=dict(os.environ, PORTAL_RUNS_DIR=runs_tmp))
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
        shutil.rmtree(runs_tmp, ignore_errors=True)

    passed = sum(1 for ok in results if ok)
    print("\n绑定与端口自适应控制检验：%d/%d" % (passed, len(results)))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
