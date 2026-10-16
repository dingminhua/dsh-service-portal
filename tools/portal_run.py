# -*- coding: utf-8 -*-
"""门户启动器：一个进程同时提供 **内网 + 外网** 两种访问，并自带控制台。

与 tools/start_public_gui.py 的区别
-----------------------------------
start_public_gui.py 是「先写死服务清单 -> 拉起 -> 建隧道」，改服务要改文件重启。
本启动器改成**控制台驱动**：

  · 服务注册表（runs/portal_registry.json）—— 运行时可增删改，不用重启；
  · 门户进程（portal_proxy）—— 同时监听内网与隧道回连，按 Host 分类认证；
  · 控制台页 —— 在浏览器里管理服务、开关、点链接访问；
  · 内网地址自动探测（所有网卡的私网 IP）；
  · 外网走 cloudflared 隧道（复用本机已有的 cloudflared.exe）。

架构
----
    cloudflared ──┐
                  ├──▶ 127.0.0.1:<portal_port>  门户（分类认证 + 控制台 + 路由）
    内网设备 ──────┘        │
                           └──▶ 各服务上游（注册表里的 target）

用法
----
    python -X utf8 tools/portal_run.py                 # 起门户 + 隧道
    python -X utf8 tools/portal_run.py --lan-only      # 只开内网（不建隧道）
    python -X utf8 tools/portal_run.py --status        # 看状态
    python -X utf8 tools/portal_run.py --stop          # 停
    python -X utf8 tools/portal_run.py --port 8899     # 指定门户端口
"""
import argparse
import json
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

ROOT = os.path.dirname(HERE)
# 状态目录可以用 PORTAL_RUNS_DIR 顶掉。给测试用的：检验脚本会起临时门户，
# 不隔离的话它们会把用户真实的 portal_state.json / portal_registry.json
# （里面有局域网口令、以及用户在控制台添加的服务）覆盖掉。
RUNS_DIR = os.environ.get("PORTAL_RUNS_DIR") or os.path.join(ROOT, "runs")
LOG_DIR = os.path.join(RUNS_DIR, "portal_logs")
STATE_FILE = os.path.join(RUNS_DIR, "portal_state.json")
REGISTRY_FILE = os.path.join(RUNS_DIR, "portal_registry.json")
PASSWORD_FILE = os.path.join(RUNS_DIR, "portal_password.txt")
# 局域网口令的副本（与公网口令分开；内网短口令好输，公网长口令抗爆破）
LAN_PASSWORD_FILE = os.path.join(RUNS_DIR, "portal_lan_password.txt")
HEALTH_PATH = "/_auth/health"

DEFAULT_PORTAL_PORT = 8899
TUNNEL_LOG = "cloudflared.log"
DEFAULT_HOST_REPO = os.environ.get("SERVICE_HOST_REPO", r"D:\DshProject\ld-rl-poker")
DEFAULT_CLOUDFLARED = os.path.join(
    os.path.expanduser("~"), ".dsh", "dsh-pocket", "bin", "cloudflared.exe")


def _log_path(name):
    os.makedirs(LOG_DIR, exist_ok=True)
    return os.path.join(LOG_DIR, name)


def read_url(log_name, timeout=75.0, since=0):
    """从 cloudflared 日志里读本次新出现的 trycloudflare 域名。

    只读 `since` 之后的**新增**内容，并且取**最后**一个匹配 —— 否则会拿到
    上一次运行残留的旧域名（外网打开 530，而本地一切正常，极难排查）。
    """
    import re
    pattern = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
    path = _log_path(log_name)
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                handle.seek(since)
                text = handle.read()
        except OSError:
            text = ""
        found = pattern.findall(text)
        if found:
            return found[-1]
        time.sleep(0.4)
    return None


def port_listening(port, host="127.0.0.1"):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.6)
        return sock.connect_ex((host, port)) == 0


def http_ok(url, timeout=4.0):
    import urllib.error
    import urllib.request
    try:
        with urllib.request.urlopen(url, timeout=timeout) as res:
            return res.status
    except urllib.error.HTTPError as err:
        return err.code
    except Exception:
        return None


def detect_lan_ips():
    """内网地址列表（**按评分从高到低**，第一个最推荐扫码）。

    评分逻辑见 tools/lan_address.py：物理网卡加分、VPN/虚拟网卡减分。
    老实现是「取第一个非回环私网地址」，在多网卡机器上会拿到 Radmin VPN 的
    198.18.0.1（手机连不上）—— 用户看到的现象就是「扫码打不开」。
    """
    import lan_address
    return lan_address.detect_lan_ips()


def lan_candidates_detailed():
    """候选明细（设置页「高级·手动选地址」用它显示网卡名）。"""
    import lan_address
    return lan_address.detect_lan_candidates()


def lan_urls_for(port, override=None):
    """内网访问地址列表。override 指定时**只有它**（用户手动锁定的地址）。

    返回 (urls, note)：note 说明覆盖是否生效（IP 不在本机时给出提示，
    不静默忽略 —— 否则用户以为选了却没生效）。
    """
    candidates = detect_lan_ips()
    if override:
        if override in candidates:
            return ["http://%s:%d" % (override, port)], None
        # 用户选的地址当前不在本机网卡上：仍按他的选择生成，但明确提示
        return (["http://%s:%d" % (override, port)],
                "选定的地址 %s 不在当前网卡列表里，请检查是否已插网线/连 WiFi"
                % override)
    if not candidates:
        return [], None
    return ["http://%s:%d" % (ip, port) for ip in candidates], None


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def _raw_prefs():
    """状态文件里现存的偏好字段（原样读，不经过任何加工）。

    用途见 save_state：写入前拿它补空，避免"这一轮拿不到的字段"把
    "上一轮已经知道的"覆盖成空 —— 那会让设置页在启动的一小段窗口里
    显示成"运行中、但没有内网地址"，看起来就是二维码和地址一起消失。
    """
    raw = load_state() or {}
    return {key: raw[key] for key in KEEP_ON_STOP if key in raw}


