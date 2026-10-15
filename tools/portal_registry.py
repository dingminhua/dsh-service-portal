# -*- coding: utf-8 -*-
"""服务注册表：把「服务清单 JSON」升级为运行时可变的注册表。

对外提供增删改查 + 持久化原子写。数据模型严格对齐
docs/40-portal-console-design.md 的「服务条目模型（注册表）」一节。

设计要点：
  * 纯标准库，无第三方依赖；面向 Python 3.10+。
  * load() 对「文件不存在 / 损坏」容忍——视为空表，绝不抛异常，
    只在 self.load_error 里记录损坏原因供调用方展示。
  * save() 原子写：tempfile 同一目录 + os.replace，不残留临时文件。
  * 校验失败统一抛 RegistryError（= ValueError），消息为中文、可直接展示。
"""
import json
import os
import re
import tempfile

#: 版本由我在 :py:mod:`json` 层定义；保留字 key（控制台/认证专用路径）。
RESERVED_KEYS = {"_auth", "_api", "api", "static", "favicon.ico"}

#: 保留路径（含子路径）——代理/控制台专用，服务不得占用。
RESERVED_MOUNTS = ("/_auth", "/_api", "/static", "/favicon.ico")

_VERSION = 1
_KEY_RE = re.compile(r"^[a-zA-Z0-9_-]{1,32}$")
_MOUNT_RE = re.compile(r"^/[a-zA-Z0-9._~/-]*$")
_BOOL_KEYS = {"enabled", "autoStart"}


class RegistryError(ValueError):
    """校验失败；消息为中文、可直接展示给用户。"""


