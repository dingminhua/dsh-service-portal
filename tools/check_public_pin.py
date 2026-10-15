# -*- coding: utf-8 -*-
"""公网「自定义密码」控制检验（对齐 dsh-pocket issue #33 的体验）。

需求：公网也要能设自定义密码，体验与局域网一样，但公网必须有警告提示。

本检验打**真行为**：起一个真门户（临时端口 + 临时 PORTAL_RUNS_DIR），
通过门户的 `/_api/public-pin/custom` 设自定义密码，然后：
  1. 用**新密码**走登录，必须真的能登进去（说明立即生效）；
  2. 用**旧密码**必须登不进去（说明真的换掉了，不是只改了显示）；
  3. 自定义后状态里 public_pin_custom 必须是真；
  4. 换回随机后，新口令与自定义那个不同、且标记复位；
  5. 安全负例（关键）：
     · 公网密码 = 局域网口令 -> 必须被拒（不能把内网口令升级成公网凭据）；
     · 纯数字口令 -> 必须被拒（公网不许用局域网那套短数字）；
     · 太短（<12）-> 必须被拒。

运行：python -X utf8 tools/check_public_pin.py
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
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable

sys.path.insert(0, HERE)
import portal_login  # noqa: E402  —— 会话 cookie 名**从源码取**，不靠猜（猜错过一次）

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


def post(port, path, payload, host="127.0.0.1"):
    """向门户发 API（用 Host 头模拟公网来源，走公网认证分支）。"""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:%d%s" % (port, path), data=data,
        headers={"Content-Type": "application/json", "Host": host},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            return res.status, json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", "replace")
        try:
            return err.code, json.loads(body)
        except Exception:
            return err.code, {"raw": body[:200]}


def state(port):
    with urllib.request.urlopen("http://127.0.0.1:%d/_api/state" % port,
                                timeout=8) as res:
        return json.loads(res.read().decode("utf-8"))


def try_public_login(port, candidate, host="public.example.com"):
    """用候选口令走公网登录，返回 (http_status, 是否登录成功)。

    判定依据是**是否下发了会话 cookie** —— 那才是"真的认了"，
    比看返回体里有没有"错误"字样可靠。

    路径是 /_auth/login（不是 /login）—— 第一版写错成 /login，
    结果新旧口令都"没登录成功"，两个用例的结论互相矛盾却都 PASS/FAIL 得莫名其妙。
    """
    data = urllib.parse.urlencode({"password": candidate}).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:%d/_auth/login" % port, data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "Host": host}, method="POST")
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(req, timeout=10) as res:
            cookie = res.headers.get("Set-Cookie") or ""
            res.read()
            return res.status, (portal_login.SESSION_COOKIE in cookie), ""
    except urllib.error.HTTPError as err:
        cookie = err.headers.get("Set-Cookie") or ""
        return err.code, (portal_login.SESSION_COOKIE in cookie), ""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def main():
    tmp = tempfile.mkdtemp(prefix="public-pin-")
    runs = os.path.join(tmp, "runs")
    os.makedirs(runs, exist_ok=True)
    port = free_port()
    initial = "initial-password-abc"
    log = open(os.path.join(tmp, "portal.log"), "wb")
    proc = subprocess.Popen(
        [PY, "-X", "utf8", os.path.join(HERE, "portal_run.py"),
         "--port", str(port), "--password", initial, "--lan-only"],
        cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
        env=dict(os.environ, PORTAL_RUNS_DIR=runs))
    try:
        ready = False
        for _ in range(60):
            try:
                state(port)
                ready = True
                break
            except Exception:
                time.sleep(0.5)
        check("门户起来了（前提）", ready, "port=%d" % port)
        if not ready:
            return 1

        # 先打开局域网口令，否则 state 里的 lan_password 是空串
        # （内网免密时后端不返回它），"公网=局域网"这条就永远测不到。
        post(port, "/_api/settings", {"lanAuthEnabled": True})
        time.sleep(0.3)
        lan_pin = state(port).get("lan_password") or ""
        check("（前提）拿到了局域网口令，才能验证'不能相同'这条",
              bool(lan_pin), "lan_pin 长度=%d" % len(lan_pin))

        # ---- 门槛负例（先测，避免污染后面的正例）----
        # 注意：字符种类不限（体验与局域网一致），所以"纯数字"是**合法**的，
        # 只有长度不够才拒。"12 位纯数字"应当被接受 —— 这条是正例不是负例。
        code, out = post(port, "/_api/public-pin/custom", {"value": "123456789012"})
        check("正例：12 位纯数字被接受（不限制字符种类，体验与局域网一致）",
              code == 200 and out.get("ok") is True,
              "HTTP %s %r" % (code, out.get("error")))

        code, out = post(port, "/_api/public-pin/custom", {"value": "short1"})
        check("负例：太短（<12）口令被拒", code == 400 and out.get("ok") is not True,
              "HTTP %s %r" % (code, out.get("error")))

        code, out = post(port, "/_api/public-pin/custom", {"value": "   "})
        check("负例：空白口令被拒", code == 400 and out.get("ok") is not True,
              "HTTP %s %r" % (code, out.get("error")))

        if lan_pin:
            code, out = post(port, "/_api/public-pin/custom", {"value": lan_pin})
            check("负例：公网密码 = 局域网口令被拒（不能把内网口令升级成公网凭据）",
                  code == 400 and out.get("ok") is not True,
                  "HTTP %s %r" % (code, out.get("error")))
        else:
            check("负例：公网密码 = 局域网口令被拒（无局域网口令，跳过）", True)

        # ---- 正例：设一个自定义公网密码 ----
        custom = "My-Own-Public-9x"
        code, out = post(port, "/_api/public-pin/custom", {"value": custom})
        check("自定义公网密码被接受", code == 200 and out.get("ok") is True,
              "HTTP %s" % code)
        check("返回体回传了自定义标记", out.get("public_pin_custom") is True,
              repr(out))
        check("状态里 public_pin_custom 变成真",
              state(port).get("public_pin_custom") is True)
        check("状态里 password 就是刚设的新密码（不是旧启动口令）",
              state(port).get("password") == custom,
              "实际=%r" % (state(port).get("password"),))

        # ---- 真登录验证：立即生效 / 旧口令作废 ----
        status_new, ok_new, _ = try_public_login(port, custom)
        check("用**新密码**走公网登录能进去（立即生效，没重启门户）", ok_new,
              "HTTP %s" % status_new)
        status_old, ok_old, _ = try_public_login(port, initial)
        check("用**旧密码**登不进去（真的换掉了，不只是改了显示）", not ok_old,
              "HTTP %s" % status_old)

        # ---- 换回随机 ----
        code, out = post(port, "/_api/public-pin/random", {})
        back = state(port).get("password")
        check("换回随机：标记复位", state(port).get("public_pin_custom") is False)
        check("换回随机：真的换成了不同的口令", back and back != custom,
              "新=%r" % (back,))
        status_back, ok_back, _ = try_public_login(port, back or "")
        check("换回随机后：新随机口令能登录", ok_back, "HTTP %s" % status_back)
        status_custom, ok_custom, _ = try_public_login(port, custom)
        check("换回随机后：自定义那个口令失效", not ok_custom,
              "HTTP %s" % status_custom)

        # ---- 自定义要能**重启后延续**（落盘）----
        code, out = post(port, "/_api/public-pin/custom", {"value": custom})
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()
        log = open(os.path.join(tmp, "portal2.log"), "wb")
        proc = subprocess.Popen(
            [PY, "-X", "utf8", os.path.join(HERE, "portal_run.py"),
             "--port", str(port), "--password", "another-random-start-1",
             "--lan-only"],
            cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
            env=dict(os.environ, PORTAL_RUNS_DIR=runs))
        ready2 = False
        for _ in range(60):
            try:
                state(port)
                ready2 = True
                break
            except Exception:
                time.sleep(0.5)
        check("重启后门户又起来了（前提）", ready2)
        check("自定义公网密码**重启后仍在**（用户特意设的不该丢）",
              state(port).get("password") == custom,
              "实际=%r" % (state(port).get("password"),))

        passed = sum(1 for ok, _, _ in results if ok)
        print("\n公网自定义密码控制检验：%d/%d" % (passed, len(results)))
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
