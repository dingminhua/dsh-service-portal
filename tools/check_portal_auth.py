# -*- coding: utf-8 -*-
"""认证层的控制检验：**只验口令**（无账号）+ 会话 cookie + 认证先于转发。

拦的是这类 bug（每条都对应一个真实会发生的失败）：
  1. 未登录请求被转发到上游 —— 保护区直接对外裸奔（最严重）；
  2. 口令错了仍下发会话 cookie —— 认证形同虚设；
  3. 会话 cookie 可伪造/篡改 —— 换掉签名照样进；
  4. 会话永不过期 —— 一次泄漏永久有效；
  5. cookie 里放的是口令本身 —— 拿 cookie 就等于拿到口令；
  6. 登录页出现账号字段或发 WWW-Authenticate —— 退回 Basic Auth 弹框体验；
  7. 未登录响应泄漏上游是否可达 —— 给攻击者做端口/服务探测的探针；
  8. 未知 content-type 的正文被当口令解析 —— 解析歧义；
  9. 健康探针被认证挡住 —— 启动脚本判活失败，误报「代理未就绪」。

依赖：只用标准库，无需第三方包（本仓库硬纪律：依赖缺失要跳过并返回 2）。

运行：python -X utf8 tools/check_portal_auth.py
退出码：0 = 全通过；1 = 有失败；2 = 跳过（依赖缺失）
"""
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
    print("跳过：当前 Python 没有 http.server（依赖缺失不代表通过）")
    raise SystemExit(2)

try:
    import tunnel_auth
    import portal_login
except ImportError as exc:
    print("跳过：无法导入认证模块（%s）；依赖缺失不代表通过" % exc)
    raise SystemExit(2)

PASSWORD = "control-check-password-123"
HITS = []


class Upstream(BaseHTTPRequestHandler):
    """假上游：记录所有到达的路径（用来证明「认证先于转发」）。"""

    protocol_version = "HTTP/1.1"

    def do_GET(self):
        HITS.append(self.path)
        body = b"UPSTREAM_OK:" + self.path.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def request(base, path, cookie=None, method="GET", data=None, ctype=None):
    """发请求；**不跟随重定向**（要断言 303 与 Set-Cookie 本身）。"""

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None

    opener = urllib.request.build_opener(NoRedirect)
    req = urllib.request.Request(base + path, data=data, method=method)
    if cookie:
        req.add_header("Cookie", cookie)
    if ctype:
        req.add_header("Content-Type", ctype)
    try:
        res = opener.open(req, timeout=5)
        return res.status, res.read(), res.headers
    except urllib.error.HTTPError as err:
        return err.code, err.read(), err.headers


