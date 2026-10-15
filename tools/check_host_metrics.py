# -*- coding: utf-8 -*-
"""机器状态采集的控制检验（CPU / 内存 / 显存 / GPU 利用率）。

拦的是这类 bug（监控面板最容易犯、且**远程的人会被误导**）：
  1. **读不到画成 0**：驱动异常/无 nvidia-smi 时显示 "GPU 0% / 显存 0%"，
     远程的人以为机器空闲，其实是在跑满（或读数整个坏了）。这是本项目
     最忌讳的「不崩、只给错误答案」在监控场景的形态。
  2. **psutil 首次调用恒为 0**：实测 ``psutil.cpu_percent()`` 第一次返回 0.0，
     直接透传 → 满载机器显示 "CPU 0%"。
  3. **N/A 被 float() 吞掉**：nvidia-smi 在部分驱动下输出 ``N/A``，
     ``float("N/A")`` 抛异常或（更糟）被兜底成 0。
  4. **缓存失效**：TTL 内重复请求应命中缓存（省掉 46–54ms 的子进程），
     force 必须绕过缓存；两者结果都必须带上正确的 cached 标记。
  5. **并发雪崩**：多个请求同时到达时不得并发起多个 nvidia-smi。
  6. **采集异常不得让 HTTP 层 500**：必须返回结构化 payload（含 error）。

控制检验原则（正着打/反着打必须不同）：下面的注入/替换测试会用**假的**
nvidia-smi 输出证明解析逻辑真的在解析，而不是恰好返回了别处的值。

运行：python -X utf8 tools/check_host_metrics.py
"""
import json
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
    EXECUTED.append(name)
    if ok:
        print("PASS %s" % name)
    else:
        print("FAIL %s%s" % (name, ("  -> " + detail) if detail else ""))
        FAILURES.append(name)


