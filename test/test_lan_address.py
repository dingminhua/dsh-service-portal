# -*- coding: utf-8 -*-
"""网卡选择与「高级·手动选地址」的真实进程验证。"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
PORT = 9021
GOOD = "192.168.71.10"
VIRTUAL = "198.18.0.1"


def call(path, method="GET", data=None):
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (PORT, path),
                                 data=data, method=method)
    req.add_header("Host", "127.0.0.1:%d" % PORT)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=8) as res:
            return res.status, json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8", "replace")
        try:
            return err.code, json.loads(raw)
        except ValueError:
            return err.code, {"raw": raw[:300]}


def main():
    import lan_address
    results = []

    def check(label, cond, detail=""):
        results.append(bool(cond))
        print("%s  %s %s" % ("PASS" if cond else "FAIL", label, detail))

    # ---- 1. 纯函数层：评分 ----
    print("[网卡评分]")
    cands = lan_address.detect_lan_candidates()
    ips = [c["ip"] for c in cands]
    check("物理网卡（192.168.x）排在虚拟网卡（198.18.x）前面",
          ips.index(GOOD) < ips.index(VIRTUAL) if GOOD in ips and VIRTUAL in ips
          else True, "顺序=%r" % ips)
    check("198.18.0.0/15 被判为不可达（基准测试网段）",
          lan_address.is_benchmark_ip(VIRTUAL) is True)
    check("192.168.x 不被误判", lan_address.is_benchmark_ip(GOOD) is False)
    check("best_lan_ip 取到真实网卡", lan_address.best_lan_ip() == GOOD,
          "得到 %r" % lan_address.best_lan_ip())
    # 反例控制：虚拟网卡必须真的被降权，不是碰巧顺序对
    scored = {c["ip"]: c["score"] for c in cands}
    check("虚拟网卡得分明显低于物理网卡（降权生效）",
          scored.get(VIRTUAL, 0) < scored.get(GOOD, 0),
          "virtual=%r physical=%r" % (scored.get(VIRTUAL), scored.get(GOOD)))

    # ---- 2. 真实门户进程：覆盖生效 ----
    print("\n[手动选地址（真实进程）]")
    runs = os.path.join(ROOT, "runs")
    state = os.path.join(runs, "portal_state.json")
    backup = state + ".lanip-check"
    if os.path.exists(state):
        os.replace(state, backup)
    log = open(os.path.join(runs, "lanip-check.log"), "wb")
    proc = subprocess.Popen(
        [sys.executable, "-X", "utf8", os.path.join(ROOT, "tools", "portal_run.py"),
         "--port", str(PORT), "--password", "lanip-check-password-1", "--lan-only"],
        cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    try:
        ready = False
        for _ in range(60):
            if call("/_auth/health")[0] == 200:
                ready = True
                break
            time.sleep(0.5)
        check("门户就绪", ready)
        if not ready:
            return 1

        _s, st = call("/_api/state")
        check("状态带候选列表（下拉框用它）",
              isinstance(st.get("lan_candidates"), list) and st["lan_candidates"],
              "candidates=%r" % st.get("lan_candidates"))
        check("状态带候选明细（含网卡名，便于判断）",
              isinstance(st.get("lan_candidate_detail"), list)
              and st["lan_candidate_detail"]
              and "name" in st["lan_candidate_detail"][0],
              "detail[0]=%r" % (st.get("lan_candidate_detail") or [None])[0])
        check("默认地址是物理网卡那个（不是 198.18.x）",
              st.get("lan_urls", [""])[0].startswith("http://" + GOOD),
              "lan_urls=%r" % st.get("lan_urls"))
        check("默认没有覆盖（lan_ip_override 为空）",
              not st.get("lan_ip_override"), repr(st.get("lan_ip_override")))

        # 选一个**另一个**候选，验证立刻生效
        other = [ip for ip in st["lan_candidates"] if ip != GOOD]
        if other:
            target = other[0]
            code, resp = call("/_api/settings", "POST",
                              json.dumps({"lanIpOverride": target}).encode())
            check("能设置手动地址", code == 200 and resp.get("ok") is True,
                  "code=%s" % code)
            _s, st2 = call("/_api/state")
            check("设置后**只有**那个地址（不再列出全部）",
                  st2.get("lan_urls") == ["http://%s:%d" % (target, PORT)],
                  "lan_urls=%r" % st2.get("lan_urls"))
            check("覆盖值被记住", st2.get("lan_ip_override") == target)

        # 非法地址必须被拒（不能静默接受一个本机没有的 IP）
        code, resp = call("/_api/settings", "POST",
                          json.dumps({"lanIpOverride": "1.2.3.4"}).encode())
        check("非本机地址被拒（400 + 中文原因）",
              code == 400 and "不是本机" in str(resp.get("error", "")),
              "code=%s err=%r" % (code, resp.get("error")))

        # 清空 = 回自动
        code, resp = call("/_api/settings", "POST",
                          json.dumps({"lanIpOverride": ""}).encode())
        _s, st3 = call("/_api/state")
        check("清空后回到自动（列出全部候选）",
              len(st3.get("lan_urls", [])) > 1 and not st3.get("lan_ip_override"),
              "lan_urls=%r" % st3.get("lan_urls"))

        # 落盘：重启后还在
        call("/_api/settings", "POST",
             json.dumps({"lanIpOverride": GOOD}).encode())
        saved = json.load(open(state, encoding="utf-8"))
        check("覆盖值立即落盘（重启不丢）",
              saved.get("lan_ip_override") == GOOD,
              "saved=%r" % saved.get("lan_ip_override"))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()
        for path in (state, state + ".tmp"):
            if os.path.exists(path):
                os.remove(path)
        if os.path.exists(backup):
            os.replace(backup, state)

    passed = sum(1 for ok in results if ok)
    print("\n网卡选择与手动选地址：%d/%d" % (passed, len(results)))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
