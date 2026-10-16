# -*- coding: utf-8 -*-
"""「屏蔽」不得停止上游进程 —— 用户最关心的语义，必须用真进程验证。

用户的原话：
  「每个节点都有屏蔽和开放的开关，不是服务开启的开关」
  「启动服务是服务本身的事情，这里只是负责可以路由」
  「如果是负责启动和停止，还需要配置对应的启停程序，暂不处理」

所以要证明两件事：
  1. 「屏蔽」只是门户不再转发（路由 404），**上游进程照跑不误**；
  2. 重启门户、删除节点，都不会去 kill 上游。

判据：上游是个真实进程（我们起的探针 HTTP 服务），直接检查它的 PID 还活着。

运行：python -X utf8 tools/check_gate_does_not_stop_upstream.py
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


def http(method, url, payload=None, timeout=30):
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
                return res.status, {"raw": body[:200]}
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", "replace")
        try:
            return err.code, json.loads(body)
        except ValueError:
            return err.code, {"raw": body[:200]}
    except Exception as exc:
        return 0, {"error": repr(exc)}


def pid_alive(pid):
    """这个 PID 还活着吗（跨平台最省事的判定）。"""
    if os.name == "nt":
        done = subprocess.run(["tasklist", "/FI", "PID eq %d" % pid],
                              capture_output=True, text=True, errors="replace",
                              encoding="utf-8", timeout=30)
        return str(pid) in (done.stdout or "")
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def main():
    tmp = tempfile.mkdtemp(prefix="gate-")
    runs = os.path.join(tmp, "runs")
    os.makedirs(runs, exist_ok=True)
    portal_port = free_port()
    upstream_port = free_port()

    # 起一个"上游程序"：真实的探针 HTTP 服务（模拟用户自己的应用）
    upstream = subprocess.Popen(
        [PY, "-X", "utf8", "-c",
         "import http.server,socketserver,sys\n"
         "class H(http.server.BaseHTTPRequestHandler):\n"
         "    def do_GET(self):\n"
         "        self.send_response(200)\n"
         "        self.send_header('Content-Type','text/html')\n"
         "        self.end_headers()\n"
         "        self.wfile.write(b'<title>UPSTREAM-OK</title>')\n"
         "    def log_message(self,*a): pass\n"
         "socketserver.TCPServer(('127.0.0.1', int(sys.argv[1])), H).serve_forever()\n",
         str(upstream_port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    log = open(os.path.join(tmp, "portal.log"), "wb")
    proc = subprocess.Popen(
        [PY, "-X", "utf8", os.path.join(HERE, "portal_run.py"),
         "--port", str(portal_port), "--password", "gate-password-123", "--lan-only"],
        cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
        env=dict(os.environ, PORTAL_RUNS_DIR=runs))
    try:
        ready = False
        for _ in range(60):
            if http("GET", "http://127.0.0.1:%d/_auth/health" % portal_port,
                    timeout=3)[0] == 200:
                ready = True
                break
            time.sleep(0.5)
        check("前提：门户起来了", ready, "port=%d" % portal_port)
        check("前提：上游探针起来了",
              pid_alive(upstream.pid), "pid=%d port=%d" % (upstream.pid, upstream_port))
        if not ready:
            return 1

        base = "http://127.0.0.1:%d" % portal_port
        # 添加节点 -> 默认开放
        code, out = http("POST", base + "/_api/services",
                         {"name": "闸门测试节点", "mount": "/gate",
                          "target": "127.0.0.1:%d" % upstream_port})
        check("添加节点成功", code == 200 and out.get("ok") is True, "HTTP %s" % code)
        check("新节点默认就是开放", (out.get("service") or {}).get("enabled") is True)

        # 开放状态下：门户能把请求转过去
        try:
            with urllib.request.urlopen(base + "/gate/", timeout=10) as res:
                body = res.read().decode("utf-8", "replace")
                check("开放时门户真的转发了（看到上游页面）", "UPSTREAM-OK" in body)
        except Exception as exc:
            check("开放时门户真的转发了（看到上游页面）", False, repr(exc))

        # ---- 核心：屏蔽 ----
        code, out = http("POST", base + "/_api/services/gate/block")
        check("屏蔽调用成功", code == 200 and out.get("ok") is True, "HTTP %s" % code)
        check("屏蔽后注册表里是关闭", (out.get("service") or {}).get("enabled") is False)
        check("**屏蔽后上游进程照样活着**（用户最关心的一条）",
              pid_alive(upstream.pid), "pid=%d" % upstream.pid)
        # 屏蔽 = 门户不转发这条路由
        code, _ = http("GET", base + "/gate/")
        check("屏蔽后门户不再转发（404）", code == 404, "HTTP %s" % code)
        # 上游自己仍然直接可访问（证明我们没碰它）
        try:
            with urllib.request.urlopen(
                    "http://127.0.0.1:%d/" % upstream_port, timeout=8) as res:
                check("绕过门户直连上游仍正常（说明我们没停它）",
                      "UPSTREAM-OK" in res.read().decode("utf-8", "replace"))
        except Exception as exc:
            check("绕过门户直连上游仍正常（说明我们没停它）", False, repr(exc))

        # ---- 重新开放 ----
        code, out = http("POST", base + "/_api/services/gate/open")
        check("重新开放成功", code == 200 and (out.get("service") or {}).get("enabled") is True)
        try:
            with urllib.request.urlopen(base + "/gate/", timeout=10) as res:
                check("重新开放后又能访问", "UPSTREAM-OK" in res.read().decode("utf-8", "replace"))
        except Exception as exc:
            check("重新开放后又能访问", False, repr(exc))

        # ---- restart 必须被拒（那是启停语义，已取消）----
        # 注意：必须在节点**还存在**时测，否则 404 是因为"没这个服务"，
        # 而不是因为"restart 被拒" —— 那样就成了"因为错误的原因通过"。
        code, out = http("POST", base + "/_api/services/gate/restart")
        check("restart 被拒（不再有启停语义）",
              code in (400, 404) and out.get("ok") is not True,
              "HTTP %s %r" % (code, out.get("error")))
        check("restart 被拒的原因是「不认识的动作」（不是「没这个服务」）",
              "不认识的动作" in str(out.get("error") or ""),
              "%r" % (out.get("error"),))
        check("被拒之后上游照样活着", pid_alive(upstream.pid), "pid=%d" % upstream.pid)

        # ---- 删除节点也不该动上游 ----
        code, out = http("POST", base + "/_api/services/gate/delete")
        check("删除节点成功", code == 200 and out.get("ok") is True, "HTTP %s" % code)
        check("**删除节点后上游进程照样活着**", pid_alive(upstream.pid),
              "pid=%d" % upstream.pid)

        passed = sum(1 for ok, _, _ in results if ok)
        print("\n「屏蔽不动上游」控制检验：%d/%d" % (passed, len(results)))
        return 0 if passed == len(results) else 1
    finally:
        for p in (proc,):
            if p.poll() is None:
                p.kill()
        # 我们自己起的探针，自己收掉（它不代表用户的服务）
        try:
            upstream.terminate()
        except Exception:
            pass
        try:
            log.close()
        except Exception:
            pass
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
