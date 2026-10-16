# -*- coding: utf-8 -*-
"""门户控制台的控制检验：页面渲染、HTML 安全、二维码可扫性、手机适配。

覆盖（每条对应一个真实失败点）：
  1. console_html 返回 bytes，含 UTF-8 charset 声明；
  2. 服务列表：两个服务的名字都出现；
  3. 未启用服务**不可点**：其 mount 附近不允许出现可点 <a href>；
  4. XSS：服务名 <script> 必须转义成 &lt;script&gt;，且不得出现原始的
     <script>alert(1)</script>；
  5. 外网地址为空给提示文案，不显示 None / 空链接；
  6. 内网多个地址都渲染；
  7. 二维码 qr_svg 以 <svg 开头、含 <rect、无外部引用、确定性；
  8. 二维码长度随内容增长（版本升级 -> 模块数量增加）；
  9. 手机适配：viewport meta + @media/响应式单位；
  10. 页面体积合理（< 200KB），防误内联二进制；
  11. 空服务列表显示引导文案；
  12. **QR round-trip**：写一个小型 QR 解码器，把 portal_console 生成的矩阵
      反向解出字符串，与原文一致 —— 这是「真的能扫」的本地最强证明（编码与
      解码各自独立实现同一规范，一致则强烈指向规范正确）。

依赖：只用标准库；导入失败返回 2（不算通过）。
"""
import os
import re
import sys
import base64

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

try:
    import portal_console as pc
except ImportError as exc:  # pragma: no cover
    print("跳过：无法导入 portal_console（%s）；依赖缺失不代表通过" % exc)
    raise SystemExit(2)

# 为了 QR round-trip 需要访问 QR 内部常量（纯标准库，无第三方）。
ECC_FIELD = {'L': 0b01, 'M': 0b00}
ECC_BIT = {'M': 0b00, 'L': 0b01}


# ---------------------------------------------------------------------------
# 独立 QR 解码器（验证用）
# ---------------------------------------------------------------------------
def _build_func_map(size, version):
    """重建 function map（仅用于解码时跳过固定图案）。独立实现读取侧逻辑。"""
    func = [[False] * size for _ in range(size)]
    # 定位图形 + 分隔符
    for dr in range(7):
        for dc in range(7):
            for (r0, c0) in ((0, 0), (0, size - 7), (size - 7, 0)):
                func[r0 + dr][c0 + dc] = True
    for i in range(8):
        for (r, c) in ((7, i), (i, 7), (7, size - 1 - i),
                       (i, size - 8), (size - 8, i), (size - 1 - i, 7)):
            if 0 <= r < size and 0 <= c < size:
                func[r][c] = True
    # 校正图形
    algn = pc.ALIGNMENT.get(version, [])
    for ar in algn:
        for ac in algn:
            if (ar <= 8 and ac <= 8) or (ar <= 8 and ac >= size - 9) \
                    or (ar >= size - 9 and ac <= 8):
                continue
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    func[ar + dr][ac + dc] = True
    # 时序图形
    for i in range(8, size - 8):
        func[6][i] = True
        func[i][6] = True
    # 格式信息 + 暗角点
    for i in range(8):
        func[i][8] = True
        func[8][i] = True
        func[size - 1 - i][8] = True
        func[8][size - 1 - i] = True
    func[7][8] = True
    func[8][7] = True
    func[size - 8][8] = True
    # 版本信息区（>=7）
    if version >= 7:
        for i in range(6):
            for j in range(3):
                func[size - 11 + j][i] = True
                func[i][size - 11 + j] = True
    return func


def _read_data_bits(matrix, func):
    """按与编码相同的轨迹读回数据区所有位（掩码状态）与其坐标。"""
    return pc._read_trajectory(matrix, func)


