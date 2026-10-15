# -*- coding: utf-8 -*-
"""局域网地址探测：按网卡性质评分选出**手机最可能连得上**的那个 IPv4。

为什么需要评分（这是实测教训，参考 dsh-pocket 的做法）：
`os.networkInterfaces()` / `getaddrinfo()` 的枚举顺序**不可靠**。Windows 上
Radmin VPN、Tailscale、vEthernet (WSL/Hyper-V)、Docker 等虚拟网卡经常排在
WLAN 前面。老实现「取第一个非回环私网地址」会拿到 `198.18.0.1`（Radmin VPN）
这种**手机根本连不上**的地址，生成一张扫了打不开的二维码 ——
用户看到的现象就是「扫码失败 / 打开超时」。

评分规则：
  · RFC1918 私网地址（10/8、172.16/12、192.168/16）优先 +100；
  · 网卡名像物理网卡（WLAN / Wi-Fi / 以太网 / en / eth / wlp）再 +20；
  · 网卡名像 VPN / 虚拟网卡（radmin / tailscale / zerotier / tun / tap /
    vEthernet / vmware / virtualbox / docker / wsl / hyper）**减 50**；
  · 同分保持原枚举顺序（稳定）。
没有任何私网地址时回退到最高分地址（例如纯 VPN 环境仍可用）。

另外单独把「198.18.0.0/15」标出来：这是 RFC 2544 基准测试网段，Radmin VPN
默认就用它，**不是**真正可路由的私网地址，绝不该拿它当内网访问地址。
"""
import ipaddress
import socket

# 名称像真实物理网卡
PHYSICAL_IFACE_RE = (
    "wlan", "wi-fi", "wifi", "wireless", "ethernet", "本地连接", "以太网",
    "无线", "有线",
)
# 名称像 VPN / 虚拟网卡（手机通常连不上）
VIRTUAL_IFACE_RE = (
    "radmin", "tailscale", "zerotier", "easytier", "et_", "tun", "tap", "vpn",
    "vethernet", "virtual", "vmware", "virtualbox", "docker", "wsl",
    "hyper-v", "loopback", "bluetooth", "蓝汛",
)
# RFC 2544 基准测试网段：Radmin VPN 等虚拟网卡的默认段，**不是**可达内网地址
BENCHMARK_NETS = (ipaddress.ip_network("198.18.0.0/15"),)


def is_benchmark_ip(ip):
    """198.18.0.0/15 —— 测速/虚拟网卡专用段，手机连不上。"""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in BENCHMARK_NETS)


def _score(name, ip):
    """给一个 (网卡名, IPv4) 打分。分越高越可能是手机可达地址。"""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None
    if addr.is_loopback or addr.is_link_local:
        return None
    score = 0
    if addr.is_private and not is_benchmark_ip(ip):
        score += 100
    # 基准网段（198.18.x）明确减分：它 is_private 为真，但不可达
    if is_benchmark_ip(ip):
        score -= 200
    lower = (name or "").lower()
    if any(token in lower for token in PHYSICAL_IFACE_RE):
        score += 20
    elif any(token in lower for token in VIRTUAL_IFACE_RE):
        score -= 50
    return score


def _iter_ipv4():
    """枚举本机 IPv4 与对应网卡名：{(ip, name)}（顺序保留）。"""
    seen = []
    # 主路由探测：连一个外部地址（不发数据）拿默认出口的本机 IP
    # —— 这通常就是真正能上外网的那张网卡
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(0.4)
            sock.connect(("8.8.8.8", 80))
            seen.append((sock.getsockname()[0], "__default_route__"))
    except OSError:
        pass

    names = {}          # ip -> 网卡名
    try:
        import psutil
        for name, addrs in (psutil.net_if_addrs() or {}).items():
            for addr in addrs:
                if getattr(addr, "family", None) == socket.AF_INET:
                    names.setdefault(addr.address, name)
    except Exception:
        pass

    if not names:
        # 没有 psutil 时退回到主机名解析（拿不到网卡名，评分只能靠网段）
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None,
                                           socket.AF_INET):
                names.setdefault(info[4][0], "")
        except OSError:
            pass

    for ip, name in names.items():
        if not any(ip == existing[0] for existing in seen):
            seen.append((ip, name))
    return seen


def detect_lan_candidates():
    """所有候选内网地址，**按评分从高到低**（第一个是推荐给用户扫码的）。"""
    scored = []
    for index, (ip, name) in enumerate(_iter_ipv4()):
        score = _score(name, ip)
        if score is None:
            continue
        # 默认出口那条加一点分：它确实能上外网
        if name == "__default_route__":
            score += 10
        scored.append({"ip": ip, "name": name if name != "__default_route__" else "",
                       "score": score, "order": index})
    scored.sort(key=lambda item: (-item["score"], item["order"]))
    # 去重（同一 IP 可能被两条路径枚举到），保留首个（分最高的那条）
    out = []
    seen = set()
    for item in scored:
        if item["ip"] in seen:
            continue
        seen.add(item["ip"])
        out.append(item)
    return out


def detect_lan_ips():
    """内网地址列表，最优的排最前（保持向后兼容：返回 IP 字符串列表）。"""
    return [item["ip"] for item in detect_lan_candidates()]


def best_lan_ip():
    """最推荐的单个内网地址（没有则 None）。"""
    candidates = detect_lan_candidates()
    return candidates[0]["ip"] if candidates else None
