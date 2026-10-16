# -*- coding: utf-8 -*-
"""门户「测试」按钮的控制检验：页面上那条探活链路，端到端真跑一遍。

## 为什么必须有这个检验
门户页新增的「测试」按钮是**前端 JS 发一次相对路径请求**，按状态码给结论。
光断言"页面上有 data-probe 属性"是**假检验** —— 属性在、逻辑错，照样绿。
这里把三件真事验掉：

  A. **服务端契约**：点「测试」会 GET `<mount>/`。上游活着 -> 转发到上游拿它的
     状态码；上游死了 -> 门户自己回 502，且正文含「上游」「Bad Gateway」。
     JS 靠这两个词区分"门户发的 502（上游没起）"与"上游自己返回的 502"——
     这个契约一旦漂移，界面就会**把上游自己的 502 冤枉成"没启动"**，
     而用户照着提示去启动一个本来就在跑的程序。所以必须钉住。
  B. **不跟随重定向也能拿到真实状态码**：JS 原来写 `redirect:"manual"`，
     按 Fetch 规范那会返回 opaque-redirect（status 恒为 0），把"上游把 / 跳转到
     /login"这种极常见的情况报成"状态 0"。断言页面里**不再**出现 manual。
  C. **只读性**：测试按钮不得引入任何写操作（不能出现 /_api/services/ 等）。

运行：python -X utf8 tools/check_portal_probe.py   （用临时端口 + 临时 runs）
"""
import http.server
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import portal_console as pc  # noqa: E402

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


def fetch(port, path):
    """返回 (状态码, 正文片段)。"""
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (port, path))
    try:
        with urllib.request.urlopen(req, timeout=8) as res:
            return res.status, res.read(600).decode("utf-8", "replace")
    except urllib.error.HTTPError as err:
        return err.code, err.read(600).decode("utf-8", "replace")
    except Exception as exc:
        return 0, repr(exc)


class Upstream(http.server.BaseHTTPRequestHandler):
    """假上游：**永远**按实例的行为回应。

    踩过的坑（第一版 harness 就是错的）：门户转发时会把 mount 前缀**剥掉**，
    所以上游看到的路径是 `/`，不是 `/boom`。我第一版按 `self.path.startswith("/boom")`
    分派，于是三个用例全打到同一分支、断言全绿或全红都说明不了问题。
    正确做法：每种行为**各起一个上游**，行为与路径无关。
    """
    behavior = "ok"

    def do_GET(self):  # noqa: N802
        if self.behavior == "redir":
            self.send_response(302)
            self.send_header("Location", "/landed")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if self.behavior == "boom":
            body = b"upstream exploded"
            self.send_response(502)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        body = b"<h1>upstream is alive</h1>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def _upstream(behavior):
    """起一个指定行为的假上游，返回 (port, server)。"""
    port = free_port()
    handler = type("H", (Upstream,), {"behavior": behavior})
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return port, srv


