# -*- coding: utf-8 -*-
"""门户代理的控制检验：Host 分类（内外网判定）、认证分层、限速、路由转发。

拦的是这类 bug（每条都对应真实的对外暴露事故）：
  1. **自建域名被误判成内网** → 外面的人无密码进得来（dsh-pocket issue #66 的原型问题）；
  2. 认不出的 Host 走「宽松」分支 → 同一类绕过（故必须 fail-closed 到 public）；
  3. 公网未登录请求被转发到上游 → 保护区裸奔；
  4. `cf-connecting-ip` 被无条件信任 → 任何人伪造该头即可绕过登录限速；
  5. 限速不生效 / 锁定期仍可尝试 → 口令可被在线暴力破解；
  6. 未注册路径被控制台兜底 → 拼错的路径「看起来能用」（本项目最忌讳的假成功）；
  7. 上游挂了返回 200 空 body → 用户以为服务正常。

运行：python -X utf8 tools/check_portal_proxy.py
退出码：0 全通过 / 1 有失败 / 2 跳过（依赖缺失）
"""
import json
import os
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

try:
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
except ImportError:  # pragma: no cover
    print("跳过：没有 http.server（依赖缺失不代表通过）")
    raise SystemExit(2)

try:
    import portal_proxy
    import portal_login
except ImportError as exc:
    print("跳过：无法导入门户模块（%s）" % exc)
    raise SystemExit(2)

PASSWORD = "proxy-check-password-1234"
HITS = []
API_CALLS = []


class Upstream(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        HITS.append(self.path)
        body = b"UPSTREAM:" + self.path.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        size = int(self.headers.get("Content-Length") or 0)
        payload = self.rfile.read(size) if size else b""
        HITS.append("POST " + self.path)
        body = b"UPSTREAM_POST:" + payload
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def fake_console_state():
    return {"services": [{"key": "train", "name": "训练台", "mount": "/train",
                          "target": "127.0.0.1:1", "enabled": True, "alive": True}],
            "lan_urls": ["http://192.168.1.5:8899"],
            "public_url": "https://demo.trycloudflare.com",
            "portal_port": 8899}


def fake_console_page(state, is_public=False):
    return ("<html><body>CONSOLE is_public=%s services=%d</body></html>"
            % (is_public, len(state.get("services", [])))).encode("utf-8")


def fake_api(handler, method, route, body):
    API_CALLS.append((method, route, body))
    if method == "GET" and route == "/services":
        handler._send_json(200, {"ok": True, "services": []})
        return True
    if method == "POST" and route == "/services":
        handler._send_json(200, {"ok": True, "created": True})
        return True
    return False


def make_resolver(mounts):
    def resolve(path):
        for mount, target in mounts.items():
            if path == mount or path.startswith(mount + "/"):
                host, port = target.split(":")
                rest = path[len(mount):] or "/"
                return mount, host, int(port), rest
        return None
    return resolve


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):
        return None


def request(port, path, host=None, cookie=None, method="GET",
            data=None, ctype=None, extra_headers=None):
    """发请求；需要时覆盖 Host 头（这是本模块测试的核心手段）。"""
    url = "http://127.0.0.1:%d%s" % (port, path)
    req = urllib.request.Request(url, data=data, method=method)
    if host:
        req.add_header("Host", host)
    if cookie:
        req.add_header("Cookie", cookie)
    if ctype:
        req.add_header("Content-Type", ctype)
    for key, value in (extra_headers or {}).items():
        req.add_header(key, value)
    try:
        res = urllib.request.build_opener(NoRedirect).open(req, timeout=5)
        return res.status, res.read(), res.headers
    except urllib.error.HTTPError as err:
        return err.code, err.read(), err.headers


