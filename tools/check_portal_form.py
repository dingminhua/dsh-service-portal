# -*- coding: utf-8 -*-
"""控制台表单提交控制检验。

拦的 bug（用户实测报的）：
  控制台页面用**原生表单提交**（`<form method="POST">`，浏览器发
  `application/x-www-form-urlencoded`），而 API 只 `json.loads` ——
  于是页面上点「添加服务」永远得到 `{"ok": false, "error": "请求体不是合法 JSON"}`。
  **功能看起来在，实际一个服务都加不进去。**

这个检验真起门户进程，用表单编码提交，并验证服务真的加进去了。
同时也验证 JSON 调用仍然可用（插件/脚本走 JSON）。
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
PORT = 9099
results = []


def check(label, cond, detail=""):
    results.append(bool(cond))
    print("%s  %s %s" % ("PASS" if cond else "FAIL", label, detail))


def call(path, method="GET", data=None, ctype=None, timeout=10):
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (PORT, path),
                                 data=data, method=method)
    req.add_header("Host", "127.0.0.1:%d" % PORT)
    if ctype:
        req.add_header("Content-Type", ctype)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        type("NR", (urllib.request.HTTPRedirectHandler,),
             {"redirect_request": lambda *a, **k: None})())
    try:
        with opener.open(req, timeout=timeout) as res:
            return res.status, res.read()
    except urllib.error.HTTPError as err:
        return err.code, err.read()
    except urllib.error.URLError:
        # 就绪轮询期间端口还没人听是正常现象，不能炸掉整份检验
        return 0, b""


def main():
    # 状态目录隔离到临时目录（见 test/portal_isolation.py）：
    # 原来是把用户真实状态文件移走再移回，中途异常退出会留在半残态。
    runs = tempfile.mkdtemp(prefix="portal-runs-")
    state = os.path.join(runs, "portal_state.json")
    reg = os.path.join(runs, "portal_registry.json")

    log = open(os.path.join(runs, "form-check.log"), "wb")
    proc = subprocess.Popen(
        [sys.executable, "-X", "utf8", os.path.join(ROOT, "tools", "portal_run.py"),
         "--port", str(PORT), "--password", "form-check-password-1", "--lan-only"],
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

        # ---- 1. 表单提交（这就是控制台页面点「添加服务」发的东西）----
        form = urllib.parse.urlencode({
            "name": "RL配置训练台", "mount": "/rltrain",
            "target": "127.0.0.1:8810", "note": "111",
        }).encode("utf-8")
        code, body = call("/_api/services", "POST", form,
                          "application/x-www-form-urlencoded")
        ok = False
        try:
            ok = json.loads(body.decode("utf-8")).get("ok") is True
        except ValueError:
            pass
        check("表单提交能添加服务（不再是「请求体不是合法 JSON」）",
              code == 200 and ok, "code=%s body=%r" % (code, body[:140]))

        # ---- 2. 服务真的落进注册表了吗（不只是回了 ok）----
        code, body = call("/_api/state")
        svc = None
        try:
            data = json.loads(body.decode("utf-8"))
            svc = next((s for s in data.get("services", [])
                        if s.get("mount") == "/rltrain"), None)
        except ValueError:
            pass
        check("服务真的进了注册表（名称/上游都对）",
              bool(svc) and svc.get("name") == "RL配置训练台"
              and svc.get("target") == "127.0.0.1:8810"
              and svc.get("note") == "111",
              "svc=%r" % svc)

        # ---- 3. JSON 调用仍然可用（插件/脚本走这条）----
        code, body = call("/_api/services", "POST",
                          json.dumps({"key": "viajson", "name": "JSON 加的",
                                      "mount": "/viajson",
                                      "target": "127.0.0.1:9999"}).encode(),
                          "application/json")
        ok = False
        try:
            ok = json.loads(body.decode("utf-8")).get("ok") is True
        except ValueError:
            pass
        check("JSON 提交仍然可用", code == 200 and ok, "code=%s" % code)

        # ---- 4. 表单开关（enable/disable 也是表单提交，空体）----
        # 用上面刚加的那个服务（不是写死 realapp —— 注册表在测试里是干净的）
        code, body = call("/_api/services/rltrain/disable", "POST", b"",
                          "application/x-www-form-urlencoded")
        check("空表单体的开关操作不报 JSON 错",
              code == 200, "code=%s body=%r" % (code, body[:120]))
        if code == 200:
            try:
                check("开关生效（disable 后 enabled=false）",
                      json.loads(body.decode("utf-8"))
                      .get("service", {}).get("enabled") is False,
                      body[:140].decode("utf-8", "replace"))
            except ValueError:
                check("开关返回 JSON", False, body[:120])

        # ---- 5. 反例控制：真的坏 JSON 要被拒（不能因为宽容而什么都收）----
        code, body = call("/_api/services", "POST", b"{this is not json",
                          "application/json")
        check("坏 JSON 被明确拒绝（不是静默当成空表单）",
              code == 400, "code=%s body=%r" % (code, body[:100]))

        # ---- 6. 表单字段缺失要给出可读错误（不是崩）----
        code, body = call("/_api/services", "POST",
                          urllib.parse.urlencode({"name": "只有名字"}).encode(),
                          "application/x-www-form-urlencoded")
        check("表单缺字段被拒且给出中文原因",
              code == 400 and b"ok" in body, "code=%s body=%r" % (code, body[:140]))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()
        shutil.rmtree(runs, ignore_errors=True)   # 临时目录整棵删除

    passed = sum(1 for ok in results if ok)
    print("\n控制台表单提交控制检验：%d/%d" % (passed, len(results)))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
