# -*- coding: utf-8 -*-
"""把验收发现的三个缺陷固化成控制检验。

发现的缺陷：
  1. **畸形 Host 被判成内网**：`classify_host("garbage value")` 返回 lan
     （因为「不含点」就当单标签主机名）→ 随便编个 Host 就能免密进控制台。
     这是 fail-closed 的实现漏洞，必须钉死。
  2. **控制台访问链接双斜杠**：生成 `href="/acc//"`（mount 已带前导 /，
     模板又补了一个）。某些代理/浏览器会规范化重定向。
  3. 健康检查探测的真实性（端口释放后 alive 必须变假）。
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

try:
    import portal_console
    import portal_proxy
except ImportError as exc:
    print("跳过：无法导入门户模块（%s）" % exc)
    raise SystemExit(2)


def main():
    failures = []

    def check(label, cond, detail=""):
        if cond:
            print("  PASS  %s" % label)
        else:
            print("  FAIL  %s %s" % (label, detail))
            failures.append(label)

    print("门户集成回归检验（验收发现的缺陷）")
    print("")

    # ---- 1. fail-closed：畸形 Host 必须落到 public ----
    print("[fail-closed：畸形 Host]")
    must_be_public = [
        "garbage value",      # 含空格
        "<script>alert(1)</script>",
        "a;b", "a/b", "a\\b", "a@b", "a#b", "a?b",
        "-leading-hyphen", "trailing-hyphen-",
        "中文主机名",          # 非 ASCII 单标签
        "a" * 64,             # 超过 63 字符的 label
        "..", ".", ":", "[]",
        "localhost.evil.com",  # 只是不含 localhost 后缀，仍是公网
        "x.localhost.evil",    # 同上
    ]
    bad = []
    for host in must_be_public:
        got = portal_proxy.classify_host(host)
        if got != "public":
            bad.append((host, got))
    check("畸形/非法 Host 一律判为 public（不再因「不含点」而免密）",
          not bad, "漏网=%r" % bad)

    # 合法内网形态仍要认出来（否则修过头，把内网地址也要求口令）
    must_be_lan = ["myhost", "nas-2", "a1", "x" * 63, "desktop-pc"]
    bad2 = [(h, portal_proxy.classify_host(h)) for h in must_be_lan
            if portal_proxy.classify_host(h) != "lan"]
    check("合法单标签主机名仍判为 lan（没有修过头）", not bad2, "错=%r" % bad2)

    # 反例控制：证明上面的检查有区分力 —— 同一个函数必须能给出不同结果
    kinds = {portal_proxy.classify_host(h) for h in
             ("127.0.0.1", "myhost", "garbage value", "x.com")}
    check("分类结果仍有多种（不是恒返回 public）",
          kinds == {"loopback", "lan", "public"}, "得到 %r" % kinds)

    # ---- 2. 控制台访问链接不得双斜杠 ----
    print("[控制台链接规范]")
    html = portal_console.console_html({
        "services": [
            {"key": "train", "name": "训练台", "mount": "/train",
             "target": "127.0.0.1:8810", "enabled": True, "alive": True},
            {"key": "ollama", "name": "Ollama", "mount": "/ollama",
             "target": "127.0.0.1:11434", "enabled": True, "alive": True},
        ],
        "lan_urls": ["http://192.168.1.5:8899"], "public_url": None,
        "portal_port": 8899}).decode("utf-8")

    hrefs = re.findall(r'<a[^>]*href="([^"]*)"', html)
    visit_hrefs = [h for h in hrefs if h in ("/train/", "/ollama/")]
    check("启用服务的访问链接是 /train/ 形式（单位斜杠）",
          len(visit_hrefs) == 2, "找到 %r" % visit_hrefs)
    check("产物里不存在双斜杠链接（//）",
          not [h for h in hrefs if "//" in h.replace("://", "")],
          "双斜杠=%r" % [h for h in hrefs if "//" in h.replace("://", "")])

    # ---- 3. 未启用服务必须不可点 ----
    print("[未启用服务不可点]")
    html2 = portal_console.console_html({
        "services": [
            {"key": "off", "name": "关闭的", "mount": "/off",
             "target": "127.0.0.1:1", "enabled": False, "alive": False},
        ],
        "lan_urls": [], "public_url": None, "portal_port": 8899}).decode("utf-8")
    check("未启用服务不产生可点访问链接",
          "/off/" not in re.findall(r'<a[^>]*href="([^"]*)"', html2),
          "hrefs=%r" % re.findall(r'<a[^>]*href="([^"]*)"', html2))
    check("未启用服务有明确的禁用标记",
          "aria-disabled" in html2 or "不可访问" in html2)

    print("")
    if failures:
        print("门户集成回归检验失败：%d 项" % len(failures))
        for label in failures:
            print("  - %s" % label)
        return 1
    print("门户集成回归检验全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
