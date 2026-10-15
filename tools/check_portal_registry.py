# -*- coding: utf-8 -*-
"""服务注册表控制检验：增删改查、校验规则、持久化、损坏容错、副本隔离。

拦的是这类 bug（每条都对应一个真实会发生的失败）：
  1. key 重名被接受 / key 含 `.`、空格、中文、超长 —— URL 与 API 直接踩雷；
  2. mount 没规范化/不以 / 开头/是根路径/含 `..`/`%`/`//` —— 代理查表对不上或路径穿越；
  3. mount 与保留路径撞车 —— 把控制台/_auth 抢了，认证形同虚设；
  4. mount 与另一**启用**条目重复 —— 代理查表歧义，转发到错的服务；
     （且重复检查必须只针对启用项：把前者禁用后应能再加同名 mount）
  5. target 端口 0/99999/无端口/空 —— 直接转发到一个必然连不上的上游；
  6. name 空/全空白/超长 —— 控制台列表渲染出奇怪的空行；
  7. save 不是原子写 —— 崩溃会留下半截 JSON 或临时文件；
  8. 损坏文件 load() 崩溃 —— 门户一启动就死；
  9. list()/mount_map() 返回内部状态引用 —— 调用方改返回值污染了注册表。

依赖：只用标准库（本仓库硬纪律：依赖缺失要跳过并返回 2）。

运行：python -X utf8 tools/check_portal_registry.py
退出码：0 = 全通过；1 = 有失败；2 = 跳过（依赖缺失）
"""
import json
import os
import sys
import shutil
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

try:
    from portal_registry import (
        Registry,
        RegistryError,
        normalise_mount,
        parse_target,
        RESERVED_KEYS,
    )
except ImportError as exc:
    print("跳过：无法导入 portal_registry（%s）；依赖缺失不代表通过" % exc)
    raise SystemExit(2)


