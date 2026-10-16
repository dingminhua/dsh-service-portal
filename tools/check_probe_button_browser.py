# -*- coding: utf-8 -*-
"""端到端跑一次「测试」按钮：起真门户 + 真上游 + 无头 Chrome 真点击。

分三种上游分别验证界面给的结论对不对：
  · 上游活着      -> 结果必须说「通了」且带 200
  · 上游没起      -> 结果必须说「不通」并提示去启动上游（而不是甩一个 502）
  · 上游自己 502  -> 结果必须说"上游在线但自己出错"，**不能**冤枉成"没启动"

最后这条最容易搞错，也是我最担心的：门户自己的 502 与上游的 502 状态码一样，
只能靠正文区分（门户那条正文固定含「Bad Gateway」「上游」）。

用法：python -X utf8 tools/check_probe_button_browser.py
"""
import http.server
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
NODE = os.path.join(
    os.environ.get("LOCALAPPDATA", ""), "Programs", "DeepSeek Harness",
    "resources", "runtime", "primary-runtime", "dependencies", "node", "bin",
    "node.exe")

results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(("PASS  " if ok else "FAIL  ") + name + ((" —— " + str(detail)) if detail else ""))


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Upstream(http.server.BaseHTTPRequestHandler):
    behavior = "ok"

    def do_GET(self):  # noqa: N802
        if self.behavior == "boom":
            body = b"upstream exploded"
            self.send_response(502)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        body = b"<h1>upstream alive</h1>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def upstream(behavior):
    port = free_port()
    srv = http.server.ThreadingHTTPServer(
        ("127.0.0.1", port), type("H", (Upstream,), {"behavior": behavior}))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return port, srv


def run_browser(url, cdp_port):
    out = subprocess.run(
        [NODE, os.path.join(HERE, "probe_button_e2e.mjs"),
         "--url", url, "--cdp-port", str(cdp_port)],
        capture_output=True, text=True, timeout=300, cwd=ROOT)
    return out.returncode, (out.stdout or "") + (out.stderr or "")


def main():
    if not os.path.isfile(NODE):
        print("跳过：找不到 node（%s）" % NODE)
        return 2

    tmp = tempfile.mkdtemp(prefix="pb-")
    runs = os.path.join(tmp, "runs")
    os.makedirs(runs, exist_ok=True)
    up_ok, srv_ok = upstream("ok")
    up_boom, srv_boom = upstream("boom")
    servers = [srv_ok, srv_boom]
    dead = free_port()

    # 三种上游放在同一个门户里：页面会有 3 张卡，测试按钮 3 个全可用，
    # e2e 脚本点的是**第一个可点**的 —— 所以把"活的"放第一个。
    with io.open(os.path.join(runs, "portal_registry.json"), "w",
                 encoding="utf-8", newline="") as fh:
        json.dump({"services": [
            {"key": "live", "name": "活的", "mount": "/live",
             "target": "127.0.0.1:%d" % up_ok, "enabled": True},
            {"key": "dead", "name": "死的", "mount": "/dead",
             "target": "127.0.0.1:%d" % dead, "enabled": True},
            {"key": "boom", "name": "自崩的", "mount": "/boom",
             "target": "127.0.0.1:%d" % up_boom, "enabled": True},
            {"key": "off", "name": "屏蔽的", "mount": "/off",
             "target": "127.0.0.1:%d" % up_ok, "enabled": False},
        ]}, fh, ensure_ascii=False)

    port = free_port()
    log = io.open(os.path.join(tmp, "portal.log"), "wb")
    proc = subprocess.Popen(
        [sys.executable, "-X", "utf8", os.path.join(HERE, "portal_run.py"),
         "--port", str(port), "--password", "probe-e2e-pass-1", "--lan-only"],
        cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
        env=dict(os.environ, PORTAL_RUNS_DIR=runs))
    try:
        for _ in range(80):
            try:
                socket.create_connection(("127.0.0.1", port), 0.5).close()
                break
            except OSError:
                time.sleep(0.5)

        url = "http://127.0.0.1:%d/" % port
        rc, out = run_browser(url, free_port())
        for line in out.strip().splitlines():
            print("    " + line)
        check("浏览器端到端脚本整体通过", rc == 0, "rc=%d" % rc)

        # 上面脚本点的是"活的"那张卡（第一个可点）。这里补一条：直接对/boom 与
        # /dead 发一次请求，确认门户给的 502 正文能被区分（界面文案的分支依据）。
        def body_of(path):
            try:
                with urllib.request.urlopen(url.rstrip("/") + path, timeout=8) as r:
                    return r.status, r.read(400).decode("utf-8", "replace")
            except urllib.error.HTTPError as e:
                return e.code, e.read(400).decode("utf-8", "replace")

        import urllib.error  # noqa: E402  (放在这里只为局部可用)

        code, body = body_of("/dead/")
        check("上游没起：门户回 502 且正文可辨认（界面据此提示去启动上游）",
              code == 502 and "Bad Gateway" in body and "上游" in body,
              "code=%s" % code)
        code, body = body_of("/boom/")
        check("上游自己 502：正文是上游的（界面不会冤枉成「没启动」）",
              code == 502 and "upstream exploded" in body
              and "Bad Gateway" not in body, "code=%s" % code)
        code, body = body_of("/live/")
        check("上游活着：200 + 上游正文（界面判「通了」）",
              code == 200 and "upstream alive" in body, "code=%s" % code)
    finally:
        try:
            urllib.request.urlopen(urllib.request.Request(
                "http://127.0.0.1:%d/_api/shutdown" % port, data=b"",
                method="POST", headers={"Content-Length": "0"}), timeout=6).read()
        except Exception:
            pass
        time.sleep(1.5)
        if proc.poll() is None:
            proc.kill()
        for srv in servers:
            srv.shutdown()
        try:
            log.close()
        except Exception:
            pass
        shutil.rmtree(tmp, ignore_errors=True)

    passed = sum(1 for ok in results if ok)
    print("\n「测试」按钮真机端到端：%d/%d" % (passed, len(results)))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
