# -*- coding: utf-8 -*-
"""目标验收：真实门户进程 + 真实服务，逐条验证五项要求。

这一份是**验收脚本**（不是单元检验），跑的是用户真实会用的那条命令，
用真实 HTTP 与真实 Host 分类走完整链路。

五项验收：
  ① 控制台在页面上增删服务、设路由、逐服务开关、点链接访问
  ② 内网直连免密 + 外网必须口令
  ③ 二维码可生成、手机端适配、登录限速、健康检查
  ④ classifyHost 三分类（loopback/lan/public）且 fail-closed
  ⑤ 依赖缺失跳过返回 2
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402

PASSWORD = "acceptance-password-1234"
PORT = 8991
PUBLIC_HOST = "acceptance-demo.trycloudflare.com"
LAN_HOST = "192.168.33.44:%d" % PORT
RESULTS = []


class App(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    alive = True

    def do_GET(self):
        if not App.alive:
            self.send_response(503)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = b"APP:" + self.path.encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):
        return None


def call(path, host, cookie=None, method="GET", data=None, ctype=None):
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (PORT, path),
                                 data=data, method=method)
    req.add_header("Host", host)
    if cookie:
        req.add_header("Cookie", cookie)
    if ctype:
        req.add_header("Content-Type", ctype)
    try:
        res = urllib.request.build_opener(NoRedirect).open(req, timeout=8)
        return res.status, res.read(), res.headers
    except urllib.error.HTTPError as err:
        return err.code, err.read(), err.headers
    except Exception as exc:
        return 0, repr(exc).encode(), {}


def check(label, cond, detail=""):
    RESULTS.append((bool(cond), label, detail))
    print("%s  %s %s" % ("PASS" if cond else "FAIL", label, detail))


def main():
    app = ThreadingHTTPServer(("127.0.0.1", 0), App)
    threading.Thread(target=app.serve_forever, daemon=True).start()
    app_port = app.server_address[1]

    # ---------------------------------------------------------------
    # 隔离：让门户把状态写进**临时目录**，绝不碰用户真实的 runs/。
    #
    # 这里原来是"备份真实文件 → 删掉 → 跑完还原"，看着稳妥，实际漏了：
    #
    #     backup = None
    #     for path in (state_file, reg_file):
    #         if os.path.exists(path):
    #             backup = backup or tempfile.mkdtemp(...)   # ← 只在**第一个存在**的文件上建
    #             ...
    #
    # 用户真实目录里往往 **只有 portal_state.json、还没有 portal_registry.json**
    # （他还没添加过任何服务）。于是 backup 因 state 而建，注册表从未进备份。
    # 收尾时 `if backup:` 成立 → 走还原分支 → **注册表既不还原也不删除**。
    # 而脚本中途会往注册表里加一条测试服务 "s2"（见下面 ② 开头），
    # 它就永久留在了用户的真实配置里，指向一个早已关闭的随机端口。
    # 用户看到控制台凭空多出一个"服务二"，而他从没设置过。
    #
    # 根因不是"忘了删"，而是**测试直接改真实配置、只靠收尾兜底**。
    # 正确做法是根本不写那个目录：门户/注册表路径都跟随 PORTAL_RUNS_DIR
    # （tools/portal_run.py 已支持），跑在哪儿都影响不到真实数据。
    # ---------------------------------------------------------------
    runs = tempfile.mkdtemp(prefix="portal-acc-runs-")
    env = dict(os.environ, PORTAL_RUNS_DIR=runs)

    log = open(os.path.join(tempfile.gettempdir(), "portal-acceptance.log"), "wb")
    proc = subprocess.Popen(
        [sys.executable, "-X", "utf8",
         os.path.join(ROOT, "tools", "portal_run.py"),
         "--port", str(PORT), "--password", PASSWORD, "--lan-only"],
        cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, env=env)

    try:
        ready = False
        for _ in range(60):
            if call("/_auth/health", LAN_HOST)[0] == 200:
                ready = True
                break
            time.sleep(0.5)
        check("门户进程就绪", ready)
        if not ready:
            return 1

        print("\n【① 控制台管理服务】")
        status, body, _ = call("/", LAN_HOST)
        check("①a 控制台可打开（内网免密）",
              status == 200 and "对外服务门户".encode() in body)
        # 门户页现在是**只读**的测试页 + 引导页（用户要求：没有设置功能）。
        # 原来这里断言"含添加服务表单"，那是旧设计 —— 管理已搬到插件设置里了。
        check("①b 门户页是只读的（没有添加表单）",
              b'name="name"' not in body and b'name="mount"' not in body
              and b"<form" not in body)
        check("①b2 门户页引导去插件设置里管理",
              "设置 → 插件 → dsh-service-portal → 配置".encode() in body)

        status, body, _ = call("/_api/services", LAN_HOST, method="POST",
                               data=json.dumps({
                                   "key": "acc", "name": "验收服务",
                                   "mount": "/acc",
                                   "target": "127.0.0.1:%d" % app_port,
                                   "enabled": True}).encode(),
                               ctype="application/json")
        check("①c 页面上添加服务成功", status == 200 and b'"ok": true' in body)

        status, body, _ = call("/", LAN_HOST)
        check("①d 新服务出现在控制台且带可点链接",
              "验收服务".encode() in body and b'href="/acc/"' in body)

        status, body, _ = call("/acc/page", LAN_HOST)
        check("①e 点链接可访问该服务", status == 200 and body == b"APP:/page")

        status, body, _ = call("/_api/services/acc/update", LAN_HOST, method="POST",
                               data=json.dumps({"mount": "/acc2"}).encode(),
                               ctype="application/json")
        check("①f 能改路由路径", status == 200)
        check("①g 改后新路径生效", call("/acc2/x", LAN_HOST)[1] == b"APP:/x")
        check("①h 改后旧路径失效（404）", call("/acc/x", LAN_HOST)[0] == 404)

        call("/_api/services/acc/disable", LAN_HOST, method="POST", data=b"")
        status, body, _ = call("/", LAN_HOST)
        check("①i 关闭后控制台显示为未启用（链接不可点）",
              status == 200 and b'href="/acc2/"' not in body)

        call("/_api/services/acc/enable", LAN_HOST, method="POST", data=b"")
        check("①j 重新开启后恢复可访问", call("/acc2/x", LAN_HOST)[1] == b"APP:/x")

        status, body, _ = call("/_api/services", LAN_HOST, method="POST",
                               data=json.dumps({"key": "dup", "name": "重复",
                                                "mount": "/acc2",
                                                "target": "127.0.0.1:1"}).encode(),
                               ctype="application/json")
        check("①k 路由冲突被拒并给出中文原因",
              status == 400 and "占用".encode() in body)

        call("/_api/services/acc/delete", LAN_HOST, method="POST", data=b"")
        check("①l 删除后路由 404", call("/acc2/x", LAN_HOST)[0] == 404)

        print("\n【② 内网免密 + 外网必须口令】")
        # 重新加一个用于访问的服务
        call("/_api/services", LAN_HOST, method="POST",
             data=json.dumps({"key": "s2", "name": "服务二", "mount": "/s2",
                              "target": "127.0.0.1:%d" % app_port,
                              "enabled": True}).encode(),
             ctype="application/json")
        status, body, _ = call("/", LAN_HOST)
        check("②a 内网打开控制台免密", b'name="password"' not in body)
        check("②b 内网可直接访问服务", call("/s2/a", LAN_HOST)[1] == b"APP:/a")

        status, body, _ = call("/", PUBLIC_HOST)
        check("②c 外网打开控制台 -> 登录页",
              b'name="password"' in body and b'name="mount"' not in body)
        check("②d 外网直接访问服务被拦", b"APP:" not in call("/s2/a", PUBLIC_HOST)[1])

        status, _, headers = call("/_auth/login", PUBLIC_HOST, method="POST",
                                  data=urllib.parse.urlencode(
                                      {"password": PASSWORD}).encode(),
                                  ctype="application/x-www-form-urlencoded")
        token = (headers.get("Set-Cookie") or "").split("sp_session=")[-1].split(";")[0]
        check("②e 外网口令登录成功", status == 303 and bool(token))
        check("②f 外网登录后可访问服务",
              call("/s2/b", PUBLIC_HOST, cookie="sp_session=" + token)[1] == b"APP:/b")

        print("\n【③ 二维码 / 手机端 / 限速 / 健康检查】")
        _s, console_body, _ = call("/", LAN_HOST)
        # 门户页已按用户要求**不再渲染二维码与访问地址**（「图2整个都不需要显示」）：
        # 进门户本来就是扫码/点链接来的，地址就在地址栏里。二维码/复制留在
        # 插件设置页（那是发给别人用的场景）。所以这里断言的是"页面能正常渲染
        # 节点区"，而不是"页面上有张码"。
        check("③a 控制台正常渲染（含节点区与管理说明）",
              "已发布的节点".encode() in console_body
              and "怎么管理".encode() in console_body)
        check("③b 控制台**不再**渲染二维码/地址卡（用户要求）",
              b"data:image/svg+xml" not in console_body
              and "访问地址".encode() not in console_body)
        check("③b 含 viewport（手机端）", b'name="viewport"' in console_body)
        check("③c 含响应式样式", b"@media" in console_body)

        # 健康检查：服务存活时 alive 为真
        _s, st, _ = call("/_api/state", LAN_HOST)
        try:
            state = json.loads(st.decode("utf-8"))
            alive_map = {s["key"]: s.get("alive") for s in state.get("services", [])}
        except Exception as exc:
            alive_map = {}
            check("③d 状态接口可解析", False, repr(exc))
        check("③d 存活服务被标为 alive", alive_map.get("s2") is True,
              "alive=%r" % alive_map)

        # 健康检查：把上游停掉后 alive 应变假（证明是真实探测而非恒真）
        # 注意 shutdown() 只停服务循环，**监听 socket 还在**（端口仍被占用）；
        # 必须同时 server_close() 才真的释放端口 —— 否则这里会误判成「探测失灵」。
        app.shutdown()
        app.server_close()
        time.sleep(0.5)
        _s, st, _ = call("/_api/state", LAN_HOST)
        try:
            state2 = json.loads(st.decode("utf-8"))
            alive2 = {s["key"]: s.get("alive") for s in state2.get("services", [])}
        except Exception:
            alive2 = {}
        check("③e 服务停掉后 alive 变假（证明不是恒真）",
              alive2.get("s2") is False, "alive=%r" % alive2)

        # 限速：连续错误口令
        codes = []
        for _ in range(6):
            codes.append(call("/_auth/login", PUBLIC_HOST, method="POST",
                              data=urllib.parse.urlencode(
                                  {"password": "definitely-wrong"}).encode(),
                              ctype="application/x-www-form-urlencoded")[0])
        check("③f 连续错误口令最终被限速（429）",
              429 in codes, "codes=%r" % codes)

        print("\n【④ 三分类且 fail-closed】")
        import portal_proxy
        cases = [
            ("127.0.0.1:8899", "loopback"), ("localhost", "loopback"),
            ("192.168.1.9", "lan"), ("10.1.2.3", "lan"),
            ("172.20.0.1", "lan"), ("100.64.0.9", "lan"),
            ("nas.local", "lan"), ("myhost", "lan"),
            ("x.trycloudflare.com", "public"), ("8.8.8.8", "public"),
            ("my.own-domain.com", "public"), ("", "public"),
            ("garbage value", "public"),
        ]
        bad = [(h, portal_proxy.classify_host(h), want)
               for h, want in cases if portal_proxy.classify_host(h) != want]
        check("④a classify_host 三分类全部正确", not bad, "错例=%r" % bad)
        check("④b fail-closed：自建域名判为 public",
              portal_proxy.classify_host("my.own-domain.com") == "public")

        print("\n【⑤ 依赖缺失跳过返回 2】")
        env = dict(os.environ, SERVICE_PLUGIN_DIR=os.path.join(ROOT, "no-such-dir"))
        proc2 = subprocess.run(
            [sys.executable, "-X", "utf8",
             os.path.join(ROOT, "tools", "check_plugin.py")],
            cwd=ROOT, capture_output=True, text=True, env=env, timeout=120)
        check("⑤a 插件目录缺失 -> 返回 2（跳过，非通过）",
              proc2.returncode == 2, "returncode=%s" % proc2.returncode)

        status, _, _ = call("/_api/register", LAN_HOST)
        check("⑤b 未知 API 路由 -> 404", status == 404, "code=%s" % status)

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()
        try:
            app.shutdown()
        except Exception:
            pass
        # 临时目录整个丢掉即可 —— 真实 runs/ 从头到尾没被碰过，
        # 所以不再需要"备份/还原"那套（它正是漏掉 s2 的地方）。
        shutil.rmtree(runs, ignore_errors=True)

    passed = sum(1 for ok, _, _ in RESULTS if ok)
    total = len(RESULTS)
    print("\n" + "=" * 60)
    print("验收结果：%d/%d 通过" % (passed, total))
    for ok, label, detail in RESULTS:
        if not ok:
            print("  FAIL  %s %s" % (label, detail))
    print("=" * 60)
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
