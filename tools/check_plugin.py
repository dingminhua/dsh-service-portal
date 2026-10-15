# -*- coding: utf-8 -*-
"""服务插件的控制检验入口（给 check_all.py 调用）。

**2026-10-15 迁移**：原在 ld-rl-poker 仓库的 tools/check_poker_viewer_plugin.py。
插件本体已随功能一起迁入本仓库 services/poker-viewer（DSH 的 link 插件）；
门户根插件 dsh-service-portal 也随仓库一起受检。

本脚本只做两件事：
  1. 用 DSH 自带的 node 跑各插件的 node:test 套件（宿主端 + 客户端契约）；
  2. 把「插件不存在」当作**跳过（返回 2）**而不是通过 —— 依赖缺失不得静默通过。

默认检验两个插件：
  · 根插件 dsh-service-portal（lib/index.js + test/，18+14 项）
  · 子插件 services/poker-viewer（lib/index.js + test/，16+10 项）

为什么把这些断言写进各自插件目录的 test/：插件是独立包（有自己的 node_modules 与
Cordis 契约），检验必须跑在被检验代码所在的环境里；否则会变成两份实现。
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# 默认检验两个插件：根门户 + 子插件 poker-viewer。
# 仍允许用环境变量覆盖（SERVICE_PLUGIN_DIR=单插件 / SERVICE_PLUGIN_DIRS=多插件，
# 后者用 os.pathsep 分隔）。
DEFAULT_PLUGIN_DIRS = (
    os.path.join(ROOT),
    os.path.join(ROOT, "services", "poker-viewer"),
)
# DSH 自带的 node（优先），其次 PATH 上的 node
DSH_NODE_CANDIDATES = [
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "DeepSeek Harness",
                 "resources", "runtime", "primary-runtime", "dependencies",
                 "node", "bin", "node.exe"),
]

SUITES = ("test/host.test.mjs", "test/client.test.mjs")


def find_node():
    for path in DSH_NODE_CANDIDATES:
        if path and os.path.isfile(path):
            return path
    found = shutil.which("node")
    return found


def main():
    env_single = os.environ.get("SERVICE_PLUGIN_DIR")
    env_multi = os.environ.get("SERVICE_PLUGIN_DIRS")
    if env_single:
        plugin_dirs = [env_single]
    elif env_multi:
        plugin_dirs = [p for p in env_multi.split(os.pathsep) if p]
    else:
        plugin_dirs = list(DEFAULT_PLUGIN_DIRS)

    if not plugin_dirs:
        print("跳过：没有指定插件目录（SERVICE_PLUGIN_DIR / SERVICE_PLUGIN_DIRS 均为空）")
        return 2

    found_any = False
    overall = 0
    for plugin_dir in plugin_dirs:
        print("=" * 72)
        print("[插件] %s" % plugin_dir)
        print("=" * 72)
        result = check_one(plugin_dir)
        if result == 0:
            found_any = True
        elif result == 1:
            overall = 1
        # result == 2（跳过）不置 found_any，也不置失败

    print("=" * 72)
    if overall != 0:
        print("插件检验失败")
        return 1
    if not found_any:
        print("跳过：所有插件目录均缺失；缺失不代表通过")
        return 2
    print("插件检验全部通过（%d 个插件）" % len(plugin_dirs))
    return 0


def check_one(plugin_dir):
    if not os.path.isdir(plugin_dir):
        print("跳过：找不到插件目录 %s" % plugin_dir)
        print("（设置 SERVICE_PLUGIN_DIR(S) 可指向别处；缺失不代表通过）")
        return 2

    index_js = os.path.join(plugin_dir, "lib", "index.js")
    if not os.path.isfile(index_js):
        print("跳过：插件缺少 lib/index.js（%s）" % plugin_dir)
        return 2

    node = find_node()
    if not node:
        print("跳过：找不到 node（DSH 运行时与 PATH 都没有）；不代表通过")
        return 2

    missing = [s for s in SUITES if not os.path.isfile(os.path.join(plugin_dir, s))]
    if missing:
        print("跳过：缺少测试套件 %s" % ", ".join(missing))
        return 2

    print("node    ：%s" % node)
    print("")

    failed_suites = []
    for suite in SUITES:
        print("=" * 72)
        print("[套件] %s" % suite)
        print("=" * 72)
        result = subprocess.run(
            [node, "--test", "--test-reporter=spec", suite],
            cwd=plugin_dir, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=600)
        out = ((result.stdout or "") + (result.stderr or "")).rstrip()
        if out:
            print(out)
        if result.returncode != 0:
            failed_suites.append(suite)
        print("")

    print("=" * 72)
    if failed_suites:
        print("插件检验失败：%s" % ", ".join(failed_suites))
        return 1
    print("插件检验通过（%d 个套件）" % len(SUITES))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())