def _ensure_bool(value, field):
    """把 truthy/falsy 值归一化成 bool；无法判定的抛错。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("1", "true", "yes", "on", "真", "是", "开"):
            return True
        if s in ("0", "false", "no", "off", "假", "否", "关"):
            return False
    raise RegistryError("字段 %s 必须是布尔值" % field)


def normalise_mount(mount):
    """把路由路径规范化成 `/xxx` 形式：`train` → `/train`，`/train/` → `/train`。"""
    if mount is None:
        raise RegistryError("路由路径(mount)不能为空")
    s = str(mount).strip()
    if not s.startswith("/"):
        s = "/" + s
    # 去掉尾部多余的斜杠，但保留根路径本身（根由上层另行拒绝）
    while len(s) > 1 and s.endswith("/"):
        s = s[:-1]
    return s


def parse_target(target):
    """校验 `host:port` 格式并返回 (host, port)。"""
    if target is None:
        raise RegistryError("上游地址(target)不能为空")
    s = str(target).strip()
    if not s:
        raise RegistryError("上游地址(target)不能为空")
    if ":" not in s:
        raise RegistryError("上游地址(target)必须是 host:端口 格式，例如 127.0.0.1:8810")
    host, _, port_str = s.rpartition(":")
    if not host:
        raise RegistryError("上游地址(target)缺少主机名")
    try:
        port = int(port_str)
    except ValueError:
        raise RegistryError("上游地址(target)端口必须是数字（1–65535）")
    if not (1 <= port <= 65535):
        raise RegistryError("上游地址(target)端口必须是 1–65535，当前是 %d" % port)
    return host, port


def _validate_key(key):
    if key is None:
        raise RegistryError("服务 key 不能为空")
    if not isinstance(key, str):
        raise RegistryError("服务 key 必须是字符串")
    if not key:
        raise RegistryError("服务 key 不能为空")
    if key in RESERVED_KEYS:
        raise RegistryError("key %r 保留给控制台/认证使用，不能用作服务 key" % key)
    if not _KEY_RE.match(key):
        raise RegistryError(
            "服务 key 只能由字母/数字/下划线/短横线组成，长度 1–32（当前: %r）" % key)
    return key


def _validate_mount(mount, registry, key):
    mount = normalise_mount(mount)
    if mount == "/":
        raise RegistryError("根路径 / 保留给控制台使用，路由路径不得为 /")
    if any((mount == r or mount.startswith(r + "/")) for r in RESERVED_MOUNTS):
        raise RegistryError(
            "路由路径 %s 与保留路径冲突（%s）" % (mount, "、".join(RESERVED_MOUNTS)))
    if ".." in mount or "%" in mount or "//" in mount:
        raise RegistryError(
            "路由路径 %s 含非法字符（不允许 .. / %% / 连续斜杠 //）" % mount)
    if not _MOUNT_RE.match(mount):
        raise RegistryError(
            "路由路径 %s 必须是 / 开头、且只含字母/数字/. _ ~ / - 的路径" % mount)
    # 重复检查只针对已启用条目
    for other in registry._entries.values():
        if other["key"] == key:
            continue
        if other["enabled"] and normalise_mount(other["mount"]) == mount:
            raise RegistryError("路由路径 %s 已被服务 %s 占用"
                                % (mount, other["key"]))
    return mount


class Registry:
    """服务注册表。path 为 JSON 落盘路径。"""

    def __init__(self, path):
        self.path = os.path.abspath(path)
        self.load_error = None
        self._entries = {}

    # ---- 持久化 ----
    def load(self):
        """读盘；文件不存在/损坏/结构不对 → 空表 + 记录 load_error，不抛异常。"""
        self._entries = {}
        self.load_error = None
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict) or not isinstance(data.get("services"), list):
                raise ValueError("顶层结构必须是 {\"version\":1, \"services\":[...]}")
            for item in data["services"]:
                if not isinstance(item, dict):
                    continue
                # 校验失败的单条跳过，不污染整表
                self.add(item)
        except (ValueError, TypeError, OSError) as exc:
            self._entries = {}
            self.load_error = "配置损坏，已按空表启动：%s" % exc

    def save(self):
        """原子写：先写同目录临时文件再 os.replace；自动创建父目录。"""
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        payload = {
            "version": _VERSION,
            "services": [dict(e) for e in self._entries.values()],
        }
        fd, tmp = tempfile.mkstemp(
            dir=os.path.dirname(self.path), prefix=".portal_registry_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
        except Exception:
            # 清理残留临时文件
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass
            raise

    # ---- 查询 ----
    def list(self):
        """全部条目（深一层副本，避免外部改动内部状态）。"""
        return [dict(e) for e in self._entries.values()]

    def get(self, key):
        entry = self._entries.get(key)
        return dict(entry) if entry is not None else None

    def enabled_entries(self):
        return [dict(e) for e in self._entries.values() if e["enabled"]]

    def mount_map(self):
        """{"/train": entry, ...}，键为规范化 mount；供代理快速查表。"""
        out = {}
        for e in self._entries.values():
            if e["enabled"]:
                out[normalise_mount(e["mount"])] = dict(e)
        return out

    # ---- 变更 ----
    def add(self, entry):
        entry = dict(entry)
        key = _validate_key(entry.get("key"))
        if key in self._entries:
            raise RegistryError("服务 key %s 已存在" % key)

        name = entry.get("name")
        if name is None:
            raise RegistryError("服务名称(name)不能为空")
        name = str(name).strip()
        if not name:
            raise RegistryError("服务名称(name)不能为空")
        if len(name) > 64:
            raise RegistryError("服务名称(name)长度不能超过 64（当前 %d）" % len(name))

        mount = _validate_mount(entry.get("mount"), self, key)
        parse_target(entry.get("target"))

        base = {
            "key": key,
            "name": name,
            "mount": mount,
            "target": str(entry.get("target")).strip(),
            "enabled": _ensure_bool(entry.get("enabled", True), "enabled"),
            "autoStart": _ensure_bool(entry.get("autoStart", False), "autoStart"),
            "script": entry.get("script") or "",
            "cwd": entry.get("cwd") or "",
            "note": entry.get("note") or "",
        }
        self._entries[key] = base
        # 立即落盘：控制台的每次改动都必须持久化，否则重启门户服务就丢了
        # （「改了但没存」是本项目最忌讳的假成功）。
        self.save()
        return dict(base)

    def update(self, key, patch):
        entry = self._entries.get(key)
        if entry is None:
            raise RegistryError("找不到服务 %s" % key)
        patch = dict(patch)
        # key 不可改：忽略 patch 中的 key 字段
        if "key" in patch:
            patch.pop("key")
        for field in ("enabled", "autoStart"):
            if field in patch:
                entry[field] = _ensure_bool(patch[field], field)
        if "mount" in patch:
            entry["mount"] = _validate_mount(patch["mount"], self, key)
        if "target" in patch:
            parse_target(patch["target"])
            entry["target"] = str(patch["target"]).strip()
        for field in ("name", "script", "cwd", "note"):
            if field in patch:
                value = patch[field]
                if field == "name":
                    value = (str(value) if value is not None else "").strip()
                    if not value:
                        raise RegistryError("服务名称(name)不能为空")
                    if len(value) > 64:
                        raise RegistryError(
                            "服务名称(name)长度不能超过 64（当前 %d）" % len(value))
                entry[field] = "" if value is None else str(value)
        self.save()
        return dict(entry)

    def remove(self, key):
        if key in self._entries:
            del self._entries[key]
            self.save()
            return True
        return False

    def set_enabled(self, key, enabled):
        entry = self._entries.get(key)
        if entry is None:
            raise RegistryError("找不到服务 %s" % key)
        entry["enabled"] = _ensure_bool(enabled, "enabled")
        self.save()
        return dict(entry)
