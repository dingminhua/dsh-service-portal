# -*- coding: utf-8 -*-
"""设置页「局域网」三项开关的转发控制检验。

真实 bug（用户截图里就摆着）：
  设置页的「局域网访问」总开关、「局域网访问密码」开关、「手动选地址」，
  都 POST 到宿主 `/settings`，而宿主那个处理函数**只认** passwordMode /
  fixedPassword —— 局域网字段被静默忽略：返回 ok:true，前端弹
  「局域网已需要口令」的 toast，**门户那边一点没变**。
  界面上就表现为：toast 说开了，开关自己弹回去、下面还写着「已关闭」。
  这是本项目最忌讳的「不崩、只给错误答案」。

本检验打的是真行为：起一个真门户（临时端口 + 临时 PORTAL_RUNS_DIR），
通过宿主的 saveSettings 改这三项，然后**问门户自己**变没变。

控制检验原则：正例（该生效）与反例（门户没在跑时要如实失败）必须可区分。

运行：python -X utf8 tools/check_portal_settings_forward.py
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


def portal_state(port):
    """直接问门户要真实状态（不经过宿主，避免自己骗自己）。"""
    with urllib.request.urlopen(
            "http://127.0.0.1:%d/_api/state" % port, timeout=6) as res:
        return json.loads(res.read().decode("utf-8"))


NODE_CALL = r"""
import { _internals } from %(lib)s;

// argv: port | deadPort | mode | key | value(raw) | infra
const [port, shouldFailPort, mode, key, value, infra] = process.argv.slice(2);
const repo = { infraPath: infra, repoPath: infra, portalPort: Number(port) };
// 值要按字段类型给：开关是布尔，手动选地址是**字符串**（第一版把 IP 也传成
// "true"，于是"手动选地址"这条永远失败 —— 那是检验自己的 bug，不是产品的）
const parsed = value === "__bool_true__" ? true
  : value === "__bool_false__" ? false
  : value;
if (mode === "real") {
  const out = await _internals.saveSettings({}, repo, { [key]: parsed });
  console.log("RESULT " + JSON.stringify(out));
} else {
  // 反例：门户没在跑（端口空着）必须**如实失败**，不能回 ok:true
  const dead = { infraPath: infra, repoPath: infra, portalPort: Number(shouldFailPort) };
  const out = await _internals.saveSettings({}, dead, { lanAuthEnabled: true });
  console.log("RESULT " + JSON.stringify(out));
}
"""


def main():
    if not NODE:
        print("找不到 node（可用 DSH_NODE 指定）")
        return 1
    tmp = tempfile.mkdtemp(prefix="settings-fwd-")
    runs = os.path.join(tmp, "runs")
    infra = os.path.join(tmp, "infra")
    os.makedirs(runs, exist_ok=True)
    os.makedirs(infra, exist_ok=True)
    shutil.copytree(HERE, os.path.join(infra, "tools"))
    port = free_port()
    log = open(os.path.join(tmp, "portal.log"), "wb")
    proc = subprocess.Popen(
        [PY, "-X", "utf8", os.path.join(infra, "tools", "portal_run.py"),
         "--port", str(port), "--password", "settings-fwd-password", "--lan-only"],
        cwd=infra, stdout=log, stderr=subprocess.STDOUT,
        env=dict(os.environ, PORTAL_RUNS_DIR=runs))
    try:
        ready = False
        for _ in range(60):
            try:
                portal_state(port)
                ready = True
                break
            except Exception:
                time.sleep(0.5)
        check("门户起来了（前提）", ready, "port=%d" % port)
        if not ready:
            return 1

        node_file = os.path.join(tmp, "call.mjs")
        with open(node_file, "w", encoding="utf-8") as handle:
            handle.write(NODE_CALL % {"lib": json.dumps(
                "file:///" + os.path.join(ROOT, "lib", "index.js").replace("\\", "/"))})

        def call_save(mode, key, value):
            # value 传 True/False 或字符串（IP）；字符串值原样送
            raw = "__bool_true__" if value is True else (
                "__bool_false__" if value is False else str(value))
            done = subprocess.run(
                [NODE, node_file, str(port), str(free_port()), mode, key,
                 raw, infra],
                cwd=ROOT, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=180)
            for line in (done.stdout or "").splitlines():
                if line.startswith("RESULT "):
                    return json.loads(line[len("RESULT "):])
            return {"__raw__": (done.stdout or "")[:300] + (done.stderr or "")[:300]}

        # ---- 正例 1：开局域网口令 ----
        before = portal_state(port)["lan_auth_enabled"]
        out = call_save("real", "lanAuthEnabled", True)
        time.sleep(0.3)
        after = portal_state(port)["lan_auth_enabled"]
        check("宿主 saveSettings 处理了 lanAuthEnabled（不再静默忽略）",
              out.get("ok") is True, "返回=%r" % (out,))
        check("开局域网口令：门户**真的**从 %r 变成 True" % before,
              before is False and after is True,
              "after=%r" % (after,))

        # ---- 正例 2：关回去（反向也要生效，防止只写死 true）----
        out = call_save("real", "lanAuthEnabled", False)
        time.sleep(0.3)
        after2 = portal_state(port)["lan_auth_enabled"]
        check("关局域网口令：门户真的变回 False", after2 is False,
              "after=%r" % (after2,))

        # ---- 正例 3：局域网总开关 ----
        out = call_save("real", "lanEnabled", False)
        time.sleep(0.3)
        after3 = portal_state(port)["lan_enabled"]
        check("关局域网总开关：门户真的变 False", after3 is False,
              "after=%r" % (after3,))
        call_save("real", "lanEnabled", True)

        # ---- 正例 4：手动选地址（用本机真实网卡地址）----
        sys.path.insert(0, HERE)
        import lan_address
        best = lan_address.best_lan_ip()
        if best:
            out = call_save("real", "lanIpOverride", best)
            time.sleep(0.3)
            after4 = portal_state(port)["lan_ip_override"]
            check("手动选地址：门户真的记下了 %s" % best, after4 == best,
                  "after=%r" % (after4,))
        else:
            check("手动选地址：门户真的记下了（本机无候选，跳过）", True)

        # ---- 反例：门户没在跑时必须如实失败（不能假成功）----
        dead = call_save("fail", "lanAuthEnabled", True)
        check("反例：门户没在跑时**如实失败**（不许回 ok:true 骗前端）",
              dead.get("ok") is False and bool(dead.get("error")),
              "返回=%r" % (dead,))

        passed = sum(1 for ok, _, _ in results if ok)
        print("\n局域网设置转发控制检验：%d/%d" % (passed, len(results)))
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
