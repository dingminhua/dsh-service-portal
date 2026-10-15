# -*- coding: utf-8 -*-
"""门户代理：按 **Host 信任分类** 决定认证，并把控制台 + 多服务路由合在一个端口。

为什么要「分类」而不是「一律要密码」
------------------------------------
对外服务门户同时提供两种访问方式：

  · 内网（http://192.168.x.x:8899）—— 同一 WiFi 下手机/笔记本直接打开；
  · 外网（https://xxx.trycloudflare.com）—— 人不在家时用。

内网访问已经在你的局域网边界内，再要一次口令纯属碍事；外网则**必须**口令。
所以认证强度按请求来源区分，这正是 dsh-pocket 的做法（本项目的参照实现）。

分类与策略（fail-closed）
-------------------------
  loopback  localhost / 127.x / ::1 / 0.0.0.0   → 免密（本机与 cloudflared 回连）
  lan       RFC1918 私网、CGNAT 100.64/10、IPv6 ULA/link-local、.local、单标签名 → 免密
  public    其余一切（含**自建域名**、公网 IP、解析不出的名字） → **必须口令**

**兜底方向是安全的**：认不出的 Host 一律当 public。曾见过反过来的实现（只把
`*.trycloudflare.com` 当外网、其余当内网），结果用户挂个自己的域名上来，
认证就被绕过了。

另一条关键规则：`cf-connecting-ip` 只在**源地址是 loopback** 时才可信
（那是 cloudflared 回连时写的真实客户端 IP）；否则任何能直连端口的人都能
伪造这个头来绕过登录限速。
"""
import ipaddress
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import portal_login
from portal_login import (
    DEFAULT_SESSION_TTL,
    HEALTH_PATH,
    LOGIN_PATH,
    LOGOUT_PATH,
    clear_cookie_header,
    login_page_html,
    make_session,
    password_matches,
    read_session_cookie,
    read_token,
    session_cookie_header,
    session_valid,
)

# 控制台自己的保留路径（由门户直接处理，绝不转发给上游）
CONSOLE_PATH = "/"
API_PREFIX = "/_api"

# 登录限速默认值（照搬 dsh-pocket：单 IP 5 次 / 60 秒，全局阈值防分布式扫描）
DEFAULT_RATE_LIMIT = {
    "maxFailures": 5,
    "windowMs": 300_000,
    "lockMs": 60_000,
    "globalMaxFailures": 30,
    "globalLockMs": 300_000,
}


# --------------------------------------------------------------------- 分类

def _hostname_of(host_header):
    """从 Host 头取出主机名（去掉端口、去掉 IPv6 方括号、小写、去尾点）。"""
    text = (host_header or "").strip().lower()
    if text.startswith("["):           # [::1]:8899
        end = text.find("]")
        if end < 0:
            return ""
        return text[1:end]
    # 只有一个冒号才当成 host:port；多个冒号是裸 IPv6（不带方括号的畸形形态）
    if text.count(":") == 1:
        text = text.split(":", 1)[0]
    return text.rstrip(".")


def _is_private_v4(addr):
    """RFC1918 + CGNAT(100.64/10, RFC6598) + 其他不可公网路由的私网段。"""
    nets = (
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("100.64.0.0/10"),   # CGNAT / Tailscale / ZeroTier
        ipaddress.ip_network("169.254.0.0/16"),  # link-local
        ipaddress.ip_network("127.0.0.0/8"),
    )
    return any(addr in net for net in nets)


def _is_single_label_hostname(name):
    """是不是合法的单标签主机名（RFC 1123 的一个 label）。

    ``myhost`` / ``nas-2`` / ``a1`` -> True；
    ``garbage value`` / ``<script>`` / ``-x`` / ``x-`` / ``""`` -> False。

    这条判定是 fail-closed 的一部分：不合法的形态必须落到 public（要求口令），
    而不是因为「不含点」就享受内网免密。
    """
    if not name or len(name) > 63:
        return False
    if name.startswith("-") or name.endswith("-"):
        return False
    for ch in name:
        if not (ch.isascii() and (ch.isalnum() or ch == "-")):
            return False
    return True


