# -*- coding: utf-8 -*-
"""门户登录取代 Basic Auth：**只验口令**，通过后下发签名会话 cookie。

为什么不用 Basic Auth
---------------------
Basic Auth 会触发浏览器原生的「账号 + 密码」弹框。对外服务门户是给「只拿到一个
口令的人」用的：多一个账号字段既是噪音，也让人以为需要记两样东西。这里改成
应用层登录页 —— 访问者只看到**一个口令输入框**。

安全设计（逐条对应真实攻击面）
------------------------------
1. **口令比较用时序安全比较**（hmac.compare_digest），不吃逐字节短路的时间差；
2. **会话 cookie 是签名值，不是口令本身**：`exp.sig`，sig = HMAC(secret, exp)。
   即使 cookie 泄漏，也拿不到口令，且到期即失效；
3. **secret 每次进程启动随机**（secrets.token_bytes）：重启门户 = 所有会话作废；
4. **HttpOnly + SameSite=Lax + Secure**：JS 读不到；Secure 因为外网入口恒为 https
   （trycloudflare），本机 http 调试时由调用方传 secure=False；
5. **登录失败不区分**「口令错」与其他原因，且失败响应带固定延时兜底（见调用方），
   避免用响应差异做口令探测；
6. **登录表单走 POST**，口令不进 URL（不进 access log、不进 Referer）；
7. 健康探针 `/_auth/health` 免认证（启动脚本靠它判活），其余一律先认证。

不做的事
--------
- 不做「记住我」长期会话：对外入口的会话有效期就是一次使用窗口（默认 12 小时）。
- 不做多用户/权限：门户只有「有口令 / 没口令」两种人。
"""
import base64
import hashlib
import hmac
import json
import secrets
import time
import urllib.parse

# 会话有效期（秒）。到期必须重新输口令。
DEFAULT_SESSION_TTL = 12 * 3600
# 会话 cookie 名。
SESSION_COOKIE = "sp_session"
# 登录相关路径（在挂载前缀之外，认证层自己处理）。
LOGIN_PATH = "/_auth/login"
LOGOUT_PATH = "/_auth/logout"
HEALTH_PATH = "/_auth/health"

MIN_PASSWORD_LEN = 12


def gen_password(nbytes=12):
    """生成随机口令（默认 16 字符 URL-safe）。**公网口令**用这个。"""
    return secrets.token_urlsafe(nbytes)


def gen_lan_password(digits=8):
    """生成随机**局域网口令**：纯数字，便于在手机上输入。

    为什么局域网口令和公网口令用不同规格（对齐 dsh-pocket）：
    · 公网口令要抗爆破，用 16 字符 URL-safe（大小写+数字+符号）；
    · 局域网口令是「同一 WiFi 下手机手输」的场景 —— 手机上切大小写/找符号
      很麻烦，所以用短数字串（默认 8 位）。风险边界不同：能连上你的 WiFi
      本身就已经是一道门槛，且我们的认证层会按 Host 把公网请求与内网分开，
      公网拿这个数字串是进不来的（公网要公网口令）。
    """
    return "".join(secrets.choice("0123456789") for _ in range(digits))


LAN_PIN_MIN = 6
LAN_PIN_MAX = 12


def validate_lan_pin(pin):
    """局域网自定义口令的门槛：6–12 位纯数字。

    比公网宽松是有意的（局域网手输场景），但仍然拒绝空值和字母符号 ——
    不允许把局域网口令设成「1」这种一眼可猜的值。
    """
    text = str(pin or "").strip()
    if not text:
        raise ValueError("局域网口令不能为空")
    if not text.isdigit():
        raise ValueError("局域网口令只能是数字（手机上好输入）")
    if not (LAN_PIN_MIN <= len(text) <= LAN_PIN_MAX):
        raise ValueError("局域网口令需要 %d–%d 位数字（当前 %d 位）"
                         % (LAN_PIN_MIN, LAN_PIN_MAX, len(text)))
    return text


