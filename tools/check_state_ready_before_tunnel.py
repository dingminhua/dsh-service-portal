# -*- coding: utf-8 -*-
"""门户状态文件必须在**建隧道之前**就可读。

为什么单独一条：CI 在 Windows 上红了，报的是
`Cannot read properties of null (reading 'running')` —— 来自
`test/host.test.mjs` 的「退出收尾：pid 匹配且端口在听」。本地 macOS
跑 20 次都不红，很容易被当成"CI 抖动"。它不是：

    端口在 make_portal_server() 构造时就已绑定并开始监听，
    而 runs/portal_state.json 原来只在**隧道建完之后**才写一次。
    于是「端口在听」与「状态文件可读」之间有一整段窗口。宿主
    （lib/index.js readPortalStatus）判「运行中」看的是端口，判 pid/口令
    看的是状态文件 —— 撞进窗口里就拿到 null。

`--lan-only` 不建隧道，窗口只有 5–17ms，本机测不出来；**建隧道**那条路
（真机最常见）窗口等于隧道建立的耗时，可以到好几秒。

这条检验的做法：让隧道阶段**稳定地**拖到一分钟以上（把 --cloudflared 指向
Python 解释器自己：它必然启动失败，日志里没有域名，read_url 就一路轮询到
75 秒超时），然后量「端口可连」与「状态文件出现」的先后。
修复前后者是 None（6 秒内都没出现），修复后两者相差几十毫秒。

运行：python -X utf8 tools/check_state_ready_before_tunnel.py
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
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


def listening(port):
    """端口能不能连上 —— 不看 HTTP，只看 TCP（状态文件写不写与这一层无关）。"""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.3):
            return True
    except Exception:
        return False


def main():
    tmp = tempfile.mkdtemp(prefix="state-ready-")
    runs = os.path.join(tmp, "runs")
    infra = os.path.join(tmp, "infra")
    os.makedirs(runs, exist_ok=True)
    os.makedirs(infra, exist_ok=True)
    shutil.copytree(HERE, os.path.join(infra, "tools"))

    # 怎么把「隧道阶段」拖长：把 --cloudflared 指向 **Python 解释器自己**。
    #
    # 为什么不用假的可执行文件（第一版就是那么写的，Windows 上不成立）：
    #   · `chmod +x` 在 Windows 上是空操作，`#!/bin/sh` 也不存在；
    #   · 更根本的是 portal_run.py 用 `subprocess.Popen([cloudflared, ...])`
    #     **不经过 shell** 调用，而 CreateProcess 无法直接执行 `.bat`
    #     （WinError 193 %1 不是有效的 Win32 程序）。
    #     于是假脚本在 CI 的那个平台上根本跑不起来 —— 隧道阶段瞬间结束，
    #     窗口被压回 0 秒，这条检验就在它最该保护的那个平台上**永远绿**。
    #     那比红更糟：它看起来在守，其实什么都没验到。
    #
    # 用解释器自己就没有可执行性差异：Popen 一定成功，process 立刻因
    # "--no-autoupdate 不是合法选项" 退出，日志里也就没有 trycloudflare 域名，
    # 于是 read_url 会一路轮询到 75 秒超时 —— 隧道阶段因此**稳定地**长达
    # 一分钟以上，任何平台上都能把下面那个窗口放大到必然可观测。
    # 检验只观察前几秒就要的数据，随后立刻 kill 掉，不会真的等满 75 秒。
    fake_cloudflared = PY

    state_path = os.path.join(runs, "portal_state.json")
    port = free_port()
    log = open(os.path.join(tmp, "portal.log"), "wb")
    proc = subprocess.Popen(
        [PY, "-X", "utf8", os.path.join(infra, "tools", "portal_run.py"),
         "--port", str(port), "--password", "state-ready-pw-1",
         "--cloudflared", fake_cloudflared],
        cwd=infra, stdout=log, stderr=subprocess.STDOUT,
        env=dict(os.environ, PORTAL_RUNS_DIR=runs))
    try:
        started = time.time()
        port_at = None
        state_at = None
        for _ in range(600):                       # 最多 6 秒（远小于 75 秒的隧道等待）
            if port_at is None and listening(port):
                port_at = time.time() - started
            if state_at is None and os.path.exists(state_path):
                state_at = time.time() - started
            if port_at is not None and state_at is not None:
                break
            time.sleep(0.01)

        check("门户端口确实起来了（前提，否则下面两条是空转）",
              port_at is not None, "port_at=%r" % (port_at,))
        if port_at is None:
            return 1

        # 核心断言：状态文件必须在端口开始监听后的很短时间里就可读，
        # 而不是等到隧道建完（那要 3 秒以上）。
        check("端口在听时状态文件已经可读（不等隧道）",
              state_at is not None,
              "state_at=%r（None = 6 秒内都没出现，正是 CI 红的那种形状）"
              % (state_at,))
        if state_at is not None:
            gap = (state_at - port_at) * 1000
            check("两者相差 < 1500ms（远小于隧道阶段的一分钟量级）",
                  gap < 1500, "gap=%.0fms" % gap)

        # 反例控制：状态文件里必须真的是"这一个进程"，否则"可读"没有意义
        if state_at is not None:
            try:
                with open(state_path, "r", encoding="utf-8") as handle:
                    state = json.load(handle)
            except Exception as exc:            # noqa: BLE001
                state = None
                check("状态文件可解析", False, repr(exc))
            if state is not None:
                check("状态文件里已有 portal_pid（收尾判归属靠它）",
                      bool(state.get("portal_pid")),
                      "portal_pid=%r" % (state.get("portal_pid"),))
                check("状态文件里已有 portal_port（宿主据此选端口）",
                      state.get("portal_port") == port,
                      "记的是 %r，实际端口 %d"
                      % (state.get("portal_port"), port))
                check("状态文件里已有 password（设置页要显示口令）",
                      bool(state.get("password")), "")

        passed = sum(1 for ok, _, _ in results if ok)
        print("\n状态文件就绪时序检验：%d/%d" % (passed, len(results)))
        return 0 if passed == len(results) else 1
    finally:
        if proc.poll() is None:
            proc.kill()
            try:
                proc.wait(timeout=10)
            except Exception:                   # noqa: BLE001
                pass
        try:
            log.close()
        except Exception:                       # noqa: BLE001
            pass
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