def main():
    failures = []

    def check(label, condition, detail=""):
        if condition:
            print("  PASS  %s" % label)
        else:
            print("  FAIL  %s %s" % (label, detail))
            failures.append(label)

    def expect_err(fn, label):
        """期望 fn 抛 RegistryError；抛了算 PASS，没抛算 FAIL。"""
        try:
            fn()
        except RegistryError:
            check(label, True)
            return True
        except Exception as exc:  # noqa: BLE001
            check(label, False, "抛了非 RegistryError：%r" % exc)
            return False
        check(label, False, "竟然没有报错")
        return False

    tmpdir = tempfile.mkdtemp(prefix="portal_registry_check_")
    path = os.path.join(tmpdir, "registry.json")

    print("服务注册表控制检验")
    print("")

    # ---- add 全流程 ----
    print("[增删改查]")
    reg = Registry(path)
    reg.add({"key": "train", "name": "训练配置台", "mount": "train",
             "target": "127.0.0.1:8810", "enabled": True, "autoStart": False})
    reg.add({"key": "web", "name": "Web 台", "mount": "/web/",
             "target": "localhost:9000", "enabled": True})
    check("add 返回完整条目", isinstance(reg.get("train"), dict)
          and reg.get("train")["key"] == "train")
    check("mount 规范化 train->/train", reg.get("train")["mount"] == "/train")
    check("mount 规范化 /web/->/web", reg.get("web")["mount"] == "/web")
    check("get 命中", reg.get("train")["name"] == "训练配置台")
    check("get 未命中返回 None", reg.get("nosuch") is None)

    updated = reg.update("train", {"name": "训练配置台 v2"})
    check("update 改 name", updated["name"] == "训练配置台 v2")
    check("update 保留 key", updated["key"] == "train")

    before = reg.list()
    check("list 全流程数量", len(before) == 2)
    removed = reg.remove("train")
    check("remove 返回 True", removed is True)
    check("remove 后消失", reg.get("train") is None)
    check("remove 不存在返回 False", reg.remove("nosuch") is False)

    # ---- key 校验 ----
    print("[key 校验]")
    def dup():
        return reg.add({"key": "web", "name": "重复", "mount": "/dup",
                        "target": "h:1"})
    expect_err(dup, "重复 key 被拒")
    for bad, why in (("", "空 key"), ("a" * 33, "超长 key"),
                     ("带.点", "含 ."), ("has space", "含空格"),
                     ("中文key", "中文"), ("a/b", "含斜杠")):
        expect_err((lambda b=bad: reg.add({"key": b, "name": "x", "mount": "/m",
                                           "target": "h:1"})), "非法 key 被拒：%s" % why)
    for rkey in RESERVED_KEYS:
        expect_err((lambda rk=rkey: reg.add({"key": rk, "name": "x", "mount": "/m",
                                             "target": "h:1"})),
                   "保留字 key 被拒：%s" % rkey)

    # ---- mount 校验 ----
    print("[mount 校验]")
    # 保留路径本身
    for rm in ("/_auth", "/_api", "/static", "/favicon.ico", "/_auth/login",
               "/static/x/y"):
        expect_err((lambda m=rm: reg.add({"key": "m_x", "name": "x", "mount": m,
                                          "target": "h:1"})),
                   "保留路径被拒：%s" % rm)
    # 非法 mount
    for bad, why in (("web", "不以 / 开头"), ("/", "根路径"),
                     ("/a/../b", "含 .."), ("/a//b", "含 //"),
                     ("/a%2Fb", "含 %"), ("/带中文", "含中文")):
        expect_err((lambda b=bad: reg.add({"key": "m_y", "name": "x", "mount": b,
                                           "target": "h:1"})),
                   "非法 mount 被拒：%s（%s）" % (bad, why))

    # 先配两个启用条目，测 mount 重复
    reg2 = Registry(os.path.join(tmpdir, "dup.json"))
    reg2.add({"key": "a", "name": "A", "mount": "/same", "target": "h:1"})
    reg2.add({"key": "b", "name": "B", "mount": "/other", "target": "h:2"})
    expect_err((lambda: reg2.add({"key": "c", "name": "C", "mount": "/same",
                                  "target": "h:3"})),
               "与另一启用条目重复 mount 被拒")
    # 反例控制：把 a 禁用后，/same 应能再加
    reg2.set_enabled("a", False)
    reg2.add({"key": "c", "name": "C", "mount": "/same", "target": "h:3"})
    check("禁用前者后同名 mount 可再加", reg2.get("c")["mount"] == "/same")

    # ---- target 校验 ----
    print("[target 校验]")
    check("parse_target 正确格式", parse_target("127.0.0.1:8810") == ("127.0.0.1", 8810))
    check("parse_target 端口 1 合法", parse_target("h:1") == ("h", 1))
    check("parse_target 端口 65535 合法",
          parse_target("h:65535") == ("h", 65535))
    for bad, why in (("host", "无端口"), ("host:0", "端口 0"),
                     ("host:99999", "端口>65535"), ("", "空"),
                     (":123", "缺主机"), ("h:abc", "端口非数字")):
        expect_err((lambda b=bad: parse_target(b)), "非法 target 被拒：%s" % why)

    # ---- name 校验 ----
    print("[name 校验]")
    for bad, why in (("", "空 name"), ("   ", "全空白"), ("x" * 65, "超长 name")):
        expect_err((lambda b=bad: reg.add({"key": "n_x", "name": b, "mount": "/n",
                                           "target": "h:1"})),
                   "非法 name 被拒：%s" % why)
    reg.add({"key": "n_y", "name": "合法名称", "mount": "/n", "target": "h:1"})
    check("正常 name 通过", reg.get("n_y")["name"] == "合法名称")

    # ---- 布尔归一化 ----
    print("[布尔归一化]")
    reg.add({"key": "b_x", "name": "布尔", "mount": "/b",
             "target": "h:1", "enabled": "1", "autoStart": "yes"})
    check("enabled '1' -> True", reg.get("b_x")["enabled"] is True)
    check("autoStart 'yes' -> True", reg.get("b_x")["autoStart"] is True)
    reg.add({"key": "b_y", "name": "布尔2", "mount": "/b2",
             "target": "h:1", "enabled": 0, "autoStart": "no"})
    check("enabled 0 -> False", reg.get("b_y")["enabled"] is False)
    check("autoStart 'no' -> False", reg.get("b_y")["autoStart"] is False)

    # ---- enabled_entries / mount_map ----
    print("[enabled_entries / mount_map]")
    reg3 = Registry(os.path.join(tmpdir, "en.json"))
    reg3.add({"key": "on", "name": "开", "mount": "/on", "target": "h:1",
              "enabled": True})
    reg3.add({"key": "off", "name": "关", "mount": "/off", "target": "h:2",
              "enabled": False})
    check("enabled_entries 只含启用", [e["key"] for e in reg3.enabled_entries()]
          == ["on"])
    m = reg3.mount_map()
    check("mount_map 键为规范化 mount", sorted(m) == ["/on"])
    check("mount_map 不含禁用项", "off" not in [e["key"] for e in m.values()])

    # ---- list/mount_map 副本隔离 ----
    print("[副本隔离]")
    reg4 = Registry(os.path.join(tmpdir, "copy.json"))
    reg4.add({"key": "k", "name": "K", "mount": "/k", "target": "h:1"})
    got = reg4.list()[0]
    got["name"] = "被外部改了"
    got["key"] = "被外部改了key"
    check("list 改动不影响内部", reg4.get("k")["name"] == "K"
          and reg4.get("k")["key"] == "k")
    gm = reg4.mount_map()
    gm["/k"]["name"] = "被外部改了"
    gm["/k"]["enabled"] = False
    check("mount_map 改动不影响内部", reg4.get("k")["name"] == "K"
          and reg4.get("k")["enabled"] is True)
    # add 返回的条目也应是副本
    e = reg4.add({"key": "k2", "name": "K2", "mount": "/k2", "target": "h:2"})
    e["name"] = "外部改"
    check("add 返回值不影响内部", reg4.get("k2")["name"] == "K2")

    # ---- set_enabled ----
    print("[set_enabled]")
    reg4.set_enabled("k", False)
    check("set_enabled 置 False", reg4.get("k")["enabled"] is False)
    reg4.set_enabled("k", True)
    check("set_enabled 置 True", reg4.get("k")["enabled"] is True)
    expect_err((lambda: reg4.set_enabled("nosuch", True)),
               "set_enabled 未知 key 抛错")

    # ---- update 不可改 key ----
    print("[key 不可改]")
    before_update = reg4.get("k")["mount"]
    reg4.update("k", {"key": "hacked", "mount": "/changed"})
    check("update 忽略 key 字段", reg4.get("k") is not None
          and reg4.get("hacked") is None)
    check("update 的其他字段仍生效", reg4.get("k")["mount"] == "/changed"
          and before_update == "/k")

    # ---- 持久化 ----
    print("[持久化]")
    p = os.path.join(tmpdir, "persist.json")
    r1 = Registry(p)
    r1.add({"key": "svc", "name": "持久服务", "mount": "/svc",
            "target": "127.0.0.1:9999", "enabled": True, "autoStart": True,
            "note": "备注"})
    r1.save()
    r2 = Registry(p)
    r2.load()
    check("重读读回一致", r2.get("svc") == r1.get("svc"))
    check("重读数量一致", len(r2.list()) == 1)
    check("重读 mount 为规范化", r2.get("svc")["mount"] == "/svc")
    # 写盘时不应残留临时文件
    leftover = [f for f in os.listdir(tmpdir) if f.startswith(".portal_registry_")]
    check("save 后无残留临时文件", not leftover, "残留 %r" % leftover)
    # UTF-8 / ensure_ascii=False
    with open(p, "r", encoding="utf-8") as fh:
        raw = fh.read()
    check("写盘是 UTF-8 且未转义中文", "持久服务" in raw)
    check("写盘带版本号", '"version": 1' in raw)
    payload = json.loads(raw)
    check("写盘结构 version+services",
          isinstance(payload.get("services"), list))

    # ---- 损坏文件 ----
    print("[损坏容错]")
    bad = os.path.join(tmpdir, "bad.json")
    with open(bad, "w", encoding="utf-8") as fh:
        fh.write("{oops not json[[")
    rb = Registry(bad)
    rb.load()
    check("坏 JSON load() 不抛异常", True)
    check("坏 JSON 视为空表", rb.list() == [])
    check("坏 JSON 记录 load_error", bool(rb.load_error))
    # 结构不对
    bad2 = os.path.join(tmpdir, "bad2.json")
    with open(bad2, "w", encoding="utf-8") as fh:
        json.dump(["not", "a", "dict"], fh)
    rb2 = Registry(bad2)
    rb2.load()
    check("坏结构 load() 不抛异常", True)
    check("坏结构视为空表", rb2.list() == [])
    check("坏结构记录 load_error", bool(rb2.load_error))
    # 文件不存在
    rn = Registry(os.path.join(tmpdir, "nonexistent.json"))
    rn.load()
    check("文件不存在 load() 不抛异常", True)
    check("文件不存在视为空表", rn.list() == [])
    check("文件不存在不记 load_error", rn.load_error is None)

    # ---- 自动建目录 ----
    print("[自动建目录]")
    deep = os.path.join(tmpdir, "a", "b", "c", "deep.json")
    rd = Registry(deep)
    rd.add({"key": "deep", "name": "深", "mount": "/deep", "target": "h:1"})
    rd.save()
    check("save 自动创建父目录", os.path.exists(deep))
    rd2 = Registry(deep)
    rd2.load()
    check("深目录可重读", rd2.get("deep")["mount"] == "/deep")

    # ---- 自动落盘（回归：曾出现过 add/update/remove 只改内存不保存的缺陷）----
    #
    # 这个 bug 的后果很隐蔽：控制台上加的服务当时能用（内存里在），重启门户
    # 就没了 —— 用户会以为「我明明加过」。所以每个写操作都必须立刻落盘。
    print("")
    print("[自动落盘]")
    auto_dir = tempfile.mkdtemp(prefix="portal_registry_autosave_")
    auto_path = os.path.join(auto_dir, "registry.json")

    reg = Registry(auto_path)
    reg.load()
    reg.add({"key": "a", "name": "A", "mount": "/a", "target": "127.0.0.1:1"})
    reread = Registry(auto_path)
    reread.load()
    check("add 之后立刻重新读盘能看到该服务",
          [e["key"] for e in reread.list()] == ["a"],
          "读回 %r" % [e["key"] for e in reread.list()])

    reg.add({"key": "b", "name": "B", "mount": "/b", "target": "127.0.0.1:2"})
    reg.update("b", {"name": "B2", "mount": "/b2"})
    reread = Registry(auto_path)
    reread.load()
    got = {e["key"]: e for e in reread.list()}
    check("update 之后立刻重新读盘能看到改动",
          got.get("b", {}).get("name") == "B2"
          and got.get("b", {}).get("mount") == "/b2",
          "读回 %r" % got.get("b"))

    reg.set_enabled("a", False)
    reread = Registry(auto_path)
    reread.load()
    got = {e["key"]: e for e in reread.list()}
    check("set_enabled 之后立刻重新读盘能看到开关状态",
          got.get("a", {}).get("enabled") is False,
          "读回 %r" % got.get("a"))

    reg.remove("b")
    reread = Registry(auto_path)
    reread.load()
    check("remove 之后立刻重新读盘看不到该服务",
          [e["key"] for e in reread.list()] == ["a"],
          "读回 %r" % [e["key"] for e in reread.list()])

    # 反例控制：证明「读回」不是恒为某个值 —— 没写过的新路径必须读回空
    empty_path = os.path.join(auto_dir, "never_written.json")
    empty = Registry(empty_path)
    empty.load()
    check("反例：没写过的新路径读回来是空的（证明上面的读回有区分力）",
          empty.list() == [], "读回 %r" % empty.list())
    shutil.rmtree(auto_dir, ignore_errors=True)

    print("")
    if failures:
        print("服务注册表控制检验失败：%d 项" % len(failures))
        for label in failures:
            print("  - %s" % label)
        return 1
    print("服务注册表控制检验全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())