def classify_host(host_header):
    """把 Host 头分成 'loopback' / 'lan' / 'public'（**认不出 -> public**）。"""
    name = _hostname_of(host_header)
    if not name:
        # 没有 Host 头（裸 HTTP/1.0 等畸形请求）-> 当公网，要求口令
        return "public"
    if name in ("localhost", "0.0.0.0", "::1", "::"):
        return "loopback"
    # 先去壳：尝试当 IP 解析
    try:
        addr = ipaddress.ip_address(name)
    except ValueError:
        addr = None
    if addr is not None:
        if addr.is_loopback:
            return "loopback"
        if isinstance(addr, ipaddress.IPv4Address):
            return "lan" if _is_private_v4(addr) else "public"
        # IPv6：ULA(fc00::/7) 与 link-local(fe80::/10) 视为内网
        if addr.is_private or addr.is_link_local:
            return "lan"
        return "public"
    # 非 IP：按域名形态判断
    if name.endswith(".local") or name.endswith(".localhost"):
        return "lan"
    # 单标签名（NetBIOS 计算机名、容器名等，不含点）-> 局域网。
    #
    # 但**必须先确认它是合法的单标签主机名**（RFC 1123：字母/数字/连字符，
    # 不以连字符开头或结尾）。否则像 "garbage value"、"<script>"、"a;b" 这类
    # 畸形 Host 也会因为「不含点」而被当成内网 —— 那就等于给了一条
    # 「随便编个 Host 就能免密」的绕过路径（fail-closed 的意义正在于此）。
    if "." not in name:
        return "lan" if _is_single_label_hostname(name) else "public"
    # 其余一律公网 —— **这条是 fail-closed 的关键**：
    # 用户自建域名（DNS 指向本机端口）也会走到这里，必须要求口令。
    return "public"


def resolve_open_classes(open_classes, provider):
    """算出「哪些来源免密」。provider 优先（设置页可即时改），出错则收紧到只免本机。"""
    if callable(provider):
        try:
            return tuple(provider())
        except Exception:
            return ("loopback",)     # provider 出错 -> 最安全：只免本机
    return tuple(open_classes or ())


def lan_access_enabled(provider):
    """局域网访问总开关。

    关掉后：同一 WiFi 的请求**看不到控制台也访问不到服务**（一律要求口令）。
    本机(loopback)不受影响，否则用户在电脑上连自己的门户都进不去。

    provider 出错 -> 返回 False（收紧）：宁可多要一次口令，也不能静默放开内网。
    """
    if callable(provider):
        try:
            return bool(provider())
        except Exception:
            return False
    return True


def needs_auth(kind, open_classes=("loopback", "lan"),
               open_classes_provider=None, lan_enabled_provider=None):
    """该来源是否需要口令（认证层的唯一判定入口，纯函数便于控制检验直接测）。

    kind: classify_host() 的分类结果（loopback / lan / public）
    """
    # 局域网总开关关掉时，内网按公网对待（同样要口令）。
    if kind == "lan" and not lan_access_enabled(lan_enabled_provider):
        return True
    return kind not in resolve_open_classes(open_classes, open_classes_provider)


def classify_source(addr):
    """按 socket 源地址分类（用于「谁是客户端」这个身份判断）。"""
    text = (addr or "").strip()
    if not text:
        return None
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        return None
    if ip.is_loopback:
        return "loopback"
    if ip.is_private or ip.is_link_local:
        return "lan"
    return "public"


def client_ip(handler):
    """客户端真实 IP。

    cloudflared 回连时源地址是 loopback，此时 `cf-connecting-ip` 才是
    Cloudflare 边缘写的真实访客 IP，可以信；其余情况一律用 socket 源地址
    （否则伪造这个头就能绕过登录限速）。
    """
    peer = handler.client_address[0] if handler.client_address else ""
    if classify_source(peer) == "loopback":
        forwarded = handler.headers.get("cf-connecting-ip") or ""
        forwarded = forwarded.strip()
        if forwarded:
            # 只取第一个（防「真 IP, 伪造 IP」这种拼接）
            return forwarded.split(",")[0].strip()
    return peer


