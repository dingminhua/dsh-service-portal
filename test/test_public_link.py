# -*- coding: utf-8 -*-
"""真实公网链路验证：隧道地址可达 + 认证边界正确。

用 curl 走（绕过本机 Clash/Mihomo 代理的 .NET 栈差异），
并且用响应**内容**判断，而不是只看状态码 —— 登录页也是 200，
只看状态码会得出「未登录也能访问 API」的错误结论。
"""
import json
import os
import socket
import ssl
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 8899
results = []


def check(label, cond, detail=""):
    results.append(bool(cond))
    print("%s  %s %s" % ("PASS" if cond else "FAIL", label, detail))


def fetch(url, host=None, timeout=25):
    """用 curl 取（显式 --noproxy 绕过本机代理）。返回 (状态码, 正文)。"""
    argv = ["curl.exe", "-s", "--noproxy", "*", "--max-time", str(timeout),
            "-w", "\n__CODE__%{http_code}"]
    if host:
        argv += ["-H", "Host: %s" % host]
    argv.append(url)
    proc = subprocess.run(argv, capture_output=True, timeout=timeout + 10)
    text = proc.stdout.decode("utf-8", "replace")
    code = ""
    if "__CODE__" in text:
        text, _, code = text.rpartition("__CODE__")
    return code.strip(), text


def wait_public_ready(url, attempts=20):
    """等隧道域名在公网 DNS 生效。

    刚建好的 trycloudflare 域名不是立刻可解析 —— 直接断言会拿到 code=000
    （连不上），那是 DNS 传播延迟，不是功能坏了。所以这里重试直到通。
    """
    for i in range(attempts):
        code, _ = fetch(url + "/_auth/health", timeout=15)
        if code == "200":
            return True, i + 1
        time.sleep(3)
    return False, attempts


def public_url():
    req = urllib.request.Request("http://127.0.0.1:%d/_api/state" % PORT,
                                 headers={"Host": "127.0.0.1:%d" % PORT})
    try:
        with urllib.request.build_opener(
                urllib.request.ProxyHandler({})).open(req, timeout=8) as res:
            return json.loads(res.read().decode("utf-8")).get("public_url") or ""
    except Exception as exc:
        print("  读状态失败：%r" % (exc,))
        return ""


def ensure_portal():
    """确保门户在跑（自包含：别的测试可能把它停了，或被 --stop 清过）。"""
    try:
        with urllib.request.build_opener(
                urllib.request.ProxyHandler({})).open(
                "http://127.0.0.1:%d/_auth/health" % PORT, timeout=4) as res:
            if res.status == 200:
                return True
    except Exception:
        pass
    log = open(os.path.join(ROOT, "runs", "public-link-check.log"), "wb")
    subprocess.Popen(
        [sys.executable, "-X", "utf8",
         os.path.join(ROOT, "tools", "portal_run.py"),
         "--port", str(PORT), "--password", "public-link-check-1234",
         "--lan-only"],
        cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    for _ in range(60):
        time.sleep(0.5)
        try:
            with urllib.request.build_opener(
                    urllib.request.ProxyHandler({})).open(
                    "http://127.0.0.1:%d/_auth/health" % PORT, timeout=3) as res:
                if res.status == 200:
                    return True
        except Exception:
            continue
    return False


def ensure_tunnel():
    """确保隧道已建立（没有就拨一次）。"""
    if public_url():
        return True
    req = urllib.request.Request("http://127.0.0.1:%d/_api/tunnel/start" % PORT,
                                 data=b"{}", method="POST",
                                 headers={"Host": "127.0.0.1:%d" % PORT,
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.build_opener(
                urllib.request.ProxyHandler({})).open(req, timeout=140) as res:
            json.loads(res.read().decode("utf-8"))
    except Exception as exc:
        print("  拨隧道失败：%r" % (exc,))
    return bool(public_url())


def main():
    if not ensure_portal():
        check("门户在跑（自包含启动）", False, "起不来，无法继续")
        return 1
    check("门户在跑", True)
    if not ensure_tunnel():
        check("隧道已建立", False, "拨不起来（本机 cloudflared / 网络问题）")
        # 隧道建不起来时后续公网检查无意义，但内网项仍可验证
    url = public_url()
    check("状态里有公网地址", bool(url), url)
    if not url:
        return 1

    ready, tries = wait_public_ready(url)
    check("公网域名在当前网络可解析可访问（DNS 传播完成）", ready,
          "试了 %d 次" % tries)
    if not ready:
        print("  提示：域名建好但本机解析不到 —— 多半是本机代理/VPN（Clash TUN）"
              "掐断了 *.trycloudflare.com 的解析。")
        return 1

    # 1. 从公网访问首页 -> 应给出登录页（不是控制台）
    code, body = fetch(url + "/")
    check("公网首页返回 200", code == "200", "code=%s" % code)
    check("公网首页是登录页（要求口令）",
          'name="password"' in body and 'name="mount"' not in body,
          "含口令输入框=%s，含添加服务表单=%s"
          % ('name="password"' in body, 'name="mount"' in body))
    check("公网登录页不泄漏控制台内容（无服务清单）",
          "服务清单" not in body)

    # 2. 未登录访问 API -> 必须是登录页，**不能**返回 JSON 数据
    code, body = fetch(url + "/_api/services")
    check("未登录访问控制台 API 拿不到数据（返回登录页而非 JSON）",
          '"services"' not in body and 'name="password"' in body,
          "code=%s 片段=%r" % (code, body[:80]))

    # 3. 未登录直接访问已注册服务路径 -> 也应是登录页
    code, body = fetch(url + "/nonexistent-svc/x")
    check("未登录访问服务路径被拦（登录页）",
          'name="password"' in body or "404" in body,
          "code=%s" % code)

    # 4. 本机（loopback）仍然免密可用
    code, body = fetch("http://127.0.0.1:%d/" % PORT)
    check("本机访问免密直接见控制台",
          'name="mount"' in body, "code=%s" % code)

    # 5. 本机内网 IP 免密（同一 WiFi 手机可用）
    code, body = fetch("http://192.168.71.10:%d/" % PORT,
                       host="192.168.71.10:%d" % PORT)
    check("内网 IP 免密直接见控制台（手机可达）",
          'name="mount"' in body, "code=%s" % code)

    # 6. 畸形 Host -> fail-closed（要求口令，不是免密）
    code, body = fetch("http://127.0.0.1:%d/" % PORT, host="garbage value")
    check("畸形 Host 落到 public（要求口令，不是免密）",
          'name="password"' in body, "code=%s" % code)

    # 7. 隧道注册日志（证明确实连上了 Cloudflare 边缘）
    log = os.path.join(ROOT, "runs", "portal_logs", "cloudflared.log")
    registered = False
    if os.path.exists(log):
        registered = "Registered tunnel connection" in open(
            log, encoding="utf-8", errors="replace").read()
    check("cloudflared 已注册到 Cloudflare 边缘（隧道真的通了）", registered)

    passed = sum(1 for ok in results if ok)
    print("\n公网链路验证：%d/%d" % (passed, len(results)))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
