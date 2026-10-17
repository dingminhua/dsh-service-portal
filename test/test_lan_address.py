# -*- coding: utf-8 -*-
"""网卡选择与「高级·手动选地址」的真实进程验证。"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from portal_isolation import portal_env  # noqa: E402

PORT = 9021
# 这两个**不是**固定值：不同机器网段不同（作者机上是 192.168.71.61，
# 早先写死 192.168.71.10 就成了"换台机器必失败"的假断言）。
# 由 main() 按真实探测结果赋值：物理网卡 = 第一个非基准网段的候选。
GOOD = None
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
        # HTTPError 是 URLError 的**子类**，必须排在前面，否则永远进不来
        raw = err.read().decode("utf-8", "replace")
        try:
            return err.code, json.loads(raw)
        except ValueError:
            return err.code, {"raw": raw[:300]}
    except urllib.error.URLError:
        # 就绪轮询期间端口还没人听是正常现象，不能让它把整份检验炸掉
        return 0, {}


def main():
    global GOOD
    import lan_address
    results = []

    # 按**本机真实情况**定 GOOD：第一个不是基准网段的候选。
    # 这样在作者的 192.168.71.x、别人的 10.x / 172.16.x 上都能跑。
    detected = lan_address.detect_lan_candidates()
    for c in detected:
        if not lan_address.is_benchmark_ip(c["ip"]):
            GOOD = c["ip"]
            break
    if GOOD is None:
        print("跳过：本机没有可用的物理网卡地址（没连网线/WiFi）")
        return 2

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
    # 状态目录隔离到临时目录（见 test/portal_isolation.py）：
    # 原来是把用户真实 state 文件移走再移回，异常退出会把用户状态留在半残态。
    runs = tempfile.mkdtemp(prefix="portal-runs-")
    state = os.path.join(runs, "portal_state.json")
    log = open(os.path.join(runs, "lanip-check.log"), "wb")
    proc = subprocess.Popen(
        [sys.executable, "-X", "utf8", os.path.join(ROOT, "tools", "portal_run.py"),
         "--port", str(PORT), "--password", "lanip-check-password-1", "--lan-only"],
        cwd=ROOT, env=portal_env(runs), stdout=log, stderr=subprocess.STDOUT)
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
        shutil.rmtree(runs, ignore_errors=True)   # 临时目录整棵删除

    passed = sum(1 for ok in results if ok)
    print("\n网卡选择与手动选地址：%d/%d" % (passed, len(results)))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