# ------------------------------------------------------------------ 限速器

class RateLimiter:
    """登录失败限速：单 IP 锁 + 全局锁（防分布式撞库）。"""

    def __init__(self, config=None):
        cfg = dict(DEFAULT_RATE_LIMIT)
        cfg.update(config or {})
        self.config = cfg
        self._fails = {}        # ip -> {"count", "start"}
        self._locks = {}        # ip -> locked_until_ms
        self._global = {"count": 0, "start": 0.0, "lockedUntil": 0.0}
        self._lock = threading.Lock()

    def status(self, ip):
        now = time.time() * 1000
        with self._lock:
            if self._global["lockedUntil"] > now:
                return {"locked": True,
                        "retryAfter": int((self._global["lockedUntil"] - now) / 1000) + 1}
            until = self._locks.get(ip, 0)
            if until > now:
                return {"locked": True,
                        "retryAfter": int((until - now) / 1000) + 1}
        return {"locked": False, "retryAfter": 0}

    def record_failure(self, ip):
        now = time.time() * 1000
        cfg = self.config
        with self._lock:
            rec = self._fails.get(ip)
            if rec is None or now - rec["start"] > cfg["windowMs"]:
                rec = {"count": 0, "start": now}
            rec["count"] += 1
            self._fails[ip] = rec
            if now - self._global["start"] > cfg["windowMs"]:
                self._global = {"count": 0, "start": now,
                                "lockedUntil": self._global["lockedUntil"]}
            self._global["count"] += 1
            locked = False
            if rec["count"] >= cfg["maxFailures"]:
                self._locks[ip] = now + cfg["lockMs"]
                locked = True
            if self._global["count"] >= cfg["globalMaxFailures"]:
                self._global["lockedUntil"] = now + cfg["globalLockMs"]
                locked = True
            # 防内存膨胀：条目过多时清掉过窗口期的
            if len(self._fails) > 2000:
                for key in [k for k, v in self._fails.items()
                            if now - v["start"] > cfg["windowMs"]]:
                    self._fails.pop(key, None)
            return {"locked": locked,
                    "retryAfter": int(cfg["lockMs"] / 1000) if locked else 0}

    def clear(self, ip):
        with self._lock:
            self._fails.pop(ip, None)
            self._locks.pop(ip, None)


# ------------------------------------------------------------- 代理 Handler

