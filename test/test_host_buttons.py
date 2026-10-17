# -*- coding: utf-8 -*-
"""端到端：模拟用户在设置页点「开启门户」→ 扫二维码 → 点停止。

走的是**插件宿主 API**（http://127.0.0.1:19387/service-portal/api），
也就是设置页按钮真正调用的那条路径 —— 之前所有测试都直接起 portal_run.py，
所以漏掉了「插件等常驻进程退出 240 秒」那个 bug。
"""
import json
import os
import time
import urllib.error
import urllib.request

API = "http://127.0.0.1:19387/service-portal/api"
PORT = 8899
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _get_status_value(key):
    """读当前状态里的某个字段（收尾核对用）。"""
    try:
        _s, st = call("/status")
        return st.get(key)
    except Exception:
        return None


def _expected_stamp():
    """当前这份代码的指纹，必须与 lib/index.js 里 CODE_STAMP 的算法一致。

    算法：`<package.json 版本>+<lib/index.js 的 mtime 毫秒>+<字节数>`。
    为什么不用纯版本号：实测踩过 —— 只把版本号从 0.7.5 提到 0.7.6，而宿主
    内存里是"同版本、但没有新修复"的旧代码，守卫放行，于是过期代码被当成
    产品失败报出来。指纹取自文件本身才认得出"代码改过了"。
    """
    lib = os.path.join(ROOT, "lib", "index.js")
    try:
        with open(os.path.join(ROOT, "package.json"), "r", encoding="utf-8") as fh:
            version = json.load(fh).get("version", "0.0.0")
        info = os.stat(lib)
        return "%s+%d+%d" % (version, int(info.st_mtime * 1000), info.st_size)
    except Exception:
        return None


