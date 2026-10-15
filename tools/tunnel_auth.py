# -*- coding: utf-8 -*-
"""给 GUI 加口令登录 + 会话 cookie 的反向代理（cloudflared 隧道的公开入口）。

为什么需要这一层
----------------
配置台（``gui/server.py``，默认 8810）与查看台（``gui/viewer_server.py``，默认 8811）
都只监听 127.0.0.1，并且**完全没有认证**：

  · 配置台可以启动/停止训练（直接占用 5090）；
  · 查看台暴露全部模型数据。

cloudflared quick tunnel 只能做「整站单目标转发」，本身**不能加密码**。
一旦把 8810/8811 直接交给隧道，任何拿到那个随机域名的人都能操作训练。
所以隧道必须指向本代理，由本代理校验口令之后再转发到上游 GUI：

    cloudflared --> 127.0.0.1:8890 (本代理) --> 127.0.0.1:8810 (配置台)
    cloudflared --> 127.0.0.1:8891 (本代理) --> 127.0.0.1:8811 (查看台)

本模块只做「认证 + 转发」，**不改动 GUI 代码**，因此不影响既有
``check_config_gui`` / ``check_gpu_gui`` / ``check_viewer_industry_standard``。

认证形态（2026-10-15 起）
------------------------
**只验口令，不要账号**：未登录访问返回一个自定义登录页（仅一个口令输入框），
不触发浏览器原生 Basic Auth 弹框；口令正确则下发签名会话 cookie。
细节与安全设计见 ``tools/portal_login.py`` 顶部。

口令来源（优先级从高到低）
--------------------------
1. ``--password-file <path>``（推荐：口令不进入命令行）
2. 环境变量 ``GUI_TUNNEL_PASSWORD``
3. ``--password <str>``（本机同用户可通过进程命令行看到，仅调试用）

命令行里出现口令等同于把口令写进 ``Get-CimInstance Win32_Process`` 的
CommandLine，所以 ``tools/start_public_gui.py`` 默认走第 2 条。

用法
----
    python -X utf8 tools/tunnel_auth.py --listen 8890 --upstream 127.0.0.1:8810 \
        --password-file C:\\path\\to\\secret.txt

    # 免认证健康探针（给启动脚本/检查用）：
    curl http://127.0.0.1:8890/_auth/health     ->  {"ok": true}
"""
import argparse
import hmac
import http.client
import json
import os
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from portal_login import (  # noqa: E402  （同目录，脚本方式运行时靠 sys.path[0]）
    DEFAULT_SESSION_TTL,
    HEALTH_PATH,
    LOGIN_PATH,
    LOGOUT_PATH,
    clear_cookie_header,
    gen_password,
    gen_secret,
    login_page_html,
    make_session,
    password_matches,
    read_session_cookie,
    read_token,
    session_cookie_header,
    session_valid,
    unauthorized_html,
    validate_password,
)
# 转发上游的响应头白名单（其余丢弃，且 Content-Length 一律按实际字节重写）。
_FORWARD_RESPONSE_HEADERS = (
    "content-type", "cache-control", "last-modified", "etag",
    "content-disposition", "pragma", "expires",
)
# 转发上游的请求头黑名单。
_SKIP_REQUEST_HEADERS = (
    "host", "authorization", "connection", "accept-encoding",
    "content-length", "transfer-encoding", "expect", "proxy-authorization",
)
HEALTH_PATH = "/_auth/health"


def parse_upstream(text):
    """'127.0.0.1:8810' -> ('127.0.0.1', 8810)"""
    if ":" not in text:
        raise ValueError("--upstream 必须是 host:port，收到 %r" % (text,))
    host, _, port = text.rpartition(":")
    host = host.strip() or "127.0.0.1"
    try:
        port_no = int(port)
    except ValueError:
        raise ValueError("--upstream 端口不是整数：%r" % (text,))
    if not (1 <= port_no <= 65535):
        raise ValueError("--upstream 端口越界：%r" % (text,))
    return host, port_no