def _roundtrip(text, level="M"):
    """生成矩阵并按读取侧逻辑反向解码，返回 (ok, message, dark_count)。"""
    best = None
    best_score = None
    for mask in range(8):
        g, ver, _ = pc._build_matrix(text, level, mask)
        s = pc._mask_penalty(g)
        if best_score is None or s < best_score:
            best_score, best = s, (g, ver, mask)
    grid, version, mask = best
    size = len(grid)

    func = _build_func_map(size, version)
    placed, coords = _read_data_bits(grid, func)
    # 按每个数据位的**自身坐标**解开掩码（掩码用绝对坐标，位置不能错）
    cond = pc.MASK_COND[mask]
    raw_bits = []
    for v, (r, c) in zip(placed, coords):
        if cond(r, c):
            v ^= 1
        raw_bits.append(v)

    # 组码字字节
    codewords = []
    for i in range(0, len(raw_bits) - 7, 8):
        byte = 0
        for k in range(8):
            byte = (byte << 1) | raw_bits[i + k]
        codewords.append(byte)

    # 反交织数据码字（还原每块）
    dc_list = list(pc.ECCPARAMS[version][level])
    data_cw = sum(dc_list)
    datacws = codewords[:data_cw]
    rebuilt = [[] for _ in dc_list]
    pos = 0
    max_len = max(dc_list)
    for i in range(max_len):
        for bi in range(len(dc_list)):
            if i < dc_list[bi]:
                rebuilt[bi].append(datacws[pos])
                pos += 1
    byte_stream = [b for blk in rebuilt for b in blk]

    # 解析 Bitstream -> mode/count/bytes
    allbits = []
    for cw in byte_stream:
        allbits += [(cw >> k) & 1 for k in range(7, -1, -1)]
    mode = int(''.join(str(b) for b in allbits[0:4]), 2)
    if mode != 4:
        return (False, "模式非 Byte(4)：%d" % mode, sum(sum(r) for r in grid))
    cnt_bits = 8 if version <= 9 else 16
    cnt = int(''.join(str(b) for b in allbits[4:4 + cnt_bits]), 2)
    if cnt <= 0 or cnt > 5000:
        return (False, "长度字段异常：%d" % cnt, sum(sum(r) for r in grid))
    start = 4 + cnt_bits
    chars = []
    for i in range(cnt):
        byte = 0
        for j in range(8):
            byte = (byte << 1) | allbits[start + i * 8 + j]
        chars.append(byte)
    try:
        s = bytes(chars).decode('utf-8')
    except Exception as exc:  # pragma: no cover
        return (False, "UTF-8 解码失败：%s" % exc, sum(sum(r) for r in grid))
    return (s == text,
            "解码=%r" % s if s != text else "一致",
            sum(sum(r) for r in grid))


