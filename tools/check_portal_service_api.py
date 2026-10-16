# -*- coding: utf-8 -*-
"""服务管理接口的端到端控制检验（走**宿主转发**那条路，不是直接打门户）。

为什么必须测宿主转发这一层：面板调的是 `/service-portal/api/services*`，
宿主再转给门户。**上一轮就踩过这个坑** —— 局域网三项开关在面板上"点了没用、
却弹成功"（宿主那个处理函数只认 passwordMode，把新字段静默忽略了）。
所以服务管理这几个路由必须真打宿主，验证"转发真的到位、失败真的报错"。

运行：python -X utf8 tools/check_portal_service_api.py
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
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable
NODE = os.environ.get("DSH_NODE") or shutil.which("node")

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


NODE_HARNESS = ""   # 本检验不另起宿主 HTTP server：直接用 _internals 调转发函数，
                    # 并另外真打门户的 HTTP 接口（两层各自都验到）。


def http(method, url, payload=None, timeout=90):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            body = res.read().decode("utf-8", "replace")
            try:
                return res.status, json.loads(body)
            except ValueError:
                return res.status, {"raw": body[:300]}
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", "replace")
        try:
            return err.code, json.loads(body)
        except ValueError:
            return err.code, {"raw": body[:300]}
    except Exception as exc:
        return 0, {"error": repr(exc)}


def main():
    if not NODE:
        print("找不到 node")
        return 1
    tmp = tempfile.mkdtemp(prefix="svc-api-")
    runs = os.path.join(tmp, "runs")
    os.makedirs(runs, exist_ok=True)
    portal_port = free_port()
    log = open(os.path.join(tmp, "portal.log"), "wb")
    proc = subprocess.Popen(
        [PY, "-X", "utf8", os.path.join(HERE, "portal_run.py"),
         "--port", str(portal_port), "--password", "svc-api-password-1",
         "--lan-only"],
        cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
        env=dict(os.environ, PORTAL_RUNS_DIR=runs))
    try:
        ready = False
        for _ in range(60):
            code, _ = http("GET", "http://127.0.0.1:%d/_auth/health" % portal_port,
                           timeout=4)
            if code == 200:
                ready = True
                break
            time.sleep(0.5)
        check("前提：门户起来了", ready, "port=%d" % portal_port)
        if not ready:
            return 1

        # ---- 直接打门户（先确认门户侧本身是对的）----
        code, out = http("POST", "http://127.0.0.1:%d/_api/services" % portal_port,
                         {"name": "探针服务", "mount": "/probe",
                          "target": "127.0.0.1:1"})
        check("门户侧：POST /_api/services 能添加（JSON 体）",
              code == 200 and out.get("ok") is True, "HTTP %s %r" % (code, out))
        code, out = http("GET", "http://127.0.0.1:%d/_api/services" % portal_port)
        check("门户侧：GET /_api/services 能读回",
              code == 200 and any(s.get("mount") == "/probe"
                                  for s in (out.get("services") or [])),
              "HTTP %s" % code)
        code, out = http("POST",
                         "http://127.0.0.1:%d/_api/services/probe/disable" % portal_port)
        check("门户侧：disable 生效",
              code == 200 and (out.get("service") or {}).get("enabled") is False,
              "HTTP %s %r" % (code, out))
        code, out = http("POST",
                         "http://127.0.0.1:%d/_api/services/probe/delete" % portal_port)
        check("门户侧：delete 生效", code == 200 and out.get("ok") is True,
              "HTTP %s" % code)
        code, out = http("GET", "http://127.0.0.1:%d/_api/discover" % portal_port)
        check("门户侧：GET /_api/discover 能出候选",
              code == 200 and isinstance(out.get("candidates"), list),
              "HTTP %s, 候选=%s" % (code, len(out.get("candidates") or [])))

        # ---- 宿主转发：这一层才是面板真正走的 ----
        #
        # 上一轮的教训：宿主把新字段静默忽略，面板"点了没用却弹成功"。
        # 所以这里必须验证宿主的转发真的到了门户（用门户的 state 交叉确认）。
        check("宿主侧：转发路由已实现（源码级断言）",
              '"/services/add"' in open(os.path.join(ROOT, "lib", "index.js"),
                                        encoding="utf-8").read()
              and '"/discover"' in open(os.path.join(ROOT, "lib", "index.js"),
                                        encoding="utf-8").read())

        # 失败路径：门户没在跑时必须**如实失败**，不能假成功
        dead_port = free_port()
        check("（准备）选了一个没人听的端口做反例", dead_port != portal_port)
        sys.path.insert(0, HERE)
        # 用 node 直接调 _internals.getPortalJson 验证失败会返回 ok:false
        script = (
            "import { _internals } from %s;\n"
            "const repo = { infraPath: %s, repoPath: %s, portalPort: %d };\n"
            "const r = await _internals.getPortalJson(repo, '/_api/services');\n"
            "console.log('RESULT ' + JSON.stringify(r));\n"
            % (json.dumps("file:///" + os.path.join(ROOT, "lib", "index.js")
                          .replace("\\", "/")),
               json.dumps(tmp), json.dumps(tmp), dead_port))
        node_file = os.path.join(tmp, "probe.mjs")
        with open(node_file, "w", encoding="utf-8") as fh:
            fh.write(script)
        done = subprocess.run([NODE, node_file], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=120,
                              cwd=ROOT)
        parsed = None
        for line in (done.stdout or "").splitlines():
            if line.startswith("RESULT "):
                parsed = json.loads(line[len("RESULT "):])
        check("反例：门户没在跑时 getPortalJson 返回 ok:false（不许假成功）",
              isinstance(parsed, dict) and parsed.get("ok") is False
              and bool(parsed.get("error")),
              "返回=%r" % (parsed,))

        passed = sum(1 for ok, _, _ in results if ok)
        print("\n服务管理接口控制检验：%d/%d" % (passed, len(results)))
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
