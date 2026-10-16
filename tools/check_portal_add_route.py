# -*- coding: utf-8 -*-
"""真·端到端：用**宿主的 HTTP 处理函数**（createHandler）+ 真门户，验证手动添加。

为什么还要再做一次（上一轮已经验过 postPortalJson 那一层）：
  · 上一轮验的是 `postPortalJson`（宿主转发函数）—— 那证明"转发函数把请求
    正确送到了门户"；
  · 但面板实际打的是 `POST /service-portal/api/services/add` 这条 **HTTP 路由**。
    路由的**匹配与参数解析**是另一段代码（正则 + readJsonBody），它错了同样
    会让"手动添加"失败，而 postPortalJson 那层测试发现不了。
  · 本项目有前科：局域网开关就是"函数层没问题、但路由层把字段漏了"。

本脚本把宿主的路由处理器挂到一个真 HTTP server 上，用**和面板一模一样的
请求**打它，然后用磁盘内容做判据。

运行：python -X utf8 tools/check_portal_add_route.py
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

# 把真实宿主的 createHandler 通过 _internals 暴露出来？没有 —— 它没导出。
# 所以这里直接把 lib/index.js **当模块导入**并抓它的 apply 注册：太重。
# 更稳的做法：起一个真 HTTP server，handler 用 lib/index.js 里那个
# createHandler 的等价物 —— 为此在 lib/index.js 里把 createHandler 导出。


def free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


NODE_HOST = r"""
import { _internals } from %(lib)s;
import http from "node:http";

