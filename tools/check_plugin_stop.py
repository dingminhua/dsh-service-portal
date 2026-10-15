# -*- coding: utf-8 -*-
"""插件「停止门户」这条路（stopPublic）的集成检验。

为什么单独测它：这是设置页「停止门户」按钮真正走的路径，而它原先只有
`portal_run.py --stop` 一条路 —— 在某些环境里那条路是**假成功**：
宿主派生的子进程与门户不在同一个作业/沙箱内，taskkill 回「找不到进程」(128)，
而门户还在应答；子进程连 runs/portal_state.json 都写不进去（Errno 13）。
用户看到的现象就是「点了停止没反应」。

现在 stopPublic 先 HTTP 请门户**自己退**，再退回 --stop。

隔离方式：把 tools/ 复制到临时目录当 infraPath，门户状态写临时 runs/，
**完全不碰用户真实的 runs/**（里面有局域网口令和用户注册的服务）。

运行：python -X utf8 tools/check_plugin_stop.py
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable
NODE = os.environ.get("DSH_NODE") or shutil.which("node")

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


def alive(port):
    try:
        with urllib.request.urlopen(
                "http://127.0.0.1:%d/_auth/health" % port, timeout=3) as res:
            return res.status == 200
    except Exception:
        return False


NODE_CALL = r"""
import { _internals } from %(lib)s;

const port = Number(process.argv[2]);
const infra = process.argv[3];
const python = process.argv[4];
const repo = { infraPath: infra, repoPath: infra, pythonPath: python,
               portalPort: port, webEnabled: true };
const out = await _internals.stopPublic(repo);
console.log("RESULT " + JSON.stringify({
  ok: out.ok, stoppedBy: out.stoppedBy, exitCode: out.exitCode,
  stdout: String(out.stdout || "").slice(0, 200),
  stderr: String(out.stderr || "").slice(0, 300),
}));
"""


def main():
    if not NODE:
        print("找不到 node（可用 DSH_NODE 指定）")
        return 1
    tmp = tempfile.mkdtemp(prefix="plugin-stop-")
    runs = os.path.join(tmp, "runs")
    infra = os.path.join(tmp, "infra")
    os.makedirs(runs, exist_ok=True)
    os.makedirs(infra, exist_ok=True)
    # tools/ 复制一份当基础设施仓库（portal_run.py 从自己所在目录往里找同级模块）
    shutil.copytree(HERE, os.path.join(infra, "tools"))
    port = free_port()
    log = open(os.path.join(tmp, "portal.log"), "wb")
    proc = subprocess.Popen(
        [PY, "-X", "utf8", os.path.join(infra, "tools", "portal_run.py"),
         "--port", str(port), "--password", "plugin-stop-password", "--lan-only"],
        cwd=infra, stdout=log, stderr=subprocess.STDOUT,
        env=dict(os.environ, PORTAL_RUNS_DIR=runs))
    try:
        ready = False
        for _ in range(60):
            if alive(port):
                ready = True
                break
            time.sleep(0.5)
        check("门户起来了（前提）", ready, "port=%d" % port)
        if not ready:
            return 1

        node_file = os.path.join(tmp, "call_stop.mjs")
        with open(node_file, "w", encoding="utf-8") as handle:
            handle.write(NODE_CALL % {"lib": json.dumps(
                "file:///" + os.path.join(ROOT, "lib", "index.js").replace("\\", "/"))})
        done = subprocess.run(
            [NODE, node_file, str(port), infra, PY],
            cwd=ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=180)
        payload = None
        for line in (done.stdout or "").splitlines():
            if line.startswith("RESULT "):
                payload = json.loads(line[len("RESULT "):])
        if payload is None:
            check("stopPublic 有结果输出", False,
                  "stdout=%r stderr=%r" % ((done.stdout or "")[:300],
                                           (done.stderr or "")[:300]))
            return 1
        check("stopPublic 认为停好了（ok=true）", payload.get("ok") is True,
              "payload=%r" % (payload,))
        check("走的是「请门户自己退」这条路", payload.get("stoppedBy") == "self",
              "stoppedBy=%r stdout=%r" % (payload.get("stoppedBy"),
                                          payload.get("stdout")))
        gone = False
        for _ in range(40):
            if not alive(port):
                gone = True
                break
            time.sleep(0.25)
        check("端口/服务确实没了（不是只有返回值好看）", gone, "port=%d" % port)
        check("门户进程也真的退出了", proc.poll() is not None,
              "poll=%r" % (proc.poll(),))
        # 状态文件里该留下"停止过"的痕迹（设置页据此不报红字）
        state_path = os.path.join(runs, "portal_state.json")
        state = None
        if os.path.exists(state_path):
            with open(state_path, "r", encoding="utf-8") as handle:
                state = json.load(handle)
        check("状态文件被标成已停止（设置页不再报红字）",
              bool(state) and state.get("stopped_clean") is True,
              "state=%r" % (state,))

        passed = sum(1 for ok, _, _ in results if ok)
        print("\n插件停止路径集成检验：%d/%d" % (passed, len(results)))
        return 0 if passed == len(results) else 1
    finally:
        if proc.poll() is None:
            proc.kill()
        try:
            log.close()
        except Exception:
            pass
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
