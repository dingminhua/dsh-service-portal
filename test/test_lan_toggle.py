# -*- coding: utf-8 -*-
"""验证「内网访问密码」开关立即生效（不重启门户）。"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from portal_isolation import isolated_runs, portal_env  # noqa: E402
PORT = 8995
LAN_HOST = "192.168.77.88:%d" % PORT
PASSWORD = "lan-toggle-test-password-1"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):
        return None


SESSION = {"cookie": ""}


def call(path, host=LAN_HOST, method="GET", data=None, ctype=None):
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (PORT, path),
                                 data=data, method=method)
    req.add_header("Host", host)
    if ctype:
        req.add_header("Content-Type", ctype)
    if SESSION["cookie"]:
        req.add_header("Cookie", SESSION["cookie"])
    try:
        res = urllib.request.build_opener(NoRedirect).open(req, timeout=8)
        setc = res.headers.get("Set-Cookie")
        if setc and "sp_session=" in setc:
            SESSION["cookie"] = setc.split(";")[0]
        return res.status, res.read()
    except urllib.error.HTTPError as err:
        # 303 会走到这里：**错误响应上同样要收 Set-Cookie**，否则登录拿不到会话
        # （这一步之前漏了，导致「登录后仍打不开」的假失败）。
        setc = err.headers.get("Set-Cookie")
        if setc and "sp_session=" in setc:
            SESSION["cookie"] = setc.split(";")[0]
        return err.code, err.read()
    except urllib.error.URLError:
        # 就绪轮询期间端口还没人听是正常现象，不能炸掉整份检验
        return 0, b""


def main():
    # 状态目录隔离到临时目录：不碰用户真实 runs/（见 test/portal_isolation.py）
    with isolated_runs() as runs:
        return _run(runs)


def _run(runs):
    state_file = os.path.join(runs, "portal_state.json")
    log = open(os.path.join(runs, "toggle-test.log"), "wb")
    proc = subprocess.Popen(
        [sys.executable, "-X", "utf8",
         os.path.join(ROOT, "tools", "portal_run.py"),
         "--port", str(PORT), "--password", PASSWORD, "--lan-only"],
        cwd=ROOT, env=portal_env(runs), stdout=log, stderr=subprocess.STDOUT)

    results = []

    def check(label, cond, detail=""):
        results.append((bool(cond), label, detail))
        print("%s  %s %s" % ("PASS" if cond else "FAIL", label, detail))

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

        # 默认：内网免密 -> 直接看到控制台
        status, body = call("/")
        check("默认内网免密：直接看到控制台（无登录框）",
              status == 200 and b'name="password"' not in body,
              "code=%s" % status)

        # 开启内网口令（不重启门户）
        status, body = call("/_api/settings", method="POST",
                            data=json.dumps({"lanAuthEnabled": True}).encode(),
                            ctype="application/json")
        check("开启内网口令成功", status == 200 and b'"ok": true' in body)

        # 立即生效：同一个内网地址现在要登录页（这就是「不用重启」的证据）
        status, body = call("/")
        check("开启后**立即**要求口令（未重启门户）",
              b'name="password"' in body, "code=%s" % status)

        # 内网即使有口令，登录后也能进（证明不是把内网锁死）
        #
        # 注意用**局域网口令**，不是公网 PASSWORD —— 两套凭据是分开的：
        # 内网短数字好输、公网长随机串抗爆破；公网口令在内网**不该**被接受。
        # 这里读的是门户刚生成/保存的那个局域网口令。
        status, body = call("/_api/state", host="127.0.0.1:%d" % PORT)
        lan_pin = ""
        try:
            lan_pin = json.loads(body).get("lan_password") or ""
        except ValueError:
            pass
        check("门户给出了局域网口令（数字，手机好输）",
              bool(lan_pin) and lan_pin.isdigit(), "lan_pin=%r" % lan_pin)
        status, _ = call("/_auth/login", method="POST",
                         data=urllib.parse.urlencode({"password": lan_pin}).encode(),
                         ctype="application/x-www-form-urlencoded")
        check("内网用局域网口令能登录", status == 303, "code=%s" % status)

        # 反例：公网口令在内网**不能**用（两套凭据真的分开了）
        status, _ = call("/_auth/login", method="POST",
                         data=urllib.parse.urlencode({"password": PASSWORD}).encode(),
                         ctype="application/x-www-form-urlencoded")
        check("内网不接受公网口令（凭据确实分开）", status == 401,
              "code=%s" % status)

        # 关掉 -> 立即恢复免密
        #
        # 注意：管理类调用走 **loopback**（本机自己），因为开了内网口令之后
        # 内网请求会先被登录页拦住（那时连「关掉开关」这个动作都做不了）。
        # 这也是插件本身的调用方式：宿主 → 127.0.0.1:port 的门户 API。
        call("/_api/settings", host="127.0.0.1:%d" % PORT, method="POST",
             data=json.dumps({"lanAuthEnabled": False}).encode(),
             ctype="application/json")
        status, body = call("/")
        check("关闭后立即恢复免密",
              status == 200 and b'name="password"' not in body)

        # 反例控制：开了内网口令时，**没有会话**的内网请求会被拦
        # （证明「免密」不是恒真，开关确实在起作用）。
        # 必须清掉会话 —— 否则我们带着上一步登录的 cookie，当然能进（那是正确行为）。
        call("/_api/settings", host="127.0.0.1:%d" % PORT, method="POST",
             data=json.dumps({"lanAuthEnabled": True}).encode(),
             ctype="application/json")
        SESSION["cookie"] = ""
        status, body = call("/_api/settings", method="GET")
        check("开了口令后无会话的内网请求会被拦（不是恒放行）",
              b'name="password"' in body, "code=%s" % status)

        # 内网登录后就能调了（有会话）—— 仍用局域网口令
        call("/_auth/login", method="POST",
             data=urllib.parse.urlencode({"password": lan_pin}).encode(),
             ctype="application/x-www-form-urlencoded")
        status, body = call("/_api/settings", method="GET")
        check("内网登录后管理 API 可用",
              status == 200 and b'"lan_auth_enabled"' in body,
              "code=%s" % status)

        # 本机（loopback）永远免密：即使内网开了口令也不该要（那是自己）
        call("/_api/settings", method="POST",
             data=json.dumps({"lanAuthEnabled": True}).encode(),
             ctype="application/json")
        status, body = call("/", host="127.0.0.1:%d" % PORT)
        check("本机访问永远免密（内网开口令也不影响 loopback）",
              status == 200 and b'name="password"' not in body,
              "code=%s" % status)

        # 隧道/公网始终要口令（不受内网开关影响）。同样要清会话 ——
        # 会话跨 Host 有效（同一门户进程），带着它测不出「公网要口令」。
        SESSION["cookie"] = ""
        status, body = call("/", host="toggle.demo.trycloudflare.com")
        check("公网始终要口令（无会话时，内网开关不影响公网）",
              b'name="password"' in body, "code=%s" % status)

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()
        # 临时目录由 isolated_runs() 整棵删除，无需还原

    passed = sum(1 for ok, _, _ in results if ok)
    print("\n内网口令开关验证：%d/%d" % (passed, len(results)))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
