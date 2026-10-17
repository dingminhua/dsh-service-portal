# -*- coding: utf-8 -*-
"""一键把配置台/查看台通过 cloudflared 隧道公开到外网：随机域名 + 随机口令。

链路
----
    https://<随机>.trycloudflare.com   (cloudflared quick tunnel，域名每次启动都换)
              |
              v
    127.0.0.1:8890/8891  tools/tunnel_auth.py（Basic Auth，口令每次启动都换）
              |
              v
    127.0.0.1:8810 配置台（gui/server.py）   /   127.0.0.1:8811 查看台（gui/viewer_server.py）

为什么不是「域名后面加路径」
----------------------------
cloudflared quick tunnel 是**单目标整站转发**：一个实例只能指向一个本地端口，
没有按路径分流的能力。而两个 GUI 的页面全部用绝对路径引用资源与 API
（``/api/...``、``/vendor/...``），即使前面加按 ``/train``、``/viewer`` 分流的
反向代理，挂到子路径下也会全线 404（要改两个 GUI 支持 base-path 才行）。

所以这里给**每个页面一个独立随机域名**：各站独占域名根，绝对路径天然可用，
零代码改动。想要「一个域名 + 路径」的固定形态，需要自有域名接入 Cloudflare
并给两个 GUI 加 ``--base-path``，不在本脚本范围内。

随机口令
--------
口令由 ``tools/tunnel_auth.py::gen_password()`` 生成，只写入
``runs/public_gui_credentials.json``（含明文，属于**机密文件**）并通过环境变量
传给代理进程——**不进命令行**（命令行会被 ``Get-CimInstance Win32_Process``
看到）。cloudflared 本身不支持加密码，所以这一层代理是外网唯一的口令关卡；
没有它，任何拿到随机域名的人都能启停你的训练。

用法
----
    # 启动（GUI 未在跑会自动拉起；已在跑则复用）
    python -X utf8 tools/start_public_gui.py

    # 只看状态，不新建隧道
    python -X utf8 tools/start_public_gui.py --status

    # 关掉本脚本起的所有东西（隧道 + 代理；不动你手动开的 GUI 和 dsh-pocket）
    python -X utf8 tools/start_public_gui.py --stop

产物
----
    runs/public_gui_credentials.json   账号/口令/两个外网 URL（机密）
    runs/public_gui_state.json         本次启动的 PID 与端口（给 --stop 用）
    runs/public_gui_logs/*.log         各子进程日志（含 cloudflared 的域名 banner）
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from tunnel_auth import gen_password, HEALTH_PATH, validate_password  # noqa: E402

RUNS_DIR = os.path.join(ROOT, "runs")
LOG_DIR = os.path.join(RUNS_DIR, "public_gui_logs")
CRED_FILE = os.path.join(RUNS_DIR, "public_gui_credentials.json")
STATE_FILE = os.path.join(RUNS_DIR, "public_gui_state.json")

def _resolve_cloudflared():
    """跨平台找 cloudflared（原来写死 .exe，macOS/Linux 上必然失败）。

    与 portal_run.py 是同一个坑：Windows 上 `cloudflared.exe` 对，别的平台
    同目录里其实叫 `cloudflared`（无后缀）。写死后缀 → 公网功能整体哑掉，
    而路径打印出来"看着是对的"，极难发现。
    """
    home = os.path.expanduser("~")
    names = ["cloudflared.exe", "cloudflared"] if sys.platform == "win32" \
        else ["cloudflared", "cloudflared.exe"]
    for base in (os.path.join(home, ".dsh", "dsh-pocket", "bin"),
                 os.path.join(home, ".dsh", "bin"),
                 os.path.join(home, ".local", "bin"),
                 "/usr/local/bin", "/opt/homebrew/bin"):
        for name in names:
            candidate = os.path.join(base, name)
            if os.path.isfile(candidate):
                return candidate
    found = shutil.which("cloudflared")
    if found:
        return found
    return os.path.join(home, ".dsh", "dsh-pocket", "bin", names[0])


DEFAULT_CLOUDFLARED = _resolve_cloudflared()
# 拉起服务用的 python：**服务脚本在宿主仓库里**，所以解释器优先取宿主仓库的
# .venv313（依赖装在那里）。本仓库只是门户/隧道基础设施，通常没有自己的 venv。
# 迁移前这里写死 ROOT/.venv313 —— 当时基础设施与服务同仓所以成立；
# 拆开后必须跟着宿主走，否则会用错解释器（缺依赖 → 服务拉不起来）。
DEFAULT_HOST_REPO = os.environ.get("SERVICE_HOST_REPO", "")
DEFAULT_PYTHON = (os.path.join(DEFAULT_HOST_REPO, ".venv313", "Scripts", "python.exe")
                  if DEFAULT_HOST_REPO else "")

# 服务清单来源（2026-10-15 迁移）。
#
# 原实现把「训练配置台 + 模型查看台」硬编码在 TARGETS 里 —— 那是本插件的
# 第一个具体用途，但现在它是通用「对外服务门户」，清单必须可配置。
# 优先级：--services <json> > $SERVICE_PORTAL_SERVICES > services.json > 内置默认。
#
# hostRepo **不再预置任何人的本机路径**（默认空）：它是「被开放的服务放在哪」，
# 只有用户自己知道。这里的服务项是相对脚本名，会相对宿主仓库根解析 ——
# 所以宿主仓库为空时会在 main() 里直接给出可操作提示并返回 2，而不是拿空路径去猜。
DEFAULT_SERVICES = {
    "hostRepo": DEFAULT_HOST_REPO,
    "services": [
        {"key": "train", "script": "gui/server.py", "guiPort": 8810,
         "proxyPort": 8890, "name": "训练配置台", "mount": "train"},
        {"key": "viewer", "script": "gui/viewer_server.py", "guiPort": 8811,
         "proxyPort": 8891, "name": "模型查看台", "mount": "viewer"},
    ],
}
URL_RE = re.compile(r"https://[a-z0-9][a-z0-9-]*\.trycloudflare\.com")
# Windows：让子进程脱离本脚本存活（否则脚本一退出隧道就断）
_CREATE_FLAGS = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP


def load_services(path=None):
    """读服务清单，返回 (host_repo, TARGETS 六元组列表)。

    清单格式（services.json）:
        {"hostRepo": "D:\\\\path\\\\to\\\\host", "services": [
            {"key":"train","script":"gui/server.py","guiPort":8810,
             "proxyPort":8890,"name":"训练配置台","mount":"train"}, ...]}

    缺失/为空时回退到 DEFAULT_SERVICES —— 那是本项目最初的服务，
    不是「打不开」的默认值。
    """
    data = None
    for candidate in ([path] if path else []) + [
            os.environ.get("SERVICE_PORTAL_SERVICES"),
            os.path.join(ROOT, "services.json")]:
        if not candidate:
            continue
        if not os.path.isfile(candidate):
            if path:
                raise SystemExit("服务清单不存在：%s" % candidate)
            continue
        with open(candidate, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        print("服务清单：%s" % candidate)
        break
    if not data:
        data = DEFAULT_SERVICES

    host_repo = data.get("hostRepo") or DEFAULT_SERVICES["hostRepo"]
    rows = data.get("services") or []
    if not rows:
        raise SystemExit("服务清单里没有任何服务（services 为空）")
    targets = []
    for row in rows:
        try:
            targets.append((
                str(row["key"]), str(row["script"]), int(row["guiPort"]),
                int(row["proxyPort"]), str(row.get("name") or row["key"]),
                str(row.get("mount") or row["key"]),
            ))
        except (KeyError, TypeError, ValueError) as exc:
            raise SystemExit("服务清单某项不合法（%r）：%s" % (row, exc))
    return host_repo, tuple(targets)


def _log(name):
    os.makedirs(LOG_DIR, exist_ok=True)
    return os.path.join(LOG_DIR, name)


def port_listening(port, host="127.0.0.1"):
    """用 TCP 连接判断端口是否已有人在听。"""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.0)
        return sock.connect_ex((host, port)) == 0


def http_ok(url, timeout=4.0):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except Exception:
        return None


def spawn(argv, log_name, cwd=ROOT, env=None, detached=True):
    """起一个后台子进程，stdout/stderr 合并进日志文件，返回 Popen。"""
    handle = open(_log(log_name), "ab")
    kwargs = dict(cwd=cwd, stdout=handle, stderr=subprocess.STDOUT,
                  stdin=subprocess.DEVNULL, env=env)
    if os.name == "nt" and detached:
        kwargs["creationflags"] = _CREATE_FLAGS
    proc = subprocess.Popen(argv, **kwargs)
    proc._log_handle = handle  # 保持引用，避免被 GC 提前关闭
    return proc


def read_url(log_name, timeout=75.0, since=0):
    """从 cloudflared 日志里抓 quick tunnel 域名。

    必须只看**本次启动新增**的内容（``since`` = 启动前的文件字节数），
    并且取**最后一个**匹配。

    为什么（2026-10-15 实测踩到的真 bug）：日志是附加(append)写的，多次启动
    会累积多条域名。旧实现用 ``URL_RE.search(全文)`` 取第一条，于是第二次
    启动抓到的是**上一次残留的旧域名** —— 凭据文件因此记下一个已经失效的
    地址，而真正可用的新域名从未被记录。症状极隐蔽：脚本报成功、代理端口
    在听、状态显示 running=true，但外网打开是 Cloudflare 530。这正是本项目
    最忌讳的「不崩、只给错误答案」。
    """
    path = _log(log_name)
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                handle.seek(since)
                text = handle.read()
        except OSError:
            text = ""
        found = URL_RE.findall(text)
        if found:
            return found[-1]  # 取最后一条：那就是本次刚创建的
        if "failed to request quick Tunnel" in text or "ERR " in text:
            return None
        time.sleep(1.0)
    return None


def start_gui_if_needed(python_exe, script, port, name, cwd=None):
    """GUI 未监听则拉起；返回 (pid_or_None, 是否本次启动)。

    ``cwd`` = 服务脚本所在的宿主仓库根（迁移后不再固定是本仓库 ROOT）：
    GUI 脚本路径是相对宿主仓库的（例如 ld-rl-poker 的 gui/server.py），
    它自己还会按 ROOT 去找同级模块，所以工作目录必须设对。
    """
    if port_listening(port):
        return None, False
    log = _log("gui_%d.log" % port)
    handle = open(log, "ab")
    proc = subprocess.Popen([python_exe, "-X", "utf8", script, "--port", str(port)],
                            cwd=cwd or ROOT, stdout=handle, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL)
    proc._log_handle = handle
    deadline = time.time() + 30
    while time.time() < deadline:
        if port_listening(port):
            return proc.pid, True
        if proc.poll() is not None:
            print("  ! %s 启动失败（退出码 %s），见 %s"
                  % (name, proc.returncode, log), file=sys.stderr)
            return proc.pid, True
        time.sleep(0.5)
    print("  ! %s 30 秒内未就绪（PID %s）" % (name, proc.pid), file=sys.stderr)
    return proc.pid, True


def start_proxy(python_exe, upstream_port, proxy_port, password,
                strip_prefix="", mounts=()):
    """起认证代理；口令走环境变量，不进命令行。

    认证形态：**只需口令**（自定义登录页 + 签名会话 cookie），没有账号。
    本机调试走 http，故传 --insecure-cookie 让 cookie 不带 Secure —— 否则
    浏览器在 http 下不会回传 cookie（外网经 cloudflared 恒为 https，无此问题）。
    """
    argv = [python_exe, "-X", "utf8", os.path.join(HERE, "tunnel_auth.py"),
            "--listen", str(proxy_port),
            "--upstream", "127.0.0.1:%d" % upstream_port,
            "--insecure-cookie"]
    if strip_prefix:
        argv += ["--strip-prefix", strip_prefix]
    if mounts:
        argv += ["--mounts", ",".join("%s=%s:%d" % row for row in mounts)]
    env = dict(os.environ, GUI_TUNNEL_PASSWORD=password,
               PYTHONIOENCODING="utf-8")
    proc = spawn(argv, "proxy_%d.log" % proxy_port, env=env)
    deadline = time.time() + 20
    while time.time() < deadline:
        if http_ok("http://127.0.0.1:%d%s" % (proxy_port, HEALTH_PATH)) == 200:
            return proc
        if proc.poll() is not None:
            print("  ! 认证代理 %d 启动失败（退出码 %s），见 %s"
                  % (proxy_port, proc.returncode, _log("proxy_%d.log" % proxy_port)),
                  file=sys.stderr)
            return None
        time.sleep(0.5)
    print("  ! 认证代理 %d 未就绪" % proxy_port, file=sys.stderr)
    return None


def start_tunnel(cloudflared, proxy_port, log_name):
    """起 cloudflared quick tunnel（随机域名），返回 (Popen, url)。

    先记下日志已有长度，只读本次新增部分 —— 否则会抓到上一次启动残留的
    旧域名（详见 read_url 的注释）。
    """
    try:
        since = os.path.getsize(_log(log_name))
    except OSError:
        since = 0
    proc = spawn([cloudflared, "--no-autoupdate", "tunnel",
                  "--url", "http://127.0.0.1:%d" % proxy_port,
                  "--protocol", "http2"], log_name)
    url = read_url(log_name, since=since)
    return proc, url


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def stop_all(quiet=False):
    """停掉本脚本记录的进程（不动 dsh-pocket 的隧道与手动开的 GUI）。"""
    state = load_state()
    if not state:
        if not quiet:
            print("没有找到 %s —— 没有本脚本启动的进程可停。" % STATE_FILE)
        return 0
    import ctypes
    killed = []
    for item in state.get("processes", []):
        pid = item.get("pid")
        if not pid:
            continue
        try:
            handle = ctypes.windll.kernel32.OpenProcess(0x0001, False, int(pid))
            if handle:
                ctypes.windll.kernel32.TerminateProcess(handle, 1)
                ctypes.windll.kernel32.CloseHandle(handle)
                killed.append("%s(%s)" % (item.get("role", "?"), pid))
        except Exception as exc:
            print("  ! 结束 %s 失败：%r" % (pid, exc), file=sys.stderr)
    for path in (STATE_FILE, CRED_FILE):
        try:
            os.remove(path)
        except OSError:
            pass
    if not quiet:
        print("已停止 %d 个进程：%s" % (len(killed), ", ".join(killed) or "（无）"))
        print("凭据文件已删除：%s" % CRED_FILE)
        print("注意：GUI 本体（8810/8811）与 dsh-pocket 的隧道未受影响。")
    return 0


def print_status():
    state = load_state()
    if not state:
        print("当前没有本脚本启动的公开入口。")
        return 0
    try:
        with open(CRED_FILE, "r", encoding="utf-8") as handle:
            cred = json.load(handle)
    except (OSError, ValueError):
        cred = {}
    print("启动时间：%s" % state.get("started_at"))
    if cred.get("mode") == "single-domain":
        print("模式    ：单域名 + 路径")
        print("入口    ：%s/" % (cred.get("base_url") or "").rstrip("/"))
    print("口令    ：%s" % cred.get("password"))
    for key, info in (cred.get("endpoints") or {}).items():
        alive = port_listening(info.get("proxy_port", 0))
        print("  [%s] %s  %s  (本地代理 %s，%s)"
              % (key, info.get("name"), info.get("url"),
                 info.get("proxy_port"), "存活" if alive else "已停止"))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="把配置台/查看台通过 cloudflared 公开到外网（随机域名 + 随机口令）")
    ap.add_argument("--cloudflared", default=DEFAULT_CLOUDFLARED,
                    help="cloudflared 可执行文件路径（默认自动探测）")
    ap.add_argument("--python", default=DEFAULT_PYTHON,
                    help="拉起 GUI 用的 python（默认 .venv313）")
    ap.add_argument("--no-user", action="store_true",
                    help=argparse.SUPPRESS)  # 兼容旧调用：账号已取消，静默忽略
    ap.add_argument("--password", default="",
                    help="固定口令；不给则每次启动自动随机生成一个新口令")
    ap.add_argument("--password-mode", default="random",
                    choices=("random", "fixed"),
                    help="口令形态：random=每次启动随机生成（默认）；"
                         "fixed=用 --password/--password-file 指定的固定口令")
    ap.add_argument("--password-file", default=None,
                    help="从文件读固定口令（推荐：口令不进命令行）；"
                         "给了它等同于 --password-mode fixed")
    ap.add_argument("--only", default=None,
                    help="只公开某个服务（用清单里的 key，默认全部）")
    ap.add_argument("--services", default=None,
                    help="服务清单 JSON 路径（默认 services.json 或内置清单）")
    ap.add_argument("--single-domain", action="store_true",
                    help="单域名 + 路径模式：一个域名下每个服务一个子路径")
    ap.add_argument("--single-port", type=int, default=8899,
                    help="单域名模式下认证代理的监听端口（默认 8899）")
    ap.add_argument("--stop", action="store_true", help="停止本脚本启动的进程")
    ap.add_argument("--status", action="store_true", help="只显示当前状态")
    args = ap.parse_args(argv)

    if args.stop:
        return stop_all()
    if args.status:
        return print_status()

    host_repo, TARGETS = load_services(args.services)
    # 宿主仓库为空 = 还没配过（默认不再猜作者本机的路径）。这里必须给一句
    # **可操作**的话，而不是让 os.path.isdir("") 报「宿主仓库不存在：」——
    # 用户看到空路径只会更困惑，不知道要填什么。
    if not host_repo:
        print("还没指定宿主仓库（被开放的服务本体所在目录）。三选一：\n"
              "  · 设置页：DSH 设置 → 插件 → dsh-service-portal → repoPath 填宿主仓库根\n"
              "  · 环境变量：set SERVICE_HOST_REPO=<宿主仓库根>\n"
              "  · 服务清单：写一个 services.json，填好 hostRepo，再用 --services 指过去\n"
              "然后把宿主仓库根配上，或直接在设置页里改即可。",
              file=sys.stderr)
        return 2
    if not os.path.isdir(host_repo):
        print("宿主仓库不存在：%s（可用 --services 指定清单，或设 SERVICE_HOST_REPO）"
              % host_repo, file=sys.stderr)
        return 2

    if not os.path.isfile(args.cloudflared):
        print("找不到 cloudflared：%s\n可用 --cloudflared 指定。" % args.cloudflared,
              file=sys.stderr)
        return 2
    python_exe = args.python if os.path.isfile(args.python) else sys.executable
    if not os.path.isfile(args.python):
        # 空字符串要单独说清楚：默认已不再猜宿主仓库，所以「未找到 ，
        # 改用 /usr/bin/python3」这种带空路径的提示会让人看不出该填什么。
        if not args.python:
            print("提示：未指定拉服务用的 python（宿主仓库未配置，无法推断 .venv313），"
                  "改用 %s。可用 --python 指定，或在宿主仓库配好 .venv313。"
                  % python_exe, file=sys.stderr)
        else:
            print("提示：未找到 %s，改用 %s" % (args.python, python_exe), file=sys.stderr)

    # 陈旧状态：先清掉上次的隧道，避免堆积
    if load_state():
        print("检测到上一次的公开入口，先停掉：")
        stop_all(quiet=True)

    # 口令两形态：
    #   random —— 每次启动都生成新口令（默认；域名与口令都换，泄漏窗口最小）
    #   fixed  —— 用用户设定的固定口令（方便；但口令在多次开启间不变，
    #             一旦泄漏就是长期有效，故启动时明确提示）
    fixed_password = ""
    if args.password_file:
        try:
            with open(args.password_file, "r", encoding="utf-8") as handle:
                fixed_password = handle.read().strip()
        except OSError as exc:
            print("读不到 --password-file：%s" % exc, file=sys.stderr)
            return 2
    elif args.password.strip():
        fixed_password = args.password.strip()

    if args.password_mode == "fixed" or fixed_password:
        if not fixed_password:
            print("拒绝启动：--password-mode fixed 必须同时给出 --password "
                  "或 --password-file", file=sys.stderr)
            return 2
        password = fixed_password
        password_mode = "fixed"
    else:
        password = gen_password(12)
        password_mode = "random"
    try:
        validate_password(password)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    selected = [t for t in TARGETS
                if args.only is None or t[0] == args.only.strip()]
    if not selected:
        print("--only 只接受清单里的 key：%s"
              % " / ".join(t[0] for t in TARGETS), file=sys.stderr)
        return 2

    os.makedirs(LOG_DIR, exist_ok=True)
    processes = []
    endpoints = {}
    started_at = time.strftime("%Y-%m-%d %H:%M:%S")

    # ---- 单域名 + 路径模式（用户最初想要的形态）----
    if args.single_domain:
        print("=" * 72)
        print("公开 GUI 到外网（单域名 + 路径，随机域名 + 随机口令）")
        print("=" * 72)
        mounts = []
        for key, script, gui_port, proxy_port, name, mount in selected:
            print("\n[%s] %s -> /%s/" % (key, name, mount))
            gui_pid, launched = start_gui_if_needed(python_exe, script, gui_port, name,
                                                    cwd=host_repo)
            if launched and gui_pid:
                processes.append({"role": "gui_%s" % key, "pid": gui_pid})
                print("  · GUI 已拉起（PID %s，端口 %d）" % (gui_pid, gui_port))
            else:
                print("  · 复用已在运行的 GUI（端口 %d）" % gui_port)
            if not port_listening(gui_port):
                print("  ! 端口 %d 未就绪，跳过 /%s/" % (gui_port, mount), file=sys.stderr)
                continue
            mounts.append(("/" + mount, "127.0.0.1", gui_port))
            endpoints[key] = {"name": name, "url": None, "path": "/%s/" % mount,
                              "proxy_port": args.single_port, "gui_port": gui_port}

        if not mounts:
            print("\n没有任何上游就绪。", file=sys.stderr)
            return 1
        if port_listening(args.single_port):
            print("  ! 端口 %d 已被占用，无法建立单域名代理" % args.single_port,
                  file=sys.stderr)
            return 1

        proxy = start_proxy(python_exe, args.single_port, args.single_port,
                            password, mounts=mounts)
        if proxy is None:
            return 1
        processes.append({"role": "proxy_single", "pid": proxy.pid})
        print("\n  · 认证代理已启动（PID %s，端口 %d，%d 个挂载点）"
              % (proxy.pid, args.single_port, len(mounts)))

        tunnel, url = start_tunnel(args.cloudflared, args.single_port,
                                   "cloudflared_%d.log" % args.single_port)
        processes.append({"role": "tunnel_single", "pid": tunnel.pid})
        if not url:
            print("  ! 未取到随机域名，见 %s"
                  % _log("cloudflared_%d.log" % args.single_port), file=sys.stderr)
            return 1
        print("  · 隧道已建立（PID %s）：%s" % (tunnel.pid, url))
        for key, info in endpoints.items():
            info["url"] = url.rstrip("/") + info["path"]

        credentials = {
            "warning": "本文件含明文口令，属机密文件；不要提交、不要外发。",
            "started_at": started_at,
            "password": password,
            "password_mode": password_mode,
            "auth": "HTTP Basic Auth",
            "mode": "single-domain",
            "base_url": url,
            "mounts": {row[0]: "%s:%d" % (row[1], row[2]) for row in mounts},
            "endpoints": endpoints,
        }
        with open(CRED_FILE, "w", encoding="utf-8") as handle:
            json.dump(credentials, handle, ensure_ascii=False, indent=2)
        with open(STATE_FILE, "w", encoding="utf-8") as handle:
            json.dump({"started_at": started_at, "processes": processes},
                      handle, ensure_ascii=False, indent=2)

        print("\n" + "=" * 72)
        print("外网入口（同一个域名，不同路径；域名每次启动都换）")
        print("=" * 72)
        print("  %s/" % url.rstrip("/"))
        for key, info in endpoints.items():
            print("    /%s" % info["path"].strip("/") + "  →  " + info["name"])
        print("\n口令：%s   （%s）"
              % (password, "固定口令" if password_mode == "fixed" else "本次随机生成"))
        print("\n凭据文件：%s（含明文口令，勿外发）" % CRED_FILE)
        print("停止：python -X utf8 tools/start_public_gui.py --stop")
        print("状态：python -X utf8 tools/start_public_gui.py --status")
        return 0

    print("=" * 72)
    print("公开 GUI 到外网（随机域名 + 随机口令）")
    print("=" * 72)
    for key, script, gui_port, proxy_port, name, _mount in selected:
        print("\n[%s] %s" % (key, name))

        gui_pid, launched = start_gui_if_needed(python_exe, script, gui_port, name,
                                                cwd=host_repo)
        if launched and gui_pid:
            processes.append({"role": "gui_%s" % key, "pid": gui_pid})
            print("  · GUI 已拉起（PID %s，端口 %d）" % (gui_pid, gui_port))
        else:
            print("  · 复用已在运行的 GUI（端口 %d）" % gui_port)
        if not port_listening(gui_port):
            print("  ! 端口 %d 未就绪，跳过 %s" % (gui_port, name), file=sys.stderr)
            continue

        if port_listening(proxy_port):
            print("  ! 端口 %d 已被占用，跳过 %s（先释放或改端口）"
                  % (proxy_port, name), file=sys.stderr)
            continue

        proxy = start_proxy(python_exe, gui_port, proxy_port, password)
        if proxy is None:
            continue
        processes.append({"role": "proxy_%s" % key, "pid": proxy.pid})
        print("  · 认证代理已启动（PID %s，127.0.0.1:%d → 127.0.0.1:%d）"
              % (proxy.pid, proxy_port, gui_port))

        tunnel, url = start_tunnel(args.cloudflared, proxy_port,
                                   "cloudflared_%d.log" % proxy_port)
        processes.append({"role": "tunnel_%s" % key, "pid": tunnel.pid})
        if not url:
            print("  ! 未取到随机域名，见 %s" % _log("cloudflared_%d.log" % proxy_port),
                  file=sys.stderr)
            continue
        print("  · 隧道已建立（PID %s）：%s" % (tunnel.pid, url))
        endpoints[key] = {"name": name, "url": url, "proxy_port": proxy_port,
                          "gui_port": gui_port}

    if not endpoints:
        print("\n没有任何端点成功建立。", file=sys.stderr)
        return 1

    credentials = {
        "warning": "本文件含明文口令，属机密文件；不要提交、不要外发。",
        "started_at": started_at,
        "password": password,
        "password_mode": password_mode,
        "auth": "HTTP Basic Auth",
        "endpoints": endpoints,
    }
    with open(CRED_FILE, "w", encoding="utf-8") as handle:
        json.dump(credentials, handle, ensure_ascii=False, indent=2)
    with open(STATE_FILE, "w", encoding="utf-8") as handle:
        json.dump({"started_at": started_at, "processes": processes},
                  handle, ensure_ascii=False, indent=2)

    print("\n" + "=" * 72)
    print("外网入口（域名每次启动都换）")
    print("=" * 72)
    for key, info in endpoints.items():
        print("  %s：%s" % (info["name"], info["url"]))
    print("\n口令：%s   （%s）"
          % (password, "固定口令" if password_mode == "fixed" else "本次随机生成"))
    print("\n凭据文件：%s（含明文口令，勿外发）" % CRED_FILE)
    print("停止：python -X utf8 tools/start_public_gui.py --stop")
    print("状态：python -X utf8 tools/start_public_gui.py --status")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
