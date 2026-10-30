# -*- coding: utf-8 -*-
"""服务插件的控制检验入口（给 check_all.py 调用）。

**2026-10-15 迁移**：原在 ld-rl-poker 仓库的 tools/check_poker_viewer_plugin.py。
2026-10-15 后插件本体即仓库根 dsh-service-portal（专用子插件 poker-viewer 已删除，
其功能吸收进根插件成为通用门户能力）。

本脚本只做两件事：
  1. 用 DSH 自带的 node 跑插件的 node:test 套件（宿主端 + 客户端契约）；
  2. 把「插件不存在」当作**跳过（返回 2）**而不是通过 —— 依赖缺失不得静默通过。

为什么把这些断言写进插件目录的 test/：插件是独立包（有自己的 node_modules 与
Cordis 契约），检验必须跑在被检验代码所在的环境里；否则会变成两份实现。
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# 默认指向本仓库根（即 dsh-service-portal 插件本体）；
# 仍允许用环境变量指向外部路径（例如开发中的另一份检出）。
PLUGIN_DIR = os.environ.get(
    "SERVICE_PLUGIN_DIR",
    os.path.join(ROOT))
# DSH 自带的 node（优先），其次 PATH 上的 node。
#
# 这里原来只认 Windows 的 `%LOCALAPPDATA%\Programs\DeepSeek Harness\...\node.exe`：
# 在 macOS/Linux 上 `LOCALAPPDATA` 为空 → 拼出 `Programs/DeepSeek Harness/...`
# 这么个**相对路径**（永远不存在），且 `.exe` 后缀在别的平台也是错的。
# 于是检验脚本在非 Windows 上直接 FileNotFoundError —— 看着像"功能坏了"，
# 其实只是找 node 的方式写死了平台。现在按平台给候选，最后回落 PATH。
DSH_NODE_CANDIDATES = [
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "DeepSeek Harness",
                 "resources", "runtime", "primary-runtime", "dependencies",
                 "node", "bin", "node.exe"),
    # 实测：运行时**不在** app.asar 里（`app.asar/runtime` 不是目录），
    # 它在 `Contents/Resources/runtime`。原先这条写错，于是 macOS 上永远
    # 落到 PATH 的 node —— 而 PATH 的 node 可能读不了 app.asar（asar 是
    # Electron 补丁过的 fs），于是需要宿主的两个套件整个 skip 掉。
    os.path.join("/Applications", "DeepSeek Harness.app", "Contents", "Resources",
                 "runtime", "primary-runtime", "dependencies",
                 "node", "bin", "node"),
    os.path.join(os.path.expanduser("~"), "Library", "Application Support",
                 "DeepSeek Harness", "resources", "runtime", "primary-runtime",
                 "dependencies", "node", "bin", "node"),
]

# manifest / host-contract 两组里有「需要宿主运行时」的项：拿不到宿主时它们
# 明确 skip（并在输出里写明原因），**不假装通过** —— 与其余检验同一条纪律。
SUITES = (
    "test/host.test.mjs",
    "test/client.test.mjs",
    "test/manifest.test.mjs",
    "test/host-contract.test.mjs",
)


# 这两组里有「需要宿主运行时」的断言（版本门禁、槽位目录、core 依赖对账）。
HOST_SUITES = ("test/manifest.test.mjs", "test/host-contract.test.mjs")

# 桌面版把宿主装进 `app.asar`，普通 node 的 fs 读不到这种虚拟路径；
# 必须用宿主自带的 Electron（`ELECTRON_RUN_AS_NODE=1` 时它会退化成 node）。
# 注意：这里的 `os.path.isfile(asar)` 判的是 **app.asar 文件本身**，
# 不能用 `os.path.isdir(app_boot)` —— 在 Python 眼里 asar 是个普通文件，
# 目录判断永远是 False，于是这条分支形同虚设（第一版就这样，两个套件全 skip）。
HOST_APPS = [
    (os.path.join("/Applications", "DeepSeek Harness.app", "Contents", "Resources",
                  "app.asar"),
     os.path.join("/Applications", "DeepSeek Harness.app", "Contents", "MacOS",
                  "DeepSeek Harness")),
]


def find_host_runner(node):
    """找「能读 app.asar 的 node」与它的环境变量。

    @param node 已选定的 node 可执行文件（本函数不使用，保留以便将来扩展）
    @returns (可执行文件路径或 None, 需要注入的环境变量字典)
    """
    for asar, electron in HOST_APPS:
        if os.path.isfile(asar) and os.path.isfile(electron):
            app_boot = os.path.join(asar, "dsh", "node_modules", "@deepseek-ai", "dsh-app-boot")
            return electron, {"ELECTRON_RUN_AS_NODE": "1", "DSH_APP_BOOT": app_boot}
    # 非桌面安装（从源码跑、或 npm 装的 CLI）：普通 node 就够，宿主通过
    # 普通包解析命中；找不到时让套件自己 skip 并说明原因。
    return None, {}


def find_node():
    for path in DSH_NODE_CANDIDATES:
        if path and os.path.isfile(path):
            return path
    found = shutil.which("node")
    return found


def main():
    if not os.path.isdir(PLUGIN_DIR):
        print("跳过：找不到插件目录 %s" % PLUGIN_DIR)
        print("（设置 SERVICE_PLUGIN_DIR 可指向别处；缺失不代表通过）")
        return 2

    index_js = os.path.join(PLUGIN_DIR, "lib", "index.js")
    if not os.path.isfile(index_js):
        print("跳过：插件缺少 lib/index.js（%s）" % PLUGIN_DIR)
        return 2

    node = find_node()
    if not node:
        print("跳过：找不到 node（DSH 运行时与 PATH 都没有）；不代表通过")
        return 2

    missing = [s for s in SUITES if not os.path.isfile(os.path.join(PLUGIN_DIR, s))]
    if missing:
        print("跳过：缺少测试套件 %s" % ", ".join(missing))
        return 2

    print("插件目录：%s" % PLUGIN_DIR)
    print("node    ：%s" % node)
    print("")

    # 需要宿主运行时的套件：普通 node 读不了 `app.asar`（Electron 的 fs 补丁），
    # 所以要用**宿主自带的 Electron 当 node**。拿不到宿主时它们会自己 skip，
    # 这里不替它们兜底 —— 跳过与通过必须可区分。
    host_runner, host_env = find_host_runner(node)

    failed_suites = []
    for suite in SUITES:
        print("=" * 72)
        print("[套件] %s" % suite)
        print("=" * 72)
        argv = [node, "--test", "--test-reporter=spec", suite]
        env = dict(os.environ)
        if suite in HOST_SUITES and host_runner:
            argv = [host_runner, "--test", "--test-reporter=spec", suite]
            env.update(host_env)
            print("宿主运行时：%s" % host_runner)
        result = subprocess.run(
            argv, cwd=PLUGIN_DIR, capture_output=True, text=True,
            env=env,
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
    print("插件检验全部通过（%d 个套件）" % len(SUITES))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())