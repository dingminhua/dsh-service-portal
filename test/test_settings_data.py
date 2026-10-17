# -*- coding: utf-8 -*-
"""验证设置页需要的数据链：宿主 status → 二维码 → 页面可用。

这是「设置页能不能显示出 dsh-pocket 那样的区块」的**后端证据**：
  · /status 返回内网地址、公网地址、lanAuthEnabled（设置页据此渲染两个区块）
  · /qr 能为内网/公网地址出二维码（设置页用它显示扫码图）
  · 二维码接口只认本门户自己的地址（防止被当免费图床）
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "test"))
from portal_isolation import portal_env  # noqa: E402
PORT = 8999


def portal_call(path, method="GET", data=None, ctype=None):
    """直连门户进程（loopback = 永远免密，是插件调用它的方式）。"""
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (PORT, path),
                                 data=data, method=method)
    req.add_header("Host", "127.0.0.1:%d" % PORT)
    if ctype:
        req.add_header("Content-Type", ctype)
    try:
        with urllib.request.urlopen(req, timeout=8) as res:
            return res.status, res.read()
    except urllib.error.HTTPError as err:
        return err.code, err.read()
    except urllib.error.URLError:
        # 就绪轮询期间端口还没人听是正常现象，不能炸掉整份检验
        return 0, b""


def main():
    # 状态目录隔离到临时目录（见 test/portal_isolation.py）
    runs = tempfile.mkdtemp(prefix="portal-runs-")
    state_file = os.path.join(runs, "portal_state.json")
    reg_file = os.path.join(runs, "portal_registry.json")

    log = open(os.path.join(runs, "setpage-check.log"), "wb")
    proc = subprocess.Popen(
        [sys.executable, "-X", "utf8",
         os.path.join(ROOT, "tools", "portal_run.py"),
         "--port", str(PORT), "--password", "setpage-check-password-1", "--lan-only"],
        cwd=ROOT, env=portal_env(runs), stdout=log, stderr=subprocess.STDOUT)

    results = []

    def check(label, cond, detail=""):
        results.append((bool(cond), label, detail))
        print("%s  %s %s" % ("PASS" if cond else "FAIL", label, detail))

    try:
        ready = False
        for _ in range(60):
            if portal_call("/_auth/health")[0] == 200:
                ready = True
                break
            time.sleep(0.5)
        check("门户就绪", ready)
        if not ready:
            return 1

        # 1. 状态接口给设置页所需字段
        status, body = portal_call("/_api/state")
        state = json.loads(body.decode("utf-8"))
        check("状态里有内网地址（设置页据此显示局域网区块）",
              bool(state.get("lan_urls")), "lan_urls=%r" % state.get("lan_urls"))
        check("状态里有 lanAuthEnabled（设置页据此渲染密码开关）",
              "lan_auth_enabled" in state, "keys=%r" % sorted(state.keys()))
        check("状态里有 portal_port", bool(state.get("portal_port")))

        # 2. 二维码接口能为内网地址出图
        lan = state["lan_urls"][0]
        status, body = portal_call("/_api/qr?url=" + urllib.parse.quote(lan))
        payload = json.loads(body.decode("utf-8"))
        check("能为内网地址生成二维码",
              status == 200 and payload.get("ok") and
              str(payload.get("qr", "")).startswith("data:image/svg+xml"),
              "status=%s" % status)
        check("二维码是内联数据（不依赖外部请求）",
              "base64," in str(payload.get("qr", "")))

        # 3. 二维码只给本门户地址（防被当图床）
        status, body = portal_call(
            "/_api/qr?url=" + urllib.parse.quote("https://evil.example.com"))
        check("拒绝为外部地址生成二维码（403）",
              status == 403, "status=%s" % status)

        # 4. 控制台页面本身可打开（扫码后到达的就是它）
        status, body = portal_call("/")
        check("控制台页面可打开（扫码后的落地页）",
              status == 200 and "对外服务门户".encode() in body)
        # 用户要求门户页只读（测试页 + 引导页，没有设置功能）：不能有添加表单
        check("门户页只读：没有添加/管理表单",
              b'name="mount"' not in body and b'name="target"' not in body
              and b"<form" not in body)
        check("门户页引导去插件设置里管理",
              "设置 → 插件 → dsh-service-portal → 配置".encode() in body)

        # 5. 切内网口令后状态与行为一致
        portal_call("/_api/settings", "POST",
                    json.dumps({"lanAuthEnabled": True}).encode(),
                    "application/json")
        status, body = portal_call("/_api/state")
        state2 = json.loads(body.decode("utf-8"))
        check("开关写入后状态接口立刻反映",
              state2.get("lan_auth_enabled") is True)

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()
        for path in (state_file, state_file + ".tmp", reg_file):
            if os.path.exists(path):
                os.remove(path)
        shutil.rmtree(runs, ignore_errors=True)   # 临时目录整棵删除

    passed = sum(1 for ok, _, _ in results if ok)
    print("\n设置页数据链验证：%d/%d" % (passed, len(results)))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
