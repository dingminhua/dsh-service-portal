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

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from portal_isolation import isolated_runs, portal_env  # noqa: E402

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
    # 状态目录用**临时目录**，不碰用户真实 runs/。
    #
    # 这里原来是"把用户的 portal_state.json 移走、跑完再移回来"。实际事故：
    # 它起停了一次门户，用户的状态被写成 stopped_clean=true，他打开设置页看到
    # 「门户未启动」—— 一个测试把用户正在用的门户关了。备份/还原在异常退出时
    # 也不会执行，等于把用户状态留在半残态。
    with isolated_runs() as runs:
        return _run(runs)


def _run(runs):
    log = open(os.path.join(runs, "lanswitch.log"), "wb")
    proc = subprocess.Popen(
        [sys.executable, "-X", "utf8", "tools/portal_run.py",
         "--port", str(PORT), "--password", "lansw-password-123456", "--lan-only"],
        cwd=ROOT, env=portal_env(runs), stdout=log, stderr=subprocess.STDOUT)
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

        # 关掉后是**硬 403**，不是登录页、也不是"输口令就能进"。
        # 为什么必须是 403（对齐 dsh-pocket 的 issue #54）：手机端的人不是
        # 决策者，给他一个登录页等于让他以为自己口令错了，白试一遍。
        code, body = call("/", lan)
        a = code == 403 and NEED_LOGIN not in body
        print("%s 3) 关掉后内网直接 403（不是登录页） HTTP %s" % ("PASS" if a else "FAIL", code))
        ok &= a

        a = "局域网访问已关闭" in body.decode("utf-8", "replace")
        print("%s 3b) 403 页面说明「已关闭」并指向电脑上开" % ("PASS" if a else "FAIL"))
        ok &= a

        # JSON 请求要拿到机器可读的原因，别让前端把它当网络故障静默重试
        code, body = call("/_api/state", lan)
        a = code == 403 and b"lan-disabled" in body
        print("%s 3c) 关掉后 API 也 403 且带 lan-disabled（可取判）" % ("PASS" if a else "FAIL"))
        ok &= a

        # 公网不受这个开关影响：它照旧走自己的口令
        code, body = call("/", "x.trycloudflare.com")
        a = NEED_LOGIN in body
        print("%s 3d) 关局域网不掐死公网（公网仍要口令）" % ("PASS" if a else "FAIL"))
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
        # 临时目录由 isolated_runs() 负责整棵删除，这里不需要还原任何东西
    print("\n局域网总开关验证：%s" % ("全部通过" if ok else "有失败"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
