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
RUNS_DIR = os.path.join(ROOT, "runs")
LOG_DIR = os.path.join(RUNS_DIR, "portal_logs")
STATE_FILE = os.path.join(RUNS_DIR, "portal_state.json")
REGISTRY_FILE = os.path.join(RUNS_DIR, "portal_registry.json")
PASSWORD_FILE = os.path.join(RUNS_DIR, "portal_password.txt")
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
    print("提示：状态文件写不进去（%s）：%s" % (STATE_FILE, last_error),
          file=sys.stderr)
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


def write_password(password):
    """把口令写到 runs/portal_password.txt（方便用户/脚本查看，**不是**唯一凭据）。

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
    temp_path = PASSWORD_FILE + ".tmp"
    last_error = None
    for attempt in range(5):
        try:
            # 原子写：临时文件 + os.replace。避免「创建后被别的进程抓住」的窗口，
            # 也避免写一半留下半个文件。
            with open(temp_path, "w", encoding="utf-8") as handle:
                handle.write(password + "\n")
            os.replace(temp_path, PASSWORD_FILE)
            try:
                os.chmod(PASSWORD_FILE, 0o600)
            except OSError:
                pass
            return True
        except OSError as exc:
            last_error = exc
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except OSError:
                pass
            time.sleep(0.15 * (attempt + 1))
    print("提示：口令副本文件写不进去（%s）：%s" % (PASSWORD_FILE, last_error),
          file=sys.stderr)
    print("不影响使用：口令已存在 runs/portal_state.json，门户会正常启动。",
          file=sys.stderr)
    return True


# --------------------------------------------------------------- 服务进程管理

class ServiceSupervisor:
    """按注册表拉起 / 停止服务进程（只管子进程，不碰别人起的服务）。"""

    def __init__(self, host_repo, python_exe):
        self.host_repo = host_repo
        self.python = python_exe
        self.procs = {}          # key -> Popen

    def alive(self, key):
        proc = self.procs.get(key)
        return proc is not None and proc.poll() is None

    def start(self, entry):
        """拉起服务（已在跑 -> 直接返回 True）。"""
        import portal_registry
        key = entry.get("key")
        target = entry.get("target") or ""
        host, _, port_text = target.rpartition(":")
        try:
            port = int(port_text)
        except ValueError:
            return False, "target 端口无效：%r" % target
        if port_listening(port):
            return True, "端口已在监听（视为已运行）"
        script = (entry.get("script") or "").strip()
        if not script:
            return False, "没有配 script，无法拉起（需外部自行启动并监听 %s）" % target
        cwd = entry.get("cwd") or self.host_repo
        if not os.path.isabs(cwd):
            cwd = os.path.join(self.host_repo, cwd)
        path = script if os.path.isabs(script) else os.path.join(self.host_repo, script)
        if not os.path.isfile(path):
            return False, "找不到脚本：%s" % path
        log = open(_log_path("service_%s.log" % key), "ab")
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        proc = subprocess.Popen(
            [self.python, "-X", "utf8", path],
            cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
            env=env, creationflags=_detached_flags())
        self.procs[key] = proc
        # 等端口就绪（最多 60 秒）
        deadline = time.time() + 60
        while time.time() < deadline:
            if port_listening(port):
                return True, "已启动（PID %d）" % proc.pid
            if proc.poll() is not None:
                return False, "进程退出（码 %s），见 %s" % (
                    proc.returncode, _log_path("service_%s.log" % key))
            time.sleep(0.5)
        return False, "启动超时（60 秒内端口未就绪）"

    def stop(self, key):
        proc = self.procs.get(key)
        if proc is None or proc.poll() is not None:
            self.procs.pop(key, None)
            return False
        try:
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
        except Exception:
            pass
        self.procs.pop(key, None)
        return True


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

    registry = portal_registry.Registry(REGISTRY_FILE)
    registry.load()
    if registry.load_error:
        print("提示：注册表读取有问题，已按空表处理：%s" % registry.load_error,
              file=sys.stderr)
    for entry in registry.list():
        if entry.get("autoStart"):
            registry.set_enabled(entry["key"], True)

    host_repo = args.host_repo or DEFAULT_HOST_REPO
    python_exe = args.python if os.path.isfile(args.python) else sys.executable
    supervisor = ServiceSupervisor(host_repo, python_exe)

    public_url_holder = {"url": None}
    tunnel_proc = {"proc": None}
    # 运行时可改的开关（改完立即生效，落盘到 runs/portal_state.json）
    #
    # 手动选的地址与两个开关都从上次的状态文件恢复（参数没显式给时）——
    # 否则「重启后设置丢了」：用户明明在设置页选过网卡，重启又回到自动。
    saved = load_state() or {}
    saved_override = str(saved.get("lan_ip_override") or "").strip()
    runtime = {
        "lan_auth": bool(args.lan_auth) or bool(saved.get("lan_auth_enabled")),
        "lan_enabled": saved.get("lan_enabled") is not False,
        "lan_ip_override": (args.lan_ip or "").strip() or saved_override,
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
            "password": password,
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

    def api_handler(handler, method, route, body):
        """控制台 API。所有写操作都落注册表，立即生效。"""
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
            if entry.get("enabled") and entry.get("autoStart"):
                ok, note = supervisor.start(entry)
                entry["startNote"] = note
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
            if method == "POST" and action in ("enable", "disable"):
                want = action == "enable"
                if want and not supervisor.alive(key):
                    ok, note = supervisor.start(entry)
                    if not ok:
                        # 端口没起来也必须把开关置位，由控制台显示红/黄状态，
                        # 但要把原因明确回报（不静默成功）。
                        registry.set_enabled(key, True)
                        handler._send_json(200, {
                            "ok": True, "service": registry.get(key),
                            "warning": note})
                        return True
                if not want:
                    supervisor.stop(key)
                handler._send_json(200, {"ok": True,
                                         "service": registry.set_enabled(key, want)})
                return True
            if method == "POST" and action == "restart":
                supervisor.stop(key)
                ok, note = supervisor.start(entry)
                handler._send_json(200, {"ok": ok, "note": note,
                                         "service": registry.get(key)})
                return True
            if method == "POST" and action == "delete":
                supervisor.stop(key)
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
                "cookie_secure": False,  # 内网是 http；公网经隧道是 https 也能用
                # 内网免密开关**动态可改**：设置页切「局域网访问密码」时立即生效，
                # 不重启门户（重启会换掉隧道域名，代价太大）。
                # loopback 永远免密：那是本机自己，要求口令毫无意义。
                "open_classes_provider": lambda: (
                    ("loopback",) if runtime["lan_auth"] else ("loopback", "lan")),
                "lan_enabled_provider": lambda: runtime["lan_enabled"],
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
        "lan_auth_enabled": bool(args.lan_auth),
        "lan_enabled": bool(runtime["lan_enabled"]),
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

    def shutdown(*_):
        print("\n正在停止…")
        for entry in registry.list():
            supervisor.stop(entry["key"])
        proc = tunnel_proc["proc"]
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
        clear_state()
        server.shutdown()
        print("已停止。")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    try:
        signal.signal(signal.SIGTERM, shutdown)
    except (AttributeError, ValueError):
        pass

    try:
        while True:
            time.sleep(1)
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


def stop_all(port=DEFAULT_PORTAL_PORT):
    state = load_state()
    killed = []
    if state:
        pid = state.get("portal_pid")
        if pid:
            try:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                                   capture_output=True)
                else:
                    os.kill(pid, signal.SIGTERM)
                killed.append(pid)
            except Exception as exc:
                print("停止 %s 失败：%r" % (pid, exc), file=sys.stderr)
    # 兜底：按端口扫孤儿进程（状态文件丢了/换了端口的情况）
    for pid in _pids_listening_on(port):
        if pid in killed:
            continue
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                               capture_output=True)
            else:
                os.kill(pid, signal.SIGTERM)
            killed.append(pid)
        except Exception:
            pass
    if killed:
        print("已停止门户进程 %s" % ", ".join(str(p) for p in killed))
    else:
        print("门户未在运行。")
    clear_state()
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
    args = build_parser().parse_args(argv)
    if args.status:
        return print_status()
    if args.stop:
        return stop_all(args.port)
    return run_portal(args)


if __name__ == "__main__":
    raise SystemExit(main())
