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
import http.server
import ipaddress
import json
import os
import re
import socket
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
    lan_disabled_html,
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


def is_lan_override_host(host_header, override):
    """这个 Host 是不是用户**手动指定**的局域网地址？

    为什么必须有这一条（dsh-pocket issue #79 的同一个坑）：
    用户在「高级·手动选地址」里可以挑任意本机网卡地址，而有些 overlay 网段
    （Radmin VPN 的 26.x、部分 Tailscale 段）**不在 RFC1918 里** ——
    classify_host() 会把它们判成 `public`，于是：
      · 用户从那个地址访问自己的门户，被要求输**公网**口令；
      · 而他看到界面上写的是「局域网地址」，去输局域网口令 —— 永远「口令错误」。
    所以：**只要 Host 等于用户手动选的地址，就按局域网裁决**（优先级高于
    classify_host）。用户已经明确说了「这是我的局域网地址」，那就以他为准。

    只比主机名（忽略端口）与大小写；override 为空表示自动，不做覆盖。
    """
    want = str(override or "").strip().lower()
    if not want:
        return False
    host = str(host_header or "").strip().lower()
    if not host:
        return False
    # 去掉端口（IPv6 的 [::1]:8899 也照顾到）
    if host.startswith("["):
        name = host[1:host.find("]")] if "]" in host else host
    elif ":" in host:
        name = host.rsplit(":", 1)[0]
    else:
        name = host
    return name == want


def lan_blocked(kind, lan_enabled_provider=None):
    """这个来源是否被「局域网访问总开关」**直接拒绝**（而不是降级成要口令）。

    为什么是拒绝而不是降级（对齐 dsh-pocket 的 issue #54 做法）：
    早先关掉开关只是让内网请求「按公网对待」—— 于是用户看到的是一个**登录页**，
    而不是「已关闭」。三处后果：
      · 界面上写「手机扫码 / 链接均不可用」，实际却是「输对口令还能进」，
        文案与实现不一致，且用户永远不知道该输哪个口令；
      · 用户关它的意图是「不想让同一 WiFi 的人看到我的控制台」，降级并没有
        满足这个意图，只是加了一道他可能并不知道口令的墙；
      · 无法区分「内网被别人连上」和「内网被自己关掉」这两种完全不同的状况。

    所以这里改成硬拒绝：返回 True 就回 403，不走认证、不给登录页。
    loopback（本机 / cloudflared 回连）**永不**被这条拦住 —— 否则用户在电脑上
    连自己的门户都进不去，公网也会被一起掐死。
    """
    if kind != "lan":
        return False
    return not lan_access_enabled(lan_enabled_provider)


def needs_auth(kind, open_classes=("loopback", "lan"),
               open_classes_provider=None, lan_enabled_provider=None):
    """该来源是否需要口令（认证层的唯一判定入口，纯函数便于控制检验直接测）。

    kind: classify_host() 的分类结果（loopback / lan / public）

    注意：内网被总开关关掉时，请求在 `lan_blocked()` 那一步就拿 403 走了，
    根本到不了这里。这里的 lan_enabled 判断保留为**纵深防御**：万一将来有人
    新增一条绕过 403 的路径，至少还会退回到「要口令」，而不是静默放行。
    """
    # 局域网总开关关掉时，内网按公网对待（同样要口令）。
    if lan_blocked(kind, lan_enabled_provider):
        return True
    return kind not in resolve_open_classes(open_classes, open_classes_provider)


