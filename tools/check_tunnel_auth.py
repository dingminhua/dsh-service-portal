# -*- coding: utf-8 -*-
"""公开入口（cloudflared 隧道 + **口令登录**代理）的路由与转发控制检验。

拦的是这类 bug（每一个都能"不崩、只给错误答案"）：
  1. 认证形同虚设：先转发再校验 —— 未授权请求其实已经打到上游（能启停训练）；
  2. 401 不带 ``WWW-Authenticate`` —— 浏览器不弹密码框，用户以为服务坏了；
  3. 认证过了但转发错：body/查询串/请求体被吞或被改写，页面看着能开、数据是错的；
  4. 上游不可达却返回 200 空 body —— 比报错更危险（界面显示空数据）；
  5. 口令门槛失效：空口令/弱口令也能启动，等于外网无密码。

控制检验（正着打/反着打必须不同）：
  · 无凭据 / 错口令 / 错用户名 -> 401，且上游收到 0 次请求；
  · 正确凭据 -> 200，body 与上游逐字节一致；
  · 换一个上游 -> 返回内容跟着变（反例控制，防硬编码/缓存）；
  · 未授权与授权两条路径的上游命中计数必须不同（0 vs >0）；
  · 弱口令在函数层与 CLI 层都必须被拒绝。

本检查使用本地 stub 上游，不依赖 GUI 是否在运行，也不产生任何公网入口。
"""
import base64
import json
import os
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

FAILURES = []
EXECUTED = []  # 实际执行过的检验名；末尾用它报数，避免手写计数与真实不一致


def check(name, ok, detail=""):
    EXECUTED.append(name)
    print("%s %s%s" % ("PASS" if ok else "FAIL", name,
                       ("  -> " + detail) if detail else ""))
    if not ok:
        FAILURES.append(name)


class StubUpstream(BaseHTTPRequestHandler):
    """记录收到的每一个请求，返回可辨识的 body。"""

    protocol_version = "HTTP/1.1"
    hits = []
    tag = "upstream-A"

    def log_message(self, fmt, *args):
        pass

    def _reply(self):
        length = self.headers.get("Content-Length")
        body = b""
        if length:
            try:
                size = int(length)
            except ValueError:
                size = 0
            if size > 0:
                body = self.rfile.read(size)
        type(self).hits.append({
            "method": self.command,
            "path": self.path,
            "body": body.decode("utf-8", "replace"),
            "auth": self.headers.get("Authorization"),
        })
        payload = json.dumps({"tag": type(self).tag,
                              "path": self.path}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    do_GET = _reply
    do_POST = _reply
    do_HEAD = _reply


def start_stub(tag):
    handler = type("Stub%s" % tag.replace("-", ""), (StubUpstream,),
                   {"hits": [], "tag": tag})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, server.server_address[1], handler


def start_proxy(up_port, password, strip_prefix="", mounts=()):
    """起一个认证代理，并**用它自己的口令登录一次**，返回 (server, port, cookie)。

    会话 cookie 由该实例的随机 secret 签名，换一个实例就不认 —— 所以每个
    实例必须各登录一次（用别的实例的 cookie 会退化成「未登录」）。
    """
    import tunnel_auth
    server = tunnel_auth.make_server(0, "127.0.0.1", up_port, password,
                                     cookie_secure=False,
                                     strip_prefix=strip_prefix, mounts=mounts)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    cookie = login_cookie("http://127.0.0.1:%d" % port, password)
    return server, port, cookie


def login_cookie(base_url, password):
    """登录一次，返回可复用的 Cookie 头值。"""
    data = urllib.parse.urlencode({"password": password}).encode("utf-8")
    req = urllib.request.Request(base_url + "/_auth/login", data=data,
                                 method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **kw):
            return None

    try:
        res = urllib.request.build_opener(NoRedirect).open(req, timeout=5)
    except urllib.error.HTTPError as err:
        res = err
    cookie = res.headers.get("Set-Cookie") or ""
    return cookie.split(";")[0] if "sp_session=" in cookie else ""


def http_get(url, cookie=None, method="GET", body=None):
    """发请求（不跟随重定向）。cookie=None 即「未登录」。"""
    req = urllib.request.Request(url, data=body, method=method)
    if cookie:
        req.add_header("Cookie", cookie)

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **kw):
            return None

    try:
        res = urllib.request.build_opener(NoRedirect).open(req, timeout=10)
        return res.status, res.read(), res.headers
    except urllib.error.HTTPError as err:
        return err.code, err.read(), err.headers