class TunnelAuthHandler(BaseHTTPRequestHandler):
    """口令登录（会话 cookie）校验通过后，把请求原样转发到上游 GUI。"""

    protocol_version = "HTTP/1.1"
    server_version = "tunnel-auth"
    sys_version = ""

    # 由 make_server() 在子类上注入
    up_host = "127.0.0.1"
    up_port = 8810
    password = ""
    upstream_timeout = 60.0
    # 路径前缀剥离（可选）：挂到 https://<域名>/train/ 时该值为 "/train"。
    # 请求 /train/api/x -> 转发给上游 /api/x；/train 与 /train/ -> 上游 /。
    # 空串 = 挂在域名根，行为与不带前缀时完全一致。
    strip_prefix = ""
    # 多挂载点模式（可选）：((前缀, 上游host, 上游port), ...)，长前缀优先。
    # 非空时用它替掉单上游；空元组 = 老的单上游行为（控制检验依赖这条）。
    mounts = ()
    # mounts 模式下访问 "/" 时的落地页（bytes）；None = 返回 404。
    landing_html = None

    # ---- 日志（默认写 stderr；启动脚本重定向到文件）----
    def log_message(self, fmt, *args):
        sys.stderr.write("[tunnel_auth] %s - %s\n"
                         % (self.address_string(), fmt % args))
        sys.stderr.flush()

    # ---- 认证（口令登录 + 签名会话 cookie，无账号）----
    # 由 make_handler() 在子类上注入：
    password = ""
    secret = b""
    session_ttl = DEFAULT_SESSION_TTL
    # cookie 是否带 Secure。外网入口恒为 https（trycloudflare）；本机 http
    # 调试/控制检验时置 False，否则浏览器不会回传 cookie。
    cookie_secure = True

    def _authorized(self):
        """会话 cookie 有效即视为已登录。**不再有账号字段。**"""
        token = read_session_cookie(self.headers.get("Cookie", ""))
        return session_valid(token, self.secret)

    def _read_body(self):
        declared = self.headers.get("Content-Length")
        if not declared:
            return b""
        try:
            size = int(declared)
        except ValueError:
            return b""
        return self.rfile.read(size) if size > 0 else b""

    def _send_html(self, status, body, extra_headers=()):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        for key, value in extra_headers:
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _login_page(self, error=None, status=200, extra_headers=()):
        """未登录 / 口令错误时给出的登录页（不触发浏览器原生弹框）。"""
        body = login_page_html(error=error)
        self._send_html(status, body, extra_headers)

    def _redirect(self, location):
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        return None

    def _handle_login(self):
        """POST 口令 -> 校验 -> 下发会话 cookie。"""
        body = self._read_body()
        content_type = self.headers.get("Content-Type", "")
        candidate = read_token({"body_bytes": body}, content_type)
        if candidate is None:
            return self._login_page("提交格式不正确，请重新输入口令。", status=400)
        if not password_matches(candidate, self.password):
            # 失败一律同一页面同一文案：不给任何可用于区分原因的差异。
            return self._login_page("口令错误，请重试。", status=401)
        token = make_session(self.secret, self.session_ttl)
        # 303 让浏览器转成 GET 落到根路径；Set-Cookie 随同一响应下发。
        self.send_response(303)
        self.send_header("Location", "/")
        self.send_header(
            "Set-Cookie",
            session_cookie_header(token, self.session_ttl,
                                  secure=self.cookie_secure))
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        return None

    def _handle_logout(self):
        self._send_html(200, login_page_html(error="已退出，请重新输入口令。"),
                        extra_headers=[("Set-Cookie", clear_cookie_header())])

    def _health(self):
        body = json.dumps({"ok": True}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _match_mount(self, path):
        """在 mounts 里找最长前缀匹配，返回 (前缀, host, port, 剩余路径) 或 None。

        最长优先：/train/api 命中 '/train' 而不是更短的 '/' 兜底。
        """
        best = None
        for prefix, host, port in self.mounts:
            if path == prefix or path.startswith(prefix + "/") \
                    or path.startswith(prefix + "?"):
                if best is None or len(prefix) > len(best[0]):
                    best = (prefix, host, port)
        if best is None:
            return None
        prefix, host, port = best
        if path == prefix:
            rest = "/"
        elif path.startswith(prefix + "?"):
            rest = "/" + path[len(prefix):]
        else:
            rest = path[len(prefix):]
        return prefix, host, port, rest

    def _resolve_target(self):
        """决定这次请求发往哪里。

        返回 (host, port, path) 或 ("", 0, None)。
        path=None 表示由本代理自己返回落地页（mounts 模式的 /）。
        """
        path = self.path
        # 健康探针永远由本代理自己答（在认证之前，供启动脚本判定存活）。
        if path.split("?", 1)[0] == HEALTH_PATH:
            return ("", 0, HEALTH_PATH)
        if self.mounts:
            hit = self._match_mount(path.split("?", 1)[0])
            if hit is None:
                return ("", 0, None)  # 无匹配 -> 落地页或 404
            _, host, port, rest = hit
            query = ""
            if "?" in path:
                query = path[path.index("?"):]
            return (host, port, rest + query)
        return (self.up_host, self.up_port, self._upstream_path())

    def _bad_gateway(self, reason, host=None, port=None):
        body = ("502 Bad Gateway：上游 %s:%d 不可达 —— %s\n"
                % (host or self.up_host, port or self.up_port, reason)).encode("utf-8")
        self.send_response(502)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _upstream_path(self):
        """把挂载前缀剥掉，得到上游真实路径。

        strip_prefix=''      -> 原样转发
        strip_prefix='/train'-> '/train/api/x' -> '/api/x'
                                '/train'       -> '/'
                                '/train/'      -> '/'
        """
        prefix = self.strip_prefix
        if not prefix:
            return self.path
        path = self.path
        if path == prefix:
            return "/"
        if path.startswith(prefix + "/"):
            return path[len(prefix):]
        if path.startswith(prefix + "?"):
            return "/" + path[len(prefix):]
        # 前缀不匹配：原样转发，让上游自己决定 404（不静默改写别的路径）。
        return path

    # ---- 转发 ----
    def _proxy(self):
        path_only = self.path.split("?", 1)[0]

        # 1) 健康探针：免认证，永远由本代理自己答（启动脚本靠它判定存活）。
        if path_only == HEALTH_PATH:
            return self._health()

        # 2) 登录/登出：认证层自己的路由，**不转发给上游**。
        #    放在认证判断之前，否则未登录的人打不开登录页。
        if path_only == LOGIN_PATH:
            if self.command == "POST":
                return self._handle_login()
            # GET 登录页：已登录就直接回根路径，省一次手动跳转。
            if self._authorized():
                return self._redirect("/")
            return self._login_page()
        if path_only == LOGOUT_PATH:
            return self._handle_logout()

        host, port, target_path = self._resolve_target()
        if target_path == HEALTH_PATH:
            return self._health()

        # 3) 认证在转发之前：未登录请求绝不触达上游，也绝不泄露上游存在与否。
        if not self._authorized():
            # 用 200 + 登录页，不用 401：401 的语义是「需要 WWW-Authenticate
            # 质询」，而我们刻意不发那个头（避免浏览器原生弹框）。用 401 会让
            # 中间的代理/CDN 或某些浏览器把它当成失败页处理。
            # 「口令错误」才是 401（见 _handle_login）。
            return self._login_page(status=200)

        if target_path is None:
            # mounts 模式下未匹配任何前缀：只有根路径给落地页，其余一律 404
            # （不能拿落地页兜底未知前缀，否则拼错的路径会"看起来能用"）。
            if self.landing_html is not None and path_only in ("/", ""):
                return self._send_html(200, self.landing_html)
            return self._send_html(404, b"404 Not Found\n")

        body = None
        declared = self.headers.get("Content-Length")
        if declared:
            try:
                size = int(declared)
            except ValueError:
                size = 0
            if size > 0:
                body = self.rfile.read(size)

        headers = {}
        for key, value in self.headers.items():
            if key.lower() in _SKIP_REQUEST_HEADERS:
                continue
            headers[key] = value

        conn = http.client.HTTPConnection(host, port,
                                          timeout=self.upstream_timeout)
        try:
            conn.request(self.command, target_path, body=body, headers=headers)
            response = conn.getresponse()
            payload = response.read()
        except Exception as exc:  # 上游挂了必须显式 502，不能装作 200 空 body
            self._bad_gateway(repr(exc), host, port)
            return
        finally:
            try:
                conn.close()
            except Exception:
                pass

        self.send_response(response.status)
        for key, value in response.getheaders():
            lower = key.lower()
            if lower == "content-length":
                continue  # 统一按实际字节重写，避免长度不符导致浏览器挂起
            if lower in _FORWARD_RESPONSE_HEADERS:
                self.send_header(key, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    do_GET = _proxy
    do_POST = _proxy
    do_HEAD = _proxy
    do_PUT = _proxy
    do_DELETE = _proxy
    do_OPTIONS = _proxy


def normalise_prefix(prefix):
    """把 'train' / '/train' / '/train/' 统一成 '/train'；空/None 变成 ''。"""
    text = (prefix or "").strip()
    if not text or text == "/":
        return ""
    if not text.startswith("/"):
        text = "/" + text
    return text.rstrip("/")


def parse_mounts(text):
    """解析 '--mounts' 参数：'/train=127.0.0.1:8810,/viewer=127.0.0.1:8811'

    返回 ((前缀, host, port), ...)；空串返回 ()。
    """
    text = (text or "").strip()
    if not text:
        return ()
    mounts = []
    for item in text.split(","):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            raise ValueError("--mounts 每项必须是 前缀=host:port，收到 %r" % item)
        prefix, _, target = item.partition("=")
        prefix = normalise_prefix(prefix)
        if not prefix:
            raise ValueError("--mounts 的前缀不能为空：%r" % item)
        host, port = parse_upstream(target)
        mounts.append((prefix, host, port))
    # 长前缀优先，避免 /a 抢走 /ab 的请求
    mounts.sort(key=lambda row: len(row[0]), reverse=True)
    return tuple(mounts)


def make_handler(up_host, up_port, password, timeout=60.0,
                 strip_prefix="", mounts=(), landing_html=None,
                 secret=None, session_ttl=DEFAULT_SESSION_TTL,
                 cookie_secure=True):
    """构造绑定了上游/口令的 Handler 子类（避免用全局可变状态）。

    ``secret=None`` 时自动生成一次性会话密钥 —— 每次进程启动都不同，
    重启门户即全体会话作废（见 portal_login 的安全设计第 3 条）。
    """
    return type("BoundTunnelAuthHandler", (TunnelAuthHandler,), {
        "up_host": up_host,
        "up_port": int(up_port),
        "password": password,
        "secret": secret if secret is not None else gen_secret(),
        "session_ttl": int(session_ttl),
        "cookie_secure": bool(cookie_secure),
        "upstream_timeout": float(timeout),
        "strip_prefix": normalise_prefix(strip_prefix),
        "mounts": tuple(mounts),
        "landing_html": landing_html,
    })


def make_server(listen_port, up_host, up_port, password,
                listen_host="127.0.0.1", timeout=60.0, strip_prefix="",
                mounts=(), landing_html=None, secret=None,
                session_ttl=DEFAULT_SESSION_TTL, cookie_secure=True):
    """起一个已配好的 ThreadingHTTPServer（listen_port=0 时自动分配端口）。"""
    handler = make_handler(up_host, up_port, password, timeout,
                           strip_prefix, mounts, landing_html,
                           secret=secret, session_ttl=session_ttl,
                           cookie_secure=cookie_secure)
    return ThreadingHTTPServer((listen_host, int(listen_port)), handler)


def resolve_password(args):
    if getattr(args, "password_file", None):
        with open(args.password_file, "r", encoding="utf-8") as handle:
            return handle.read().strip()
    env = os.environ.get("GUI_TUNNEL_PASSWORD")
    if env:
        return env.strip()
    return (getattr(args, "password", None) or "").strip()


def build_parser():
    ap = argparse.ArgumentParser(
        description="给 GUI 加「口令登录」的反向代理（cloudflared 隧道入口，无需账号）")
    ap.add_argument("--listen", type=int, default=8890,
                    help="本代理监听端口（只绑 127.0.0.1，默认 8890）")
    ap.add_argument("--upstream", default="127.0.0.1:8810",
                    help="上游 GUI，host:port（默认 127.0.0.1:8810 配置台）")
    ap.add_argument("--password", default="",
                    help="访问口令；仅调试用，正式走 --password-file 或环境变量")
    ap.add_argument("--password-file", default=None,
                    help="从文件读取口令（推荐，口令不进入命令行）")
    ap.add_argument("--strip-prefix", default="",
                    help="挂载前缀，如 /train：请求 /train/api/x 转发给上游 /api/x")
    ap.add_argument("--mounts", default="",
                    help="多挂载点，如 '/train=127.0.0.1:8810,/viewer=127.0.0.1:8811'"
                         "（一个域名 + 多个路径；给定时 --upstream 仅作兜底）")
    ap.add_argument("--timeout", type=float, default=60.0, help="上游超时秒数")
    ap.add_argument("--session-ttl", type=int, default=DEFAULT_SESSION_TTL,
                    help="登录会话有效期秒数（默认 %d）" % DEFAULT_SESSION_TTL)
    ap.add_argument("--insecure-cookie", action="store_true",
                    help="会话 cookie 不带 Secure（仅供本机 http 调试；外网必须保持默认）")
    return ap


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    password = resolve_password(args)
    try:
        validate_password(password)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    try:
        up_host, up_port = parse_upstream(args.upstream)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    try:
        mounts = parse_mounts(args.mounts)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    landing = None
    if mounts:
        rows = "".join(
            '<li><a href="%s/">%s/</a> → %s:%d</li>' % (p, p, h, pt)
            for p, h, pt in mounts)
        landing = (
            "<!DOCTYPE html><html lang=\"zh\"><head><meta charset=\"utf-8\">"
            "<title>dsh-service-portal 对外服务门户</title></head><body"
            " style=\"font-family:system-ui;background:#121212;color:#eee;"
            "padding:2rem\"><h1>dsh-service-portal 对外服务门户</h1>"
            "<p>需要口令登录才能访问下列服务。</p><ul>%s</ul>"
            "</body></html>" % rows).encode("utf-8")

    server = make_server(args.listen, up_host, up_port, password,
                         timeout=args.timeout,
                         strip_prefix=args.strip_prefix,
                         mounts=mounts, landing_html=landing,
                         session_ttl=args.session_ttl,
                         cookie_secure=not args.insecure_cookie)
    host, port = server.server_address[0], server.server_address[1]
    prefix = normalise_prefix(args.strip_prefix)
    print("认证代理已启动：http://%s:%d%s/  ->  http://%s:%d/"
          % (host, port, prefix, up_host, up_port))
    print("  登录方式: 只需口令（%s%s）"
          % (LOGIN_PATH, "，本机调试 cookie 不带 Secure" if args.insecure_cookie else ""))
    print("  口令    : 已设置（%d 字符，不回显）" % len(password))
    print("  会话有效期: %d 秒" % args.session_ttl)
    if prefix:
        print("  挂载前缀: %s（请求 %s/api/x → 上游 /api/x）" % (prefix, prefix))
    for mount_prefix, mount_host, mount_port in mounts:
        print("  挂载点: %s/  →  %s:%d" % (mount_prefix, mount_host, mount_port))
    print("  健康探针: http://%s:%d%s" % (host, port, HEALTH_PATH))
    sys.stdout.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