def gen_secret():
    """每次进程启动一个新的会话签名密钥（重启即全体登出）。"""
    return secrets.token_bytes(32)


def validate_password(password):
    """口令门槛。返回 True 或抛 ValueError（调用方决定退出码）。"""
    if not password or not password.strip():
        raise ValueError("拒绝启动：公开入口必须设置非空口令")
    if len(password.strip()) < MIN_PASSWORD_LEN:
        raise ValueError(
            "拒绝启动：口令至少 %d 字符（当前 %d 字符）"
            % (MIN_PASSWORD_LEN, len(password.strip())))
    return True


def validate_public_pin(value):
    """设置页「自定义公网密码」的门槛。返回**洗净后的口令**或抛 ValueError。

    与 validate_password 分开的两个理由：
      1. 那条是**启动路径**用的，报错文案是「拒绝启动：…」——在设置页里点保存
         弹出"拒绝启动"会让用户以为门户要重启；这里必须是设置页的说法。
      2. 这条要**返回口令本身**（调用方要拿去立即生效 + 落盘），而不是 True。

    门槛 = 至少 MIN_PASSWORD_LEN（12）位。
    **不限制字符种类**（纯数字也行）：用户要求"体验和局域网一样"，而局域网就是
    手输数字；拦掉数字只会让他设不成自己想记的密码。公网比局域网更长这一点，
    由长度门槛承担；风险由设置页的警示块明确告知，而不是替用户做绝对化的限制。
    """
    text = str(value or "").strip()
    if not text:
        raise ValueError("公网密码不能为空")
    if len(text) < MIN_PASSWORD_LEN:
        raise ValueError(
            "公网密码至少 %d 位（当前 %d 位）—— 公网面向整个互联网，"
            "比局域网口令（%d–%d 位）要求更长"
            % (MIN_PASSWORD_LEN, len(text), LAN_PIN_MIN, LAN_PIN_MAX))
    return text


def password_matches(candidate, expected):
    """时序安全的口令比较。两边都编码成 bytes 再比，避免类型差异短路。"""
    if not isinstance(candidate, str) or not isinstance(expected, str):
        return False
    if not expected:
        return False
    return hmac.compare_digest(
        candidate.encode("utf-8"), expected.encode("utf-8"))


def make_session(secret, ttl=DEFAULT_SESSION_TTL, now=None):
    """生成会话 cookie 值：``<到期时间戳>.<HMAC 前 32 字节 hex>``。"""
    expires = int((now if now is not None else time.time()) + int(ttl))
    payload = str(expires).encode("ascii")
    sig = hmac.new(secret, payload, hashlib.sha256).hexdigest()[:32]
    return "%d.%s" % (expires, sig)


def session_valid(token, secret, now=None):
    """校验会话 cookie：签名对 **且** 未过期。任一不满足返回 False。"""
    if not token or not isinstance(token, str):
        return False
    head, _, sig = token.partition(".")
    if not head or not sig:
        return False
    try:
        expires = int(head)
    except ValueError:
        return False
    expected = hmac.new(secret, head.encode("ascii"), hashlib.sha256).hexdigest()[:32]
    # 先比签名（时序安全），再看是否过期 —— 过期判断不涉及秘密，先后无泄漏差异。
    if not hmac.compare_digest(sig, expected):
        return False
    return expires > int(now if now is not None else time.time())


def parse_cookies(header):
    """把 Cookie 头解析成 dict（容错：坏片段直接跳过，不影响其余）。"""
    out = {}
    for chunk in (header or "").split(";"):
        name, _, value = chunk.partition("=")
        name = name.strip()
        if not name:
            continue
        out[name] = value.strip()
    return out


def read_session_cookie(cookie_header):
    return parse_cookies(cookie_header).get(SESSION_COOKIE, "")