def main():
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    up_port = upstream.server_address[1]

    config = {
        "password": PASSWORD,
        "cookie_secure": False,
        "open_classes": ("loopback", "lan"),
        "console_state": fake_console_state,
        "console_page": fake_console_page,
        "api_handler": fake_api,
        "resolve_upstream": make_resolver({"/train": "127.0.0.1:%d" % up_port}),
        "rate_limiter": portal_proxy.RateLimiter({"maxFailures": 3, "lockMs": 2000}),
    }
    server = portal_proxy.make_portal_server(0, config)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]

    failures = []

    def check(label, cond, detail=""):
        if cond:
            print("  PASS  %s" % label)
        else:
            print("  FAIL  %s %s" % (label, detail))
            failures.append(label)

    # ============ A. Host 分类（安全判定核心）============
    print("[A] Host 分类")
    cases = [
        # (Host 头, 期望分类, 原因)
        ("localhost:8899", "loopback", "本机"),
        ("127.0.0.1:8899", "loopback", "本机 IPv4"),
        ("127.5.6.7", "loopback", "127/8 全段都是回环"),
        ("[::1]:8899", "loopback", "本机 IPv6"),
        ("192.168.1.5:8899", "lan", "私网"),
        ("10.0.0.8", "lan", "私网"),
        ("172.16.5.5", "lan", "私网"),
        ("172.31.255.254", "lan", "私网边界"),
        ("100.64.3.4", "lan", "CGNAT/Tailscale"),
        ("169.254.1.1", "lan", "link-local"),
        ("my-laptop:8899", "lan", "单标签计算机名"),
        ("nas.local", "lan", "mDNS"),
        # ---- 以下必须是 public ----
        ("demo.trycloudflare.com", "public", "cloudflared 隧道"),
        ("8.8.8.8", "public", "公网 IP"),
        ("172.32.0.1", "public", "私网段之外（172.16/12 边界外）"),
        ("100.128.0.1", "public", "CGNAT 段之外"),
        ("my.domain.com", "public", "**自建域名必须当公网**（防绕过）"),
        ("portal.example.org", "public", "自建域名"),
        ("", "public", "无 Host -> fail closed"),
        ("   ", "public", "空白 Host -> fail closed"),
    ]
    for host, expected, why in cases:
        got = portal_proxy.classify_host(host)
        check("classify_host(%-24r) = %-8s  # %s" % (host, expected, why),
              got == expected, "实际 %r" % got)

    # 反例控制：证明分类不是恒返回同一个值
    kinds = {portal_proxy.classify_host(h) for h, _, _ in cases}
    check("分类结果确有三种（不是恒返回同一个值）",
          kinds == {"loopback", "lan", "public"}, "得到 %r" % kinds)

    print("[A2] 源地址分类")
    check("127.0.0.1 -> loopback",
          portal_proxy.classify_source("127.0.0.1") == "loopback")
    check("192.168.1.9 -> lan",
          portal_proxy.classify_source("192.168.1.9") == "lan")
    check("1.2.3.4 -> public",
          portal_proxy.classify_source("1.2.3.4") == "public")
    check("坏地址 -> None（不做任何收紧）",
          portal_proxy.classify_source("not-an-ip") is None)

    # ============ B. 内外网认证分层 ============
    print("[B] 认证分层")
    status, body, _ = request(port, "/", host="192.168.1.5:8899")
    check("内网访问控制台 -> 免密直接看到控制台",
          status == 200 and b"CONSOLE" in body, "code=%s" % status)

    status, body, _ = request(port, "/", host="localhost:8899")
    check("回环访问控制台 -> 免密",
          status == 200 and b"CONSOLE" in body)

    status, body, _ = request(port, "/", host="portal.example.org")
    check("**自建域名访问 -> 必须登录页（不放行控制台）**",
          b"CONSOLE" not in body and b'name="password"' in body,
          "code=%s" % status)

    status, body, _ = request(port, "/", host="demo.trycloudflare.com")
    check("公网访问 -> 登录页", b'name="password"' in body)
    check("公网登录页标明是公网入口",
          b"CONSOLE" not in body, "不该泄漏控制台内容")

    HITS.clear()
    status, body, _ = request(port, "/train/api/x", host="demo.trycloudflare.com")
    check("公网未登录 -> 不触达上游", not HITS, "上游命中 %r" % HITS)
    check("公网未登录 -> 不泄漏上游内容", b"UPSTREAM" not in body)

    # 内网免密时，服务代理也应免密
    HITS.clear()
    status, body, _ = request(port, "/train/api/x", host="192.168.1.5:8899")
    check("内网免密 -> 可直接访问已启用服务",
          status == 200 and b"UPSTREAM" in body, "code=%s" % status)
    check("内网访问确实到达上游", HITS == ["/api/x"], "命中 %r" % HITS)

    # 公网登录后可以访问
    status, _, headers = request(
        port, "/_auth/login", host="demo.trycloudflare.com", method="POST",
        data=urllib.parse.urlencode({"password": PASSWORD}).encode(),
        ctype="application/x-www-form-urlencoded")
    cookie = headers.get("Set-Cookie") or ""
    token = cookie.split("sp_session=")[1].split(";")[0] if "sp_session=" in cookie else ""
    check("公网用正确口令能登录", status == 303 and bool(token))

    HITS.clear()
    status, body, _ = request(port, "/train/api/x",
                              host="demo.trycloudflare.com",
                              cookie="sp_session=" + token)
    check("公网登录后可以访问服务",
          status == 200 and b"UPSTREAM" in body, "code=%s" % status)

    # 会话在两种分类下都有效（同一进程同一密钥）
    status, body, _ = request(port, "/", host="192.168.1.5:8899",
                              cookie="sp_session=" + token)
    check("会话在内外网之间通用（同一门户进程）", b"CONSOLE" in body)

    # ============ C. 路由与转发 ============
    print("[C] 路由与转发")
    HITS.clear()
    status, body, _ = request(port, "/train", host="192.168.1.5:8899")
    check("裸 mount 映射到上游 /",
          status == 200 and HITS == ["/"], "上游 %r" % HITS)

    HITS.clear()
    status, body, _ = request(port, "/train/deep/path?a=1&b=2",
                              host="192.168.1.5:8899")
    check("深层路径与查询串原样转发",
          HITS == ["/deep/path?a=1&b=2"], "上游 %r" % HITS)

    HITS.clear()
    status, body, _ = request(port, "/train/post", host="192.168.1.5:8899",
                              method="POST", data=b"hello", ctype="text/plain")
    check("POST 体转发到上游",
          b"UPSTREAM_POST:hello" in body, "body=%r" % body[:40])

    status, body, _ = request(port, "/not-registered/x", host="192.168.1.5:8899")
    check("未注册路径 -> 404（不拿控制台兜底）",
          status == 404 and b"CONSOLE" not in body, "code=%s" % status)

    status, body, _ = request(port, "/_auth/health", host="demo.trycloudflare.com")
    check("健康探针免认证（公网也不必登录）",
          status == 200 and b'"ok"' in body)

    # ============ D. 控制台 API ============
    print("[D] 控制台 API")
    API_CALLS.clear()
    status, body, _ = request(port, "/_api/services", host="192.168.1.5:8899")
    check("内网可直接调 API", status == 200 and b'"ok"' in body)

    API_CALLS.clear()
    status, body, _ = request(port, "/_api/services", host="portal.example.org")
    check("**公网未登录调 API -> 不放行**",
          b'"ok"' not in body and not API_CALLS,
          "code=%s calls=%r" % (status, API_CALLS))

    status, body, _ = request(port, "/_api/nope", host="192.168.1.5:8899")
    check("未知 API 路由 -> 404", status == 404, "code=%s" % status)

    # ============ E. 登录限速 ============
    print("[E] 登录限速")
    # 独立实例，避免影响前面的会话
    server2 = portal_proxy.make_portal_server(0, dict(
        config, rate_limiter=portal_proxy.RateLimiter(
            {"maxFailures": 3, "lockMs": 3000, "windowMs": 60000,
             "globalMaxFailures": 100})))
    threading.Thread(target=server2.serve_forever, daemon=True).start()
    port2 = server2.server_address[1]

    def bad_login():
        return request(port2, "/_auth/login", host="demo.trycloudflare.com",
                       method="POST",
                       data=urllib.parse.urlencode({"password": "wrong"}).encode(),
                       ctype="application/x-www-form-urlencoded")

    codes = [bad_login()[0] for _ in range(3)]
    check("连续错误口令依次被拒", all(c == 401 for c in codes), "codes=%r" % codes)
    code_locked, body_locked, _ = bad_login()
    check("达到阈值后锁定（429）", code_locked == 429, "code=%s" % code_locked)
    check("锁定提示里给出等待秒数", b"\xe7\xa7\x92" in body_locked)

    # 锁定期间即使口令正确也不放行（否则限速形同虚设）
    status, _, headers = request(
        port2, "/_auth/login", host="demo.trycloudflare.com", method="POST",
        data=urllib.parse.urlencode({"password": PASSWORD}).encode(),
        ctype="application/x-www-form-urlencoded")
    check("锁定期间正确口令也不放行", status == 429, "code=%s" % status)

    # 等锁过期后能登录（证明锁是限时的，不是永久封死）
    import time as _time
    _time.sleep(3.2)
    status, _, headers = request(
        port2, "/_auth/login", host="demo.trycloudflare.com", method="POST",
        data=urllib.parse.urlencode({"password": PASSWORD}).encode(),
        ctype="application/x-www-form-urlencoded")
    check("锁过期后正确口令可以登录", status == 303, "code=%s" % status)

    # ============ F. cf-connecting-ip 信任边界 ============
    print("[F] 客户端 IP 判定")
    limiter = portal_proxy.RateLimiter({})
    check("限速器初始不锁任何 IP",
          limiter.status("1.2.3.4")["locked"] is False)

    class FakeHandler:
        def __init__(self, peer, headers):
            self.client_address = (peer, 12345)
            self.headers = headers

    h_loop = FakeHandler("127.0.0.1", {"cf-connecting-ip": "9.9.9.9"})
    check("源为 loopback 时信任 cf-connecting-ip（隧道回连）",
          portal_proxy.client_ip(h_loop) == "9.9.9.9")

    h_direct = FakeHandler("192.168.1.50", {"cf-connecting-ip": "9.9.9.9"})
    check("**源不是 loopback 时忽略该头（防伪造绕过限速）**",
          portal_proxy.client_ip(h_direct) == "192.168.1.50",
          "得到 %r" % portal_proxy.client_ip(h_direct))

    h_multi = FakeHandler("127.0.0.1", {"cf-connecting-ip": "1.1.1.1, 2.2.2.2"})
    check("多个转发 IP 只取第一个",
          portal_proxy.client_ip(h_multi) == "1.1.1.1")

    # ============ G. 上游不可达 ============
    print("[G] 上游不可达")
    server3 = portal_proxy.make_portal_server(0, dict(
        config, resolve_upstream=make_resolver({"/dead": "127.0.0.1:1"})))
    threading.Thread(target=server3.serve_forever, daemon=True).start()
    port3 = server3.server_address[1]
    status, body, _ = request(port3, "/dead/x", host="192.168.1.5:8899")
    check("上游不可达 -> 502（不是 200 空 body）",
          status == 502 and b"502" in body, "code=%s" % status)
    check("502 里带上游地址便于排查",
          b"127.0.0.1:1" in body, "body=%r" % body[:60])

    # ---- 根绝对路径改写：挂在 /xxx 下的站点，其 /assets/... 必须能经门户取到 ----
    #
    # 现场（2026-10-28）：上游是个 vite 打包的 SPA，dist/index.html 写的是
    #   <script src="/assets/index-xxx.js">
    # 经门户 /solver/ 打开时，浏览器按**站点根**解析，于是请求
    # http://<门户>/assets/index-xxx.js —— 门户根没有这个文件，404，页面白屏。
    # 反向代理本该吞掉这类差异（nginx 的 sub_filter 就是干这个的），
    # 不能要求用户去改自己网站的 vite base。
    import http.server as _hs

    class RewriteUpstream(_hs.BaseHTTPRequestHandler):
        """按路径回不同 Content-Type 的上游，用来验证改写只发生在该改的地方。"""
        HTML = (b'<script type="module" src="/assets/app.js"></script>'
                b'<link rel="stylesheet" href="/assets/app.css">'
                b'<a href="//cdn.example.com/x.js">cdn</a>'
                b'<a href="/solver/already">ok</a>')
        CSS = b'a{background:url(/img/bg.png)} b{background:url("/img/b2.png")}'
        JSON_BODY = b'{"path":"/assets/not-a-reference"}'

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path.endswith(".css"):
                body, ctype = self.CSS, "text/css; charset=utf-8"
            elif path.endswith(".json"):
                body, ctype = self.JSON_BODY, "application/json"
            else:
                body, ctype = self.HTML, "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("ETag", '"deadbeef"')      # 改写后必须被丢掉
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    rw_up = _hs.ThreadingHTTPServer(("127.0.0.1", 0), RewriteUpstream)
    threading.Thread(target=rw_up.serve_forever, daemon=True).start()
    rw_port = rw_up.server_address[1]

    rw_config = {
        "password": PASSWORD,
        "cookie_secure": False,
        "open_classes": ("loopback", "lan"),
        "console_state": fake_console_state,
        "console_page": fake_console_page,
        "api_handler": fake_api,
        "resolve_upstream": make_resolver({"/solver": "127.0.0.1:%d" % rw_port}),
        "rate_limiter": portal_proxy.RateLimiter(),
    }
    rw_server = portal_proxy.make_portal_server(0, rw_config)
    threading.Thread(target=rw_server.serve_forever, daemon=True).start()
    rw_srv_port = rw_server.server_address[1]

    status, body, headers = request(rw_srv_port, "/solver/", host="192.168.1.5:8899")
    text = body.decode("utf-8", "replace")
    check("HTML 里 /assets/ 引用被补上 mount 前缀",
          'src="/solver/assets/app.js"' in text, "body=%r" % text[:120])
    check("HTML 里 href 也被补前缀",
          'href="/solver/assets/app.css"' in text, "body=%r" % text[:120])
    check("协议相对 URL（//cdn...）不被误改",
          'href="//cdn.example.com/x.js"' in text, "body=%r" % text[:120])
    check("已带 mount 前缀的路径不重复加",
          'href="/solver/already"' in text and "/solver/solver/" not in text,
          "body=%r" % text[:120])
    check("改写后 ETag 被丢弃（避免 304 复用未改写内容）",
          headers.get("ETag") is None, "etag=%r" % headers.get("ETag"))

    status, body, _ = request(rw_srv_port, "/solver/app.css", host="192.168.1.5:8899")
    css = body.decode("utf-8", "replace")
    check("CSS 的 url(/img/..) 被补前缀",
          "url(/solver/img/bg.png)" in css, "css=%r" % css[:120])
    check("CSS 带引号的 url 也被补，且括号不重复",
          'url("/solver/img/b2.png")' in css, "css=%r" % css[:120])

    status, body, _ = request(rw_srv_port, "/solver/x.json", host="192.168.1.5:8899")
    check("JSON 正文里的 /assets/ 不被改写（那是数据不是引用）",
          b"/assets/not-a-reference" in body, "body=%r" % body[:80])

    # 反例控制：改写只发生在**有 mount 前缀**的转发上。根路径请求（控制台）
    # 不该被改动 —— 否则控制台自己的引用就可能被莫名加上前缀。
    status, body, _ = request(rw_srv_port, "/", host="192.168.1.5:8899")
    check("门户控制台（根路径）不参与改写",
          b"/solver/" not in body, "body=%r" % body[:120])

    rw_server.shutdown()
    rw_server.server_close()
    rw_up.shutdown()
    rw_up.server_close()

    for srv in (server, server2, server3, upstream):
        srv.shutdown()
        srv.server_close()

    print("")
    if failures:
        print("门户代理控制检验失败：%d 项" % len(failures))
        for label in failures:
            print("  - %s" % label)
        return 1
    print("门户代理控制检验全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
