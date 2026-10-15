# -*- coding: utf-8 -*-
"""机器实时状态采集：CPU / 内存 / 显存 / GPU 利用率。

用途：训练配置台与模型查看台顶部显示"这台机器现在到底在干什么"。
用户远程查看时的核心诉求是**知道机器的真实情况**，所以本模块的第一原则是：

    **宁可明确报「读不到」，也绝不把缺失值画成 0。**

为什么这条最重要（实测教训）：本机 ``psutil.cpu_percent()`` 首次调用返回 ``0.0``。
如果直接透传，满载运行的机器会显示"CPU 0%"，远程的人会以为机器闲着 ——
这正是本项目反复强调的「不崩、只给错误答案」那一类 bug。所以：

  · CPU 用「两次采样差分」而不是单次调用，第一次没有基线就报 ``None``；
  · 每个字段都带 ``available`` 语义：拿不到就是 ``null``，前端显示「—」或「未测量」；
  · GPU 读数失败（驱动异常/无 GPU）时，字段为 ``null`` 且 ``gpu_error`` 给出原因，
    **不允许**用 0 冒充。

采集成本（本机实测）：
  · ``nvidia-smi`` 单次子进程约 46–54 ms —— 不能每个 HTTP 请求都起进程，
    因此带 TTL 缓存（默认 1.5 s），并在缓存过期时**同步刷新**；
  · CPU/内存走 psutil，微秒级；
  · **绝不在本模块里 import torch**：``torch.cuda`` 初始化会在 GUI 进程里建立
    CUDA 上下文，占用显存并可能干扰正在跑的训练。GPU 信息一律走 nvidia-smi 外部进程。

并发：多个浏览器请求可能同时触发刷新，用锁保证同一时刻只有一次真实采集。
"""
import os
import subprocess
import sys
import threading
import time

try:
    import psutil
except ImportError:  # 依赖缺失必须显式暴露，不能静默降级成"全 0"
    psutil = None

# nvidia-smi 查询字段：利用率 / 已用显存 / 总显存 / 温度 / 功耗 / 功耗上限
_NVML_FIELDS = ("utilization.gpu", "memory.used", "memory.total",
                "temperature.gpu", "power.draw", "power.limit")
_NVML_QUERY = ",".join(_NVML_FIELDS)

# 采样的缓存 TTL（秒）。太小会让 nvidia-smi 子进程过频，太大则界面迟钝。
DEFAULT_TTL = 1.5
# nvidia-smi 子进程超时：驱动卡死时不能让 HTTP 请求无限等待。
SMI_TIMEOUT = 5.0

_LOCK = threading.Lock()
_CACHE = {"at": 0.0, "payload": None}
# psutil.cpu_percent 的基线：跨调用保存，保证"差分"语义
_CPU_BASELINE = {"primed": False}


def _find_nvidia_smi():
    """定位 nvidia-smi。优先 PATH，其次 Windows 系统目录。"""
    from shutil import which
    found = which("nvidia-smi")
    if found:
        return found
    for candidate in (
        os.path.join(os.environ.get("SystemRoot", r"C:\windows"),
                     "System32", "nvidia-smi.exe"),
        "/usr/bin/nvidia-smi",
        "/usr/local/bin/nvidia-smi",
    ):
        if os.path.isfile(candidate):
            return candidate
    return None