def resolve_request_kind(host_header, lan_ip_override=None):
    """请求的最终分类 —— 手动指定的局域网地址**优先**于按网段判定。

    这是 classify_host() 外面的一层：用户手动选了地址，就按局域网处理
    （见 is_lan_override_host 的说明）。没选就完全按 classify_host。
    """
    if is_lan_override_host(host_header, lan_ip_override):
        return "lan"
    return classify_host(host_header)


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
    # 局域网口令（内网访问用）。与公网 password 分开：内网口令短好输，
    # 公网口令长抗爆破。为空表示内网免密（不需要口令）。
    lan_password = ""
    # 动态 provider（可选）：设置页刷新/自定义内网口令后要立即生效，不重启门户。
    lan_password_provider = None
    # 公网口令的动态 provider（可选）：设置页「自定义公网密码」后要**立即生效**，
    # 不重启门户 —— 重启门户会换掉 trycloudflare 域名，代价太大（用户刚把地址
    # 发出去就失效了）。与 lan_password_provider 同一套机制，对称。
    password_provider = None
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
    # 用户手动选定的局域网地址（可选 provider）：命中这个 Host 就按局域网裁决，
    # 不管它的网段是否落在 RFC1918 里（Radmin 26.x / Tailscale 等 overlay）。
    lan_ip_override_provider = None
    upstream_timeout = 60.0
    # 回调：() -> dict(控制台 state)；以及 API 处理器
    console_state = None        # callable() -> dict
    console_page = None         # callable(state, is_public) -> bytes
    api_handler = None          # callable(handler, method, route, body) -> bool(已处理)
    rate_limiter = None         # RateLimiter
    # 上游查表：callable(path) -> (mount, host, port, rest_path) 或 None
    resolve_upstream = None
    # 响应体里「根绝对路径」的改写开关（见 _rewrite_root_absolute）
    rewrite_root_absolute = True

    # ---- 日志 ----
    def log_message(self, fmt, *args):
        sys.stderr.write("[portal] %s - %s\n"
                         % (self.address_string(), fmt % args))
        sys.stderr.flush()

    # ---- 工具 ----
    def _lan_password(self):
        """当前局域网口令（优先取动态 provider —— 设置页刷新/自定义后立即生效）。"""
        provider = type(self).lan_password_provider
        if callable(provider):
            try:
                return str(provider() or "")
            except Exception:
                return ""
        return type(self).lan_password

    def _password(self):
        """当前公网口令（优先取动态 provider —— 设置页自定义后**立即生效**）。

        为什么需要动态：自定义公网密码若要重启门户才生效，就会换掉隧道域名。
        用户场景恰恰是"把地址发出去了，再改个记得住的密码"，重启等于把地址废掉。
        """
        provider = type(self).password_provider
        if callable(provider):
            try:
                return str(provider() or "")
            except Exception:
                return ""
        return type(self).password

    def _request_class(self):
        # 用户手动指定的局域网地址优先（见 resolve_request_kind 的说明）：
        # 他明确选了这个地址，就按局域网裁决，不看网段。
        provider = type(self).lan_ip_override_provider
        override = ""
        if callable(provider):
            try:
                override = str(provider() or "")
            except Exception:
                override = ""
        return resolve_request_kind(self.headers.get("Host", ""), override)

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

    def _lan_disabled(self):
        """局域网访问被关掉：HTML 请求给说明页，其它请求给机器可读的 JSON。

        判断顺序（不能只看 Accept）：
          1. `/_api/*` 一律给 JSON —— 那是程序调用；给它 HTML 只会让调用方
             解析失败，然后把"已关闭"误当成"网络故障"去重试；
          2. Accept 含 text/html -> 说明页（手机浏览器要看到**人话**）；
          3. 其余一律 JSON —— 包括**根本不发 Accept** 的 urllib / curl / 脚本。
             原先「没有 Accept 就按 HTML」是错的：最可能不带 Accept 的恰恰是程序。
        """
        path = self.path.split("?", 1)[0]
        accept = (self.headers.get("Accept") or "").lower()
        wants_html = ("text/html" in accept) and not path.startswith(API_PREFIX)
        if wants_html:
            return self._send(403, lan_disabled_html(),
                              extra_headers=(("X-Portal-Lan", "disabled"),))
        return self._send(403, json.dumps(
            {"error": "lan-disabled",
             "detail": "局域网访问已关闭：请在电脑上打开「局域网访问」开关"},
            ensure_ascii=False),
            content_type="application/json; charset=utf-8",
            extra_headers=(("X-Portal-Lan", "disabled"),))

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
        """POST 口令 -> 校验（带限速）-> 下发会话。

        **两套口令分开校验**（对齐 dsh-pocket 的 lanToken / accessToken 分离）：
          · 内网（loopback/lan）：用**局域网口令**；
          · 公网（public）：用**公网口令**。
        为什么不共用一个：公网口令是抗爆破用的 16 字符随机串，让手机在同一 WiFi
        下每次手输那一长串没法用；而局域网口令短、好输，但绝不能拿去当公网凭据。
        早先只有一个 self.password，内网与公网同口令 —— 既不好用（手机输长串），
        也不该（局域网用户知道了等于知道公网口令）。
        """
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

        # 按请求来源选该比对哪个口令。注意这里用的是**已解析出的分类**
        # （含手动选地址的覆盖），与后面放行判定用的是同一套，不会出现
        # 「放行看内网、验口令看公网」这种自相矛盾。
        kind = self._request_class()
        lan_pin = self._lan_password()
        if kind in ("loopback", "lan") and lan_pin:
            expected = lan_pin
            expected_label = "局域网口令"
        else:
            expected = self._password()
            expected_label = "口令"

        if not expected or not password_matches(candidate, expected):
            if limiter is not None:
                limiter.record_failure(ip)
            return self._login_page("口令错误，请重试（%s）。" % expected_label,
                                    status=401)
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
    # ---- WebSocket 透传 ----

    # ---- 响应改写：根绝对路径 → 带 mount 前缀 ----

    # 需要改写 body 的内容类型（HTML/CSS 是引用资源的两种载体）。
    # JS 不改：打包后的 JS 里通常是相对 import 与运行时拼的字符串，正则改写
    # 风险大于收益；实测的那类白屏问题也都出在 index.html 的 /assets/ 引用上。
    _REWRITE_TYPES = ("text/html", "application/xhtml+xml", "text/css")

    # 只改这些属性/函数里以单个 / 开头、且**不**以 // 开头的路径。
    # 排除 // 是为了不误伤协议相对 URL（//cdn.example.com/x.js）。
    # 注意 `(?P<path>` 从斜杠**之后**开始：前缀要插在斜杠前，不是插在它后面
    # （第一版写成属性里已含斜杠、再拼 prefix+raw，得到 /solverassets/... 这种坏路径）。
    _ROOT_ABS_RE = re.compile(
        r'(?P<attr>\b(?:src|href)\s*=\s*["\'])/(?![/\\])(?P<path>[^"\']*)'
        r'|url\(\s*(?P<q>["\']?)/(?![/\\])(?P<csspath>[^"\')\s]*)(?P=q)(?P<close>\s*\))',
        re.IGNORECASE)

    def _should_rewrite(self, mount, content_type, body):
        """这次响应要不要做根绝对路径改写？

        只在**有 mount 前缀**时才有意义：挂在 /solver 下的站点，其 /assets/x.js
        经门户访问会变成门户根的 /assets/x.js（那里没有），必须补成
        /solver/assets/x.js。而门户根下的服务本就用不到这层改写。
        """
        if not type(self).rewrite_root_absolute:
            return False
        if not mount or mount == "/":
            return False
        if not body:
            return False
        ctype = (content_type or "").lower()
        return any(t in ctype for t in self._REWRITE_TYPES)

    @staticmethod
    def _already_prefixed(raw, prefix):
        """这个路径是否已经在 mount 里面（避免重复加前缀）。

        raw 是**斜杠之后**的那段，所以已经带前缀的 /solver/ok 在 raw 里是
        "solver/ok" —— 判断要拿它跟去掉前导斜杠的 prefix 比。
        """
        p = prefix.lstrip("/")
        return raw == p or raw.startswith(p + "/")

    def _rewrite_root_absolute(self, mount, content_type, body):
        """把响应体里的根绝对引用补上 mount 前缀。

        为什么必须由门户来做（而不是让用户去改上游网站）：
        反向代理本来就该吞掉这类差异 —— nginx 的 `sub_filter` 就是干这个的。
        要求用户改自己网站的 vite `base`，等于把代理的职责推给被代理方，
        而且第三方/打包好的站点根本改不了。

        只改"引用位置"（src / href / url()），不做全文替换：
        全文替换会把 JS 字符串里的 "/api/x" 也改掉，那是数据不是引用，
        改了就变成另一种坏法。
        """
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError:
            return body                     # 非 UTF-8：不动，原样返回
        if not text:
            return body
        prefix = mount.rstrip("/")

        def repl(match):
            attr = match.group("attr")
            if attr is not None:
                raw = match.group("path")
                if raw is None:
                    return match.group(0)
                if self._already_prefixed(raw, prefix):
                    return match.group(0)   # 已在 mount 内，不重复加
                # attr 已含 `src="` 这类前缀（**不含**斜杠），补 `prefix/` 即可
                return attr + prefix + "/" + raw
            raw = match.group("csspath")
            if raw is None:
                return match.group(0)
            if self._already_prefixed(raw, prefix):
                return match.group(0)
            quote = match.group("q") or ""
            close = match.group("close") or ")"
            return "url(%s%s/%s%s%s" % (quote, prefix, raw, quote, close)

        new_text = self._ROOT_ABS_RE.sub(repl, text)
        if new_text == text:
            return body
        return new_text.encode("utf-8")

    def _is_websocket_upgrade(self):
        """是不是 WebSocket 握手（Upgrade: websocket 且 Connection 含 upgrade）。"""
        if self.command not in ("GET", "POST"):
            return False
        if (self.headers.get("Upgrade") or "").strip().lower() != "websocket":
            return False
        connection = (self.headers.get("Connection") or "").lower()
        return "upgrade" in connection

    def _tunnel_websocket(self, host, port, target, headers):
        """把 WebSocket 升级请求转到上游，握手成功后做**双向字节透传**。

        只搬字节、不解析帧：门户不需要理解 WebSocket 协议内容（也不该理解 ——
        解析就得跟着协议版本变），保持成一根哑管道最稳。

        这一段的正确性关键（每一条都是踩出来的）：
          · 必须把客户端原始的 `Upgrade` / `Connection: Upgrade` / `Sec-WebSocket-*`
            原样送去，否则上游不认这次握手；
          · **Host 要改写成上游的**（127.0.0.1:port），因为上游多半按 Host 做校验；
          · 上游的 101 响应（含 Sec-WebSocket-Accept）必须原样回给客户端 ——
            少一个头浏览器就断连，且现象是"静默不工作"；
          · 握手之后**不能再走 HTTP 解析**，两边剩下的字节全都要双向搬。
        """
        import socket as socket_module

        upstream_headers = dict(headers)
        # 透传升级相关头（上面统一过滤里去掉的，这里补回来）
        for key in ("Upgrade", "Connection", "Sec-WebSocket-Key",
                    "Sec-WebSocket-Version", "Sec-WebSocket-Protocol",
                    "Sec-WebSocket-Extensions", "Origin"):
            value = self.headers.get(key)
            if value:
                upstream_headers[key] = value
        upstream_headers["Host"] = "%s:%d" % (host, port)

        # 1) 自己连上上游并发出握手请求（用裸 socket，便于之后接管双向搬运）
        try:
            upstream = socket_module.create_connection(
                (host, port), timeout=self.upstream_timeout)
        except OSError as exc:
            return self._send(
                502, "502 Bad Gateway：上游 %s:%d 不可达 —— %r\n" % (host, port, exc),
                content_type="text/plain; charset=utf-8")

        try:
            request_lines = ["%s %s HTTP/1.1" % (self.command, target)]
            for key, value in upstream_headers.items():
                request_lines.append("%s: %s" % (key, value))
            request_lines.append("")
            request_lines.append("")
            upstream.sendall("\r\n".join(request_lines).encode("latin-1"))

            # 2) 读上游的响应头（要点：**必须**原样回给客户端，
            #    包括 101 的 Sec-WebSocket-Accept）
            head = b""
            upstream.settimeout(self.upstream_timeout)
            while b"\r\n\r\n" not in head:
                chunk = upstream.recv(4096)
                if not chunk:
                    break
                head += chunk
                if len(head) > 65536:      # 头异常大：不给它无限吃内存
                    break
            if b"\r\n\r\n" not in head:
                return self._send(
                    502, "502 Bad Gateway：上游对 WebSocket 握手没有完整响应\n",
                    content_type="text/plain; charset=utf-8")
            header_part, _, leftover = head.partition(b"\r\n\r\n")
            # 原样回写（含状态行与全部响应头）
            self.connection.sendall(header_part + b"\r\n\r\n")

            status_line = header_part.split(b"\r\n", 1)[0].decode("latin-1", "replace")
            if "101" not in status_line:
                # 上游没同意升级：把剩余响应体也给它，然后结束（不假装成功）
                if leftover:
                    self.connection.sendall(leftover)
                return None

            # 3) 双向透传：两个方向各起一个线程，把剩下所有字节搬运过去
            self.close_connection = True
            self._relay_both_ways(upstream, leftover)
            return None
        except Exception as exc:
            try:
                self._send(502, "502 Bad Gateway：WebSocket 透传失败 —— %r\n" % (exc,),
                           content_type="text/plain; charset=utf-8")
            except Exception:
                pass
            return None
        finally:
            try:
                upstream.close()
            except Exception:
                pass

    def _relay_both_ways(self, upstream, initial):
        """双向字节搬运，直到任一侧关闭。

        用线程而非 select：Windows 上 select 对 socket 数量有限制且语义不同，
        而这里只有两根管子，线程最直接。任何一侧出错/关闭都要**两边都收摊**，
        否则会留下半开连接（手机上表现为"一直转圈"）。
        """
        import socket as socket_module
        import threading

        client_sock = self.connection
        stop = threading.Event()
        timeout_error = socket_module.timeout

        def copy(src, dst, first=None):
            try:
                if first:
                    dst.sendall(first)
                while not stop.is_set():
                    src.settimeout(1.0)
                    try:
                        data = src.recv(16384)
                    except timeout_error:
                        continue          # 只是没数据，不是断开
                    except OSError:
                        break
                    if not data:
                        break             # 对端关闭
                    dst.sendall(data)
            except Exception:
                pass
            finally:
                stop.set()

        up_thread = threading.Thread(target=copy, args=(upstream, client_sock),
                                     daemon=True)
        down_thread = threading.Thread(target=copy, args=(client_sock, upstream),
                                       daemon=True)
        up_thread.start()
        down_thread.start()
        up_thread.join()
        down_thread.join()

    # ---- HTTP 转发 ----

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

        # 3) 局域网总开关关掉 -> **直接 403**，不给登录页、不转发任何东西。
        #    必须排在认证之前：否则用户看到的是登录页，误以为口令错了。
        #    WebSocket 在 _tunnel_websocket 里另有一道同样的判定（见那里）。
        if lan_blocked(kind, type(self).lan_enabled_provider):
            return self._lan_disabled()

        # 3b) 认证先于一切转发：公网必须持有有效会话
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
        # mount 必须留住：响应改写要用它补前缀（_should_rewrite / _rewrite_root_absolute）
        mount, host, port, rest = resolved

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

        # ---- WebSocket 升级：转成裸 TCP 双向透传 ----
        #
        # 为什么必须支持：本机服务里有相当一部分靠 WebSocket 工作 ——
        # Jupyter 的 kernel 通道、训练看板的实时曲线、日志流式推送等。
        # 早先的实现只走 http.client「一问一答」，遇上 Upgrade 请求会：
        #   · Connection 头被过滤掉 → 上游看不到升级意图 → 握手失败；
        #   · 即便握手成功，也没有双向管道把帧搬来搬去。
        # 用户看到的现象是「页面能打开，但实时数据不刷新 / 终端连不上」。
        if self._is_websocket_upgrade():
            return self._tunnel_websocket(host, port, target, headers)

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

        # 取上游的 content-type：改写判定要用它，且必须在发头之前算好。
        upstream_ctype = response.getheader("Content-Type") or ""
        rewritten = False
        if self._should_rewrite(mount, upstream_ctype, data):
            new_data = self._rewrite_root_absolute(mount, upstream_ctype, data)
            if new_data is not data:
                data = new_data
                rewritten = True

        self.send_response(response.status)
        for key, value in response.getheaders():
            lower = key.lower()
            if lower in ("content-length", "connection", "transfer-encoding"):
                continue
            # 改写过的响应体里，原 ETag / Last-Modified 对应的是**未改写**的内容。
            # 留着它们会让浏览器 304 复用旧版（仍指向 /assets/...），症状是
            # 「代理明明改对了，用户刷新还是白屏」——必须一并丢掉。
            if rewritten and lower in ("etag", "last-modified", "content-md5"):
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