def call(path, method="GET", body=None, timeout=120):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(API + path, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status, json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8", "replace")
        try:
            return err.code, json.loads(raw)
        except ValueError:
            return err.code, {"raw": raw[:400]}


def portal_alive():
    try:
        with urllib.request.urlopen(
                "http://127.0.0.1:%d/_auth/health" % PORT, timeout=4) as res:
            return res.status == 200
    except Exception:
        return False


def check(label, cond, detail=""):
    print("%s  %s %s" % ("PASS" if cond else "FAIL", label, detail))
    return bool(cond)


def main():
    ok = True

    # --- 0. 先确认这个测试有意义：宿主上跑的必须是**当前这份**代码 ---
    #
    # 这个测试打的是活着的 DSH 宿主（设置页按钮真正走的那条路）。宿主进程只在
    # DSH **启动时**把 lib/index.js 读进内存，之后不会热加载（实测：临时加一个
    # 字段，/status 里一直看不到）。改了代码没重启 DSH，测出来的"失败"是
    # **测试自己过期**，不是插件坏了 —— 报成 FAIL 会把排查方向带偏。
    # 按本仓库纪律：前置条件不满足就**明确跳过并返回 2**，不静默通过也不假报失败。
    import json as _json
    expected = _expected_stamp()
    try:
        probe_status, probe = call("/status", timeout=20)
    except Exception as exc:
        print("宿主 API 不可达（%r）：跳过" % (exc,))
        return 2
    if not isinstance(probe, dict) or probe_status != 200:
        print("宿主 API 异常（HTTP %r）：跳过" % (probe_status,))
        return 2
    if probe.get("codeStamp") != expected:
        print("宿主跑的**不是**当前代码：期望 codeStamp=%r，实际 %r"
              % (expected, probe.get("codeStamp")))
        print("（宿主只在 DSH 启动时加载 lib/index.js，改完要重启 DSH。）")
        print("按纪律跳过（返回 2），不算通过。")
        return 2

    # --- 起点：不强求是停止状态 ---
    # 这个测试打的是宿主 API，而宿主上通常正跑着用户自己的门户。原来一上来就
    # 断言「门户已停止（干净起点）」，用户门户正在跑时必然失败 —— 而且它把用户的
    # 门户停掉之后并不恢复。现在：先记下现场，结束时恢复回原样。
    was_alive = portal_alive()

    # 还要记下 **autoStart**：宿主路由 `/stop` 会把用户的启停偏好写成 false
    # （"用户主动停掉的下次就别自动起了"）。这是正确行为，但这个测试是**故意**
    # 制造一次"用户停止"，若不还原，用户下次开 DSH 门户就不自动起来了 ——
    # 实测就是这样把用户的门户"关掉"的：状态文件被写成 stopped_clean=true，
    # 打开设置页看到的是「门户未启动」。
    _s0, _st0 = call("/status")
    was_autostart = _st0.get("autoStart")

    # 停一次，顺带验证「停止」真的有效（这次修的正是它）
    call("/stop", "POST", {}, timeout=90)
    time.sleep(2)
    ok &= check("点「停止」后门户真的停了（端口释放）", not portal_alive(),
                "进门前门户在运行=%r" % was_alive)

    # --- 1. 点「开启门户（只内网）」 ---
    t0 = time.time()
    status, payload = call("/start", "POST", {"lanOnly": True}, timeout=180)
    elapsed = time.time() - t0
    ok &= check("开启不阻塞（远小于 240 秒的超时）", elapsed < 90,
                "耗时 %.1fs" % elapsed)
    ok &= check("开启返回 ok=true", payload.get("ok") is True,
                "exitCode=%r stderr=%r" % (payload.get("exitCode"),
                                           str(payload.get("stderr"))[:160]))
    ok &= check("门户真的在监听", portal_alive())

    # --- 2. 状态接口给出设置页要渲染的字段 ---
    status, st = call("/status")
    ok &= check("状态 running=true", st.get("running") is True)
    ok &= check("有内网地址（设置页据此显示二维码）",
                bool(st.get("lanUrls")), "lanUrls=%r" % st.get("lanUrls"))
    ok &= check("有口令（公网用；内网免密时仍显示）", bool(st.get("password")))
    ok &= check("有控制台地址（扫码后打开的就是它）",
                bool(st.get("portalUrl")), st.get("portalUrl"))
    ok &= check("没有 problem 字段（不是「状态文件还在但端口没监听」）",
                not st.get("problem"), st.get("problem"))

    # --- 3. 重复点「开启」不应该起第二个 ---
    status, again = call("/start", "POST", {"lanOnly": True}, timeout=180)
    ok &= check("重复开启幂等（不重复起进程）", again.get("ok") is True)
    time.sleep(1)
    ok &= check("重复开启后门户仍健康", portal_alive())

    # --- 4. 点「停止」 ---
    status, stopped = call("/stop", "POST", {}, timeout=90)
    time.sleep(3)
    ok &= check("停止返回 ok=true", stopped.get("ok") is True)
    ok &= check("停止后端口真的释放", not portal_alive())
    # 走的是"请门户自己退"这条可靠路径（沙箱里从外面杀 pid 看不见进程）。
    # 旧版宿主没这个字段 —— 那时不要误判成失败。
    if "stoppedBy" in stopped:
        ok &= check("停止走的是「门户自退」（不是靠 taskkill 猜）",
                    stopped.get("stoppedBy") == "self",
                    "stoppedBy=%r" % stopped.get("stoppedBy"))

    # --- 5. 收尾：把现场恢复回原样 ---
    # 5a. 先还原 autoStart（必须在重启门户**之前**，否则重启后再改，下一轮
    #     自动启动的判定仍是错的）。暂停过程中它被 /stop 改成了 false。
    if isinstance(was_autostart, bool):
        status, _ = call("/settings", "POST", {"autoStart": was_autostart})
        ok &= check("收尾：还原用户原来的 autoStart 偏好（%r）" % was_autostart,
                    _get_status_value("autoStart") == was_autostart,
                    "HTTP %r" % (status,))

    # 5b. 再把门户恢复回"进门前是否在跑"
    if was_alive:
        status, back = call("/start", "POST", {"lanOnly": True}, timeout=180)
        time.sleep(2)
        ok &= check("收尾：把用户原来在跑的门户恢复了", portal_alive(),
                    "ok=%r" % back.get("ok"))

    print("\n设置页按钮端到端：%s" % ("全部通过" if ok else "有失败"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
