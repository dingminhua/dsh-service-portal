# -*- coding: utf-8 -*-
"""服务自动发现的控制检验。

用户要求：插件设置里能「刷新当前系统服务 / 自动发现 / 手动添加」。
自动发现是**风险最高**的一环 —— 扫出来的端口点一下就能挂到公网。本检验钉住
它的安全边界，防止以后被"优化"掉。

控制检验原则：正例（该推荐的）与反例（绝不推荐的）都必须能区分。反例不是
凑数，是实测本机真出现过的：DSH 自己的界面、本项目 cloudflared 隧道、
clash 代理、远程控制软件、系统服务。

运行：python -X utf8 tools/check_portal_discover.py
"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import portal_discover  # noqa: E402

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


def level_of(candidates, port):
    for c in candidates:
        if c.get("port") == port:
            return c
    return None


def main():
    print("[① 分级函数：已知危险进程必须判 danger]")
    # 直接调 _classify，用**真实出现过的**进程名（实测本机抓到的）
    cases = [
        ("acme.exe", "", "ok", "普通进程 -> 可推荐"),
        ("DeepSeek Harness.exe", "", "danger", "DSH 自身界面（实测 2462-2465/19387）"),
        ("cloudflared.exe", "", "danger", "本项目隧道（实测 20241，成环）"),
        ("clash-verge.exe", "", "danger", "代理（实测 8738）"),
        ("verge-mihomo.exe", "", "danger", "代理（实测 7897）"),
        ("ToDesk.exe", "", "danger", "远程控制（实测 35600/37600）"),
        ("ArmourySocketServer.exe", "", "danger", "厂商常驻服务（实测 9013）"),
        ("asus_framework.exe", "", "danger", "厂商常驻服务（实测 1042）"),
        ("vsvnhttpsvc.exe", "", "danger", "VPN 组件（实测 443）"),
        ("lsass.exe", "", "danger", "Windows 核心进程"),
        ("spoolsv.exe", "", "danger", "Windows 核心进程"),
    ]
    for proc, cmd, want, why in cases:
        got, reason = portal_discover._classify(
            50000 if want == "ok" else 2462, proc, cmd,
            portal_port=8899, registered_ports=set(), exclude_ports=set())
        check("分级：%s -> %s（%s）" % (proc, want, why), got == want,
              "实际=%s reason=%r" % (got, reason))

    print("\n[② 门户自己的端口必须排除]")
    got, reason = portal_discover._classify(
        8899, "python.exe", "", portal_port=8899,
        registered_ports=set(), exclude_ports=set())
    check("门户端口 -> danger", got == "danger", "实际=%s" % got)
    got, _ = portal_discover._classify(
        9102, "python.exe", "", portal_port=8899,
        registered_ports=set(), exclude_ports=set())
    check("别的端口不受影响（反例控制：不是恒 danger）", got == "ok",
          "实际=%s" % got)

    print("\n[③ exclude_ports 生效（本项目自己的进程）]")
    got, reason = portal_discover._classify(
        20241, "cloudflared.exe", "", portal_port=8899,
        registered_ports=set(), exclude_ports=[20241])
    check("显式排除的端口 -> danger", got == "danger", "实际=%s" % got)

    print("\n[④ 系统端口表]")
    got, _ = portal_discover._classify(
        445, "svc.exe", "", portal_port=8899, registered_ports=set(),
        exclude_ports=set())
    check("445 SMB -> danger", got == "danger", "实际=%s" % got)
    got, _ = portal_discover._classify(
        3389, "svc.exe", "", portal_port=8899, registered_ports=set(),
        exclude_ports=set())
    check("3389 RDP -> danger", got == "danger", "实际=%s" % got)

    print("\n[⑤ 已注册的端口不再推荐（不是标危险，是已有）]")
    got, _ = portal_discover._classify(
        8810, "python.exe", "", portal_port=8899,
        registered_ports={8810}, exclude_ports=set())
    check("8810 已注册 -> danger/present", got == "danger", "实际=%s" % got)

    print("\n[⑥ 真实扫描：真起一个 HTTP 服务，必须能被发现且判 ok]")
    port = free_port()
    # 起一个最简单的 HTTP 服务（纯标准库，不依赖别的进程）
    srv = subprocess.Popen(
        [sys.executable, "-X", "utf8", "-c",
         "import http.server,socketserver,sys\n"
         "class H(http.server.BaseHTTPRequestHandler):\n"
         "    def do_GET(self):\n"
         "        self.send_response(200)\n"
         "        self.send_header('Content-Type','text/html')\n"
         "        self.end_headers()\n"
         "        self.wfile.write(b'<title>Discovery Probe Target</title>')\n"
         "    def log_message(self,*a): pass\n"
         "socketserver.TCPServer(('127.0.0.1', int(sys.argv[1])), H).serve_forever()\n",
         str(port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        ready = False
        for _ in range(40):
            try:
                with urllib.request.urlopen(
                        "http://127.0.0.1:%d/" % port, timeout=1) as res:
                    res.read(64)
                    ready = True
                    break
            except Exception:
                time.sleep(0.25)
        check("前提：探针 HTTP 服务起来了", ready, "port=%d" % port)
        if ready:
            res = portal_discover.discover_services(portal_port=8899)
            found = level_of(res["candidates"], port)
            check("真实扫描能发现这个端口", found is not None)
            if found:
                check("发现的条目判为 ok（是普通 Web 服务）",
                      found["level"] == "ok", "实际=%s" % found["level"])
                check("证据里带上了页面标题（用户能认出来）",
                      "Discovery Probe Target" in (found.get("evidence") or ""),
                      "evidence=%r" % found.get("evidence"))
                check("target 拼成 127.0.0.1:<port>",
                      found.get("target") == "127.0.0.1:%d" % port,
                      "实际=%r" % found.get("target"))
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()

    print("\n[⑦ 真实扫描的反例：本机的危险项必须被标 danger]")
    res = portal_discover.discover_services(portal_port=8899)
    dsh = [c for c in res["candidates"]
           if "harness" in (c.get("proc") or "").lower()]
    if dsh:
        check("本机 DSH 端口全部标 danger（%d 个）" % len(dsh),
              all(c["level"] == "danger" for c in dsh),
              "等级=%r" % sorted({c["level"] for c in dsh}))
    else:
        check("本机 DSH 端口全部标 danger（本次未探到，跳过）", True)
    cf = [c for c in res["candidates"]
          if "cloudflared" in (c.get("proc") or "").lower()]
    if cf:
        check("本机 cloudflared 标 danger", all(c["level"] == "danger" for c in cf),
              "等级=%r" % [c["level"] for c in cf])
    else:
        check("本机 cloudflared 标 danger（本次未跑隧道，跳过）", True)

    print("\n[⑧ 不写任何东西：发现是只读操作]")
    reg_before = None
    reg_path = os.path.join(ROOT, "runs", "portal_registry.json")
    if os.path.exists(reg_path):
        with open(reg_path, "rb") as fh:
            reg_before = fh.read()
    portal_discover.discover_services(portal_port=8899)
    reg_after = None
    if os.path.exists(reg_path):
        with open(reg_path, "rb") as fh:
            reg_after = fh.read()
    check("发现过程不改注册表", reg_before == reg_after,
          "before=%s after=%s" % (len(reg_before or b""), len(reg_after or b"")))

    passed = sum(1 for ok, _, _ in results if ok)
    print("\n自动发现控制检验：%d/%d" % (passed, len(results)))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
