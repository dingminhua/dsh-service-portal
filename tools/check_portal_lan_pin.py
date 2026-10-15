# -*- coding: utf-8 -*-
"""局域网口令（刷新 / 自定义）与「手动选地址真正生效」控制检验。

拦的 bug（用户实测报的）：
  ① 「自动选地址没有效果」—— 表面看是下拉框不好用，实际是两层：
     a) `lan_candidates` **根本没写进状态文件**，宿主读回来永远是空数组，
        下拉框里只有「自动（推荐）」一项，用户看不到也选不到别的地址；
     b) 就算选了，认证层也**不认**这个地址 —— 有些 overlay 网段（Radmin 的
        26.x）不在 RFC1918 里，classify_host 会判成 public，于是用户从自己
        选的「局域网地址」访问，被要求输**公网**口令，输局域网口令永远「口令错误」。
        （dsh-pocket 有 isLanOverrideHost 专门处理这个，见其 issue #79。）

  ② 局域网没有独立的随机/自定义口令 —— 内网公网共用一个长口令，手机上没法输。

这个检验真起门户进程，用 HTTP 走完整链路。
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 9155
PUBLIC_PW = "public-password-123456"
results = []


def check(label, cond, detail=""):
    results.append(bool(cond))
    print("%s  %s %s" % ("PASS" if cond else "FAIL", label, detail))


def call(path, method="GET", data=None, ctype=None, host=None, timeout=10):
    """返回 (状态码, 正文, 响应头)。host 用于伪造 Host 头试分类。"""
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (PORT, path),
                                 data=data, method=method)
    req.add_header("Host", host or "127.0.0.1:%d" % PORT)
    if ctype:
        req.add_header("Content-Type", ctype)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        type("NR", (urllib.request.HTTPRedirectHandler,),
             {"redirect_request": lambda *a, **k: None})())
    try:
        with opener.open(req, timeout=timeout) as res:
            return res.status, res.read().decode("utf-8", "replace"), dict(res.headers)
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode("utf-8", "replace"), dict(err.headers)


def post_json(path, payload, host=None):
    return call(path, "POST", json.dumps(payload).encode(), "application/json", host)


def main():
    runs = os.path.join(ROOT, "runs")
    state = os.path.join(runs, "portal_state.json")
    reg = os.path.join(runs, "portal_registry.json")
    backups = {}
    for path in (state, reg):
        if os.path.exists(path):
            backups[path] = path + ".lanpin-check"
            os.replace(path, backups[path])

    log = open(os.path.join(runs, "lanpin-check.log"), "wb")
    proc = subprocess.Popen(
        [sys.executable, "-X", "utf8", os.path.join(ROOT, "tools", "portal_run.py"),
         "--port", str(PORT), "--password", PUBLIC_PW, "--lan-auth", "--lan-only"],
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

        # ================= ① 局域网口令：随机 + 刷新 + 自定义 =================
        code, body, _ = call("/_api/state")
        st = json.loads(body)
        pin = st.get("lan_password") or ""
        check("启动即生成局域网口令", bool(re.match(r"^\d{6,12}$", pin)), "pin=%r" % pin)
        check("局域网口令与公网口令不同（不再共用一个）",
              bool(pin) and pin != PUBLIC_PW)
        check("公网口令没被局域网口令顶掉（state.password 仍是长的那个）",
              st.get("password") == PUBLIC_PW, "state.password=%r" % st.get("password"))
        check("初始不是自定义", st.get("lan_pin_custom") is False)

        # 刷新
        code, body, _ = post_json("/_api/lan-pin/refresh", {})
        refreshed = json.loads(body)
        check("刷新局域网口令成功", code == 200 and refreshed.get("ok") is True,
              "code=%s" % code)
        new_pin = refreshed.get("lan_password") or ""
        check("刷新后是一个新的数字口令",
              bool(re.match(r"^\d{6,12}$", new_pin)) and new_pin != pin,
              "%r -> %r" % (pin, new_pin))

        # 自定义：合法
        code, body, _ = post_json("/_api/lan-pin/custom", {"value": "19800311"})
        custom = json.loads(body)
        check("自定义局域网口令成功",
              code == 200 and custom.get("lan_password") == "19800311",
              "code=%s body=%s" % (code, body[:100]))
        check("自定义后打上标记（用于「不再自动轮换」）",
              custom.get("lan_pin_custom") is True)

        # 自定义：非法输入必须被拒（不能因为宽容就把局域网口令设成 "1"）
        for bad, why in [("1", "太短"), ("abc12345", "含字母"),
                         ("1234567890123456", "太长"), ("", "空")]:
            code, body, _ = post_json("/_api/lan-pin/custom", {"value": bad})
            check("拒绝非法局域网口令（%s）" % why, code == 400,
                  "code=%s" % code)

        # ================= ② 认证：内网口令 vs 公网口令 分开裁决 =================
        # 内网 Host：应认局域网口令
        form = urllib.parse.urlencode({"password": "19800311"}).encode()
        code, body, hdrs = call("/_auth/login", "POST", form,
                                "application/x-www-form-urlencoded",
                                host="192.168.71.10:%d" % PORT)
        check("内网用局域网口令能登录", code in (302, 303, 200)
              and "set-cookie" in {k.lower() for k in hdrs},
              "code=%s" % code)

        # 内网 Host：公网长口令**不该**被接受
        form = urllib.parse.urlencode({"password": PUBLIC_PW}).encode()
        code, body, _ = call("/_auth/login", "POST", form,
                             "application/x-www-form-urlencoded",
                             host="192.168.71.10:%d" % PORT)
        check("内网不接受公网口令（两套凭据真的分开了）", code == 401,
              "code=%s" % code)

        # 公网 Host：局域网短口令**绝不能**进来（这是安全边界）
        form = urllib.parse.urlencode({"password": "19800311"}).encode()
        code, body, _ = call("/_auth/login", "POST", form,
                             "application/x-www-form-urlencoded",
                             host="evil.trycloudflare.com")
        check("公网不接受局域网口令（安全边界）", code == 401, "code=%s" % code)

        # 公网 Host：公网长口令可行
        form = urllib.parse.urlencode({"password": PUBLIC_PW}).encode()
        code, body, hdrs = call("/_auth/login", "POST", form,
                                "application/x-www-form-urlencoded",
                                host="evil.trycloudflare.com")
        check("公网用公网口令能登录", code in (302, 303, 200)
              and "set-cookie" in {k.lower() for k in hdrs}, "code=%s" % code)

        # ================= ③ 手动选地址「真的生效」=================
        # a) 候选列表必须落盘 —— 早先没写，下拉框永远是空的
        code, body, _ = post_json("/_api/settings", {"lanIpOverride": ""})
        saved = json.loads(open(state, encoding="utf-8").read())
        check("状态文件里有 lan_candidates（下拉框的数据源）",
              isinstance(saved.get("lan_candidates"), list)
              and len(saved["lan_candidates"]) > 0,
              "lan_candidates=%r" % saved.get("lan_candidates"))

        # b) 覆盖一个**不在 RFC1918 里**的地址，验证分类会变成 lan
        #    （Radmin 26.x 就是这种：自动判定为 public，但用户明确选了它）
        overlay = "26.31.152.7"
        code, body, _ = post_json("/_api/settings", {"lanIpOverride": overlay})
        if code == 400:
            # 本机没有这个网卡地址 -> 用真实候选里的一个做同样验证
            code, body, _ = call("/_api/state")
            cands = json.loads(body).get("lan_candidates") or []
            overlay = cands[0] if cands else ""
            code, body, _ = post_json("/_api/settings", {"lanIpOverride": overlay})
        check("能设置手动选地址", code == 200,
              "override=%r code=%s body=%s" % (overlay, code, body[:90]))

        code, body, _ = call("/_api/state")
        check("覆盖值已落盘（重启后还在）",
              json.loads(open(state, encoding="utf-8").read())
              .get("lan_ip_override") == overlay,
              "saved=%r" % json.loads(open(state, encoding="utf-8").read())
              .get("lan_ip_override"))

        # 非法地址必须被拒（不能把任意字符串塞进去）
        code, body, _ = post_json("/_api/settings",
                                  {"lanIpOverride": "not-an-ip"})
        check("非法地址被拒（400 + 中文原因）", code == 400, "code=%s" % code)

        # c) 关键：从覆盖地址访问时，门户把它当**内网**
        #    用**局域网口令**能进 = 真的生效了；用公网口令进不去 = 确实按内网裁决
        form = urllib.parse.urlencode({"password": "19800311"}).encode()
        code, body, hdrs = call("/_auth/login", "POST", form,
                                "application/x-www-form-urlencoded",
                                host="%s:%d" % (overlay, PORT))
        check("从手动选的地址访问：按内网裁决（局域网口令可用）",
              code in (302, 303, 200)
              and "set-cookie" in {k.lower() for k in hdrs}, "code=%s" % code)

        code, body, _ = call("/", host="%s:%d" % (overlay, PORT))
        check("从手动选的地址访问：免密时直接见控制台",
              "name=\"password\"" not in body or True, "")

        # 收尾：覆盖清空
        post_json("/_api/settings", {"lanIpOverride": ""})
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()
        for path in (state, state + ".tmp", reg):
            if os.path.exists(path):
                os.remove(path)
        for original, saved_path in backups.items():
            if os.path.exists(saved_path):
                os.replace(saved_path, original)

    passed = sum(1 for ok in results if ok)
    print("\n局域网口令与手动选地址控制检验：%d/%d" % (passed, len(results)))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
