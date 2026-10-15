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
    """探测本机所有可用的私网 IPv4（内网访问地址就是 http://<ip>:<port>）。"""
    ips = []
    # 主路由探测：连一个外部地址（不发数据）拿到默认出口的本机 IP
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(0.4)
            sock.connect(("8.8.8.8", 80))
            ips.append(sock.getsockname()[0])
    except OSError:
        pass
    # 再补上所有网卡的私网地址（多网卡/虚拟网卡场景）
    try:
        import ipaddress
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            addr = info[4][0]
            if addr in ips:
                continue
            try:
                ip = ipaddress.ip_address(addr)
            except ValueError:
                continue
            if ip.is_loopback or ip.is_link_local:
                continue
            if ip.is_private:
                ips.append(addr)
    except OSError:
        pass
    return ips


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def save_state(state):
    os.makedirs(RUNS_DIR, exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_FILE)


def clear_state():
    try:
        os.remove(STATE_FILE)
    except OSError:
        pass


def read_password():
    try:
        with open(PASSWORD_FILE, "r", encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def write_password(password):
    os.makedirs(RUNS_DIR, exist_ok=True)
    with open(PASSWORD_FILE, "w", encoding="utf-8") as handle:
        handle.write(password + "\n")
    try:
        os.chmod(PASSWORD_FILE, 0o600)
    except OSError:
        pass


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
    runtime = {"lan_auth": bool(args.lan_auth), "lan_enabled": True}

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
        lan_urls = ["http://%s:%d" % (ip, args.port) for ip in detect_lan_ips()]
        if not lan_urls:
            lan_urls = ["http://127.0.0.1:%d" % args.port]
        return {
            "services": entries,
            "lan_urls": lan_urls,
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
            try:
                data = json.loads(body.decode("utf-8") or "{}")
            except ValueError:
                handler._send_json(400, {"ok": False, "error": "请求体不是合法 JSON"})
                return True
            if "lanAuthEnabled" in data:
                runtime["lan_auth"] = bool(data["lanAuthEnabled"])
            if "lanEnabled" in data:
                runtime["lan_enabled"] = bool(data["lanEnabled"])
            # 立即落盘，重启门户后开关还在（不落盘就是「改完就丢」）
            try:
                st = load_state() or {}
                st["lan_auth_enabled"] = bool(runtime["lan_auth"])
                st["lan_enabled"] = bool(runtime["lan_enabled"])
                save_state(st)
            except OSError as exc:
                handler._send_json(500, {"ok": False, "error": "写状态失败：%r" % exc})
                return True
            handler._send_json(200, {
                "ok": True,
                "lan_auth_enabled": bool(runtime["lan_auth"]),
                "lan_enabled": bool(runtime["lan_enabled"]),
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
            try:
                data = json.loads(body.decode("utf-8") or "{}")
            except ValueError:
                handler._send_json(400, {"ok": False, "error": "请求体不是合法 JSON"})
                return True
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
                try:
                    data = json.loads(body.decode("utf-8") or "{}")
                except ValueError:
                    handler._send_json(400, {"ok": False, "error": "请求体不是合法 JSON"})
                    return True
                try:
                    updated = registry.update(key, data)
                except portal_registry.RegistryError as exc:
                    handler._send_json(400, {"ok": False, "error": str(exc)})
                    return True
                handler._send_json(200, {"ok": True, "service": updated})
                return True
        handler._send_json(404, {"ok": False, "error": "未知接口 %s" % route})
        return True

    server = portal_proxy.make_portal_server(args.port, {
        "password": password,
        "cookie_secure": False,     # 内网是 http；公网经隧道是 https 也能用
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


def stop_all():
    state = load_state()
    if not state:
        print("门户未在运行。")
        return 0
    pid = state.get("portal_pid")
    if pid:
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                               capture_output=True)
            else:
                os.kill(pid, signal.SIGTERM)
            print("已请求停止门户进程 %s" % pid)
        except Exception as exc:
            print("停止失败：%r" % (exc,), file=sys.stderr)
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
    ap.add_argument("--status", action="store_true", help="显示状态")
    ap.add_argument("--stop", action="store_true", help="停止门户")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.status:
        return print_status()
    if args.stop:
        return stop_all()
    return run_portal(args)


if __name__ == "__main__":
    raise SystemExit(main())