def main():
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    server = tunnel_auth.make_server(0, "127.0.0.1", upstream.server_address[1],
                                     PASSWORD, cookie_secure=False)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % server.server_address[1]

    failures = []

    def check(label, condition, detail=""):
        if condition:
            print("  PASS  %s" % label)
        else:
            print("  FAIL  %s %s" % (label, detail))
            failures.append(label)

    print("认证层控制检验（代理 %s，上游 %s:%d）"
          % (base, *upstream.server_address))
    print("")

    # ---- 未登录 ----
    print("[未登录]")
    status, body, headers = request(base, "/")
    check("返回登录页", status == 200 and b'name="password"' in body)
    check("不发 WWW-Authenticate（无原生弹框）",
          headers.get("WWW-Authenticate") is None)
    check("登录页没有账号输入字段",
          b'name="user"' not in body and b'name="username"' not in body
          and b'type="text"' not in body)

    HITS.clear()
    status, body, _ = request(base, "/secret-area")
    check("未登录绝不触达上游", not HITS, "上游命中了 %r" % HITS)
    check("未登录响应不泄漏上游内容", b"UPSTREAM_OK" not in body)

    # ---- 健康探针 ----
    print("[健康探针]")
    status, body, _ = request(base, "/_auth/health")
    check("免认证可访问", status == 200 and b'"ok"' in body)

    # ---- 登录 ----
    print("[登录]")
    HITS.clear()
    status, body, headers = request(
        base, "/_auth/login", method="POST",
        data=urllib.parse.urlencode({"password": "wrong-password"}).encode(),
        ctype="application/x-www-form-urlencoded")
    check("错误口令返回 401", status == 401)
    check("错误口令不下发会话", "Set-Cookie" not in headers)
    check("错误口令不触达上游", not HITS)

    status, _, headers = request(
        base, "/_auth/login", method="POST",
        data=urllib.parse.urlencode({"password": PASSWORD}).encode(),
        ctype="application/x-www-form-urlencoded")
    check("正确口令 303 跳转", status == 303)
    cookie = headers.get("Set-Cookie") or ""
    check("下发会话 cookie", "sp_session=" in cookie)
    check("cookie 是 HttpOnly", "HttpOnly" in cookie)
    check("cookie 里不含口令本身", PASSWORD not in cookie)
    token = cookie.split("sp_session=")[1].split(";")[0] if "sp_session=" in cookie else ""

    # ---- 会话 ----
    print("[会话]")
    HITS.clear()
    status, body, _ = request(base, "/page?a=1", cookie="sp_session=" + token)
    check("有效会话转发到上游", status == 200 and b"UPSTREAM_OK" in body)
    check("上游收到原路径（未被改写）", HITS == ["/page?a=1"], "实际 %r" % HITS)

    for label, forged in (
        ("伪造签名", "sp_session=9999999999.deadbeefdeadbeefdeadbeefdeadbeef"),
        ("篡改签名", "sp_session=" + (token[:-2] + "ff" if token else "x.y")),
        ("无签名", "sp_session=9999999999"),
    ):
        HITS.clear()
        status, body, _ = request(base, "/page", cookie=forged)
        check("%s 不放行" % label,
              status == 200 and b'name="password"' in body and not HITS)

    expired = portal_login.make_session(b"k" * 32, ttl=-10)
    check("过期会话无效（签名对也不行）",
          not portal_login.session_valid(expired, b"k" * 32))

    status, _, headers = request(base, "/_auth/logout")
    check("登出清除 cookie", "Max-Age=0" in (headers.get("Set-Cookie") or ""))

    # ---- 口令解析与比较 ----
    print("[口令解析]")
    check("表单取口令",
          portal_login.read_token({"body_bytes": b"password=abc"},
                                  "application/x-www-form-urlencoded") == "abc")
    check("JSON 取口令",
          portal_login.read_token({"body_bytes": b'{"password":"abc"}'},
                                  "application/json") == "abc")
    check("未知 content-type 拒收",
          portal_login.read_token({"body_bytes": b"password=abc"},
                                  "text/plain") is None)
    check("坏 JSON 拒收",
          portal_login.read_token({"body_bytes": b"{oops"},
                                  "application/json") is None)
    check("空正文拒收",
          portal_login.read_token({"body_bytes": b""},
                                  "application/json") is None)

    print("[口令比较]")
    check("相等为真", portal_login.password_matches("abc", "abc"))
    check("不等为假", not portal_login.password_matches("abd", "abc"))
    check("空期望恒假", not portal_login.password_matches("", ""))
    check("None 恒假", not portal_login.password_matches(None, "abc"))
    check("非字符串恒假", not portal_login.password_matches(123, "abc"))

    print("[口令门槛]")
    for bad, why in (("", "空口令"), ("short", "太短"), ("   ", "全空白")):
        try:
            portal_login.validate_password(bad)
            check("拒绝%s" % why, False, "竟然通过了")
        except ValueError:
            check("拒绝%s" % why, True)
    check("接受足够长的口令", portal_login.validate_password(PASSWORD) is True)

    server.shutdown()
    upstream.shutdown()
    print("")
    if failures:
        print("认证层控制检验失败：%d 项" % len(failures))
        for label in failures:
            print("  - %s" % label)
        return 1
    print("认证层控制检验全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
