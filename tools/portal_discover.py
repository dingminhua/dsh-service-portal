# -*- coding: utf-8 -*-
"""服务自动发现：扫描本机在听的端口，筛出「像 Web 服务」的候选。

## 为什么单独一个模块
门户主体（:mod:`portal_run`）已经很重（1300+ 行）。发现逻辑是可独立测试的纯函数，
放这里既能被控制检验直接调用，也不把门户撑得更大。

## 为什么**必须**做安全分级（这个功能最大的坑）
实测本机扫出 16 个"像 Web 服务"的端口，其中一批**绝不能一键对外暴露**：

  · 19387  = DSH 自己的界面      -> 暴露等于把整个 IDE 挂到公网
  · 20241  = 本项目自己的 cloudflared 隧道 -> 暴露会形成环
  · 8738 / 7897 = clash 代理      -> 暴露等于开放翻墙入口
  · 443 / 9013 / 9014 / Armoury  = 系统组件 -> 暴露毫无意义且危险

所以发现的产出**不是**"可以直接添加的服务"，而是"带风险标签的候选"：
  · ``level`` 三档：ok / caution / danger
  · ``danger`` 的候选在界面上**默认不勾选**，并写明原因
  · 是否添加始终由用户决定（不自动写入注册表）

## 判定原则
只做**保守**的启发式：判不出来就不推荐（``ok`` 都不是"安全"，只是"没识别出风险"）。
"""
import json
import os
import re
import subprocess
import urllib.error
import urllib.request

#: 明确的系统/基础服务端口。这些不是"用户想开放的应用"，直接标 danger。
SYSTEM_PORTS = {
    135: "Windows RPC", 139: "NetBIOS", 445: "SMB 文件共享",
    5040: "Windows 连接设备平台", 5357: "WSD 设备发现",
    5353: "mDNS 组播 DNS", 7680: "Windows 更新传递优化",
    3389: "远程桌面 RDP", 1900: "SSDP 即插即用",
    3702: "WS-Discovery", 21: "FTP", 22: "SSH", 23: "Telnet",
    25: "SMTP", 53: "DNS", 110: "POP3", 143: "IMAP",
}

#: 进程名关键字 -> 风险说明。命中即标 danger（比端口号更可靠）。
DANGER_PROC = (
    (r"clash|mihomo|v2ray|xray|sing-box|shadowsocks|trojan|verge",
     "代理软件：暴露等于把翻墙/代理入口开放给所有人"),
    (r"vsvnhttpsvc|vpn|openvpn|wireguard|tailscale|zerotier",
     "VPN / 组网组件：不应对外发布"),
    (r"armoury|asus|rog\b|live?service", "主板/整机厂商的常驻系统服务"),
    (r"todesk|sunlogin|teamviewer|anydesk|rustdesk",
     "远程控制软件：暴露等于把远程桌面入口开放（极危险）"),
    (r"lsass|wininit|services\.exe|spoolsv|csrss|smss",
     "Windows 核心系统进程"),
    # 宿主 IDE 自己的界面。实测本机它是 4 个端口（2462-2465）+ 19387，
    # 全都被探成"像 Web 服务"。一键发布等于把整个 DSH 挂到公网上。
    (r"deepseek\s*harness|dsh\.exe|dsh-host|electron",
     "这是 DSH（宿主 IDE）自己的界面：发布等于把整个开发环境暴露到公网"),
    # 本项目自己的隧道进程。实测它也被探成"像 Web 服务"（HTTP 404）。
    # 按**进程名**判定而不是端口号：隧道端口每次启动都会变，写死端口会漏。
    # 发布隧道自身等于让门户经过自己的隧道再回到自己 —— 成环。
    (r"cloudflared",
     "本插件自己的隧道进程：发布会造成请求成环，不要添加"),
)

#: 这些端口一旦被发布，会直接破坏本插件自身或 DSH 的运行 ——
#: 由调用方通过 exclude_ports 传入（门户端口、cloudflared 端口等），
#: 因为它们随运行环境变化，写死在这里会漂移。