def main():
    print("[A. 页面结构：测试按钮与探活逻辑都在]")
    state = {
        "portal_port": 8899,
        "lan_urls": ["http://192.168.71.10:8899"],
        "public_url": None,
        "services": [
            {"key": "live", "name": "活的", "mount": "/live",
             "target": "127.0.0.1:1", "enabled": True, "alive": True, "note": ""},
            {"key": "dead", "name": "死的", "mount": "/dead",
             "target": "127.0.0.1:1", "enabled": True, "alive": False, "note": ""},
            {"key": "off", "name": "屏蔽的", "mount": "/off",
             "target": "127.0.0.1:1", "enabled": False, "alive": False, "note": ""},
        ],
    }
    html = pc.console_html(state).decode("utf-8")
    check("开放的节点有「测试」按钮", html.count('class="btn probe"') == 2,
          "count=%d" % html.count('class="btn probe"'))
    check("「测试」按钮带 data-probe（JS 据此知道打哪个路径）",
          'data-probe="/live/"' in html and 'data-probe="/dead/"' in html)
    # 真 bug（我自己第一版就是）：探测路径若用 urllib_quote(safe="")，`/` 会被编码成
    # %2F，data-probe 变成 "%2Flive%2F"，门户按 mount 匹配不上 -> **点测试永远 404**，
    # 而页面看起来完全正常。所以这条要显式钉住"斜杠没被编码"。
    check("data-probe 里的斜杠没被编码成 %2F（否则点测试永远 404）",
          "%2F" not in html.split('data-probe="')[1].split('"')[0]
          if 'data-probe="' in html else False,
          repr(html.split('data-probe="')[1].split('"')[0]
               if 'data-probe="' in html else ""))
    check("被屏蔽的节点「测试」按钮是禁用的",
          bool(re.search(r'<button[^>]*disabled[^>]*>\s*测试', html)))
    check("结果框存在（就地显示结论）", 'class="result"' in html)
    check("有「鼓励一下」链接（指仓库）",
          "鼓励一下 ★" in html and pc.REPO_URL in html)
    check("测试按钮**不**引入写操作",
          "/_api/services/" not in html and "<form" not in html)

    print("\n[B. JS 不发 opaque-redirect 请求]")
    check("没有 redirect:\"manual\"（那会让状态码恒为 0）",
          'redirect:"manual"' not in html and "redirect: 'manual'" not in html)
    check("探活用相对路径（内网/公网都能用）", 'data-probe="/' in html)
    check("能区分「门户发的 502」与「上游自己的 502」",
          '"上游"' in html and '"Bad Gateway"' in html)
    # 顺带把 path_quote 这个单元也钉住：单段用 urllib_quote、整条路径用 path_quote
    check("path_quote 保留斜杠、urllib_quote 编码斜杠（两个函数不能混用）",
          pc.path_quote("/a/b") == "/a/b" and pc.urllib_quote("/a/b") == "%2Fa%2Fb")
    check("path_quote 仍会编码非 ASCII（/中文 不能原样塞进属性）",
          "%" in pc.path_quote("/中文"))

    # ---------------- 端到端：真起上游 + 真起门户 ----------------
    print("\n[C. 端到端：真跑一遍探活链路]")
    tmp = tempfile.mkdtemp(prefix="probe-")
    runs = os.path.join(tmp, "runs")
    os.makedirs(runs, exist_ok=True)
    # 三个行为不同的上游（门户会把 mount 剥掉，所以不能靠路径分派行为）
    up_ok, srv_ok = _upstream("ok")
    up_redir, srv_redir = _upstream("redir")
    up_boom, srv_boom = _upstream("boom")
    servers = [srv_ok, srv_redir, srv_boom]

    portal_port = free_port()
    dead_port = free_port()          # 没人听 -> 门户自己回 502
    with io.open(os.path.join(runs, "portal_registry.json"), "w",
                 encoding="utf-8", newline="") as fh:
        json.dump({"services": [
            {"key": "live", "name": "活的", "mount": "/live",
             "target": "127.0.0.1:%d" % up_ok, "enabled": True},
            {"key": "dead", "name": "死的", "mount": "/dead",
             "target": "127.0.0.1:%d" % dead_port, "enabled": True},
            {"key": "boom", "name": "自己崩的", "mount": "/boom",
             "target": "127.0.0.1:%d" % up_boom, "enabled": True},
            {"key": "redir", "name": "会跳转的", "mount": "/redir",
             "target": "127.0.0.1:%d" % up_redir, "enabled": True},
        ]}, fh, ensure_ascii=False)

    log = io.open(os.path.join(tmp, "portal.log"), "wb")
    proc = subprocess.Popen(
        [sys.executable, "-X", "utf8", os.path.join(HERE, "portal_run.py"),
         "--port", str(portal_port), "--password", "probe-password-1", "--lan-only"],
        cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
        env=dict(os.environ, PORTAL_RUNS_DIR=runs))
    try:
        ready = False
        for _ in range(80):
            if port_open(portal_port):
                ready = True
                break
            time.sleep(0.5)
        check("前提：临时门户起来了", ready, "port=%d" % portal_port)
        if not ready:
            return 1

        # ① 上游活着：转发后应拿到上游的 200
        code, body = fetch(portal_port, "/live/")
        check("上游活着 -> 200（JS 判「通了」）", code == 200, "code=%s" % code)
        check("转发的是上游正文", "upstream is alive" in body)

        # ② 上游死了：门户自己回 502，正文必须含 JS 用来区分的那两个词
        code, body = fetch(portal_port, "/dead/")
        check("上游没起 -> 502（JS 判「不通」）", code == 502, "code=%s" % code)
        check("502 正文含「Bad Gateway」与「上游」（JS 靠它区分是谁发的）",
              "Bad Gateway" in body and "上游" in body, repr(body[:120]))

        # ③ 上游自己返回 502：正文**不含**门户那套措辞 —— JS 据此不冤枉它
        code, body = fetch(portal_port, "/boom/")
        check("上游自己的 502 原样透传", code == 502, "code=%s" % code)
        check("该 502 正文是上游的（不含门户措辞，不会被误判成没启动）",
              "upstream exploded" in body and "Bad Gateway" not in body,
              repr(body[:120]))

        # ④ 上游重定向。这里要验的**不是**"重定向能用"，而是两条更基本的事实：
        #    (a) 门户把 302 原样透传了（Location 保留）——用"不跟随"的 opener 看；
        #    (b) 浏览器默认跟随重定向时，拿到的是**真实状态码**而不是 0
        #        （这正是 JS 里不能再写 redirect:"manual" 的原因：manual 在 Fetch
        #         规范下返回 opaque-redirect，status 恒为 0）。
        # 顺带记录一个**上游侧的限制**（不是本插件 bug，是"按 mount 前缀转发"的
        # 固有性质）：上游若把请求重定向到 mount 之外的绝对路径（/redir -> /landed），
        # 跟随过去就落到门户的另一个路径上，那里没有注册 -> 门户回 404。
        # 上游要跳转就应跳自己 mount 内的相对路径。
        class _NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None

        opener = urllib.request.build_opener(_NoRedirect)
        try:
            with opener.open("http://127.0.0.1:%d/redir/" % portal_port,
                             timeout=8) as res:
                code, loc = res.status, res.headers.get("Location")
        except urllib.error.HTTPError as err:
            code, loc = err.code, err.headers.get("Location")
        check("门户把上游的 302 原样透传（Location 保留）",
              code == 302 and loc == "/landed", "code=%s loc=%r" % (code, loc))

        code, _ = fetch(portal_port, "/redir/")   # 这个 opener 会跟随
        check("跟随重定向时也拿到真实状态码（不是 0 = opaque-redirect）",
              code != 0, "code=%s" % code)
    finally:
        try:
            req = urllib.request.Request(
                "http://127.0.0.1:%d/_api/shutdown" % portal_port, data=b"",
                method="POST", headers={"Content-Length": "0"})
            urllib.request.urlopen(req, timeout=6).read()
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

    passed = sum(1 for ok, _, _ in results if ok)
    print("\n门户「测试」按钮控制检验：%d/%d" % (passed, len(results)))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
