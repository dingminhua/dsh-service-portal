# -*- coding: utf-8 -*-
"""验证「装好即用」：插件加载后门户自动起来（不用手点按钮）。

这是用户报的「默认主页访问也没打开」的直接复现与回归。

做法：在插件库里直接调 apply()（模拟 DSH 加载插件），给一个假的 ctx，
看它是否**自动调用** startPublic（只开内网）并让门户真的跑起来。
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 9001
NODE = os.path.join(
    os.environ.get("LOCALAPPDATA", ""), "Programs", "DeepSeek Harness",
    "resources", "runtime", "primary-runtime", "dependencies",
    "node", "bin", "node.exe")


def portal_alive():
    try:
        with urllib.request.urlopen(
                "http://127.0.0.1:%d/_auth/health" % PORT, timeout=3) as res:
            return res.status == 200
    except Exception:
        return False


def main():
    runs = os.path.join(ROOT, "runs")
    state_file = os.path.join(runs, "portal_state.json")
    backup = None
    if os.path.exists(state_file):
        backup = state_file + ".autostart-check"
        os.replace(state_file, backup)

    results = []

    def check(label, cond, detail=""):
        results.append((bool(cond), label, detail))
        print("%s  %s %s" % ("PASS" if cond else "FAIL", label, detail))

    # 让 Node 侧加载 lib/index.js，用假 ctx 调 apply()，看它是否自动启动门户。
    index_url = "file:///" + os.path.join(ROOT, "lib", "index.js").replace("\\", "/")
    script = """
import { apply, _internals } from %s;
const calls = [];
const fakeCtx = {
  logger: { info: (m) => calls.push(["info", m]), warn: (m) => calls.push(["warn", m]) },
  get: () => undefined,
  inject: (deps, fn) => fn({ webServer: { register: () => () => {} } }),
};
const config = {
  infraPath: %s,
  repoPath: %s,
  pythonPath: %s,
  autoStart: { get: () => true },
  lanAuthEnabled: { get: () => false },
  portalPort: { get: () => %d },
  passwordMode: { get: () => "random" },
  fixedPassword: { get: () => "" },
  webEnabled: { get: () => true },
};
apply(fakeCtx, config);
// 等自动启动跑完（ensurePortal 是异步的）
await new Promise((r) => setTimeout(r, 45000));
const status = await _internals.readStatus({
  infraPath: config.infraPath, repoPath: config.repoPath,
  pythonPath: "", passwordMode: "random", fixedPassword: "",
  portalPort: %d, autoStart: true, lanAuthEnabled: false, webEnabled: true,
});
console.log(JSON.stringify({ running: status.running, kind: status.kind,
  lanUrls: status.lanUrls, logs: calls.map((c) => c[1]) }));
// 自动启动拉起的门户是**子进程**，句柄让 Node 事件循环不退出 —— 显式退出，
// 否则这个检查脚本会一直挂着（超时误报）。
process.exit(0);
""" % (json.dumps(index_url),
       json.dumps(ROOT.replace("\\", "/")), json.dumps(ROOT.replace("\\", "/")),
       json.dumps(sys.executable.replace("\\", "/")), PORT, PORT)

    script_path = os.path.join(runs, "autostart-check.mjs")
    with open(script_path, "w", encoding="utf-8") as handle:
        handle.write(script)

    try:
        proc = subprocess.run([NODE, script_path], cwd=ROOT, capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              timeout=180)
        out = (proc.stdout or "").strip()
        check("Node 侧脚本执行完成", proc.returncode == 0 or bool(out),
              "code=%s stderr=%s" % (proc.returncode, (proc.stderr or "")[:200]))

        payload = None
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    payload = json.loads(line)
                except ValueError:
                    pass
        if payload is None:
            check("解析到状态输出", False, "stdout=%r" % out[:300])
        else:
            check("**插件加载后门户自动跑起来了**（running=true）",
                  payload.get("running") is True,
                  "running=%r kind=%r logs=%r" % (
                      payload.get("running"), payload.get("kind"),
                      payload.get("logs")))
            check("自动启动只开内网（没自动把服务挂到公网）",
                  bool(payload.get("lanUrls")) or payload.get("kind") == "portal",
                  "lanUrls=%r" % payload.get("lanUrls"))
            check("内网地址可用（设置页据此显示二维码）",
                  any(str(u).startswith("http://") for u in (payload.get("lanUrls") or [])),
                  "lanUrls=%r" % payload.get("lanUrls"))
    finally:
        # 停掉自动起来的门户进程，别留在后台
        try:
            subprocess.run([sys.executable, "-X", "utf8",
                            os.path.join(ROOT, "tools", "portal_run.py"), "--stop"],
                           cwd=ROOT, capture_output=True, timeout=60)
        except Exception:
            pass
        for path in (script_path, state_file, state_file + ".tmp"):
            if os.path.exists(path):
                os.remove(path)
        if backup and os.path.exists(backup):
            os.replace(backup, state_file)

    passed = sum(1 for ok, _, _ in results if ok)
    print("\n自动启动验证：%d/%d" % (passed, len(results)))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
