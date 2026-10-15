# -*- coding: utf-8 -*-
"""页面接线检查：本插件的状态条必须真的接到页面上（针对**被服务**的页面）。

拦的 bug：
  1. 页面没接状态条 / 没轮询 /api/host → 用户看不到机器状态（静默缺失）；
  2. 缺值被画成 0 而不是「—」→ 远程误读为空闲；
  3. 为接状态条而改坏页面里被**宿主项目**既有检查依赖的字面量
     （例如 ld-rl-poker 的 check_config_gui.py 断言页面必须含 /api/presets）。

2026-10-15 迁移说明：本文件原在 ld-rl-poker（与被服务的页面同仓）。
搬入本仓库后，页面本身仍由**被服务的宿主项目**提供，因此用
``SERVICE_PAGES_DIR`` 指向它；未提供该目录时**跳过（返回 2）**，
绝不静默通过 —— 页面不在就无从检验接线。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# 被服务的页面所在目录（含 config_page.html / viewer_page.html）。
# 默认沿用迁移前的位置（ld-rl-poker 的 gui/），可用环境变量覆盖。
PAGES_DIR = os.environ.get("SERVICE_PAGES_DIR",
                           r"D:\DshProject\ld-rl-poker\gui")

FAILURES = []


def check(name, ok, detail=""):
    if ok:
        print("PASS %s" % name)
    else:
        print("FAIL %s%s" % (name, ("  -> " + detail) if detail else ""))
        FAILURES.append(name)


def main():
    cfg_path = os.path.join(PAGES_DIR, "config_page.html")
    vw_path = os.path.join(PAGES_DIR, "viewer_page.html")
    missing = [p for p in (cfg_path, vw_path) if not os.path.isfile(p)]
    if missing:
        print("跳过：找不到被服务的页面 %s" % ", ".join(missing))
        print("（设置 SERVICE_PAGES_DIR 可指向别处；缺失不代表通过）")
        return 2
    cfg = open(cfg_path, encoding="utf-8").read()
    vw = open(vw_path, encoding="utf-8").read()

    # 既有断言（check_config_gui.py 第 712-715 行）
    check("config: 含 $('presetList').onchange（既有断言）",
          "$('presetList').onchange" in cfg)
    check("config: 含 /api/presets 字面量（既有断言）",
          "/api/presets" in cfg)
    check("config: 仍不含 tr_hands（既有断言）", "tr_hands" not in cfg)
    check("config: 仍不含 tr_n_envs（既有断言）", "tr_n_envs" not in cfg)

    # 新增能力
    for elem in ("hm-cpu", "hm-mem", "hm-vram", "hm-gpu", "hm-warn"):
        check("config: 状态条含 %s" % elem, elem in cfg)
        check("viewer: 状态条含 %s" % elem, elem in vw)

    # 子路径前缀逻辑必须保留（否则挂 /train/、/viewer/ 时 404）
    check("config: 保留 BASE 前缀推导", "const BASE = (function ()" in cfg)
    check("viewer: 保留 BASE 前缀推导", "const BASE = (function ()" in vw)
    check("config: 状态条自带前缀推导（不依赖后面才定义的 BASE）",
          "HM_BASE" in cfg)
    check("config: 状态条请求走 HM_BASE", "HM_BASE + '/api/host'" in cfg)
    check("viewer: 状态条请求走 BASE", "BASE + '/api/host'" in vw)

    # 缺值显示「—」而不是 0 —— 两个页面都必须有这个分支
    check("config: 缺值显示「—」（pct 函数）", "return '—';" in cfg)
    check("viewer: 缺值显示「—」（pct 函数）", "return '—';" in vw)

    # 两个页面都必须真的去拉 /api/host
    check("config: 轮询 /api/host", "/api/host" in cfg)
    check("viewer: 轮询 /api/host", "/api/host" in vw)

    print()
    if FAILURES:
        print("页面契约检查失败 %d 项：%s" % (len(FAILURES), FAILURES))
        return 1
    print("页面契约检查全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