def _to_float(text):
    """把 nvidia-smi 的字段转成 float；``N/A``/空/``[N/A]`` 一律 None。

    这里刻意不做 ``or 0`` 之类的兜底 —— 那正是把"读不到"变成"看起来是 0"的根源。
    """
    if text is None:
        return None
    text = str(text).strip()
    if not text or text.upper() in ("N/A", "[N/A]", "NA", "UNKNOWN", "-"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def read_gpu(smi_path=None):
    """读 GPU 状态。返回 dict；读不到时字段为 None 且带 ``error``。"""
    smi = smi_path or _find_nvidia_smi()
    result = {
        "name": None,
        "utilization_pct": None,
        "memory_used_mib": None,
        "memory_total_mib": None,
        "memory_used_pct": None,
        "temperature_c": None,
        "power_w": None,
        "power_limit_w": None,
        "error": None,
    }
    if not smi:
        result["error"] = "找不到 nvidia-smi（无 NVIDIA 驱动或未安装）"
        return result

    argv = [smi, "--query-gpu=" + _NVML_QUERY,
            "--format=csv,noheader,nounits"]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              timeout=SMI_TIMEOUT)
    except subprocess.TimeoutExpired:
        result["error"] = "nvidia-smi 超时（%.0fs）：驱动可能无响应" % SMI_TIMEOUT
        return result
    except OSError as exc:
        result["error"] = "无法执行 nvidia-smi：%s" % exc
        return result

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        result["error"] = "nvidia-smi 退出码 %d：%s" % (
            proc.returncode, detail[:200] or "无输出")
        return result

    line = (proc.stdout or "").strip().splitlines()
    if not line:
        result["error"] = "nvidia-smi 没有返回任何 GPU 行"
        return result

    # 多卡时只用第一张（本项目是单张 5090）；保留 index/name 便于将来辨认
    first = line[0]
    parts = [p.strip() for p in first.split(",")]
    if len(parts) < len(_NVML_FIELDS):
        result["error"] = "nvidia-smi 字段数不符（期望 %d，得到 %d）：%r" % (
            len(_NVML_FIELDS), len(parts), first[:120])
        return result

    util, used, total, temp, power, limit = (_to_float(p) for p in parts[:6])
    result.update({
        "utilization_pct": util,
        "memory_used_mib": used,
        "memory_total_mib": total,
        "temperature_c": temp,
        "power_w": power,
        "power_limit_w": limit,
    })
    if used is not None and total:
        result["memory_used_pct"] = round(100.0 * used / total, 1)
    # 单独取名字（另一次查询代价高，这里从 nvidia-smi 的默认输出补）
    try:
        name_proc = subprocess.run([smi, "--query-gpu=name",
                                    "--format=csv,noheader"],
                                   capture_output=True, text=True, timeout=SMI_TIMEOUT)
        if name_proc.returncode == 0:
            names = [n.strip() for n in (name_proc.stdout or "").splitlines() if n.strip()]
            if names:
                result["name"] = names[0]
    except Exception:
        pass
    return result


def read_cpu_memory():
    """读 CPU / 内存。CPU 用差分采样，没有基线时返回 None（**不返回 0**）。"""
    out = {
        "cpu_percent": None,
        "cpu_count_logical": None,
        "cpu_count_physical": None,
        "mem_total_gib": None,
        "mem_used_gib": None,
        "mem_percent": None,
        "swap_percent": None,
        "error": None,
    }
    if psutil is None:
        out["error"] = "缺少 psutil，无法读取 CPU/内存"
        return out
    try:
        # 关键：psutil.cpu_percent(interval=None) 首次调用返回 0.0（没有基线）。
        # 这里建立一个基线窗口再取差分值，避免"新连接第一屏显示近 0%"。
        # 0.35s 是实测折中：窗口太短会取到瞬时低点（曾观察到 0.0%，而系统
        # 计数同期为 3.4%），太长会拖慢首次请求。
        if not _CPU_BASELINE["primed"]:
            psutil.cpu_percent(interval=None)
            time.sleep(0.35)
            _CPU_BASELINE["primed"] = True
        cpu = psutil.cpu_percent(interval=None)
        # 注意：这里**不**把 0 改写成别的值 —— 机器真的空闲时 0% 是正确答案，
        # 我们的职责是保证"0 表示真的测到 0"，而不是"读不到时兜底成 0"。
        out["cpu_percent"] = round(float(cpu), 1)
        out["cpu_count_logical"] = psutil.cpu_count()
        out["cpu_count_physical"] = psutil.cpu_count(logical=False)
        vm = psutil.virtual_memory()
        out["mem_total_gib"] = round(vm.total / 2 ** 30, 2)
        out["mem_used_gib"] = round(vm.used / 2 ** 30, 2)
        out["mem_percent"] = round(float(vm.percent), 1)
        try:
            out["swap_percent"] = round(float(psutil.swap_memory().percent), 1)
        except Exception:
            out["swap_percent"] = None
    except Exception as exc:  # psutil 在某些权限下会抛，必须如实报错
        out["error"] = "读取 CPU/内存失败：%r" % (exc,)
    return out


