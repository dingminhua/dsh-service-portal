# -*- coding: utf-8 -*-
"""外网启动器「域名解析」的控制检验。

拦的是这类 bug（2026-10-15 实测踩到的真 bug，症状极隐蔽）：
  cloudflared 日志是**追加**写入的。旧实现用 ``URL_RE.search(整个日志)``
  取第一条匹配，于是**第二次启动**抓到的是上一次残留的旧域名：

    - 脚本报「隧道已建立」成功；
    - 代理端口确实在监听；
    - 状态接口显示 running=true；
    - 但凭据文件里记的是一个**已经失效的地址**，外网打开是 Cloudflare 530。

  这是本项目最忌讳的「不崩、只给错误答案」——页面看起来一切正常，
  只有真的从外网访问才发现打不开。

控制检验（正着打/反着打必须不同）：
  · 日志里有两个域名时，必须取**最后一个**（本次创建的），不是第一个；
  · ``since`` 偏移生效：只解析本次新增区间；
  · 旧域名仍留在日志里时，结果必须跟着 ``since`` 变（证明不是硬编码）；
  · 异步写入（先无域名、后出现）时必须能等到，不能提前放弃。

本检查只读/写临时目录里的日志，不起隧道、不开公网入口、不碰真实凭据。
"""
import os
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

FAILURES = []
EXECUTED = []


def check(name, ok, detail=""):
    """detail 只在**失败**时打印——通过却显示失败描述会误导读者。"""
    EXECUTED.append(name)
    if ok:
        print("PASS %s" % name)
    else:
        print("FAIL %s%s" % (name, ("  -> " + detail) if detail else ""))
        FAILURES.append(name)


# cloudflared 的真实输出形态（含框线与前后噪声）
BANNER_OLD = """\
2026-10-14T16:45:02Z INF Requesting new quick Tunnel on trycloudflare.com...
2026-10-14T16:45:10Z INF |  Your quick Tunnel has been created! Visit it at  |
2026-10-14T16:45:10Z INF |  https://first-old-domain.trycloudflare.com        |
2026-10-14T16:45:10Z INF |  (it may take some time to be reachable)          |
"""

BANNER_NEW = """\
2026-10-15T01:12:29Z INF Requesting new quick Tunnel on trycloudflare.com...
2026-10-15T01:12:32Z INF |  Your quick Tunnel has been created! Visit it at  |
2026-10-15T01:12:32Z INF |  https://second-new-domain.trycloudflare.com      |
2026-10-15T01:12:32Z INF |  (it may take some time to be reachable)          |
"""


class LogDir(object):
    """把 start_public_gui 的日志目录临时改到别处，避免污染真实 runs/。"""

    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix="public_gui_log_test_")
        import start_public_gui as spg
        self.spg = spg
        self._orig = spg.LOG_DIR
        spg.LOG_DIR = self.tmp

    def path(self, name):
        return os.path.join(self.tmp, name)

    def write(self, name, text, mode="a"):
        with open(self.path(name), mode, encoding="utf-8") as handle:
            handle.write(text)

    def restore(self):
        self.spg.LOG_DIR = self._orig
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)


def main():
    import start_public_gui as spg

    lab = LogDir()
    try:
        LOG = "cloudflared_test.log"

        # --- 1) 旧 bug 的复现：日志里有两个域名，必须取最后一个 ---
        lab.write(LOG, BANNER_OLD, mode="w")
        lab.write(LOG, BANNER_NEW, mode="a")
        url = spg.read_url(LOG, timeout=3, since=0)
        check("整份日志有两个域名时取**最后一个**（本次创建的）",
              url == "https://second-new-domain.trycloudflare.com",
              "得到 %r" % url)
        # 反着打：这必须与第一个不同，否则「取最后一个」是假的
        check("反例：结果不等于第一个（旧）域名",
              url != "https://first-old-domain.trycloudflare.com",
              "得到 %r" % url)

        # --- 2) since 偏移生效：只解析本次新增区间 ---
        first_len = len(BANNER_OLD)
        url_since = spg.read_url(LOG, timeout=3, since=first_len)
        check("since 指向新增区间时同样得到新域名",
              url_since == "https://second-new-domain.trycloudflare.com",
              "得到 %r" % url_since)

        # --- 3) 关键回归：since 停在旧内容中间，绝不能抓出旧域名 ---
        #     模拟「日志已有 5 次启动」+ 本次启动从头读 => 必须仍是最后一个
        lab.write(LOG, BANNER_OLD, mode="w")
        for _ in range(5):
            lab.write(LOG, BANNER_OLD, mode="a")
        lab.write(LOG, BANNER_NEW, mode="a")
        url_many = spg.read_url(LOG, timeout=3, since=0)
        check("日志累积多次启动后仍取最新域名（旧实现会取到最早的）",
              url_many == "https://second-new-domain.trycloudflare.com",
              "得到 %r" % url_many)

        # --- 4) 异步写入：先无域名，稍后出现，必须等到 ---
        lab.write(LOG, "", mode="w")
        def late_writer():
            time.sleep(1.2)
            lab.write(LOG, BANNER_NEW, mode="a")
        thread = threading.Thread(target=late_writer, daemon=True)
        thread.start()
        t0 = time.time()
        url_late = spg.read_url(LOG, timeout=15, since=0)
        waited = time.time() - t0
        check("域名稍后才写入日志时必须等到（不提前放弃）",
              url_late == "https://second-new-domain.trycloudflare.com"
              and waited >= 0.8,
              "等待 %.1fs，得到 %r" % (waited, url_late))

        # --- 5) 真错误必须识别为失败（不能把「失败」说成「有域名」）---
        lab.write(LOG, "ERR failed to request quick Tunnel: dial tcp timeout\n",
                  mode="w")
        url_err = spg.read_url(LOG, timeout=3, since=0)
        check("cloudflared 报错时返回 None（不编造域名）",
              url_err is None, "得到 %r" % url_err)

        # --- 6) 只有旧域名、本次还没写：不能把旧域名当成新的（关键）---
        #     这是修复的核心语义：since 之后没内容就该继续等，而不是回退读旧内容。
        lab.write(LOG, BANNER_OLD, mode="w")
        since_old = len(BANNER_OLD)
        url_none = spg.read_url(LOG, timeout=2, since=since_old)
        check("本次新增区间为空时返回 None（不回退拿旧域名）",
              url_none is None, "得到 %r" % url_none)

        # --- 7) URL 正则不会把非 trycloudflare 域名误当隧道 ---
        lab.write(LOG, "INF https://example.com/not-a-tunnel\n", mode="w")
        check("非 trycloudflare 域名不被误认",
              spg.read_url(LOG, timeout=2, since=0) is None,
              "得到 %r" % spg.read_url(LOG, timeout=2, since=0))
    finally:
        lab.restore()

    # --- 8) 静态契约：调用点必须传 since（防止有人改回去）---
    with open(os.path.join(HERE, "start_public_gui.py"), encoding="utf-8") as fh:
        source = fh.read()
    check("start_tunnel 记录启动前日志长度并传给 read_url",
          "since = os.path.getsize" in source and "read_url(log_name, since=since)" in source,
          "调用点缺少 since 传递")
    check("read_url 使用 findall 取最后一个（而非 search 取第一个）",
          "URL_RE.findall(text)" in source and "found[-1]" in source,
          "read_url 仍是取第一条的旧写法")

    print()
    if FAILURES:
        print("域名解析检查失败 %d 项：%s" % (len(FAILURES), FAILURES))
        return 1
    print("域名解析检查全部通过（%d 项）" % len(EXECUTED))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