def session_cookie_header(token, ttl=DEFAULT_SESSION_TTL, secure=True):
    """构造 Set-Cookie 头。secure=False 仅用于本机 http 调试。"""
    parts = [
        "%s=%s" % (SESSION_COOKIE, token),
        "Path=/",
        "HttpOnly",
        "SameSite=Lax",
        "Max-Age=%d" % int(ttl),
    ]
    if secure:
        parts.append("Secure")
    return "; ".join(parts)


def clear_cookie_header():
    return ("%s=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"
            % SESSION_COOKIE)


def read_token(headers, content_type=""):
    """从请求里取出待校验口令。

    支持两种提交方式：
      · ``application/x-www-form-urlencoded`` 表单（登录页默认，口令不进 URL）；
      · ``application/json``（脚本/curl 用）。
    其它 content-type 一律返回 None（不猜、不猜错）。
    """
    kind = (content_type or "").split(";")[0].strip().lower()
    body = headers.get("body_bytes") or b""
    if not body:
        return None
    try:
        text = body.decode("utf-8", "strict")
    except UnicodeDecodeError:
        return None
    if kind == "application/x-www-form-urlencoded":
        parsed = urllib.parse.parse_qs(text, keep_blank_values=False)
        values = parsed.get("password") or []
        return values[0] if values else None
    if kind == "application/json":
        try:
            data = json.loads(text)
        except ValueError:
            return None
        if isinstance(data, dict):
            value = data.get("password")
            return value if isinstance(value, str) else None
        return None
    return None


def _escape(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def login_page_html(error=None, next_url="/", title="对外服务门户"):
    """只含一个口令输入框的登录页（无账号字段）。"""
    error_html = ""
    if error:
        error_html = '<p class="err">%s</p>' % _escape(error)
    return ("""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>%s</title><style>
:root{color-scheme:dark light}
body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
font-family:system-ui,-apple-system,"Segoe UI",sans-serif;background:#14161a;color:#e8eaed}
form{background:#1c1f26;padding:32px 28px;border-radius:16px;width:min(92vw,340px);
box-shadow:0 12px 40px rgba(0,0,0,.45);border:1px solid #2a2f38}
h1{font-size:17px;margin:0 0 6px}
p.hint{font-size:12.5px;color:#98a0ad;margin:0 0 20px;line-height:1.5}
label{display:block;font-size:12.5px;color:#b6bdc9;margin-bottom:7px}
input{width:100%%;box-sizing:border-box;padding:11px 13px;border-radius:9px;
border:1px solid #363c47;background:#12141a;color:#e8eaed;font-size:15px;
font-family:ui-monospace,Menlo,monospace;letter-spacing:.4px}
input:focus{outline:none;border-color:#4f6ef7;box-shadow:0 0 0 3px rgba(79,110,247,.22)}
button{width:100%%;margin-top:16px;padding:11px;border:none;border-radius:9px;
background:#4f6ef7;color:#fff;font-size:14px;font-weight:600;cursor:pointer}
button:hover{background:#5c79f8}
p.err{margin:0 0 14px;padding:9px 11px;border-radius:8px;font-size:12.5px;
background:rgba(220,38,38,.12);color:#f87171;border:1px solid rgba(220,38,38,.3)}
</style></head><body><form method="POST" action="%s" autocomplete="off">
<h1>%s</h1>
<p class="hint">请输入访问口令。口令由门户持有者提供，不是你的账号密码。</p>
%s
<label for="pw">口令</label>
<input id="pw" name="password" type="password" autocomplete="current-password"
 autofocus required spellcheck="false">
<button type="submit">进入</button>
</form></body></html>""" % (_escape(title), _escape(LOGIN_PATH),
                            _escape(title), error_html)).encode("utf-8")


def unauthorized_html(message="口令错误，请重试。"):
    """登录失败的响应体（用登录页本身，带错误提示）。"""
    return login_page_html(error=message)