const [portalPort, hostPort] = process.argv.slice(2).map(Number);
const repo = { infraPath: %(tmp)s, repoPath: %(tmp)s, portalPort: portalPort };
const ctx = { config: { portalPort }, logger: { info() {}, error() {} } };
// 用真实的路由处理器：与 DSH 里挂载的是同一个函数
const handler = _internals.createHandler(() => repo, ctx);
http.createServer((req, res) => {
  handler(req, res).catch((err) => {
    res.writeHead(500, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ ok: false, error: String(err) }));
  });
}).listen(hostPort, "127.0.0.1", () => console.log("HOST_READY"));
"""


def http(method, url, payload=None, timeout=90):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status, json.loads(res.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", "replace")
        try:
            return err.code, json.loads(body)
        except ValueError:
            return err.code, {"raw": body[:200]}
    except Exception as exc:
        return 0, {"error": repr(exc)}


def main():
    tmp = tempfile.mkdtemp(prefix="add-route-")
    runs = os.path.join(tmp, "runs")
    os.makedirs(runs, exist_ok=True)
    reg = os.path.join(runs, "portal_registry.json")
    portal_port = free_port()
    host_port = free_port()
    env = dict(os.environ, PORTAL_RUNS_DIR=runs)

    log = open(os.path.join(tmp, "portal.log"), "wb")
    portal = subprocess.Popen(
        [PY, "-X", "utf8", os.path.join(HERE, "portal_run.py"),
         "--port", str(portal_port), "--password", "add-route-password-1", "--lan-only"],
        cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, env=env)
    host = None
    results = []

    def check(name, cond, detail=""):
        results.append(bool(cond))
        print(("PASS  " if cond else "FAIL  ") + name
              + ((" —— " + detail) if detail else ""))

    try:
        for _ in range(60):
            if http("GET", "http://127.0.0.1:%d/_auth/health" % portal_port,
                    timeout=3)[0] == 200:
                break
            time.sleep(0.5)

        node_file = os.path.join(tmp, "host.mjs")
        with open(node_file, "w", encoding="utf-8") as fh:
            fh.write(NODE_HOST % {
                "lib": json.dumps("file:///" + os.path.join(
                    ROOT, "lib", "index.js").replace("\\", "/")),
                "tmp": json.dumps(tmp),
            })
        host_log = open(os.path.join(tmp, "host.log"), "wb")
        host = subprocess.Popen([NODE, node_file, str(portal_port), str(host_port)],
                                cwd=ROOT, stdout=host_log, stderr=subprocess.STDOUT)
        host_ready = False
        for _ in range(60):
            if http("GET", "http://127.0.0.1:%d/service-portal/api/services"
                    % host_port, timeout=3)[0] == 200:
                host_ready = True
                break
            time.sleep(0.5)
        check("前提：宿主路由处理器起来了", host_ready, "host=%d" % host_port)

        if host_ready:
            # ---- 面板发的就是这一条（与 client/index.jsx 的 request 一致）----
            code, out = http("POST",
                             "http://127.0.0.1:%d/service-portal/api/services/add"
                             % host_port,
                             {"name": "路由层测试服务", "mount": "/routeprobe",
                              "target": "127.0.0.1:19090", "note": "走宿主HTTP路由"})
            check("POST /service-portal/api/services/add -> ok:true",
                  code == 200 and out.get("ok") is True,
                  "HTTP %s %r" % (code, out))

            # 判据在磁盘上
            saved = None
            if os.path.exists(reg):
                with open(reg, encoding="utf-8") as fh:
                    saved = json.load(fh)
            found = [s for s in ((saved or {}).get("services") or [])
                     if s.get("mount") == "/routeprobe"]
            check("磁盘上真的写进去了", len(found) == 1)
            if found:
                check("中文名/上游/备注都无损",
                      found[0].get("name") == "路由层测试服务"
                      and found[0].get("target") == "127.0.0.1:19090"
                      and found[0].get("note") == "走宿主HTTP路由",
                      "%r" % found[0])

            # ---- 读回：宿主 /services 这条 ----
            code, out = http("GET",
                             "http://127.0.0.1:%d/service-portal/api/services"
                             % host_port)
            mounts = [s.get("mount") for s in (out.get("services") or [])]
            check("GET /service-portal/api/services 能读回",
                  code == 200 and "/routeprobe" in mounts, "清单=%r" % mounts)

            # ---- 启停 / 删除也走宿主路由（面板的按钮就是这些）----
            code, out = http(
                "POST", "http://127.0.0.1:%d/service-portal/api/services/routeprobe/disable"
                % host_port)
            check("宿主路由：disable 生效",
                  code == 200 and (out.get("service") or {}).get("enabled") is False,
                  "HTTP %s" % code)
            code, out = http(
                "POST", "http://127.0.0.1:%d/service-portal/api/services/routeprobe/delete"
                % host_port)
            check("宿主路由：delete 生效", code == 200 and out.get("ok") is True,
                  "HTTP %s" % code)
            mounts = [s.get("mount") for s in
                      (http("GET", "http://127.0.0.1:%d/service-portal/api/services"
                            % host_port)[1].get("services") or [])]
            check("删除后清单里没有了", "/routeprobe" not in mounts,
                  "清单=%r" % mounts)

            # ---- 自动发现也走宿主路由 ----
            code, out = http("GET",
                             "http://127.0.0.1:%d/service-portal/api/discover"
                             % host_port, timeout=120)
            check("宿主路由：/discover 能出候选",
                  code == 200 and isinstance(out.get("candidates"), list),
                  "HTTP %s 候选=%s" % (code, len(out.get("candidates") or [])))

            # ---- 反例：校验失败必须如实报错 ----
            code, out = http("POST",
                             "http://127.0.0.1:%d/service-portal/api/services/add"
                             % host_port,
                             {"name": "坏数据", "mount": "/bad", "target": "没有冒号"})
            check("反例：target 非法时如实报错（HTTP 400 + error）",
                  code == 400 and out.get("ok") is not True and out.get("error"),
                  "HTTP %s %r" % (code, out.get("error")))

        passed = sum(1 for r in results if r)
        print("\n手动添加（宿主路由层）控制检验：%d/%d" % (passed, len(results)))
        return 0 if passed == len(results) else 1
    finally:
        for p in (host, portal):
            if p is not None and p.poll() is None:
                p.kill()
        for fh in (log,):
            try:
                fh.close()
            except Exception:
                pass
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