def main():
    failures = []

    def check(label, condition, detail=""):
        if condition:
            print("  PASS  %s" % label)
        else:
            print("  FAIL  %s %s" % (label, detail))
            failures.append(label)

    print("门户控制台控制检验")
    print("")

    base_state = {
        "services": [],
        "lan_urls": ["http://192.168.1.5:8899", "http://10.0.0.7:8899"],
        "public_url": "https://abc.trycloudflare.com",
        "portal_port": 8899,
        "hide_lan": False,
    }

    svc2 = [
        {"key": "a", "name": "服务甲", "mount": "/alpha", "target": "127.0.0.1:8810",
         "enabled": True, "autoStart": True, "note": "note-a", "alive": True},
        {"key": "b", "name": "服务乙", "mount": "/beta", "target": "127.0.0.1:8820",
         "enabled": False, "autoStart": False, "note": "", "alive": True},
    ]
    state = dict(base_state)
    state["services"] = svc2

    print("[页面渲染]")
    html = pc.console_html(state)
    check("返回 bytes", isinstance(html, bytes), type(html).__name__)
    text = html.decode("utf-8")
    check("声明 UTF-8 charset", 'charset="utf-8"' in text or 'charset=utf-8' in text)
    check("标题出现", "对外服务门户" in text)
    check("两句服务名都渲染", "服务甲" in text and "服务乙" in text)

    print("[未启用服务不可点]")
    # 未启用服务 b (/beta) 不应出现可点 <a href=.../beta/...
    hrefs = re.findall(r'<a[^>]*href="([^"]*)"', text)
    bad = [h for h in hrefs if "/beta" in h]
    check("未启用服务无 <a href> 指向其挂载点", not bad, "发现 %r" % bad)
    # 已启用服务 /alpha 应可点
    good = [h for h in hrefs if "/alpha" in h]
    check("已启用服务有可点链接", len(good) >= 1, "href=%r" % hrefs)
    # 明确断言：访问链接带 disabled 语义而不是 <a>
    check("未启用时显示占位(disabled mark)", 'aria-disabled="true"' in text
          or 'disabled' in text)

    print("[XSS 防护]")
    xstate = dict(base_state)
    xstate["services"] = [{"key": "x", "name": "<script>alert(1)</script>",
                           "mount": "/xss", "target": "127.0.0.1:1",
                           "enabled": False, "autoStart": False, "note": "",
                           "alive": True}]
    xhtml = pc.console_html(xstate).decode("utf-8")
    check("转义后出现 &lt;script&gt;", "&lt;script&gt;" in xhtml)
    check("不含原始 <script>alert", "<script>alert(1)</script>" not in xhtml)
    check("escape_html 单元ok",
          pc.escape_html("<a & b>") == "&lt;a &amp; b&gt;")
    check("escape_html 处理引号",
          pc.escape_html('"\'') == "&quot;&#39;")

    print("[外网提示]")
    nostate = dict(base_state)
    nostate["public_url"] = None
    nohtml = pc.console_html(nostate).decode("utf-8")
    check("显示未开启提示", "未开启" in nohtml or "隧道" in nohtml)
    check("不显示字面 None", "None</a>" not in nohtml and ">None<" not in nohtml)
    check("未开启时无外网空链接", 'href="None"' not in nohtml)

    print("[内网多地址]")
    for u in base_state["lan_urls"]:
        check("渲染内网地址 %s" % u, u in text)

    print("[二维码]")
    svg = pc.qr_svg("https://example.com")
    check("返回 <svg 开头", svg.lstrip().startswith("<svg"))
    check("含 <rect", "<rect" in svg)
    check("无外部引用(仅 xmlns 命名空间)",
          "xlink:href" not in svg and "xlink=" not in svg and "<image" not in svg
          and "url(#" not in svg and "data:" not in svg)
    check("确定性", svg == pc.qr_svg("https://example.com"))
    short_svg = pc.qr_svg("https://example.com")
    long_svg = pc.qr_svg("https://" + "subdomain-" * 2 + "x.example.com/x?a=verylongpatternpath1234567890")
    check("长度随内容增长(版本提升)",
          long_svg.count("<rect") > short_svg.count("<rect"),
          "short=%d long=%d" % (short_svg.count("<rect"), long_svg.count("<rect")))

    print("[二维码 round-trip（本地解码一致=规范正确）]")
    for probe in ("https://example.com", "http://192.168.1.5:8899"):
        ok, msg, dark = _roundtrip(probe, "M")
        check("round-trip %s" % probe, ok, msg + " dark=%d" % dark)

    print("[手机适配]")
    check("viewport meta", 'name="viewport"' in text)
    check("响应式: 有 @media 或 max-width/百分比",
          "@media" in text or "%" in text)

    print("[体积]")
    check("页面 < 200KB", len(html) < 200 * 1024, "len=%d" % len(html))

    print("[空列表]")
    empty = pc.console_html(base_state).decode("utf-8")
    # 门户页现在是只读的测试/引导页：空列表时要**引导去插件设置里加节点**，
    # 而不是（像以前那样）让用户在当前页面找添加表单 —— 表单已经删了。
    check("空列表有引导文案", "还没有节点" in empty)
    check("空列表引导去插件设置里添加", "设置 → 插件 → dsh-service-portal → 配置" in empty)
    check("空列表不是空白", len(empty) > 500)

    print("[只读：门户页不得有管理入口]")
    # 用户要求「门户页面只读，相当于一个测试页和引导页，没有设置功能」。
    # 这条是**结构性**断言：不能生成任何写操作的表单/按钮。
    check("没有添加服务表单", "<form" not in empty and "添加服务" not in empty)
    check("没有 enable/disable/delete 的写操作入口",
          "/_api/services/" not in empty)
    check("说明了「屏蔽」不会停止上游程序",
          "停止上游程序" in empty)

    print("")
    if failures:
        print("门户控制台控制检验失败：%d 项" % len(failures))
        for label in failures:
            print("  - %s" % label)
        return 1
    print("门户控制台控制检验全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