def _make_server_class():
    """门户服务器类：**独占绑定**（Windows 上必须这样）。

    为什么不用默认的 `allow_reuse_address = 1`：
    在 Windows 上 `SO_REUSEADDR` 的语义是「允许**重复**绑定同一端口」，
    所以端口被别的进程占着时，我们的绑定**照样成功**，然后流量被内核随机分到
    两个进程之一 —— 表现为「有时能访问、有时打不开」，极难排查。
    改用 `SO_EXCLUSIVEADDRUSE`：端口被占就直接抛错，交由启动器换端口。
    """
    import socketserver

    class _PortalServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True
        # Windows 上用 SO_EXCLUSIVEADDRUSE 独占；其他平台沿用 SO_REUSEADDR
        # （Linux 上它的语义是「快速重用 TIME_WAIT」，不会重复绑定）。
        allow_reuse_address = os.name != "nt"
        if os.name == "nt":
            allow_reuse_port = False

        def server_bind(self):
            if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                self.socket.setsockopt(socket.SOL_SOCKET,
                                       socket.SO_EXCLUSIVEADDRUSE, 1)
            # 直接调父类的父类，避开 HTTPServer 里对 allow_reuse_address 的处理
            socketserver.TCPServer.server_bind(self)
            host, port = self.server_address[:2]
            self.server_name = host
            self.server_port = port

    return _PortalServer


