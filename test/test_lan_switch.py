# -*- coding: utf-8 -*-
"""局域网总开关的真实进程验证（不是单元级）。
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.getcwd()
PORT = 9003
NEED_LOGIN = b'name="password"'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):
        return None


def call(path, host, method="GET", data=None, ctype=None):
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (PORT, path),
                                 data=data, method=method)
    req.add_header("Host", host)
    if ctype:
        req.add_header("Content-Type", ctype)
    try:
        res = urllib.request.build_opener(NoRedirect).open(req, timeout=8)
        return res.status, res.read()
    except urllib.error.HTTPError as err:
        return err.code, err.read()


def main():
    state = os.path.join(ROOT, "runs", "portal_state.json")
    backup = state + ".lanswitch"
    if os.path.exists(state):
        os.replace(state, backup)
    log = open(os.path.join(ROOT, "runs", "lanswitch.log"), "wb")
    proc = subprocess.Popen(
        [sys.executable, "-X", "utf8", "tools/portal_run.py",
         "--port", str(PORT), "--password", "lansw-password-123456", "--lan-only"],
        cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    ok = True
    try:
        time.sleep(6)
        lan = "192.168.9.9:%d" % PORT
        loop = "127.0.0.1:%d" % PORT
        body = call("/", lan)[1]
        a = NEED_LOGIN not in body
        print("%s 1) 局域网开关默认开：内网免密直接见控制台" % ("PASS" if a else "FAIL"))
        ok &= a

        code = call("/_api/settings", loop, "POST",
                    json.dumps({"lanEnabled": False}).encode(),
                    "application/json")[0]
        a = code == 200
        print("%s 2) 从本机关闭局域网开关（HTTP %s）" % ("PASS" if a else "FAIL", code))
        ok &= a

        a = NEED_LOGIN in call("/", lan)[1]
        print("%s 3) 关掉后内网被要求口令" % ("PASS" if a else "FAIL"))
        ok &= a

        a = NEED_LOGIN not in call("/", loop)[1]
        print("%s 4) 关掉后本机仍免密（否则自己在电脑上都进不去）" % ("PASS" if a else "FAIL"))
        ok &= a

        call("/_api/settings", loop, "POST",
             json.dumps({"lanEnabled": True}).encode(), "application/json")
        a = NEED_LOGIN not in call("/", lan)[1]
        print("%s 5) 重新打开后内网恢复免密" % ("PASS" if a else "FAIL"))
        ok &= a

        state_json = json.loads(call("/_api/state", loop)[1].decode("utf-8"))
        a = "lan_enabled" in state_json and state_json["lan_enabled"] is True
        print("%s 6) 状态接口暴露 lan_enabled（设置页据此渲染开关）" % ("PASS" if a else "FAIL"))
        ok &= a
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
    print("\n局域网总开关验证：%s" % ("全部通过" if ok else "有失败"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
