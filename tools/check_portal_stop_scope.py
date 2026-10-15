# -*- coding: utf-8 -*-
"""`--stop` 的作用域控制检验（拦"顺手把用户的门户杀了"这类 bug）。

背景（真实事故）：
  检验脚本里一句裸的 `python tools/portal_run.py --stop`，把用户**正在运行**的
  门户干掉了 —— 用户看到页面上的二维码和访问地址一起消失，以为是插件把功能删了。

根因：`stop_all()` 的端口兜底默认扫 DEFAULT_PORTAL_PORT(8899)，
而 `--stop` 调用点传的是 `args.port`（argparse 默认值 = 8899），
于是"停我这一个"变成了"杀掉任何监听 8899 的进程"。

本检验打的是行为，不是文案：
  ① `--port N --stop`：明确要求了才按端口扫（正例控制：必须真能停掉）；
  ② 裸 `--stop`：只管状态文件里记的那个进程，**不碰**同端口上别的监听者；
  ③ `--stop` 之后状态文件**仍然存在**，且局域网口令/候选地址这些偏好还在
     （删掉整个文件会让"局域网口令重启后不变"失效）；
  ④ 反例控制：本来没有偏好时，不会凭空造出局域网口令。

注意（写检验时踩过）：占端口的"别的程序"必须是**独立进程**。第一版用
本进程内的线程起 HTTP 服务，结果 `--port N --stop` 按端口扫到的 pid 就是
检验脚本自己 —— `taskkill /T /F` 把自己杀了，表现为"零输出 + 退出码 1"。

运行：python -X utf8 tools/check_portal_stop_scope.py
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable
SCRIPT = os.path.join(HERE, "portal_run.py")

results = []


def check(name, ok, detail=""):
    results.append((bool(ok), name, detail))
    print(("PASS  " if ok else "FAIL  ") + name + ((" —— " + detail) if detail else ""))


def free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def port_open(port):
    sock = socket.socket()
    sock.settimeout(1.5)
    try:
        sock.connect(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def start_decoy(port, portal_like=False):
    """起一个**独立进程**占着这个端口。

    portal_like=True：对 `/_auth/health` 回 200 + {"ok": true}，
    模拟"这端口上真的是我们的门户"；否则是普通 http.server（对该路径回 404），
    模拟"端口被别的程序占了"。
    """
    if portal_like:
        code = (
            "from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer\n"
            "class H(BaseHTTPRequestHandler):\n"
            "    def do_GET(self):\n"
            "        body = b'{\"ok\": true}'\n"
            "        self.send_response(200)\n"
            "        self.send_header('Content-Type', 'application/json')\n"
            "        self.send_header('Content-Length', str(len(body)))\n"
            "        self.end_headers()\n"
            "        self.wfile.write(body)\n"
            "    def log_message(self, *a):\n"
            "        pass\n"
            "ThreadingHTTPServer(('127.0.0.1', %d), H).serve_forever()\n" % port
        )
        proc = subprocess.Popen([PY, "-X", "utf8", "-c", code],
                                cwd=tempfile.gettempdir(),
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
    else:
        proc = subprocess.Popen(
            [PY, "-X", "utf8", "-m", "http.server", str(port), "--bind", "127.0.0.1"],
            cwd=tempfile.gettempdir(),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        if port_open(port):
            break
        time.sleep(0.15)
    return proc


def run_stop(runs_dir, *extra):
    env = dict(os.environ, PORTAL_RUNS_DIR=runs_dir)
    return subprocess.run([PY, "-X", "utf8", SCRIPT, "--stop", *extra],
                          cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env, timeout=90)


def write_state(runs_dir, state):
    os.makedirs(runs_dir, exist_ok=True)
    with open(os.path.join(runs_dir, "portal_state.json"), "w",
              encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False)


def read_state(runs_dir):
    path = os.path.join(runs_dir, "portal_state.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def main():
    root = tempfile.mkdtemp(prefix="portal-stop-scope-")
    decoys = []
    # 每个场景一个独立的"仓库状态目录"：不隔离的话，后面场景的 --stop
    # 会把前面场景刚写下的状态覆盖掉，断言就测错了对象（第一版踩过）。
    d_ok = os.path.join(root, "ok")
    d_foreign = os.path.join(root, "foreign")
    d_bare = os.path.join(root, "bare")
    d_empty = os.path.join(root, "empty")
    try:
        # ---- ① 正例控制：端口上是"我们的门户"时，显式 --port N 必须真能停掉 ----
        # 先证明这个检验"看得见行为"，否则下面的"没被误杀"可能只是没生效。
        victim_port = free_port()
        decoys.append(start_decoy(victim_port, portal_like=True))
        write_state(d_ok, {"portal_pid": 999999, "portal_port": victim_port,
                           "lan_password": "24681357",
                           "lan_pin_custom": True,
                           "lan_candidates": ["192.168.1.7"]})
        run_stop(d_ok, "--port", str(victim_port))
        time.sleep(0.8)
        check("显式 --port N --stop：端口上是本门户时确实停掉了（正例控制）",
              not port_open(victim_port), "端口 %d" % victim_port)

        # ---- ③ 停止成功后：状态文件还在，偏好还留着，运行痕迹清掉 ----
        state = read_state(d_ok)
        check("--stop 之后状态文件仍然存在（不是整个删掉）", state is not None)
        check("局域网口令被保留（重启后不变，用户手机里存过）",
              bool(state) and state.get("lan_password") == "24681357",
              "state=%r" % (state,))
        check("自定义口令标记被保留（否则用户以为「我设过固定口令」）",
              bool(state) and state.get("lan_pin_custom") is True)
        check("网卡候选被保留（设置页未启动时才能显示将用地址）",
              bool(state) and state.get("lan_candidates") == ["192.168.1.7"])
        check("停止被标记为「干净停止」（设置页据此不再报红字）",
              bool(state) and state.get("stopped_clean") is True)
        check("运行痕迹（pid/端口）被清掉，不会显示成「还在跑」",
              bool(state) and not state.get("portal_pid")
              and not state.get("portal_port"))

        # ---- ①b 反例控制：端口上**不是**我们的门户时，即使给了 --port 也不许杀 ----
        # 只认"端口上有人"就杀，会误杀端口被别的程序占用的机器。
        foreign_port = free_port()
        decoys.append(start_decoy(foreign_port, portal_like=False))
        write_state(d_foreign, {"portal_port": foreign_port,
                                "lan_password": "24681357"})
        foreign = run_stop(d_foreign, "--port", str(foreign_port))
        time.sleep(0.6)
        check("别的程序占着端口时：--stop 不碰它（要看 /_auth/health 认不认）",
              port_open(foreign_port),
              "端口 %d 仍被占；stderr=%r" % (foreign_port,
                                          (foreign.stderr or "").strip()[:80]))
        foreign_state = read_state(d_foreign)
        check("不碰它，也不谎报杀掉了它（stdout 不能说「已停止门户进程」）",
              "已停止门户进程" not in (foreign.stdout or ""),
              "stdout=%r" % (foreign.stdout or "").strip())
        # 我们的门户确实没在跑 → 标记成"干净停止"是对的（设置页不该因此报红字）
        check("按端口扫到的东西不是我们的 → 状态按「本门户没在跑」处理",
              bool(foreign_state) and not foreign_state.get("portal_port"),
              "state=%r" % (foreign_state,))

        # ---- ② 裸 --stop：不能碰"别的程序"占着的端口 ----
        # 状态文件里只有一个**已经退出**的 pid、且没写端口：此时唯一可能被
        # 误杀的就是"按默认端口扫"的那个兜底。它必须什么都没做。
        other_port = free_port()
        decoys.append(start_decoy(other_port))
        write_state(d_bare, {"portal_pid": 999999, "lan_password": "24681357"})
        bare = run_stop(d_bare)
        time.sleep(0.6)
        check("裸 --stop（状态文件里没有端口）：不猜测、不误杀别的监听者",
              port_open(other_port),
              "别的进程仍在监听 %d；输出=%r" % (other_port,
                                             (bare.stdout or "").strip()))
        check("旧 pid 已经不在了 → 算「停好了」而不是失败（返回码 0）",
              bare.returncode == 0, "returncode=%d" % bare.returncode)

        # ---- ④ 反例控制：本来没有的偏好，不能凭空多出来 ----
        run_stop(d_empty)
        empty = read_state(d_empty)
        check("反例：没有偏好可留时，不会凭空造出局域网口令",
              empty is not None and not empty.get("lan_password"),
              "state=%r" % (empty,))

        passed = sum(1 for ok, _, _ in results if ok)
        print("\n停止作用域控制检验：%d/%d" % (passed, len(results)))
        return 0 if passed == len(results) else 1
    finally:
        for proc in decoys:
            try:
                proc.kill()
            except Exception:
                pass
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