def _is_local(host):
    return host in ("127.0.0.1", "0.0.0.0", "[::]", "[::1]", "::", "*")


def _parse_netstat(text):
    """netstat 输出 -> {port: pid}（只取本机在听的 TCP）。"""
    rows = {}
    for line in (text or "").splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[0].upper() != "TCP":
            continue
        if parts[3].upper() != "LISTENING":
            continue
        host, _, port_text = parts[1].rpartition(":")
        if not port_text.isdigit() or not _is_local(host):
            continue
        try:
            pid = int(parts[4])
        except ValueError:
            continue
        rows.setdefault(int(port_text), pid)
    return rows


def _listening_ports():
    """本机在听的 TCP 端口（Windows 走 netstat；其他平台走 ss/lsof 兜底）。"""
    cmds = [
        ["netstat", "-ano", "-p", "TCP"],
        ["ss", "-ltnp"],
        ["netstat", "-an"],
    ]
    for cmd in cmds:
        try:
            done = subprocess.run(cmd, capture_output=True, text=True,
                                  errors="replace", encoding="utf-8", timeout=25)
        except (OSError, subprocess.SubprocessError):
            continue
        if done.returncode == 0 and (done.stdout or "").strip():
            rows = _parse_netstat(done.stdout)
            if rows:
                return rows
    return {}


def _proc_info():
    """PID -> (进程名, 命令行)。取不到就返回空表（功能降级但不报错）。"""
    try:
        done = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process | "
             "Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Compress"],
            capture_output=True, text=True, errors="replace",
            encoding="utf-8", timeout=60)
    except (OSError, subprocess.SubprocessError):
        return {}
    out = (done.stdout or "").strip()
    if not out:
        return {}
    try:
        data = json.loads(out)
    except ValueError:
        return {}
    if isinstance(data, dict):
        data = [data]
    info = {}
    for row in data:
        try:
            info[int(row.get("ProcessId"))] = (
                str(row.get("Name") or ""), str(row.get("CommandLine") or ""))
        except (TypeError, ValueError):
            continue
    return info


def _probe_web(port, timeout=0.7):
    """这个端口是不是 HTTP 服务？返回 (是, 证据串)。

    "有响应"就算 —— 401/403/404 也证明它在说 HTTP，那就是个 Web 服务。
    连不上/不是 HTTP 就返回 False（不推荐）。
    """
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:%d/" % port, method="GET",
            headers={"User-Agent": "service-portal-discover"})
        with urllib.request.urlopen(req, timeout=timeout) as res:
            body = res.read(2048).decode("utf-8", "replace")
            title = ""
            match = re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I)
            if match:
                title = " ".join(match.group(1).split())[:60]
            return True, "HTTP %d%s" % (res.status, (" · " + title) if title else "")
    except urllib.error.HTTPError as err:
        return True, "HTTP %d" % err.code
    except Exception:
        return False, ""


def _probe_many(ports, timeout=0.7, workers=16):
    """并发探一批端口 -> {port: (is_web, evidence)}。

    为什么要并发：顺序探每个端口最坏要等满 timeout。实测本机 40+ 个在听端口，
    顺序探测会让"发现"按钮转十几秒 —— 用户以为卡死。并发后通常 1 秒内出结果。
    """
    if not ports:
        return {}
    from concurrent.futures import ThreadPoolExecutor
    out = {}
    with ThreadPoolExecutor(max_workers=min(workers, len(ports))) as pool:
        futures = {pool.submit(_probe_web, p, timeout): p for p in ports}
        for future, port in futures.items():
            try:
                out[port] = future.result()
            except Exception:
                out[port] = (False, "")
    return out