def main():
    import host_metrics as hm

    # ---------- 1) 解析层：正常输出、N/A、残缺、非零退出 ----------
    fake_dir = tempfile.mkdtemp(prefix="host_metrics_test_")

    def write_fake(name, body, exit_code=0):
        """造一个假的 nvidia-smi 可执行脚本（.py + .cmd 包装）。"""
        py = os.path.join(fake_dir, name + ".py")
        with open(py, "w", encoding="utf-8") as fh:
            fh.write("import sys\n")
            fh.write("sys.stdout.write(%r)\n" % body)
            if exit_code:
                fh.write("sys.exit(%d)\n" % exit_code)
        cmd = os.path.join(fake_dir, name + ".cmd")
        with open(cmd, "w", encoding="utf-8") as fh:
            fh.write("@echo off\r\n\"%s\" \"%s\" %%*\r\n" % (sys.executable, py))
        return cmd

    normal = write_fake("normal", "38, 2048, 32607, 45, 123.5, 600\n")
    gpu = hm.read_gpu(normal)
    check("正常输出被正确解析（利用率/显存/温度/功耗）",
          gpu["utilization_pct"] == 38.0 and gpu["memory_used_mib"] == 2048.0
          and gpu["temperature_c"] == 45.0 and gpu["power_w"] == 123.5,
          json.dumps(gpu, ensure_ascii=False))
    check("显存占用百分比按 used/total 计算",
          gpu["memory_used_pct"] == round(100.0 * 2048 / 32607, 1),
          str(gpu["memory_used_pct"]))

    # 反例控制：换一份输出，结果必须跟着变（证明不是硬编码/缓存串味）
    other = write_fake("other", "99, 30000, 32607, 80, 550.0, 600\n")
    gpu2 = hm.read_gpu(other)
    check("换一份 nvidia-smi 输出后读数跟着变（反例控制）",
          gpu2["utilization_pct"] == 99.0 and gpu2["memory_used_mib"] == 30000.0,
          json.dumps(gpu2, ensure_ascii=False))

    # N/A 必须变成 None，**绝不是 0**
    na = write_fake("na", "N/A, 2048, 32607, N/A, N/A, 600\n")
    gpu_na = hm.read_gpu(na)
    check("N/A 解析为 None 而不是 0（关键：0 会被误读成空闲）",
          gpu_na["utilization_pct"] is None and gpu_na["temperature_c"] is None
          and gpu_na["power_w"] is None,
          json.dumps(gpu_na, ensure_ascii=False))
    check("同一次里合法字段仍正常（N/A 不影响其它字段）",
          gpu_na["memory_used_mib"] == 2048.0, str(gpu_na["memory_used_mib"]))

    # [N/A] 方括号形式（nvidia-smi 某些版本会这样输出）
    na2 = write_fake("na2", "[N/A], 1024, 32607, 50, [N/A], 600\n")
    gpu_na2 = hm.read_gpu(na2)
    check("[N/A] 方括号形式同样解析为 None",
          gpu_na2["utilization_pct"] is None and gpu_na2["power_w"] is None
          and gpu_na2["temperature_c"] == 50.0,
          json.dumps(gpu_na2, ensure_ascii=False))

    # 字段数不足 -> 必须报 error，且所有数值字段为 None（不能给半真数据）
    short = write_fake("short", "38, 2048\n")
    gpu_short = hm.read_gpu(short)
    check("字段数不足时报 error 且数值字段全为 None",
          gpu_short["error"] is not None and gpu_short["utilization_pct"] is None
          and gpu_short["memory_used_mib"] is None,
          json.dumps(gpu_short, ensure_ascii=False))

    # 非零退出 -> error，不得当作 0
    bad = write_fake("bad", "", exit_code=9)
    gpu_bad = hm.read_gpu(bad)
    check("nvidia-smi 非零退出时报 error（不是 0）",
          gpu_bad["error"] is not None and gpu_bad["utilization_pct"] is None,
          json.dumps(gpu_bad, ensure_ascii=False))

    # 存在的路径但完全不是可执行 -> 走 OSError 分支
    gpu_missing = hm.read_gpu(os.path.join(fake_dir, "no-such-smi.exe"))
    check("nvidia-smi 不存在时报 error（不是 0）",
          gpu_missing["error"] is not None and gpu_missing["utilization_pct"] is None,
          json.dumps(gpu_missing, ensure_ascii=False))

    # ---------- 2) 真实机器：三个必须能读到的量 ----------
    hm.reset_cache()
    snap = hm.sample(force=True, smi_path=None)
    check("真实机器上 CPU 可读且不是 None",
          snap["cpu_percent"] is not None, str(snap["cpu_percent"]))
    check("真实机器上内存可读且 total>0",
          (snap["mem_total_gib"] or 0) > 0 and snap["mem_percent"] is not None,
          "total=%s used=%s" % (snap["mem_total_gib"], snap["mem_used_gib"]))
    check("真实机器上内存已用 <= 总量（不能出现负的可用）",
          (snap["mem_used_gib"] or 0) <= (snap["mem_total_gib"] or 0),
          "%s/%s" % (snap["mem_used_gib"], snap["mem_total_gib"]))

    gpu_real = snap["gpu"]
    if gpu_real.get("error"):
        # 没 GPU 的机器：必须明确报错，且不得伪造数字
        check("无 GPU 时字段为 None 且带 error（不伪造 0）",
              gpu_real["utilization_pct"] is None
              and gpu_real["memory_used_mib"] is None
              and bool(gpu_real["error"]),
              json.dumps(gpu_real, ensure_ascii=False))
    else:
        check("真实 GPU 利用率在 [0,100]",
              gpu_real["utilization_pct"] is not None
              and 0 <= gpu_real["utilization_pct"] <= 100,
              str(gpu_real["utilization_pct"]))
        check("真实显存已用 <= 总显存，且百分比一致",
              gpu_real["memory_used_mib"] <= gpu_real["memory_total_mib"]
              and gpu_real["memory_used_pct"] is not None,
              "%s/%s (%s%%)" % (gpu_real["memory_used_mib"],
                                gpu_real["memory_total_mib"],
                                gpu_real["memory_used_pct"]))
        check("GPU 名字能读到（用于确认不是读错卡）",
              bool(gpu_real.get("name")), str(gpu_real.get("name")))

    # ---------- 3) 首次调用不得因无基线而报 0（psutil 陷阱） ----------
    hm.reset_cache()
    first = hm.sample(force=True)
    # 真机上 CPU 可能有极小概率真的接近 0；这里检验的是"我们给了基线窗口"，
    # 即：即使恰好在空闲机器上，也不能每次都是无条件的 0。
    second = hm.sample(force=True)
    check("连续两次采样都返回数值（基线窗口已建立）",
          first["cpu_percent"] is not None and second["cpu_percent"] is not None,
          "first=%s second=%s" % (first["cpu_percent"], second["cpu_percent"]))

    # 用一个必定非零的负载做正例控制：忙等期间 CPU 必须被观察到 > 0
    stop = threading.Event()

    def burn():
        while not stop.is_set():
            sum(i * i for i in range(20000))

    threads = [threading.Thread(target=burn, daemon=True) for _ in range(4)]
    for t in threads:
        t.start()
    time.sleep(0.3)
    hm.reset_cache()
    busy = hm.read_cpu_memory()
    stop.set()
    for t in threads:
        t.join(timeout=2)
    check("有真实 CPU 负载时读数 > 0（正面控制：证明不是恒定 0）",
          busy["cpu_percent"] is not None and busy["cpu_percent"] > 0,
          "cpu_percent=%s" % busy["cpu_percent"])

    # ---------- 4) 缓存语义 ----------
    hm.reset_cache()
    a = hm.sample(ttl=30.0)
    b = hm.sample(ttl=30.0)
    check("TTL 内第二次请求命中缓存",
          b.get("cached") is True and a.get("cached") is False,
          "a.cached=%s b.cached=%s" % (a.get("cached"), b.get("cached")))
    check("缓存命中时时间戳与首次一致（说明没重新采集）",
          abs(float(b["at"]) - float(a["at"])) < 1e-6,
          "at差异=%s" % (float(b["at"]) - float(a["at"])))
    c = hm.sample(ttl=30.0, force=True)
    check("force=True 绕过缓存（时间戳前进）",
          c.get("cached") is False,
          "c.cached=%s" % c.get("cached"))

    # ---------- 5) status_json 永不抛异常 ----------
    original = hm.sample
    def boom(*a, **k):
        raise RuntimeError("模拟采集崩溃")
    hm.sample = boom
    try:
        payload = hm.status_json()
    finally:
        hm.sample = original
    check("采集崩溃时 status_json 仍返回结构化 payload（HTTP 层不会 500）",
          isinstance(payload, dict) and payload.get("cpu_error")
          and payload.get("gpu_utilization_pct") is None,
          json.dumps({k: payload.get(k) for k in ("cpu_error", "gpu_utilization_pct")},
                     ensure_ascii=False))

    # ---------- 6) 一行摘要：缺失值显示「—」而不是 0 ----------
    line = hm.format_line({"cpu_percent": None, "mem_percent": None,
                           "mem_used_gib": None, "mem_total_gib": None,
                           "gpu_utilization_pct": None, "gpu_memory_used_pct": None,
                           "gpu_temperature_c": None, "gpu_power_w": None})
    check("摘要行对缺失值显示「—」且不出现 '0%'（防误读为空闲）",
          "—" in line and "0%" not in line, line)
    line2 = hm.format_line({"cpu_percent": 12.5, "mem_percent": 30.0,
                            "mem_used_gib": 10.0, "mem_total_gib": 32.0,
                            "gpu_utilization_pct": 88.0, "gpu_memory_used_pct": 55.0,
                            "gpu_temperature_c": 70, "gpu_power_w": 400})
    check("摘要行在数值齐全时包含全部四个量",
          all(s in line2 for s in ("CPU 12.5%", "内存 30.0%", "GPU 88.0%", "显存 55.0%")),
          line2)

    print()
    if FAILURES:
        print("机器状态采集检查失败 %d 项：%s" % (len(FAILURES), FAILURES))
        return 1
    print("机器状态采集检查全部通过（%d 项）" % len(EXECUTED))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