class PortalHandler(BaseHTTPRequestHandler):
    """控制台 + 认证 + 多服务路由的合并 Handler。

    子类由 make_portal_server() 注入配置。核心流程：
      1. 分类 Host -> loopback / lan / public
      2. 健康探针免认证
      3. public 且无有效会话 -> 登录页（认证先于一切转发）
      4. 控制台路径 / 与 /_api/* -> 交给回调（console/API）
      5. 其余 -> 按 mount 查注册表转发到上游
    """

    protocol_version = "HTTP/1.1"
    server_version = "service-portal"
    sys_version = ""

    password = ""
    secret = b""
    session_ttl = DEFAULT_SESSION_TTL
    cookie_secure = True
    # 免密分类集合：默认内网与回环都免密（用户选定「内网免密」）
    open_classes = ("loopback", "lan")
    # 动态免密集合（可选）：callable() -> tuple。给了它就优先于上面的静态值，
    # 这样设置页切换「内网访问密码」能**立即生效**，不用重启门户进程
    # （重启会换掉隧道域名，代价太大）。
    open_classes_provider = None
    # 局域网访问总开关（可选 provider）：callable() -> bool。返回 False 时内网按
    # 公网对待（要口令），用于设置页的「局域网访问」总开关。
    lan_enabled_provider = None
    upstream_timeout = 60.0
    # 回调：() -> dict(控制台 state)；以及 API 处理器
    console_state = None        # callable() -> dict
    console_page = None         # callable(state, is_public) -> bytes
    api_handler = None          # callable(handler, method, route, body) -> bool(已处理)
    rate_limiter = None         # RateLimiter
    # 上游查表：callable(path) -> (mount, host, port, rest_path) 或 None
    resolve_upstream = None

    # ---- 日志 ----
    def log_message(self, fmt, *args):
        sys.stderr.write("[portal] %s - %s\n"
                         % (self.address_string(), fmt % args))
        sys.stderr.flush()

    # ---- 工具 ----
    def _request_class(self):
        return classify_host(self.headers.get("Host", ""))

    def _needs_auth(self, kind):
        return needs_auth(
            kind,
            open_classes=type(self).open_classes,
            open_classes_provider=type(self).open_classes_provider,
            lan_enabled_provider=type(self).lan_enabled_provider,
        )

    def _authorized(self):
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

    def _send(self, status, body, content_type="text/html; charset=utf-8",
              extra_headers=(), no_store=True):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if no_store:
            self.send_header("Cache-Control", "no-store")
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        for key, value in extra_headers:
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_json(self, status, payload):
        self._send(status, json.dumps(payload, ensure_ascii=False, indent=2),
                   content_type="application/json; charset=utf-8")

    def _redirect(self, location, extra_headers=()):
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        for key, value in extra_headers:
            self.send_header(key, value)
        self.end_headers()

    # ---- 特殊路由 ----
    def _health(self):
        self._send_json(200, {"ok": True})

    def _login_page(self, error=None, status=200):
        self._send(status, login_page_html(error=error))

    def _handle_login(self):
        """POST 口令 -> 校验（带限速）-> 下发会话。"""
        ip = client_ip(self)
        limiter = type(self).rate_limiter
        if limiter is not None:
            state = limiter.status(ip)
            if state["locked"]:
                return self._login_page(
                    "尝试次数过多，请 %d 秒后再试。" % state["retryAfter"],
                    status=429)
        body = self._read_body()
        candidate = read_token({"body_bytes": body},
                               self.headers.get("Content-Type", ""))
        if candidate is None:
            return self._login_page("提交格式不正确，请重新输入口令。", status=400)
        if not password_matches(candidate, self.password):
            if limiter is not None:
                limiter.record_failure(ip)
            return self._login_page("口令错误，请重试。", status=401)
        if limiter is not None:
            limiter.clear(ip)
        token = make_session(self.secret, self.session_ttl)
        self._redirect("/", extra_headers=[
            ("Set-Cookie", session_cookie_header(token, self.session_ttl,
                                                 secure=self.cookie_secure)),
        ])

    def _handle_logout(self):
        self._send(200, login_page_html(error="已退出，请重新输入口令。"),
                   extra_headers=[("Set-Cookie", clear_cookie_header())])

    def _console(self):
        kind = self._request_class()
        state = {}
        # 回调都在**类**上，必须绕开描述符绑定（见 _proxy 里的说明）
        get_state = type(self).console_state
        render = type(self).console_page
        if callable(get_state):
            try:
                state = get_state() or {}
            except Exception as exc:            # 控制台渲染失败必须显式暴露
                state = {"error": "读取服务状态失败：%r" % (exc,), "services": []}
        state = dict(state, request_class=kind)
        if callable(render):
            try:
                body = render(state, kind == "public")
            except Exception as exc:
                return self._send(500, "控制台渲染失败：%r" % (exc,),
                                  content_type="text/plain; charset=utf-8")
        else:
            body = b"<html><body>portal</body></html>"
        self._send(200, body)

    # ---- 转发 ----
    def _proxy(self):
        path = self.path.split("?", 1)[0]

        # 1) 健康探针：免认证，永远由门户自己答
        if path == HEALTH_PATH:
            return self._health()

        # 2) 登录/登出：门户自己的路由
        if path == LOGIN_PATH:
            if self.command == "POST":
                return self._handle_login()
            if self._authorized():
                return self._redirect("/")
            return self._login_page()
        if path == LOGOUT_PATH:
            return self._handle_logout()

        kind = self._request_class()

        # 3) 认证先于一切转发：公网必须持有有效会话
        if self._needs_auth(kind) and not self._authorized():
            return self._login_page()

        # 4) 控制台与 API
        if path in ("/", ""):
            return self._console()
        if path == API_PREFIX or path.startswith(API_PREFIX + "/"):
            api = type(self).api_handler
            if not callable(api):
                return self._send_json(404, {"error": "api disabled"})
            body = self._read_body()
            route = path[len(API_PREFIX):] or "/"
            try:
                handled = api(self, self.command, route, body)
            except Exception as exc:
                return self._send_json(500, {"error": repr(exc)})
            if not handled:
                return self._send_json(404, {"error": "unknown api route %s" % route})
            return None

        # 5) 按注册表转发
        # 注意：回调是**类属性**，直接 self.xxx(...) 会被当成绑定方法（Python 会把
        # self 作为第一个参数传进回调）——必须从类型上取，避免这个陷阱。
        resolver = type(self).resolve_upstream
        resolved = resolver(path) if callable(resolver) else None
        if resolved is None:
            # 未注册的路径：明确 404（不拿控制台兜底未知路径）
            return self._send(404, b"404 Not Found\n",
                              content_type="text/plain; charset=utf-8")
        _, host, port, rest = resolved

        query = ""
        if "?" in self.path:
            query = self.path[self.path.index("?"):]
        target = rest + query

        payload = self._read_body() or None
        headers = {}
        for key, value in self.headers.items():
            lower = key.lower()
            if lower in ("host", "cookie", "connection", "accept-encoding",
                         "content-length", "transfer-encoding", "expect",
                         "proxy-authorization", "cf-connecting-ip",
                         "cf-connecting-ipv6", "cf-ipcountry", "cf-ray",
                         "x-forwarded-for", "x-forwarded-proto", "x-real-ip"):
                continue
            headers[key] = value

        import http.client
        conn = http.client.HTTPConnection(host, port,
                                          timeout=self.upstream_timeout)
        try:
            conn.request(self.command, target, body=payload, headers=headers)
            response = conn.getresponse()
            data = response.read()
        except Exception as exc:
            return self._send(
                502, "502 Bad Gateway：上游 %s:%d 不可达 —— %r\n" % (host, port, exc),
                content_type="text/plain; charset=utf-8")
        finally:
            try:
                conn.close()
            except Exception:
                pass

        self.send_response(response.status)
        for key, value in response.getheaders():
            lower = key.lower()
            if lower in ("content-length", "connection", "transfer-encoding"):
                continue
            if lower in ("content-type", "cache-control", "last-modified",
                         "etag", "content-disposition", "pragma", "expires",
                         "location", "set-cookie"):
                self.send_header(key, value)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)
        return None

    do_GET = _proxy
    do_POST = _proxy
    do_HEAD = _proxy
    do_PUT = _proxy
    do_DELETE = _proxy
    do_OPTIONS = _proxy