def _classify(port, proc_name, cmdline, *, portal_port, registered_ports,
              exclude_ports):
    """给一个候选定风险档：(level, reason)。"""
    text = ("%s %s" % (proc_name, cmdline)).lower()
    if port == portal_port:
        return "danger", "这是门户自己的端口"
    if port in exclude_ports:
        return "danger", "本插件自己的进程，不能发布（会造成环）"
    if port in registered_ports:
        return "danger", "已经在服务清单里了"
    if port in SYSTEM_PORTS:
        return "danger", "系统服务（%s），不应对外发布" % SYSTEM_PORTS[port]
    for pattern, reason in DANGER_PROC:
        if re.search(pattern, text, re.I):
            return "danger", reason
    if port < 1024:
        return "caution", "系统保留端口段（<1024），通常不是你的应用"
    if port == 443 or port == 80:
        return "caution", "标准 Web 端口，可能被别的程序占用"
    return "ok", ""


def discover_services(*, portal_port=8899, registered=None, exclude_ports=(),
                      probe=True, timeout=0.7):
    """扫描本机在听的端口，返回带风险档的候选列表（**不写入任何东西**）。

    :param portal_port: 门户自己的端口（永远排除）
    :param registered: 已注册服务的 target 端口集合（排除，避免重复推荐）
    :param exclude_ports: 额外的排除端口（如本项目 cloudflared 的端口）
    :param probe: 是否真去 HTTP 探一下（关掉则只按进程/端口分级，不做探测）
    :returns: dict(ok=True, candidates=[...], scanned=N, note=...)

    ``candidates`` 每项：
        port / target / name / level / reason / evidence / kind
    ``level``: "ok" 可推荐 / "caution" 谨慎 / "danger" 绝不要
    """
    registered_ports = set()
    for item in (registered or []):
        text = str(item)
        if ":" in text:
            tail = text.rpartition(":")[2]
            if tail.isdigit():
                registered_ports.add(int(tail))
        elif text.isdigit():
            registered_ports.add(int(text))
    exclude = set(int(p) for p in exclude_ports if str(p).isdigit())

    ports = _listening_ports()
    procs = _proc_info()
    # 先挑出"候选"（排除已注册/系统进程），再并发探测 —— 避免白探一堆系统端口
    probe_targets = []
    for port, pid in sorted(ports.items()):
        if port in registered_ports:
            continue
        name, _cmdline = procs.get(pid, ("", ""))
        if name.lower() in ("system", "system idle process", ""):
            continue
        probe_targets.append(port)
    probes = _probe_many(probe_targets, timeout=timeout) if probe else {}

    out = []
    for port in probe_targets:
        pid = ports.get(port)
        name, cmdline = procs.get(pid, ("", ""))
        is_web, evidence = probes.get(port, (False, ""))
        if probe and not is_web:
            continue                      # 不是 Web 服务，不推荐
        level, reason = _classify(
            port, name, cmdline, portal_port=portal_port,
            registered_ports=registered_ports, exclude_ports=exclude)
        out.append({
            "port": port,
            "target": "127.0.0.1:%d" % port,
            "name": _guess_name(port, name, evidence),
            "proc": name,
            "level": level,
            "reason": reason,
            "evidence": evidence,
            "kind": "web" if is_web else "unknown",
        })
    # 排序：可推荐的在前，危险的在最后（界面上危险项折叠）
    order = {"ok": 0, "caution": 1, "danger": 2}
    out.sort(key=lambda c: (order.get(c["level"], 3), c["port"]))
    return {
        "ok": True,
        "candidates": out,
        "scanned": len(ports),
        "note": "只列出本机在听、且像 HTTP 服务的端口；已注册的不再列出。"
                "标 danger 的默认不勾选，请确认后再添加。",
    }


def _guess_name(port, proc_name, evidence):
    """给候选起一个用户能认的名字（尽力而为，用户可以改）。"""
    title = ""
    if evidence and "·" in evidence:
        title = evidence.split("·", 1)[1].strip()
    if title:
        return title[:40]
    base = os.path.splitext(proc_name)[0] if proc_name else ""
    if base:
        return "%s:%d" % (base, port)
    return "端口 %d" % port