def save_state(state):
    """原子写状态文件。

    **临时文件名必须唯一**（带 pid）：早期用固定的 `portal_state.json.tmp`，
    两个门户进程同时启动时（DSH 的 autoStart 与设置页按钮并发，或用户手点两次）
    会同时写同一个临时文件 —— Windows 上后开的那个直接
    `PermissionError [Errno 13]`，门户起不来，而日志里只有一堆栈帧。
    这是实际踩到的 bug：表现为「点开启没反应 / 报 502」。

    仍然保留重试：杀毒软件/索引器会在文件刚创建时短暂占用，重试即可穿过。
    """
    os.makedirs(RUNS_DIR, exist_ok=True)
    # 拿不到值的偏好字段，用上一轮已经知道的顶上。
    # 实测场景：门户刚起来那几秒，网卡探测还没跑完，这一轮写进去的
    # lan_candidates 是空的 —— 设置页于是"运行中但没有内网地址"（二维码和
    # 地址整块不见）。偏好本来就不会因为一次探测失败而作废，补上更诚实。
    kept = _raw_prefs()
    merged = dict(state)
    for key, value in kept.items():
        if merged.get(key) in (None, "", [], {}):
            merged[key] = value
    state = merged
    # 唯一临时名：pid + 线程 id（同一进程内也可能并发调用）
    unique = "%s.%d.%d.tmp" % (STATE_FILE, os.getpid(),
                               threading.get_ident())
    last_error = None
    for attempt in range(5):
        try:
            with open(unique, "w", encoding="utf-8") as handle:
                json.dump(state, handle, ensure_ascii=False, indent=2)
            os.replace(unique, STATE_FILE)
            return True
        except OSError as exc:
            last_error = exc
            try:
                os.remove(unique)
            except OSError:
                pass
            time.sleep(0.1 * (attempt + 1))
    # 原子路径失败就退一步**原地覆盖**。实测：DSH 宿主派生出来的子进程
    # 在 runs/ 下**新建**文件会被拒（Errno 13），但改写已有文件可以。
    # 原地写没有原子性（理论上可能留半截），但比"一个字都没写进去、
    # 局域网口令和停止标记全丢"要好；降级会明确报到 stderr，不静默。
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2)
        print("提示：状态文件降级为原地写入（原子替换被拒：%s）" % (last_error,),
              file=sys.stderr)
        return True
    except OSError as exc:
        print("提示：状态文件写不进去（%s）：%s" % (STATE_FILE, last_error),
              file=sys.stderr)
        print("提示：原地写入也失败：%s" % (exc,), file=sys.stderr)
        return False


def clear_state():
    try:
        os.remove(STATE_FILE)
    except OSError:
        pass
    # 顺手清理可能残留的临时文件（崩溃留下的）
    try:
        for name in os.listdir(RUNS_DIR):
            if name.startswith(os.path.basename(STATE_FILE)) and name.endswith(".tmp"):
                try:
                    os.remove(os.path.join(RUNS_DIR, name))
                except OSError:
                    pass
    except OSError:
        pass