def make_portal_server(listen_port, config, listen_host="127.0.0.1"):
    """创建门户服务器（listen_port=0 时自动分配端口）。

    ``config`` 是 dict，键与 PortalHandler 的类属性同名：
      password / secret / session_ttl / cookie_secure / open_classes /
      console_state / console_page / api_handler / resolve_upstream /
      rate_limiter / upstream_timeout
    """
    attrs = {
        "password": config.get("password", ""),
        "secret": config.get("secret") or portal_login.gen_secret(),
        "session_ttl": int(config.get("session_ttl", DEFAULT_SESSION_TTL)),
        "cookie_secure": bool(config.get("cookie_secure", True)),
        "open_classes": tuple(config.get("open_classes", ("loopback", "lan"))),
        "open_classes_provider": config.get("open_classes_provider"),
        "lan_enabled_provider": config.get("lan_enabled_provider"),
        "console_state": config.get("console_state"),
        "console_page": config.get("console_page"),
        "api_handler": config.get("api_handler"),
        "resolve_upstream": config.get("resolve_upstream"),
        "rate_limiter": config.get("rate_limiter"),
        "upstream_timeout": float(config.get("upstream_timeout", 60.0)),
    }
    handler = type("BoundPortalHandler", (PortalHandler,), attrs)
    return ThreadingHTTPServer((listen_host, int(listen_port)), handler)
