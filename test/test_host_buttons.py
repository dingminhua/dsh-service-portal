# -*- coding: utf-8 -*-
"""端到端：模拟用户在设置页点「开启门户」→ 扫二维码 → 点停止。

走的是**插件宿主 API**（http://127.0.0.1:19387/service-portal/api），
也就是设置页按钮真正调用的那条路径 —— 之前所有测试都直接起 portal_run.py，
所以漏掉了「插件等常驻进程退出 240 秒」那个 bug。
"""
import json
import time
import urllib.error
import urllib.request

API = "http://127.0.0.1:19387/service-portal/api"
PORT = 8899


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

    # --- 0. 先确保是停止状态 ---
    call("/stop", "POST", {}, timeout=90)
    time.sleep(2)
    check("门户已停止（干净起点）", not portal_alive())

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

    print("\n设置页按钮端到端：%s" % ("全部通过" if ok else "有失败"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
