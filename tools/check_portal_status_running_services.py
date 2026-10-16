# -*- coding: utf-8 -*-
"""「添加服务后设置页看不到」这个真 bug 的控制检验。

## 现象（用户报的）
用户在插件设置里添加了一个服务（`训练 /rl-train`），门户那边**存下来了**
（`/_api/state` 报 4 个服务），但设置页的清单还是空的 —— 就是"看不到"。

## 根因
`readPortalStatus` 只在 `needLive` 为真时才去问活着的门户要实时状态：

    const needLive = !Array.isArray(state.lan_urls) || state.lan_urls.length === 0
      || !state.password;

而 `lan_urls` 和 `password` 在状态文件（runs/portal_state.json）里**一般都有**，
于是 `needLive` 恒为 false —— **从来不去问活门户**。服务清单只在门户内存里，
状态文件从来不写它，所以 `services` 永远是空数组。

## 本检验怎么抓它
造一个"状态文件里地址/口令都齐、但没有 services"的场景（真实情况），
起一个真门户（它内存里有服务），然后调 `readPortalStatus`：
  · 修复前：services 为空（因为不去问活门户）
  · 修复后：services 有内容（问活门户拿到了）
反例控制：门户**没在跑**时，services 必须是空数组（不能凭空编造）。

运行：python -X utf8 tools/check_portal_status_running_services.py
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


def call_status(infra, port):
    """用真实 readPortalStatus 取状态（走 node，因为要 import ESM）。"""
    script = os.path.join(infra, "read_status.mjs")
    with open(script, "w", encoding="utf-8") as fh:
        fh.write(
            "import { _internals } from %s;\n"
            "const [infraPath, configuredPort] = process.argv.slice(2);\n"
            "const s = await _internals.readPortalStatus(infraPath, infraPath,\n"
            "  Number(configuredPort));\n"
            "console.log('RESULT ' + JSON.stringify(s));\n"
            % json.dumps("file:///" + os.path.join(ROOT, "lib", "index.js")
                         .replace("\\", "/")))
    done = subprocess.run([NODE, script, infra, str(port)],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", cwd=ROOT, timeout=180)
    for line in (done.stdout or "").splitlines():
        if line.startswith("RESULT "):
            return json.loads(line[len("RESULT "):])
    return {"__raw__": (done.stdout or "")[:300] + (done.stderr or "")[:400]}


def main():
    if not NODE:
        print("找不到 node")
        return 1
    tmp = tempfile.mkdtemp(prefix="svc-visible-")
    runs = os.path.join(tmp, "runs")
    os.makedirs(runs, exist_ok=True)
    port = free_port()
    env = dict(os.environ, PORTAL_RUNS_DIR=runs)

    log = open(os.path.join(tmp, "portal.log"), "wb")
    proc = subprocess.Popen(
        [PY, "-X", "utf8", os.path.join(HERE, "portal_run.py"),
         "--port", str(port), "--password", "visible-password-123", "--lan-only"],
        cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, env=env)
    try:
        ready = False
        for _ in range(60):
            try:
                with urllib.request.urlopen(
                        "http://127.0.0.1:%d/_auth/health" % port, timeout=3) as res:
                    res.read(32)
                    ready = True
                    break
            except Exception:
                time.sleep(0.5)
        check("前提：门户起来了", ready, "port=%d" % port)
        if not ready:
            return 1

        # 添加一个服务（这就是用户做的"添加"）
        body = json.dumps({"name": "可见性测试服务", "mount": "/visibleprobe",
                           "target": "127.0.0.1:18081"}).encode()
        req = urllib.request.Request(
            "http://127.0.0.1:%d/_api/services" % port, data=body,
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=20) as res:
            added = json.loads(res.read().decode("utf-8"))
        check("门户侧添加成功", added.get("ok") is True, "%r" % added)

        # 等门户把状态写盘（它写完才有状态文件）
        state_file = os.path.join(runs, "portal_state.json")
        for _ in range(40):
            if os.path.exists(state_file):
                break
            time.sleep(0.25)

        # ---- 核心断言：readPortalStatus 必须能看到这个服务 ----
        s = call_status(tmp, port)
        check("readPortalStatus 返回了状态", isinstance(s, dict) and s.get("kind") == "portal",
              "%r" % (str(s)[:200],))
        services = (s or {}).get("services") or []
        mounts = [x.get("mount") for x in services]
        check("**能看到刚添加的服务**（就是用户说的「看不到」那个 bug）",
              "/visibleprobe" in mounts, "清单=%r" % mounts)

        # 诊断信息：状态文件里确实没有 services（证明必须问活门户）
        if os.path.exists(state_file):
            with open(state_file, encoding="utf-8") as fh:
                disk = json.load(fh)
            check("状态文件里本来就没有 services（所以必须问活门户）",
                  "services" not in disk, "键=%r" % sorted(disk.keys())[:12])

        # ---- 反例控制：门户停掉后不能凭空编造服务 ----
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        time.sleep(1)
        s2 = call_status(tmp, port)
        check("反例：门户停掉后 services 是空数组（不编造）",
              isinstance(s2, dict) and s2.get("services") == [],
              "%r" % (str((s2 or {}).get("services"))[:120],))

        passed = sum(1 for ok, _, _ in results if ok)
        print("\n服务可见性控制检验：%d/%d" % (passed, len(results)))
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
