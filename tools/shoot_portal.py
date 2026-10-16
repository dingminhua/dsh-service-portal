# -*- coding: utf-8 -*-
"""起一个**真的**门户（跑新代码）+ 无头 Chrome 截图，人工核对页面。

为什么不直接截用户线上的 8899：那个进程里是**改动前**的 portal_console 模块
（Python 一 import 就固定），要看到新页必须重启用户的门户 —— 重启会换掉
cloudflared 隧道域名（用户可能已经把地址发出去了）。所以这里在临时端口起一个
真门户：同一段渲染代码、真 HTTP、真状态，只是不碰用户的进程。

用法：python -X utf8 tools/shoot_portal.py
"""
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "runs", "shots")


def find_chrome():
    """找一个无头浏览器。环境变量 CHROME 优先，其次按平台常见安装位置找。

    原来这里写死 r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" ——
    只有作者的 Windows 机器成立（本仓库的截图为实测要求跨平台可跑）。
    """
    env = os.environ.get("CHROME")
    if env and os.path.isfile(env):
        return env
    candidates = []
    if sys.platform == "darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        ]
    elif os.name == "nt":
        candidates = [
            os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                         r"Google\Chrome\Application\chrome.exe"),
            os.path.join(os.environ.get("ProgramFiles(x86)",
                                        r"C:\Program Files (x86)"),
                         r"Google\Chrome\Application\chrome.exe"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""),
                         r"Google\Chrome\Application\chrome.exe"),
        ]
    else:
        candidates = [
            "/usr/bin/google-chrome", "/usr/bin/chromium",
            "/usr/bin/chromium-browser", "/snap/bin/chromium",
        ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    raise SystemExit(
        "找不到无头浏览器。设环境变量 CHROME 指向可执行文件，或装 Chrome/Chromium。")


CHROME = None  # 由 main() 调 find_chrome() 填充（import 期不探文件系统）

STATE_SERVICES = [
    {"key": "realapp", "name": "真实应用", "mount": "/realapp",
     "target": "127.0.0.1:2460", "enabled": True, "note": ""},
    {"key": "rltrain", "name": "RL配置训练台", "mount": "/rltrain",
     "target": "127.0.0.1:8810", "enabled": True, "note": "111"},
    {"key": "viewer", "name": "模型查看台", "mount": "/viewer",
     "target": "127.0.0.1:8811", "enabled": False, "note": "test"},
]


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def main():
    global CHROME
    CHROME = find_chrome()
    os.makedirs(OUT, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="shoot-")
    runs = os.path.join(tmp, "runs")
    os.makedirs(runs, exist_ok=True)
    with io.open(os.path.join(runs, "portal_registry.json"), "w",
                 encoding="utf-8", newline="") as fh:
        json.dump({"services": STATE_SERVICES}, fh, ensure_ascii=False)

    port = free_port()
    log = io.open(os.path.join(tmp, "portal.log"), "wb")
    proc = subprocess.Popen(
        [sys.executable, "-X", "utf8", os.path.join(HERE, "portal_run.py"),
         "--port", str(port), "--password", "shoot-password-1", "--lan-only"],
        cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
        env=dict(os.environ, PORTAL_RUNS_DIR=runs))
    try:
        for _ in range(80):
            try:
                socket.create_connection(("127.0.0.1", port), 0.5).close()
                break
            except OSError:
                time.sleep(0.5)

        prof = os.path.join(tmp, "chrome")
        url = "http://127.0.0.1:%d/" % port
        for name, args in (
            ("real-phone.png", ["--window-size=520,1700"]),
            ("real-phone-dark.png", ["--window-size=520,1700", "--force-dark-mode"]),
            ("real-wide.png", ["--window-size=1000,1400"]),
        ):
            target = os.path.join(OUT, name)
            subprocess.run([CHROME, "--headless", "--disable-gpu", "--no-sandbox",
                            "--user-data-dir=" + prof, "--hide-scrollbars"] + args
                           + ["--screenshot=" + target, url],
                           capture_output=True, timeout=120)
            print("  已截图 %s" % target)

        html = urllib.request.urlopen(url, timeout=10).read().decode("utf-8")
        print("\n  真门户返回的页面：")
        print("    标题       : %s" % ("对外服务门户" in html))
        print("    测试按钮   : %d 个" % html.count('class="btn probe"'))
        print("    鼓励一下   : %s" % ("鼓励一下 ★" in html))
        print("    语义令牌   : %s" % ("--brand:" in html))
        print("    写操作入口 : %s" % ("/_api/services/" in html))
        return 0
    finally:
        try:
            urllib.request.urlopen(urllib.request.Request(
                "http://127.0.0.1:%d/_api/shutdown" % port, data=b"",
                method="POST", headers={"Content-Length": "0"}), timeout=6).read()
        except Exception:
            pass
        time.sleep(1.5)
        if proc.poll() is None:
            proc.kill()
        try:
            log.close()
        except Exception:
            pass
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
