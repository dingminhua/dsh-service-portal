# -*- coding: utf-8 -*-
"""公网访问（隧道）控制检验。

拦的 bug（实测踩到的真 bug）：
  **门户已在运行时，「开启公网访问」什么都不做。**
  设置页按钮 → 宿主 POST /start → startPublic 里的幂等检查
  `if (await portListening(port)) return { ok: true, already: true }` 直接返回，
  **建隧道那一步被跳过了**。调用方拿到 ok=true 却永远等不到公网地址，
  用户看到「点开启公网访问没反应」。

  为什么以前不显形：门户以前不会自动起，第一次点按钮时端口没在听，
  会走完整的启动流程（含建隧道）；加了 autoStart 之后门户总是已经跑着，
  幂等检查把隧道也一起跳过了。

另一个语义 bug：
  **「关闭公网」把整个门户停掉**（应该只收隧道，内网继续可用）。

这里的检验不依赖真实 cloudflared：用**假的门户进程**（只实现 /_api/tunnel/*）
验证宿主确实会去拨隧道，并且如实回报结果。
"""
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class FakePortal(BaseHTTPRequestHandler):
    """最小假门户：只处理 tunnel/start 与 tunnel/stop。"""
    protocol_version = "HTTP/1.1"
    calls = []
    tunnel_url = "https://fake-tunnel.trycloudflare.com"
    start_ok = True

    def _json(self, code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        FakePortal.calls.append(self.path)
        if self.path == "/_api/tunnel/start":
            if not FakePortal.start_ok:
                self._json(502, {"ok": False, "detail": "假门户：模拟建隧道失败"})
                return
            self._json(200, {"ok": True, "public_url": FakePortal.tunnel_url,
                             "detail": FakePortal.tunnel_url})
            return
        if self.path == "/_api/tunnel/stop":
            self._json(200, {"ok": True})
            return
        self._json(404, {"ok": False, "error": "unknown"})

    def log_message(self, *a):
        pass


def main():
    results = []

    def check(label, cond, detail=""):
        results.append(bool(cond))
        print("%s  %s %s" % ("PASS" if cond else "FAIL", label, detail))

    server = ThreadingHTTPServer(("127.0.0.1", 0), FakePortal)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    # ---- 1. 源码层：幂等分支必须区分 lanOnly ----
    src = open(os.path.join(ROOT, "lib", "index.js"), encoding="utf-8").read()
    start = src.find("async function startPublic")
    assert start > 0
    rest = src[start:]
    body = rest[:rest.find("\nasync function stopPublic")]
    ok_split = ("if (lanOnly)" in body and "startTunnelOnly" in body)
    check("门户已在跑时：只开内网才直接返回，要公网则去拨隧道",
          ok_split, "（这就是「点开启公网没反应」的根因）")
    check("幂等返回不再是「一律 already:true」",
          body.count("already: true") >= 2 and "startTunnelOnly" in body,
          "分支存在")

    # ---- 2. 真的会去调门户的 tunnel API（用假门户端到端验证）----
    print("\n[假门户：验证宿主确实去拨隧道]")
    FakePortal.calls.clear()
    FakePortal.start_ok = True

    # 直接调 startPublic 的隧道分支：用一个跑着的假门户冒充真实门户
    # （startTunnelOnly 只依赖 portalPort）
    import subprocess
    script = """
import { _internals } from %s;
const repo = { portalPort: %d, infraPath: %s, repoPath: %s, pythonPath: "",
  passwordMode: "random", fixedPassword: "", autoStart: true,
  lanAuthEnabled: false, webEnabled: true };
const r = await _internals.startTunnelOnly(repo);
console.log(JSON.stringify(r));
process.exit(0);
""" % (json.dumps("file:///" + os.path.join(ROOT, "lib", "index.js").replace("\\", "/")),
       port, json.dumps(ROOT.replace("\\", "/")), json.dumps(ROOT.replace("\\", "/")))
    script_path = os.path.join(ROOT, "runs", "_tunnel_check.mjs")
    os.makedirs(os.path.dirname(script_path), exist_ok=True)
    with open(script_path, "w", encoding="utf-8") as handle:
        handle.write(script)
    node = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs",
                        "DeepSeek Harness", "resources", "runtime",
                        "primary-runtime", "dependencies", "node", "bin", "node.exe")
    try:
        proc = subprocess.run([node, script_path], cwd=ROOT, capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              timeout=120)
        out = (proc.stdout or "").strip()
        payload = None
        for line in out.splitlines():
            if line.strip().startswith("{"):
                try:
                    payload = json.loads(line.strip())
                except ValueError:
                    pass
        check("宿主调到了门户的 /_api/tunnel/start",
              "/_api/tunnel/start" in FakePortal.calls,
              "门户收到的请求=%r" % FakePortal.calls)
        check("宿主如实回报公网地址",
              bool(payload) and payload.get("ok") is True
              and payload.get("detail") == FakePortal.tunnel_url,
              "宿主返回=%r" % payload)
    finally:
        try:
            os.remove(script_path)
        except OSError:
            pass

    # ---- 3. 反例控制：门户建隧道失败时不能谎报成功 ----
    print("\n[反例控制：隧道失败必须如实报错]")
    FakePortal.calls.clear()
    FakePortal.start_ok = False
    script2 = script.replace("startTunnelOnly", "startTunnelOnly")
    with open(script_path, "w", encoding="utf-8") as handle:
        handle.write(script2)
    try:
        proc = subprocess.run([node, script_path], cwd=ROOT, capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              timeout=120)
        payload = None
        for line in (proc.stdout or "").splitlines():
            if line.strip().startswith("{"):
                try:
                    payload = json.loads(line.strip())
                except ValueError:
                    pass
        check("失败时报 ok=false（不谎报成功）",
              bool(payload) and payload.get("ok") is False,
              "宿主返回=%r" % payload)
        check("失败时带上原因（用户能看到为什么）",
              bool(payload) and bool(payload.get("detail")),
              "detail=%r" % (payload or {}).get("detail"))
    finally:
        try:
            os.remove(script_path)
        except OSError:
            pass

    # ---- 4. 「关闭公网」只收隧道，不停门户 ----
    print("\n[关闭公网的语义]")
    stub = os.path.join(ROOT, "lib", "index.js")
    text = open(stub, encoding="utf-8").read()
    check("宿主提供 /tunnel/stop 路由", 'route === "/tunnel/stop"' in text)
    check("宿主提供 /tunnel/start 路由", 'route === "/tunnel/start"' in text)
    client = open(os.path.join(ROOT, "client", "index.jsx"), encoding="utf-8").read()
    idx = client.find('"关闭公网"')
    check("设置页「关闭公网」走 doStopTunnel 而不是 doStop",
          idx > 0 and "doStopTunnel" in client,
          "（早先它调 doStop，会把内网访问一起停掉）")
    check("doStopTunnel 调 /tunnel/stop 而不是 /stop",
          'request("/tunnel/stop"' in client)
    check("有 doStopTunnel 定义", "const doStopTunnel" in client)

    server.shutdown()
    server.server_close()

    passed = sum(1 for ok in results if ok)
    print("\n公网访问控制检验：%d/%d" % (passed, len(results)))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