def read_password():
    try:
        with open(PASSWORD_FILE, "r", encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def _write_secret_file(path, value):
    """把一段凭据原子写进文件，带重试；失败不阻断（返回 True/False）。

    这个文件只是「给人看的副本」——真正的凭据在 runs/portal_state.json 里。
    所以它写失败**不该让门户起不来**（早期版本直接抛 traceback 或退出码 4，
    结果用户看到「启动失败」却不知道为什么，而门户其实完全能跑）。

    写失败最常见的原因（Windows）：
      · 杀毒软件/索引器刚创建文件就抢着扫描，此时 open(...,'w') 会短暂
        报 PermissionError [Errno 13] —— 文件甚至还不存在。重试几次就好；
      · 旧门户进程仍占着该文件。
    因此这里用**原子写**（先写临时文件再替换）+ 重试，把这类瞬时冲突挡掉。
    """
    os.makedirs(RUNS_DIR, exist_ok=True)
    temp_path = "%s.%d.tmp" % (path, os.getpid())
    last_error = None
    for _attempt in range(5):
        try:
            with open(temp_path, "w", encoding="utf-8") as handle:
                handle.write(value + "\n")
            os.replace(temp_path, path)
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
            return True
        except OSError as exc:
            last_error = exc
            time.sleep(0.15)
            try:
                os.remove(temp_path)
            except OSError:
                pass
    print("提示：凭据副本写不进去（%s）：%s —— 门户照常运行，"
          "真凭据在 %s" % (os.path.basename(path), last_error,
                           os.path.basename(STATE_FILE)), file=sys.stderr)
    return False


def write_password(password):
    return _write_secret_file(PASSWORD_FILE, password)


def write_lan_password(pin):
    return _write_secret_file(LAN_PASSWORD_FILE, pin)


# --------------------------------------------------------------- 服务进程管理
#
# **本插件不再管理任何上游进程。**
#
# 用户明确要求：开关只负责「门户要不要把请求转过去」（路由闸门），
# 不负责启停上游程序。原话：「如果是负责启动和停止，还需要配置对应的启停程序，
# 暂不处理」—— 那个判断是对的：要可靠地拉起别人的程序，得先知道它的启动方式
# （命令、工作目录、环境变量、就绪判定），这是一整套配置，而且很容易做出
# "以为在管、其实没管住"的假象。
#
# 所以原 ServiceSupervisor（按 script 拉起/停止子进程）整块删掉了：
#   · 注册表的 enabled 只表示"这条路由开放/屏蔽"；
#   · 上游程序由用户自己的脚本/IDE 启动，插件只探测它通不通（port_listening）。
# 注册表里的 script / cwd / autoStart 字段保留着（老数据仍能读，不破坏兼容），
# 但本插件不再拿它们去 spawn 任何东西。


def _detached_flags():
    if os.name == "nt":
        return 0x00000008 | 0x00000200   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    return 0


# --------------------------------------------------------------------- 运行

def run_portal(args):
    import portal_console
    import portal_proxy
    import portal_registry
    import portal_login

    if not os.path.isdir(RUNS_DIR):
        os.makedirs(RUNS_DIR, exist_ok=True)

    # 口令：固定（--password/--password-file）或随机
    if args.password_file:
        try:
            with open(args.password_file, "r", encoding="utf-8") as handle:
                password = handle.read().strip()
        except OSError as exc:
            print("读不到 --password-file：%s" % exc, file=sys.stderr)
            return 2
    else:
        password = (args.password or "").strip() or portal_login.gen_password(12)
    try:
        portal_login.validate_password(password)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    write_password(password)

    # ---- 局域网口令（与公网口令分开）----
    # 对齐 dsh-pocket：公网 16 字符随机串抗爆破；局域网用 8 位数字，手机好输。
    # 从上次状态文件恢复（用户自定义过 / 刷新过的值要延续），没有就新生成一个。
    _saved_pw = (load_state() or {})
    lan_password = str(_saved_pw.get("lan_password") or "").strip()
    if not lan_password or not lan_password.isdigit():
        lan_password = portal_login.gen_lan_password(8)
    write_lan_password(lan_password)

    registry = portal_registry.Registry(REGISTRY_FILE)
    registry.load()
    if registry.load_error:
        print("提示：注册表读取有问题，已按空表处理：%s" % registry.load_error,
              file=sys.stderr)

    host_repo = args.host_repo or DEFAULT_HOST_REPO

    public_url_holder = {"url": None}
    tunnel_proc = {"proc": None}
    # 运行时可改的开关（改完立即生效，落盘到 runs/portal_state.json）
    #
    # 手动选的地址与两个开关都从上次的状态文件恢复（参数没显式给时）——
    # 否则「重启后设置丢了」：用户明明在设置页选过网卡，重启又回到自动。
    saved = load_state() or {}
    saved_override = str(saved.get("lan_ip_override") or "").strip()
    # 公网口令：可**运行期改**（设置页「自定义公网密码」），改完立即生效、
    # 不重启门户 —— 重启会换掉 trycloudflare 域名。
    #
    # 只有「用户自定义过」（public_pin_custom）才沿用上次那份；否则必须用本次
    # 启动的口令（随机模式下每次启动本来就该换新）。若不加这个条件，用户一次
    # 自定义之后，随机模式永远换不回新口令了。
    saved_public = str(saved.get("public_password") or "").strip()
    if saved.get("public_pin_custom") and saved_public:
        password = saved_public
    write_password(password)

    runtime = {
        "lan_auth": bool(args.lan_auth) or bool(saved.get("lan_auth_enabled")),
        "lan_enabled": saved.get("lan_enabled") is not False,
        "lan_ip_override": (args.lan_ip or "").strip() or saved_override,
        # 局域网口令：上面已经算好（沿用上次自定义/刷新的值，没有就新生成）
        "lan_password": lan_password,
        "lan_pin_custom": bool(saved.get("lan_pin_custom")),
        "password": password,
        "public_pin_custom": bool(saved.get("public_pin_custom")) and bool(saved_public),
    }

    # ---- 门户回调 ----
    def state_snapshot():
        """门户状态快照（控制台页面与设置页 API 共用同一份真相）。"""
        entries = []
        for entry in registry.list():
            item = dict(entry)
            target = entry.get("target") or ""
            _, _, port_text = target.rpartition(":")
            try:
                item["alive"] = port_listening(int(port_text))
            except ValueError:
                item["alive"] = False
            entries.append(item)
        public_url = public_url_holder["url"]
        override = runtime.get("lan_ip_override") or ""
        lan_urls, lan_note = lan_urls_for(args.port, override)
        if not lan_urls:
            lan_urls = ["http://127.0.0.1:%d" % args.port]
        # 候选明细：设置页「高级·手动选地址」的下拉框用它（带网卡名，便于判断）
        candidates = lan_candidates_detailed()
        return {
            "services": entries,
            "lan_urls": lan_urls,
            "lan_candidates": [item["ip"] for item in candidates],
            "lan_candidate_detail": candidates,
            "lan_ip_override": override,
            "lan_note": lan_note,
            "public_url": public_url,
            "portal_port": args.port,
            "host_repo": host_repo,
            "lan_auth_enabled": bool(runtime["lan_auth"]),
            "lan_enabled": bool(runtime["lan_enabled"]),
            # 公网口令：控制台与设置页都要显示它。**用 runtime 里的当前值**，
            # 不是启动时那个局部变量 —— 自定义之后局部变量是旧的，界面就会
            # 显示过期口令（用户拿它去登录必然失败）。
            "password": runtime["password"],
            "public_pin_custom": bool(runtime["public_pin_custom"]),
            # 局域网口令与「是否自定义」：控制台与设置页都要能显示/刷新它。
            # 内网免密时不返回它（那时它为空，显示出来反而误导用户以为要输）。
            "lan_password": runtime["lan_password"] if runtime["lan_auth"] else "",
            "lan_pin_custom": bool(runtime["lan_pin_custom"]),
        }

    def console_state():
        return state_snapshot()

    def resolve_upstream(path):
        for entry in registry.list():
            if not entry.get("enabled"):
                continue
            mount = entry.get("mount") or ""
            if not mount:
                continue
            if path == mount or path.startswith(mount + "/"):
                target = entry.get("target") or ""
                host, _, port_text = target.rpartition(":")
                try:
                    port = int(port_text)
                except ValueError:
                    return None
                rest = path[len(mount):] or "/"
                return mount, host, port, rest
        return None

    def start_tunnel_now():
        """按需建立隧道（设置页「开启外网访问」）。返回 (ok, 说明)。"""
        cloudflared = args.cloudflared or DEFAULT_CLOUDFLARED
        if not os.path.isfile(cloudflared):
            return False, "找不到 cloudflared：%s" % cloudflared
        proc = tunnel_proc["proc"]
        if proc is not None and proc.poll() is None and public_url_holder["url"]:
            return True, "隧道已在运行"
        try:
            since = os.path.getsize(_log_path(TUNNEL_LOG))
        except OSError:
            since = 0
        log = open(_log_path(TUNNEL_LOG), "ab")
        proc = subprocess.Popen(
            [cloudflared, "--no-autoupdate", "tunnel",
             "--url", "http://127.0.0.1:%d" % args.port, "--protocol", "http2"],
            stdout=log, stderr=subprocess.STDOUT, creationflags=_detached_flags())
        tunnel_proc["proc"] = proc
        url = read_url(TUNNEL_LOG, timeout=75, since=since)
        public_url_holder["url"] = url
        # 隧道地址变了要写回状态文件，否则设置页/状态命令看到的还是旧地址
        try:
            st = load_state() or {}
            st["public_url"] = url
            save_state(st)
        except OSError:
            pass
        if not url:
            return False, "隧道未在 75 秒内给出地址，见 %s" % _log_path(TUNNEL_LOG)
        return True, url

    def stop_tunnel_now():
        proc = tunnel_proc["proc"]
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
        tunnel_proc["proc"] = None
        public_url_holder["url"] = None
        try:
            st = load_state() or {}
            st["public_url"] = None
            save_state(st)
        except OSError:
            pass

    def parse_body(handler, body):
        """把请求体解析成 dict —— **同时接受 JSON 与表单**。

        为什么必须两种都收（实测踩到的真 bug）：
        控制台页面用的是**原生表单提交**（`<form method="POST">`，浏览器发
        `application/x-www-form-urlencoded`）。早先这里只 `json.loads`，
        于是页面上点「添加服务」永远得到 `请求体不是合法 JSON` ——
        功能看起来在，实际一个服务都加不进去。

        表单是网页最自然的提交方式，不该为了配合后端而被迫改写成 JS fetch；
        而插件/脚本调用走 JSON 更自然。两种都收，各自自然。
        """
        text = (body or b"").decode("utf-8", "replace").strip()
        if not text:
            return {}
        ctype = (handler.headers.get("Content-Type") or "").lower()
        looks_json = text[:1] in ("{", "[")
        if "json" in ctype or (looks_json and "form" not in ctype):
            try:
                parsed = json.loads(text)
                return parsed if isinstance(parsed, dict) else {"value": parsed}
            except ValueError:
                pass                      # 落到表单解析兜底
        # 表单：k=v&k=v（urlencoded）。multipart 不做完整解析，只取最简单的部分。
        try:
            fields = urllib.parse.parse_qs(text, keep_blank_values=True)
            return {k: (v[0] if len(v) == 1 else v) for k, v in fields.items()}
        except Exception:
            return {}

    # 关闭自己的函数在下面才定义（要等 server 就绪），用 holder 传进来：
    # 直接在 api_handler 里引用 `shutdown` 会在极早期请求上 NameError。
    shutdown_holder = {"fn": None}

    def api_handler(handler, method, route, body):
        """控制台 API。所有写操作都落注册表，立即生效。"""
        if method == "POST" and route == "/shutdown":
            # 让门户**自己退**。插件（DSH 宿主）从外面杀 pid 在某些环境里
            # 根本看不见这个进程 —— 实测宿主派生出来的子进程与门户不在同一个
            # 作业/沙箱内，taskkill 直接回"找不到进程"(128)，门户却活得好好的，
            # 于是"停止"报成功但什么都没停。请求它自己退出才是可靠路径。
            #
            # 安全：只接受**本机**发起的请求。门户监听 0.0.0.0，局域网和公网
            # 都连得到它 —— 不能让人从手机上把门户关掉。
            peer = handler.client_address[0] if handler.client_address else ""
            if peer not in ("127.0.0.1", "::1", "localhost"):
                handler._send_json(403, {"ok": False,
                                         "error": "只允许本机停止门户（当前来自 %s）"
                                                  % peer})
                return True
            fn = shutdown_holder["fn"]
            if fn is None:
                handler._send_json(503, {"ok": False, "error": "门户还没就绪"})
                return True
            handler._send_json(200, {"ok": True, "stopping": True})
            # 先把响应发出去，再关服务（否则客户端拿到的是"连接被重置"）
            threading.Timer(0.3, fn).start()
            return True
        if method == "GET" and route == "/services":
            handler._send_json(200, {"ok": True, "services": console_state()["services"]})
            return True
        if method == "GET" and route == "/state":
            handler._send_json(200, dict(console_state(), ok=True))
            return True
        if method == "GET" and route == "/qr":
            # 供插件设置页取二维码：?url=<地址>（只允许本地/隧道地址，防被当图床滥用）
            raw = urllib.parse.urlparse(handler.path).query
            target = urllib.parse.parse_qs(raw).get("url", [""])[0]
            if not target:
                handler._send_json(400, {"ok": False, "error": "缺少 url 参数"})
                return True
            allowed = set(state_snapshot()["lan_urls"])
            public = public_url_holder["url"]
            if public:
                allowed.add(public)
            if target not in allowed:
                handler._send_json(403, {"ok": False,
                                         "error": "只允许为本门户的地址生成二维码"})
                return True
            try:
                import portal_console
                data_uri = portal_console.qr_data_uri(target)
            except Exception as exc:
                handler._send_json(500, {"ok": False, "error": repr(exc)})
                return True
            handler._send_json(200, {"ok": True, "url": target, "qr": data_uri})
            return True
        if method == "GET" and route == "/settings":
            handler._send_json(200, {
                "ok": True,
                "lan_auth_enabled": bool(runtime["lan_auth"]),
                "lan_enabled": bool(runtime["lan_enabled"]),
                "public_url": public_url_holder["url"],
                "has_tunnel": tunnel_proc["proc"] is not None,
            })
            return True
        if method == "POST" and route == "/settings":
            data = parse_body(handler, body)
            if "lanAuthEnabled" in data:
                runtime["lan_auth"] = bool(data["lanAuthEnabled"])
            if "lanEnabled" in data:
                runtime["lan_enabled"] = bool(data["lanEnabled"])
            if "lanIpOverride" in data:
                # 手动选地址：空字符串 = 回到自动（按网卡评分）
                value = str(data["lanIpOverride"] or "").strip()
                if value and value not in detect_lan_ips():
                    handler._send_json(400, {
                        "ok": False,
                        "error": "%s 不是本机当前的网卡地址，请从候选里选" % value,
                    })
                    return True
                runtime["lan_ip_override"] = value
            # 立即落盘，重启门户后开关还在（不落盘就是「改完就丢」）
            try:
                st = load_state() or {}
                st["lan_auth_enabled"] = bool(runtime["lan_auth"])
                st["lan_enabled"] = bool(runtime["lan_enabled"])
                st["lan_ip_override"] = runtime["lan_ip_override"]
                save_state(st)
            except OSError as exc:
                handler._send_json(500, {"ok": False, "error": "写状态失败：%r" % exc})
                return True
            handler._send_json(200, {
                "ok": True,
                "lan_auth_enabled": bool(runtime["lan_auth"]),
                "lan_enabled": bool(runtime["lan_enabled"]),
                "lan_ip_override": runtime["lan_ip_override"],
            })
            return True
        # ---- 局域网口令：刷新（随机）/ 自定义 ----
        # 对齐 dsh-pocket 的 lanTokenRefresh 与 pinSetCustom（issue #33）：
        # 局域网口令可以「刷新」成一个新的随机值，也可以「自定义」成用户记得住的；
        # 自定义后**不再自动轮换**（用户选了自己要的，就别给他换掉）。
        if method == "POST" and route == "/lan-pin/refresh":
            runtime["lan_password"] = portal_login.gen_lan_password(8)
            runtime["lan_pin_custom"] = False
            write_lan_password(runtime["lan_password"])
            try:
                st = load_state() or {}
                st["lan_password"] = runtime["lan_password"]
                st["lan_pin_custom"] = False
                save_state(st)
            except OSError as exc:
                handler._send_json(500, {"ok": False, "error": "写状态失败：%r" % exc})
                return True
            handler._send_json(200, {"ok": True,
                                     "lan_password": runtime["lan_password"],
                                     "lan_pin_custom": False})
            return True
        if method == "POST" and route == "/lan-pin/custom":
            data = parse_body(handler, body)
            try:
                value = portal_login.validate_lan_pin(data.get("value"))
            except ValueError as exc:
                handler._send_json(400, {"ok": False, "error": str(exc)})
                return True
            runtime["lan_password"] = value
            runtime["lan_pin_custom"] = True
            write_lan_password(value)
            try:
                st = load_state() or {}
                st["lan_password"] = value
                st["lan_pin_custom"] = True
                save_state(st)
            except OSError as exc:
                handler._send_json(500, {"ok": False, "error": "写状态失败：%r" % exc})
                return True
            handler._send_json(200, {"ok": True, "lan_password": value,
                                     "lan_pin_custom": True})
            return True
        # ---- 公网口令：自定义（设置页「自定义公网密码」）----
        #
        # 体验与局域网对称（对齐 dsh-pocket issue #33：公网/局域网各自可设固定密码）。
        # 关键差别在**安全门槛**：公网是对全互联网暴露的，所以这里比局域网严得多 ——
        #   · 局域网：6–12 位**纯数字**（手机手输方便）；
        #   · 公网：至少 12 位（MIN_PASSWORD_LEN），且不许用局域网那种短数字串。
        # 内网口令绝不能拿来当公网凭据：局域网里任何人都可能知道它。
        if method == "POST" and route == "/public-pin/custom":
            data = parse_body(handler, body)
            raw = str(data.get("value") or "").strip()
            # 先查"是否等于局域网口令"再查长度门槛：局域网口令必然比公网门槛短
            # （6–12 位 < 12 位门槛附近的边界），若先查长度，这条安全规则会被
            # 长度规则先拦下、永远不触发 —— 那样它就是死代码，而用户看到的
            # 报错也会是"太短"而不是真正的问题（你用了局域网口令）。
            if raw and raw == str(runtime["lan_password"] or ""):
                handler._send_json(400, {
                    "ok": False,
                    "error": "公网密码不能和局域网口令相同 —— 局域网口令会传给"
                             "同一 WiFi 的设备，用它当公网凭据等于把内网口令公开",
                })
                return True
            try:
                value = portal_login.validate_public_pin(raw)
            except ValueError as exc:
                handler._send_json(400, {"ok": False, "error": str(exc)})
                return True
            runtime["password"] = value
            runtime["public_pin_custom"] = True
            write_password(value)
            try:
                st = load_state() or {}
                st["public_password"] = value
                st["public_pin_custom"] = True
                save_state(st)
            except OSError as exc:
                handler._send_json(500, {"ok": False, "error": "写状态失败：%r" % exc})
                return True
            handler._send_json(200, {"ok": True, "password": value,
                                     "public_pin_custom": True})
            return True
        if method == "POST" and route == "/public-pin/random":
            # 回到随机轮换：换一个新的长随机口令，并取消"自定义"标记
            # （否则下次开公网还是不再轮换，用户以为按钮坏了）。
            value = portal_login.gen_password(12)
            runtime["password"] = value
            runtime["public_pin_custom"] = False
            write_password(value)
            try:
                st = load_state() or {}
                st["public_password"] = value
                st["public_pin_custom"] = False
                save_state(st)
            except OSError as exc:
                handler._send_json(500, {"ok": False, "error": "写状态失败：%r" % exc})
                return True
            handler._send_json(200, {"ok": True, "password": value,
                                     "public_pin_custom": False})
            return True
        if method == "POST" and route == "/tunnel/start":
            if public_url_holder["url"]:
                handler._send_json(200, {"ok": True,
                                         "public_url": public_url_holder["url"],
                                         "note": "隧道已在运行"})
                return True
            ok, detail = start_tunnel_now()
            handler._send_json(200 if ok else 502, {
                "ok": ok, "public_url": public_url_holder["url"], "detail": detail})
            return True
        if method == "POST" and route == "/tunnel/stop":
            stop_tunnel_now()
            handler._send_json(200, {"ok": True})
            return True
        if method == "POST" and route == "/services":
            data = parse_body(handler, body)
            # 控制台表单只收集「名称 / 路由路径 / 上游 / 备注」——**没有 key**。
            # 但注册表要求一个内部标识符 key（用于 API 路径与状态文件）。
            # 用户不该为了加个服务去起一个内部 key，所以这里**从路由路径派生**：
            #   /rltrain -> rltrain  ·  /a/b -> a_b  ·  非法字符一律转下划线。
            # 只有在完全没有 mount 时才让注册报表（那时确实是缺必填项）。
            if not str(data.get("key") or "").strip() and str(data.get("mount") or "").strip():
                data = dict(data)
                data["key"] = derive_key_from_mount(data["mount"])
            try:
                entry = registry.add(data)
            except portal_registry.RegistryError as exc:
                handler._send_json(400, {"ok": False, "error": str(exc)})
                return True
            # 不在这里拉起上游进程：本插件只管路由（见下面"路由闸门"的说明）。
            handler._send_json(200, {"ok": True, "service": entry})
            return True

        parts = [p for p in route.split("/") if p]
        if len(parts) >= 2 and parts[0] == "services":
            key = parts[1]
            action = parts[2] if len(parts) > 2 else None
            entry = registry.get(key)
            if entry is None:
                handler._send_json(404, {"ok": False,
                                         "error": "没有服务 %s" % key})
                return True
            if method == "POST" and action in ("enable", "disable", "open", "block"):
                # ---- 这是「路由闸门」，不是"启停服务" ----
                #
                # 用户明确要求：开关只管"门户要不要把请求转过去"，**不负责启停上游程序**。
                # 原话：「如果是负责启动和停止，还需要配置对应的启停程序，暂不处理」。
                #
                # 所以这里**只改注册表的 enabled**，绝不 spawn/kill 任何进程 ——
                # 上游起不起来是上游自己的事（它归用户自己的启动脚本/IDE 管）。
                # 这个区分很重要：早先这里会 supervisor.start()，于是"开放"一个
                # 没配 script 的服务会报"没有配 script，无法拉起"，用户以为功能坏了。
                want = action in ("enable", "open")
                handler._send_json(200, {"ok": True,
                                         "service": registry.set_enabled(key, want)})
                return True
            if method == "POST" and action == "delete":
                # 删除只从注册表移除（不再顺手 stop 进程 —— 见上面"路由闸门"的说明：
                # 上游进程不归本插件管，它可能正被别的用途使用）。
                registry.remove(key)
                handler._send_json(200, {"ok": True})
                return True
            if method == "POST" and action == "update":
                data = parse_body(handler, body)
                try:
                    updated = registry.update(key, data)
                except portal_registry.RegistryError as exc:
                    handler._send_json(400, {"ok": False, "error": str(exc)})
                    return True
                handler._send_json(200, {"ok": True, "service": updated})
                return True
            # 认得出是"节点动作"、但动作不被支持：要说清**为什么**，
            # 不能只回一句"未知接口" —— 用户（或老客户端）看到 restart 被拒，
            # 需要知道"这是有意的：本插件不再启停上游程序"。
            if method == "POST" and action:
                handler._send_json(404, {
                    "ok": False,
                    "error": "不认识的动作 %s（本插件只管路由开关："
                             "open/block；不再启停上游程序）" % action,
                })
                return True
        handler._send_json(404, {"ok": False, "error": "未知接口 %s" % route})
        return True

    # 绑定端口这一步最容易被环境挡住，必须**明确报错并退出**，不能继续往下
    # 打印「门户已启动」—— 那是最坏的一类 bug（不崩、只给错误答案：
    # 界面显示成功，实际什么都没在听）。
    #
    # 端口被占用（10048 / EADDRINUSE）时**自动往后试几个**（对齐 dsh-pocket 的
    # 「端口自适应」）：因为「上个门户没停干净」是最常见的情况，为用户这点小事
    # 报错退出太粗糙。试到就继续，全试完才报错。
    # 但 WinError 10013（系统保留段）**不往后试** —— 那是整段预约，
    # 逐个试只会连着失败十几次，不如直接告诉用户原因。
    bind_attempts = [args.port] if args.no_port_fallback else (
        [args.port] + [args.port + i for i in range(1, 6)])
    server = None
    last_error = None
    for attempt_port in bind_attempts:
        try:
            server = portal_proxy.make_portal_server(attempt_port, {
                "password": password,
                # 公网口令**动态可改**：设置页「自定义公网密码」后立即生效，
                # 不重启门户（重启会换掉隧道域名 —— 用户刚发出去的地址就废了）。
                "password_provider": lambda: runtime["password"],
                # 内网口令**动态可改**：设置页刷新/自定义后立即生效，不用重启门户。
                "lan_password_provider": lambda: runtime["lan_password"],
                "cookie_secure": False,  # 内网是 http；公网经隧道是 https 也能用
                # 内网免密开关**动态可改**：设置页切「局域网访问密码」时立即生效，
                # 不重启门户（重启会换掉隧道域名，代价太大）。
                # loopback 永远免密：那是本机自己，要求口令毫无意义。
                "open_classes_provider": lambda: (
                    ("loopback",) if runtime["lan_auth"] else ("loopback", "lan")),
                "lan_enabled_provider": lambda: runtime["lan_enabled"],
        "lan_ip_override_provider": lambda: runtime["lan_ip_override"],
                "console_state": console_state,
                "console_page": lambda state, is_public: portal_console.console_html(
                    state, is_public=is_public),
                "api_handler": api_handler,
                "resolve_upstream": resolve_upstream,
                "rate_limiter": portal_proxy.RateLimiter(),
            })
        except OSError as exc:
            last_error = exc
            winerr = getattr(exc, "winerror", None)
            if winerr == 10013 or "10013" in str(exc):
                break                     # 保留段：试下一个也没用
            if winerr == 10048 or getattr(exc, "errno", None) in (98, 48):
                if attempt_port != bind_attempts[-1]:
                    print("端口 %d 已被占用，换 %d 试试…"
                          % (attempt_port, attempt_port + 1), file=sys.stderr)
                continue
            break                         # 其他错误：不猜，直接报
        if attempt_port != args.port:
            print("注意：实际监听端口是 %d（原定 %d 被占用）"
                  % (attempt_port, args.port), file=sys.stderr)
        args.port = attempt_port           # 后续状态/隧道/URL 都用真实端口
        break

    if server is None:
        exc = last_error
        winerr = getattr(exc, "winerror", None) if exc else None
        print("")
        print("=" * 66, file=sys.stderr)
        print("门户启动失败：无法绑定端口 %d" % args.port, file=sys.stderr)
        print("=" * 66, file=sys.stderr)
        print("原因：%s" % exc, file=sys.stderr)
        if winerr == 10013:
            print("", file=sys.stderr)
            print("这是 Windows **保留端口**（Hyper-V / WSL / Docker 会成段预约）。", file=sys.stderr)
            print("查一下 %d 是否落在保留段里：" % args.port, file=sys.stderr)
            print("    netsh interface ipv4 show excludedportrange protocol=tcp", file=sys.stderr)
            print("换一个没被保留的端口即可，例如：", file=sys.stderr)
            print("    python -X utf8 tools/portal_run.py --port 18899", file=sys.stderr)
            print("也可以在 DSH 设置页把「门户端口」改成该端口。", file=sys.stderr)
        elif winerr == 10048:
            print("", file=sys.stderr)
            print("端口 %d 及其后 5 个都被占用。" % args.port, file=sys.stderr)
            print("先停掉旧的门户：", file=sys.stderr)
            print("    python -X utf8 tools/portal_run.py --stop", file=sys.stderr)
            print("或显式换端口：--port 18899", file=sys.stderr)
        return 3
    # ---- 关闭流程：必须在**开始接受请求之前**就装好 ----
    #
    # 踩过的真 bug（用户重启 DSH 后 test_host_buttons 从 SKIP 变 FAIL 才暴露）：
    # 原来 `serve_forever` 先起（端口开始监听），而 `shutdown_holder["fn"]`
    # 晚得多才赋值 —— 中间还夹着隧道建立和一次可能重试 ~2 秒的 save_state
    # （实测沙箱里写 runs/ 会 Errno 13）。于是在那个窗口里：
    #   · 宿主看端口在听 -> 认为"运行中"，设置页可点「停止」；
    #   · 点下去 POST /_api/shutdown -> 命中 `fn is None` -> **503「门户还没就绪」**；
    #   · 宿主判 asked=false -> 退到 `portal_run.py --stop` 兜底；
    #   · 而兜底那个子进程在沙箱里 taskkill 看不见门户、又读不到状态文件，
    #     回一句"门户未在运行" —— 结果就是**第二次停止失败**：报错、门户还活着。
    #
    # 修法：把 stopped / shutdown / signal / shutdown_holder 全部提前，
    # 让"端口开始监听"与"能接受关闭请求"**同时成立**，消灭这个窗口。
    stopped = {"flag": False}

    def shutdown(*_):
        # 可能被信号处理器（主线程）或 /_api/shutdown 的 Timer 线程调用，防重入
        if stopped["flag"]:
            return
        stopped["flag"] = True
        print("\n正在停止…")
        # 不再停任何"服务进程"：本插件不管理上游程序（见上面"服务进程管理"说明）。
        # 上游该由它自己的启动方式去停 —— 我们只负责把门户关掉。
        proc = tunnel_proc["proc"]
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
        # 用 mark_stopped() 而不是 clear_state()：状态文件里存着**要留存的偏好**
        # （局域网口令、自定义标记、网卡候选、手动选的地址）。删掉它，
        # 「局域网口令重启后不变」就失效了，用户手机里存过的口令也白存。
        mark_stopped()
        server.shutdown()
        print("已停止。")
        sys.stdout.flush()
        # 从信号处理器（主线程）里 sys.exit 会把进程带出去；但从 HTTP 的
        # Timer 线程里 exit 只结束那个线程 —— 实测结果是"端口松了、进程还在"。
        # 所以主线程那条路交给下面的 while 条件退出。
        if threading.current_thread() is threading.main_thread():
            sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    # 让 POST /_api/shutdown 也能走到同一个关闭流程（见 api_handler 里的说明）
    shutdown_holder["fn"] = shutdown
    try:
        signal.signal(signal.SIGTERM, shutdown)
    except (AttributeError, ValueError):
        pass

    threading.Thread(target=server.serve_forever, daemon=True).start()

    # ---- 隧道（复用 start_tunnel_now，避免同一段逻辑写两份）----
    if not args.lan_only:
        if not os.path.isfile(args.cloudflared or DEFAULT_CLOUDFLARED):
            print("提示：找不到 cloudflared，只开内网。"
                  "可用 --cloudflared 指定，或加 --lan-only 跳过。", file=sys.stderr)
        else:
            print("等待隧道建立…")
            ok, detail = start_tunnel_now()
            if not ok:
                print("隧道建立失败：%s" % detail, file=sys.stderr)

    save_state({
        "portal_port": args.port,
        "portal_pid": os.getpid(),
        "password": password,
        "public_url": public_url_holder["url"],
        "lan_urls": state_snapshot()["lan_urls"],
        # 候选列表也要落盘：设置页「高级·手动选地址」的下拉框靠它列出可选项。
        # 早先**没写这个字段**，宿主读回来永远是空数组 —— 下拉框里只有
        # 「自动（推荐）」一项，用户看不到也选不到别的地址，
        # 表现出来就是「自动选地址没有效果」。
        "lan_candidates": state_snapshot()["lan_candidates"],
        "lan_candidate_detail": state_snapshot()["lan_candidate_detail"],
        "lan_auth_enabled": bool(runtime["lan_auth"]),
        "lan_enabled": bool(runtime["lan_enabled"]),
        "lan_password": runtime["lan_password"],
        "lan_pin_custom": bool(runtime["lan_pin_custom"]),
        "lan_ip_override": runtime["lan_ip_override"],
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    })

    lan_urls = state_snapshot()["lan_urls"]
    print("")
    print("=" * 66)
    print("门户已启动")
    print("=" * 66)
    print("内网访问：")
    for url in lan_urls or ["（没探测到内网 IP，可用 http://127.0.0.1:%d）" % args.port]:
        print("  %s" % url)
    if args.lan_only:
        print("外网访问：未开启（--lan-only）")
    elif public_url_holder["url"]:
        print("外网访问：%s" % public_url_holder["url"])
        print("  （外网需要口令；内网免密）")
    else:
        print("外网访问：隧道未建立（见 %s）" % _log_path(TUNNEL_LOG))
    print("口令    ：%s" % password)
    print("控制台  ：在浏览器打开上面的地址即可")
    print("停止    ：Ctrl+C，或 python -X utf8 tools/portal_run.py --stop")
    print("=" * 66)
    sys.stdout.flush()

    # 关闭流程已在上面（开始接受请求之前）装好 —— 见那段注释里说明的竞态。

    try:
        # server.shutdown() 之后 serve_forever 返回，但主线程还停在这个循环里，
        # 所以循环条件要看 stopped 标记 —— 否则"端口松了、进程还在"。
        while not stopped["flag"]:
            time.sleep(0.5)
    except KeyboardInterrupt:
        shutdown()


def print_status():
    state = load_state()
    if not state:
        print("门户未运行（没有状态文件）")
        return 0
    port = state.get("portal_port")
    alive = port_listening(port) if port else False
    print("门户端口：%s  %s" % (port, "监听中" if alive else "**未监听**"))
    print("口令    ：%s" % state.get("password"))
    for url in state.get("lan_urls", []):
        print("内网    ：%s" % url)
    print("外网    ：%s" % (state.get("public_url") or "（未开启）"))
    print("启动于  ：%s" % state.get("started_at"))
    if not alive:
        print("提示：状态文件还在但端口没监听 —— 门户已停止或异常退出。")
    return 0


def derive_key_from_mount(mount):
    """从路由路径派生服务 key：/rltrain -> rltrain，/a/b -> a_b。

    控制台表单只让用户填「名称 / 路由路径 / 上游 / 备注」——那是用户能理解的东西；
    key 是内部标识符（用于 API 路径与状态），不该要用户自己想一个。
    非法字符统一转下划线，并截断到 32 字符（与注册表的校验一致）。

    全中文等无法转成 ASCII 的路径（`/中文`）会派生出空串 —— 那时退回一个
    基于路径的稳定短哈希（`svc_<hash>`），保证用户仍能添加成功。
    只有 mount 本身为空才返回空串，交给注册表报「不能为空」。
    """
    text = str(mount or "").strip().strip("/")
    if not text:
        return ""
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_")
    if safe:
        return safe[:32]
    # 全非 ASCII（如 /中文路径）：用稳定哈希兜底，保证能加进去
    import hashlib
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
    return "svc_" + digest


def _pids_listening_on(port):
    """找出正在监听该端口的进程 PID（用于清理状态文件丢失后的孤儿进程）。

    只靠状态文件里的 pid 是不够的：状态文件可能被覆盖/删掉，或门户是被别的方式
    起的（测试、手动运行），那时 --stop 会报「已停止」而进程还活着 —— 之后重新
    开启就会撞端口。所以按端口兜底再扫一遍。

    netstat 在中文 Windows 上输出的是 **GBK**（不是 UTF-8）：按 utf-8 解码会抛
    UnicodeDecodeError，子进程的 reader 线程崩掉后 stdout 变成 None。所以这里
    **不解析文本**：只看每行里是否出现 `:PORT` 与 `LISTENING`，再用正则取末尾数字。
    """
    pids = set()
    if os.name == "nt":
        try:
            raw = subprocess.run(["netstat", "-ano", "-p", "TCP"],
                                 capture_output=True, timeout=20).stdout or b""
        except Exception:
            return pids
        text = raw.decode("utf-8", "replace")
        needle = ":%d " % port
        for line in text.splitlines():
            if "LISTENING" not in line or needle not in line:
                continue
            match = re.search(r"(\d+)\s*$", line.strip())
            if match:
                pids.add(int(match.group(1)))
    else:
        try:
            out = subprocess.run(["lsof", "-ti", "tcp:%d" % port],
                                 capture_output=True, text=True, timeout=20).stdout or ""
            pids.update(int(x) for x in out.split() if x.isdigit())
        except Exception:
            pass
    return pids


# 停止时要**留下**的东西：它们是"偏好"，不是"运行痕迹"。
# 踩过的坑：stop_all() 原来结尾 clear_state() 把整个状态文件删了，于是
#   · 局域网口令（重启后不变，用户手机里存过的）下次启动变成新随机口令；
#   · 自定义口令标记 lan_pin_custom 一起丢，用户以为"我设过固定口令"；
#   · 网卡候选没了，设置页在未启动时连"将要使用哪个地址"都显示不出来。
KEEP_ON_STOP = (
    "lan_password", "lan_pin_custom", "lan_candidates", "lan_candidate_detail",
    "lan_ip_override", "lan_auth_enabled", "lan_enabled", "password_mode",
    # 公网自定义口令也要留：用户特意设了记得住的密码，重启门户就丢回随机，
    # 那"自定义"这个功能等于半废（他的手机/便签里存的是旧密码）。
    "public_password", "public_pin_custom",
)


def _looks_like_our_portal(port, timeout=2.5):
    """这个端口上监听的是**我们的门户**吗？

    光看"端口上有人"就杀是危险的：端口可能配到了别的程序、或者被别的程序占了。
    我们的门户对 `/_auth/health` 一定有响应，且响应体是它自己的 JSON
    （实测：门户返回 200 + {"ok": true}；普通 http.server 返回 404）。
    判不出来就**不杀** —— 宁可留给用户手动处理，也不要顺手杀掉不相干的进程。
    """
    import urllib.error
    import urllib.request
    url = "http://127.0.0.1:%d%s" % (port, HEALTH_PATH)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as res:
            body = res.read(4096).decode("utf-8", "replace")
            return res.status == 200 and '"ok"' in body.replace(" ", "")
    except urllib.error.HTTPError as err:
        # 401/403 也说明"这里有个要求口令的东西"，很可能是我们的门户
        return err.code in (401, 403)
    except Exception:
        return False


def mark_stopped():
    """把状态文件从"正在运行"改成"已停止"，但保留上面那些偏好。"""
    state = load_state() or {}
    kept = {key: state[key] for key in KEEP_ON_STOP if key in state}
    kept["stopped_clean"] = True
    kept["stopped_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return save_state(kept)


def _kill_pid(pid):
    """尽力杀，返回 (状态, 原因)；状态是 "killed" / "gone" / "failed"。

    为什么要三种而不是布尔：把"进程早就退出了"和"我杀不掉它"混成一种，
    就会出现两种错误答案 —— 状态文件里是个旧 pid 时谎报"没杀掉"，
    或者权限不足时谎报"已停止"。taskkill 用退出码 128 表示找不到进程。
    """
    if os.name != "nt":
        try:
            os.kill(pid, signal.SIGTERM)
            return "killed", "SIGTERM"
        except ProcessLookupError:
            return "gone", "进程不存在"
        except Exception as exc:  # noqa: BLE001 - 要如实上报
            return "failed", repr(exc)
    # 优先绝对路径调 taskkill：宿主派生出来的子进程 PATH 可能不含 System32，
    # 裸名 "taskkill" 会 FileNotFoundError，表现成"进程不存在"的假象。
    taskkill = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                            "System32", "taskkill.exe")
    argv0 = taskkill if os.path.exists(taskkill) else "taskkill"
    try:
        done = subprocess.run([argv0, "/PID", str(pid), "/T", "/F"],
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        return "failed", "调用 taskkill 失败：%r" % (exc,)
    if done.returncode == 0:
        return "killed", "taskkill"
    text = ((done.stderr or "") + (done.stdout or "")).strip().replace("\r", " ")
    if done.returncode == 128 or "not found" in text.lower() or "找不到" in text:
        return "gone", text[:200]
    return "failed", "taskkill 退出码 %d：%s" % (done.returncode, text[:200])


def stop_all(port=None):
    """停止本仓库记录的门户进程。返回 0=停好了（或本来就没在跑），1=没停掉。

    三处都是踩出来的规则：

    ① 端口兜底**只在明确指定时**才做。以前默认扫 DEFAULT_PORTAL_PORT(8899)，
       于是检验脚本里一句裸的 `portal_run.py --stop` 把用户**正在运行**的门户
       干掉了 —— 先按状态文件里的 pid 杀（pid 被别的测试换成自己的），
       端口兜底又打到了用户那个。

    ② 按端口杀之前**先确认这端口上是我们的门户**（`_looks_like_our_portal`）。
       只认"端口上有人"就杀，会误杀端口被别的程序占用的场景。

    ③ 停不掉就 return 1（宿主据此把失败透给设置页），不谎报"已停止"。
    """
    state = load_state()
    killed = []
    failed = []
    if state:
        pid = state.get("portal_pid")
        if pid:
            how, why = _kill_pid(pid)
            if how == "killed":
                killed.append(pid)
            elif how == "failed":
                failed.append((pid, why))
            # how == "gone"：状态文件是旧的，进程早没了 —— 什么都不用做
    # 扫端口用的端口：显式 --port 优先；否则用状态文件里记的（那也是本仓库的门户）
    scan_port = port
    if scan_port is None and state:
        scan_port = state.get("portal_port")
    if scan_port:
        scan_port = int(scan_port)
        if port_listening(scan_port):
            if _looks_like_our_portal(scan_port):
                for pid in _pids_listening_on(scan_port):
                    if pid in killed:
                        continue
                    how, why = _kill_pid(pid)
                    if how == "killed":
                        killed.append(pid)
                    elif how == "failed":
                        failed.append((pid, why))
            else:
                # 这端口上有个东西，但不是我们的门户：**不碰**
                print("端口 %s 上的东西不像是本门户（%s 不认识），没有动它"
                      % (scan_port, HEALTH_PATH), file=sys.stderr)
    for pid, why in failed:
        print("进程 %s 没杀掉：%s" % (pid, why), file=sys.stderr)
    if killed:
        print("已停止门户进程 %s" % ", ".join(str(pid) for pid in killed))
    else:
        print("门户未在运行。")
    if failed:
        # 有活着的目标却没杀掉：不能让调用方以为停好了
        return 1
    # 注意：这里**不** clear_state()，见 KEEP_ON_STOP 的说明
    mark_stopped()
    return 0


def build_parser():
    ap = argparse.ArgumentParser(
        description="对外服务门户：内网 + 外网访问，自带控制台管理服务")
    ap.add_argument("--port", type=int, default=DEFAULT_PORTAL_PORT,
                    help="门户监听端口（默认 %d）" % DEFAULT_PORTAL_PORT)
    ap.add_argument("--password", default="", help="固定口令（默认随机生成）")
    ap.add_argument("--password-file", default=None, help="从文件读口令")
    ap.add_argument("--host-repo", default=None, help="服务脚本所在仓库根")
    ap.add_argument("--python", default=sys.executable or "python",
                    help="拉起服务用的解释器")
    ap.add_argument("--cloudflared", default=DEFAULT_CLOUDFLARED,
                    help="cloudflared.exe 路径")
    ap.add_argument("--lan-only", action="store_true", help="只开内网，不建隧道")
    ap.add_argument("--lan-auth", action="store_true",
                    help="内网访问也要求口令（默认内网免密，仅同一局域网可用）")
    ap.add_argument("--lan-ip", default="",
                    help="手动指定内网访问用的网卡地址（默认按网卡评分自动选）")
    ap.add_argument("--no-port-fallback", action="store_true",
                    help="端口被占用时不要自动往后试（默认会往后试 5 个）")
    ap.add_argument("--status", action="store_true", help="显示状态")
    ap.add_argument("--stop", action="store_true", help="停止门户")
    return ap


def main(argv=None):
    raw = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(raw)
    if args.status:
        return print_status()
    if args.stop:
        # 只有**显式**写了 --port 才允许按端口扫孤儿进程。`--port` 在参数表里
        # 有默认值 8899，直接传 args.port 等于"永远都在扫 8899"，就退回了
        # 那个会误杀用户门户的旧行为。
        explicit = any(a == "--port" or a.startswith("--port=") for a in raw)
        return stop_all(args.port if explicit else None)
    return run_portal(args)


if __name__ == "__main__":
    raise SystemExit(main())