def make_portal_server(listen_port, config, listen_host="0.0.0.0"):
    """创建门户服务器（listen_port=0 时自动分配端口）。

    ``listen_host`` 默认 **0.0.0.0**（全部网卡）—— 门户要能被同一 WiFi 下的
    手机访问，只绑 127.0.0.1 的话手机永远连不上（扫码后就是「打不开」）。
    认证层按 Host 分类做豁免，所以暴露到局域网是安全的：loopback/lan 免密、
    public（公网/自建域名）必须口令。

    ``config`` 是 dict，键与 PortalHandler 的类属性同名：
      password / secret / session_ttl / cookie_secure / open_classes /
      console_state / console_page / api_handler / resolve_upstream /
      rate_limiter / upstream_timeout
    """
    attrs = {
        "password": config.get("password", ""),
        "password_provider": config.get("password_provider"),
        "lan_password": config.get("lan_password", ""),
        "lan_password_provider": config.get("lan_password_provider"),
        "secret": config.get("secret") or portal_login.gen_secret(),
        "session_ttl": int(config.get("session_ttl", DEFAULT_SESSION_TTL)),
        "cookie_secure": bool(config.get("cookie_secure", True)),
        "open_classes": tuple(config.get("open_classes", ("loopback", "lan"))),
        "open_classes_provider": config.get("open_classes_provider"),
        "lan_enabled_provider": config.get("lan_enabled_provider"),
        "lan_ip_override_provider": config.get("lan_ip_override_provider"),
        "console_state": config.get("console_state"),
        "console_page": config.get("console_page"),
        "api_handler": config.get("api_handler"),
        "resolve_upstream": config.get("resolve_upstream"),
        "rate_limiter": config.get("rate_limiter"),
        "upstream_timeout": float(config.get("upstream_timeout", 60.0)),
        # 默认开启：挂在 /xxx 下的站点常把资源写成根绝对路径（/assets/...），
        # 经门户会被打到门户根而 404。这个开关把响应体里的这类引用补上前缀。
        "rewrite_root_absolute": bool(config.get("rewrite_root_absolute", True)),
    }
    handler = type("BoundPortalHandler", (PortalHandler,), attrs)
    return _make_server_class()((listen_host, int(listen_port)), handler)