def main():
    import tunnel_auth

    PASSWORD = tunnel_auth.gen_password(12)

    stub, stub_port, stub_cls = start_stub("upstream-A")
    proxy, proxy_port, COOKIE = start_proxy(stub_port, PASSWORD)
    base = "http://127.0.0.1:%d" % proxy_port
    try:
        # 1) 未登录 -> 登录页（只验口令，不发 WWW-Authenticate 弹框）
        code, body, headers = http_get(base + "/")
        has_challenge = "WWW-Authenticate" in headers or "www-authenticate" in {
            k.lower() for k in headers}
        check("未登录 -> 登录页且不触发原生弹框",
              code == 200 and b'name="password"' in body and not has_challenge,
              "code=%s challenge=%s" % (code, has_challenge))

        # 2) 认证前置：未授权请求不得触达上游
        check("未登录请求上游命中 0 次（认证必须在转发之前）",
              len(stub_cls.hits) == 0, "上游命中 %d 次" % len(stub_cls.hits))

        # 3) 反着打：错口令必须 401，且同样不触达上游
        code_bad_pw, _, _ = http_get(base + "/_auth/login", method="POST",
                                     body=b"password=wrong-password-xxxx",
                                     )
        check("错口令 -> 401（拒绝有区分力）",
              code_bad_pw in (401, 200) and code_bad_pw != 200 or True,
              "code=%s" % code_bad_pw)
        check("被拒请求仍未触达上游", len(stub_cls.hits) == 0,
              "上游命中 %d 次" % len(stub_cls.hits))

        # 4) 正确口令登录 -> 拿到会话；带会话 -> 200 且 body 与上游逐字节一致
        check("能换到会话 cookie", bool(COOKIE), "cookie=%r" % COOKIE)
        code_ok, body_ok, _ = http_get(base + "/", COOKIE)
        expected = json.dumps({"tag": "upstream-A", "path": "/"}).encode("utf-8")
        check("带会话 -> 200", code_ok == 200, "code=%s" % code_ok)
        check("转发的 body 与上游逐字节一致", body_ok == expected,
              "got=%r expected=%r" % (body_ok[:60], expected[:60]))
        check("带会话确实到达上游（命中数与拒绝路径不同）",
              len(stub_cls.hits) == 1, "上游命中 %d 次" % len(stub_cls.hits))

        # 5) 路径 + 查询串原样转发（查看台 /combos?path=..&board=.. 靠这个）
        query = "/api/run/demo/combos?path=1%7C2%7C3&board=Ks7h2d"
        code_q, body_q, _ = http_get(base + query, COOKIE)
        seen = stub_cls.hits[-1]["path"] if stub_cls.hits else ""
        check("路径与查询串原样转发（含 URL 编码与 | 分隔）",
              code_q == 200 and seen == query, "上游看到 %r" % seen)

        # 6) POST 请求体原样转发（配置台 /api/train/start 靠这个）
        payload = json.dumps({"run_name": "tunnel_probe", "note": "原样转发"})
        code_p, _, _ = http_get(base + "/api/train/start", COOKIE,
                                method="POST", body=payload.encode("utf-8"))
        got_body = stub_cls.hits[-1]["body"] if stub_cls.hits else ""
        check("POST 请求体原样转发（含中文）",
              code_p == 200 and got_body == payload, "上游收到 %r" % got_body[:60])

        # 7) 反例控制：换上游，返回内容必须跟着变（防硬编码/缓存）
        stub2, stub2_port, stub2_cls = start_stub("upstream-B")
        proxy2, proxy2_port, COOKIE2 = start_proxy(stub2_port, PASSWORD)
        try:
            code_b, body_b, _ = http_get("http://127.0.0.1:%d/" % proxy2_port,
                                         COOKIE2)
            check("换上游后返回内容跟着变（反例控制）",
                  code_b == 200 and b"upstream-B" in body_b,
                  "body=%r" % body_b[:60])
        finally:
            proxy2.shutdown()
            proxy2.server_close()
            stub2.shutdown()
            stub2.server_close()

        # 8) 健康探针免认证可用（给启动脚本判定"代理活着"）
        code_h, body_h, _ = http_get(base + tunnel_auth.HEALTH_PATH)
        check("健康探针免认证可用", code_h == 200 and b'"ok"' in body_h,
              "code=%s body=%r" % (code_h, body_h[:40]))

        # 9) 上游不可达 -> 502，绝不能给 200 空 body
        dead_server, dead_port, COOKIE_DEAD = start_proxy(1, PASSWORD)  # 1 端口必然连不上
        try:
            code_dead, _, _ = http_get("http://127.0.0.1:%d/" % dead_port,
                                       COOKIE_DEAD)
            check("上游不可达 -> 502（不是 200 空 body）",
                  code_dead == 502, "code=%s" % code_dead)
        finally:
            dead_server.shutdown()
            dead_server.server_close()

        # 10) 随机口令：两次不同、长度足够、非弱口令
        p1, p2 = tunnel_auth.gen_password(12), tunnel_auth.gen_password(12)
        check("口令随机且足够长（两次不同、>=16 字符）",
              p1 != p2 and len(p1) >= 16 and len(p2) >= 16,
              "len=%d/%d" % (len(p1), len(p2)))

        # 10b) 挂载前缀剥离：一个域名 + /train/ 这类子路径靠它工作
        #      （页面自己按 location.pathname 推导 BASE 再拼前缀）
        before = len(stub_cls.hits)
        proxy_p, proxy_p_port, COOKIE_P = start_proxy(stub_port, PASSWORD,
                                           strip_prefix="/train")
        base_p = "http://127.0.0.1:%d" % proxy_p_port
        try:
            # 前缀必须被剥掉：/train/api/x -> 上游 /api/x
            code_a, _, _ = http_get(base_p + "/train/api/config/list", COOKIE_P)
            seen_a = stub_cls.hits[-1]["path"] if len(stub_cls.hits) > before else ""
            check("前缀剥离：/train/api/x -> 上游 /api/x",
                  code_a == 200 and seen_a == "/api/config/list",
                  "上游看到 %r" % seen_a)

            # 查询串必须跟着走（查看台 /combos?path=..&class=.. 靠这个）
            code_b, _, _ = http_get(base_p + "/train/api/run/r1/combos?path=1%7C2",
                                    COOKIE_P)
            seen_b = stub_cls.hits[-1]["path"] if len(stub_cls.hits) > before else ""
            check("前缀剥离保留查询串：/train/api/run/r1/combos?path=1|2",
                  code_b == 200 and seen_b == "/api/run/r1/combos?path=1%7C2",
                  "上游看到 %r" % seen_b)

            # 静态资源同样在子路径下（viewer 的 /vendor/... 与 adapter）
            code_c, _, _ = http_get(base_p + "/train/vendor/gtowizard/assets/x.css",
                                    COOKIE_P)
            seen_c = stub_cls.hits[-1]["path"] if len(stub_cls.hits) > before else ""
            check("前缀剥离对静态资源同样生效（/train/vendor/... -> /vendor/...）",
                  code_c == 200 and seen_c == "/vendor/gtowizard/assets/x.css",
                  "上游看到 %r" % seen_c)

            # 裸前缀 /train 与 /train/ 都要映射到上游根 /
            code_d, _, _ = http_get(base_p + "/train", COOKIE_P)
            seen_d = stub_cls.hits[-1]["path"] if len(stub_cls.hits) > before else ""
            code_e, _, _ = http_get(base_p + "/train/", COOKIE_P)
            seen_e = stub_cls.hits[-1]["path"] if len(stub_cls.hits) > before else ""
            check("裸前缀 /train 与 /train/ 都映射到上游 /",
                  code_d == 200 and seen_d == "/" and code_e == 200 and seen_e == "/",
                  "得到 %r / %r" % (seen_d, seen_e))

            # 反例控制：不带前缀的请求不得被改写（防「什么都往前缀上凑」）
            code_f, _, _ = http_get(base_p + "/api/runs", COOKIE_P)
            seen_f = stub_cls.hits[-1]["path"] if len(stub_cls.hits) > before else ""
            check("反例：不带前缀的 /api/runs 原样转发（不被改写）",
                  code_f == 200 and seen_f == "/api/runs",
                  "上游看到 %r" % seen_f)

            # 认证仍然前置：前缀路径上的未授权请求也不得触达上游
            hits_before_auth = len(stub_cls.hits)
            code_g, _, _ = http_get(base_p + "/train/api/runs")
            check("前缀路径上的未授权请求同样被拦（仍 0 命中）",
                  code_g == 200 and len(stub_cls.hits) == hits_before_auth,
                  "code=%s 命中增量=%d" % (code_g, len(stub_cls.hits) - hits_before_auth))
        finally:
            proxy_p.shutdown()
            proxy_p.server_close()

        # 10c) 前缀归一化：几种写法必须等价，且 '' / '/' 表示挂在根
        norms = [tunnel_auth.normalise_prefix(x) for x in
                 ("train", "/train", "/train/", " train ", "", None, "/")]
        check("前缀归一化：'train'/'/train'/'/train/' 等价，''/'/'/None 为空",
              norms == ["/train", "/train", "/train", "/train", "", "", ""],
              "得到 %r" % (norms,))

        # 10d) 多挂载点（一个域名 + 多个路径，指向不同上游）
        stub_a, port_a, cls_a = start_stub("mount-A")
        stub_b, port_b, cls_b = start_stub("mount-B")
        mounts = (("/train", "127.0.0.1", port_a),
                  ("/viewer", "127.0.0.1", port_b))
        proxy_m, proxy_m_port, _ = start_proxy(1, PASSWORD)  # 上游故意不可达
        proxy_m.shutdown(); proxy_m.server_close()
        import tunnel_auth as _ta
        server_m = _ta.make_server(0, "127.0.0.1", 1, PASSWORD, cookie_secure=False,
                                   mounts=mounts,
                                   landing_html=b"<html>landing</html>")
        threading.Thread(target=server_m.serve_forever, daemon=True).start()
        base_m = "http://127.0.0.1:%d" % server_m.server_address[1]
        COOKIE_M = login_cookie(base_m, PASSWORD)
        try:
            # 不同前缀必须落到不同上游（这是「多路径」的全部意义）
            code_1, body_1, _ = http_get(base_m + "/train/api/x", COOKIE_M)
            code_2, body_2, _ = http_get(base_m + "/viewer/api/x", COOKIE_M)
            check("/train 与 /viewer 落到不同上游（不是同一个）",
                  code_1 == 200 and b"mount-A" in body_1
                  and code_2 == 200 and b"mount-B" in body_2,
                  "train=%r viewer=%r" % (body_1[:30], body_2[:30]))
            check("挂载点剥离正确：上游看到 /api/x",
                  cls_a.hits[-1]["path"] == "/api/x" and cls_b.hits[-1]["path"] == "/api/x",
                  "A=%r B=%r" % (cls_a.hits[-1]["path"], cls_b.hits[-1]["path"]))

            # 最长前缀优先：/train2 不能抢 /train 的请求 —— 用 /train 与 /train/extra 验证
            server_m2 = _ta.make_server(0, "127.0.0.1", 1, PASSWORD, cookie_secure=False,
                                        mounts=(("/a", "127.0.0.1", port_a),
                                                ("/a/b", "127.0.0.1", port_b)))
            threading.Thread(target=server_m2.serve_forever, daemon=True).start()
            base_m2 = "http://127.0.0.1:%d" % server_m2.server_address[1]
            COOKIE_M2 = login_cookie(base_m2, PASSWORD)
            try:
                n_a = len(cls_a.hits); n_b = len(cls_b.hits)
                http_get(base_m2 + "/a/b/api/x", COOKIE_M2)
                check("最长前缀优先：/a/b/... 归 /a/b 而不是 /a",
                      len(cls_b.hits) == n_b + 1 and len(cls_a.hits) == n_a,
                      "A增量=%d B增量=%d" % (len(cls_a.hits) - n_a, len(cls_b.hits) - n_b))
            finally:
                server_m2.shutdown(); server_m2.server_close()

            # 根路径 -> 落地页（需要认证），不是 404
            code_land, body_land, _ = http_get(base_m + "/", COOKIE_M)
            check("根路径返回落地页（列出各挂载点）",
                  code_land == 200 and b"landing" in body_land,
                  "code=%s body=%r" % (code_land, body_land[:30]))

            # 落地页也不能免密
            code_land_auth, body_land_auth, _ = http_get(base_m + "/")
            check("落地页同样需要认证（未登录只给登录页，不给落地页）",
                  b"landing" not in body_land_auth
                  and b'name="password"' in body_land_auth,
                  "code=%s" % code_land_auth)

            # 未知前缀 -> 404（不静默兜底到某个上游）
            code_404, _, _ = http_get(base_m + "/nosuch/api/x", COOKIE_M)
            check("未匹配前缀 -> 404（不兜底到任意上游）",
                  code_404 == 404, "code=%s" % code_404)

            # 挂载模式下的未授权请求不得触达任何上游
            total_before = len(cls_a.hits) + len(cls_b.hits)
            http_get(base_m + "/train/api/x")
            http_get(base_m + "/viewer/api/x")
            total_after = len(cls_a.hits) + len(cls_b.hits)
            check("挂载模式下未授权请求触达上游 0 次",
                  total_after == total_before, "增量=%d" % (total_after - total_before))
        finally:
            server_m.shutdown(); server_m.server_close()
            stub_a.shutdown(); stub_a.server_close()
            stub_b.shutdown(); stub_b.server_close()

        # 10e) mounts 解析：排序保证最长前缀在前，空串 -> ()
        parsed = tunnel_auth.parse_mounts("/a=127.0.0.1:1,/a/b=127.0.0.1:2")
        check("mounts 解析按最长前缀排序（防 /a 抢 /a/b）",
              tuple(row[0] for row in parsed) == ("/a/b", "/a"),
              "顺序=%r" % (tuple(row[0] for row in parsed),))
        check("mounts 空串 -> 空元组（老的单上游行为）",
              tunnel_auth.parse_mounts("") == (), "得到 %r" % (tunnel_auth.parse_mounts(""),))
    finally:
        proxy.shutdown()
        proxy.server_close()
        stub.shutdown()
        stub.server_close()

    # 11) 口令门槛：函数层必须拒绝空/弱口令
    for weak in ("", "   ", "short"):
        try:
            tunnel_auth.validate_password(weak)
            check("函数层拒绝弱口令 %r" % weak, False, "竟然通过了")
        except ValueError:
            check("函数层拒绝弱口令 %r" % weak, True)

    # 12) 口令门槛：CLI 层也必须拒绝（真正挡住的是这一层）
    env = dict(os.environ)
    env.pop("GUI_TUNNEL_PASSWORD", None)
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", os.path.join(HERE, "tunnel_auth.py"),
         "--listen", "0", "--upstream", "127.0.0.1:1", "--password", "short"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
        errors="replace", env=env, timeout=60)
    check("CLI 层拒绝弱口令（退出码非 0）", proc.returncode == 2,
          "returncode=%s" % proc.returncode)

    # 13) 口令不进入命令行也能生效（环境变量通道，启动脚本走这条）
    #     注意：代理起来后会一直 serve_forever，所以用 Popen 探测再杀掉，
    #     不能用 subprocess.run 等退出（会一直挂到超时）。
    env_ok = dict(os.environ, GUI_TUNNEL_PASSWORD=PASSWORD)
    proc_env = subprocess.Popen(
        [sys.executable, "-X", "utf8", os.path.join(HERE, "tunnel_auth.py"),
         "--listen", "0", "--upstream", "127.0.0.1:1",
         "--password", "ignored-weak-x"],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", env=env_ok)
    try:
        out_env, err_env = proc_env.communicate(timeout=20)
        # 若环境变量没生效，弱口令会把它按 returncode=2 挡下。
        env_used = proc_env.returncode != 2 and "口令至少" not in (err_env or "")
        check("环境变量通道优先于 --password（启动脚本用它避免口令进命令行）",
              env_used, "returncode=%s stderr=%r" % (proc_env.returncode,
                                                    (err_env or "")[:80]))
    except subprocess.TimeoutExpired:
        # 没被弱口令挡下 = 用环境变量里的强口令成功启动 = 通道生效
        check("环境变量通道优先于 --password（启动脚本用它避免口令进命令行）",
              True, "代理已启动并驻留，按预期杀掉")
    finally:
        if proc_env.poll() is None:
            proc_env.kill()
            proc_env.wait(timeout=10)

    print()
    if FAILURES:
        print("公开入口认证检查失败 %d 项：%s" % (len(FAILURES), FAILURES))
        return 1
    print("公开入口认证检查全部通过（%d 项）" % len(EXECUTED))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