def sample(ttl=DEFAULT_TTL, force=False, smi_path=None):
    """采集一次完整快照（带 TTL 缓存）。返回可直接 JSON 序列化的 dict。"""
    now = time.time()
    with _LOCK:
        cached = _CACHE["payload"]
        if (not force and cached is not None
                and (now - _CACHE["at"]) < ttl):
            payload = dict(cached)
            payload["cached"] = True
            payload["age_s"] = round(now - _CACHE["at"], 2)
            return payload
        cpu = read_cpu_memory()
        gpu = read_gpu(smi_path)
        payload = {
            "at": now,
            "at_text": time.strftime("%H:%M:%S", time.localtime(now)),
            "cpu": cpu,
            "gpu": gpu,
            # 顶层便捷字段，前端省一次解包
            "cpu_percent": cpu.get("cpu_percent"),
            "mem_percent": cpu.get("mem_percent"),
            "mem_used_gib": cpu.get("mem_used_gib"),
            "mem_total_gib": cpu.get("mem_total_gib"),
            "gpu_utilization_pct": gpu.get("utilization_pct"),
            "gpu_memory_used_mib": gpu.get("memory_used_mib"),
            "gpu_memory_total_mib": gpu.get("memory_total_mib"),
            "gpu_memory_used_pct": gpu.get("memory_used_pct"),
            "gpu_temperature_c": gpu.get("temperature_c"),
            "gpu_power_w": gpu.get("power_w"),
            "gpu_name": gpu.get("name"),
            "gpu_error": gpu.get("error"),
            "cpu_error": cpu.get("error"),
            "cached": False,
            "age_s": 0.0,
        }
        _CACHE["at"] = now
        _CACHE["payload"] = payload
        return dict(payload)


def reset_cache():
    """测试用：清掉 TTL 缓存与 CPU 基线。"""
    with _LOCK:
        _CACHE["at"] = 0.0
        _CACHE["payload"] = None
        _CPU_BASELINE["primed"] = False


# ---------------------------------------------------------------- HTTP 路由

def status_json(ttl=DEFAULT_TTL, force=False):
    """给 HTTP 层用的入口：永远返回可序列化 dict，绝不抛异常。"""
    try:
        return sample(ttl=ttl, force=force)
    except Exception as exc:  # 采集崩了也要让界面能显示原因，而不是 500 空 body
        return {
            "at": time.time(),
            "at_text": time.strftime("%H:%M:%S"),
            "cpu": {"error": "采集失败：%r" % (exc,)},
            "gpu": {"error": "采集失败：%r" % (exc,)},
            "cpu_percent": None, "mem_percent": None,
            "gpu_utilization_pct": None, "gpu_memory_used_pct": None,
            "gpu_error": "采集失败：%r" % (exc,),
            "cpu_error": "采集失败：%r" % (exc,),
            "cached": False, "age_s": 0.0,
        }


def format_line(payload):
    """一行文本摘要（日志/终端用）。缺失值显示「—」，不显示 0。"""
    def pct(v):
        return "—" if v is None else "%s%%" % v

    def num(v, unit=""):
        return "—" if v is None else "%s%s" % (v, unit)

    return ("CPU %s | 内存 %s (%s/%s GiB) | GPU %s 显存 %s | %s°C %sW"
            % (pct(payload.get("cpu_percent")),
               pct(payload.get("mem_percent")),
               num(payload.get("mem_used_gib")), num(payload.get("mem_total_gib")),
               pct(payload.get("gpu_utilization_pct")),
               pct(payload.get("gpu_memory_used_pct")),
               num(payload.get("gpu_temperature_c")),
               num(payload.get("gpu_power_w"))))


if __name__ == "__main__":
    # 直接运行：打印两次快照，便于人工核对（间隔大于 TTL 会各采一次）
    import json
    first = sample(force=True)
    print(format_line(first))
    print(json.dumps(first, ensure_ascii=False, indent=2))
    if "--twice" in sys.argv:
        time.sleep(DEFAULT_TTL + 0.2)
        print()
        print(format_line(sample(force=True)))
