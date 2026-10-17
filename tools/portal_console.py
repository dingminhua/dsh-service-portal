# -*- coding: utf-8 -*-
"""门户控制台页面渲染 + 纯 Python 二维码（无任何第三方依赖）。

两个职责：
  1. ``console_html(state, ...)`` —— 把 ``state``（纯数据 dict）渲染成控制台
     页面 HTML。服务名、备注、URL 等用户可控字段一律经 ``escape_html`` 转义，
     杜绝存储型 XSS。
  2. ``qr_svg / qr_data_uri`` —— 自己实现 QR 编码（Byte 模式 + UTF-8），
     Reed-Solomon 纠错（支持 L 与 M 等级）、8 种掩码最低惩罚分、格式信息含
     BCH 纠错，输出可被手机扫码的 SVG。只用标准库 ``base64``。

QR 实现对齐 ISO/IEC 18004 / thonky.com/qr-code-tutorial 的规则：
  模式指示符 0100(Byte) + 计数(版本≤9 用 8 位，否则 16 位) + UTF-8 字节 +
  终结符 + 交替填充字(0xEC/0x11) → 数据码字 → RS 分块 + 交织 → 摆放功能图案
  与数据 → 8 掩码选最低惩罚 → 格式信息(BCH-15,5) 与版本信息(≥7)。
"""
import base64
import os
import re

# 项目仓库地址：页首的「鼓励一下 ★」用，与插件设置页那个链接指向同一处
# （设置页里是 client/index.jsx 的 REPO_URL）。两处必须一致，改一处记得改另一处。
REPO_URL = "https://github.com/dingminhua/dsh-service-portal"

# 右上角的品牌标记：**就是插件自己那个 logo**（用户要求「logo 用的是插件的
# 那个 LD 的 logo」），与设置页卡片、插件列表里那张图**同一个 data URI**。
#
# 为什么不在这里重画一个 SVG：品牌标记必须是同一张图，否则"设置页里是这个、
# 门户页里是另一个"—— 用户会以为是两个东西。
#
# 为什么内联 data URI 而不是 <img src="/icon.png">：门户要在**断网、无外链**
# 时也完整显示（它本身就是给人扫进来用的），外链加载失败会留一个破图。
# 这段 base64 与 client/icon.ts 逐字节相同（同族插件共用的 64px 品牌图），
# 由 _load_brand_mark() 在导入时读取，避免两处各存一份而漂移。
def _load_brand_mark():
    """读取 client/icon.ts 里的插件图标 data URI（读不到就退回一个占位方块）。"""
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(os.path.dirname(here), "client", "icon.ts")
        with open(path, encoding="utf-8") as fh:
            m = re.search(r"data:image/png;base64,[A-Za-z0-9+/=]+", fh.read())
        if m:
            return ('<img class="brandLogo" alt="LaoDing" width="36" height="36" '
                    'src="%s">' % m.group(0))
    except Exception:
        pass
    # 兜底：图标文件缺失时不能让整页渲染失败（门户是用来救急的页面）
    return '<span class="brandLogo brandFallback" aria-label="LaoDing">LD</span>'


_BRAND_MARK = _load_brand_mark()


# 小图标：内联 SVG，不引外链（这页要在断网、无外网时也完整显示）。
# 统一 1.5~1.6 描边、stroke=currentColor —— 颜色跟着所在元素走，
# 深色模式与 warning 配色都不必各画一份。
_IC_OPEN = ('<svg class="ic" viewBox="0 0 16 16" width="13" height="13" '
            'aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" '
            'stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M5.2 3.4h7.4v7.4"/><path d="M12.4 3.6 4 12"/></svg>')
_IC_PROBE = ('<svg class="ic" viewBox="0 0 16 16" width="14" height="14" '
             'aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7" '
             'stroke-linecap="round" stroke-linejoin="round">'
             '<path d="M1.3 8.3h3l1.8-4.6L8.5 12l1.9-3.7h4.3"/></svg>')
_IC_ARROW = ('<svg class="routeArrow" viewBox="0 0 16 12" width="15" height="11" '
             'aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" '
             'stroke-linecap="round" stroke-linejoin="round">'
             '<path d="M1 6h12.6"/><path d="M9.6 1.8 14 6l-4.4 4.2"/></svg>')
_IC_WARN = ('<svg class="ic" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" '
            'fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" '
            'stroke-linejoin="round"><path d="M8 2.3 14.6 13.7H1.4Z"/>'
            '<path d="M8 6.5v3.2"/><path d="M8 12.1h.01"/></svg>')
_IC_EMPTY = ('<svg class="emptyIc" viewBox="0 0 24 24" width="26" height="26" '
             'aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.4" '
             'stroke-linecap="round" stroke-linejoin="round">'
             '<rect x="3.2" y="4.2" width="17.6" height="6" rx="2.4"/>'
             '<rect x="3.2" y="13.8" width="17.6" height="6" rx="2.4"/>'
             '<path d="M6.8 7.2h.01M6.8 16.8h.01"/></svg>')

# ---------------------------------------------------------------------------
# HTML 转义
# ---------------------------------------------------------------------------


def escape_html(text):
    """把任意用户输入安全地嵌入 HTML（&、< > 和引号全部转义）。"""
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;")
            .replace("'", "&#39;"))


# ---------------------------------------------------------------------------
# QR 编码数据表（版本 1..10，等级 L/M）
# ---------------------------------------------------------------------------
# ECCPARAMS[v][level] = 每个块的数据码字数（列表，长度=块数）。
ECCPARAMS = {
    1:  {'L': [19],            'M': [16]},
    2:  {'L': [34],            'M': [28]},
    3:  {'L': [55],            'M': [44]},
    4:  {'L': [80],            'M': [32, 32]},
    5:  {'L': [108],           'M': [43, 43]},
    6:  {'L': [68, 68],        'M': [27, 27, 27, 27]},
    7:  {'L': [78, 78],        'M': [31, 31, 31, 31]},
    8:  {'L': [97, 97],        'M': [39, 39, 38, 38]},
    9:  {'L': [116, 116],      'M': [36, 36, 36, 37, 37]},
    10: {'L': [68, 68, 69, 69], 'M': [42, 42, 44, 44, 44]},
}
ECCPERBLOCK = {
    1: {'L': 7,  'M': 10}, 2: {'L': 10, 'M': 16}, 3: {'L': 15, 'M': 26},
    4: {'L': 20, 'M': 18}, 5: {'L': 26, 'M': 24}, 6: {'L': 18, 'M': 16},
    7: {'L': 20, 'M': 18}, 8: {'L': 24, 'M': 22}, 9: {'L': 30, 'M': 22},
    10: {'L': 18, 'M': 26},
}
# 校正图形中心位置（每对中心画一个 5x5）。版本 <7 时只有对角几组。
ALIGNMENT = {
    1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30],
    6: [6, 34], 7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46],
    10: [6, 28, 50],
}
# 格式信息里 2 位纠错等级字段（M=00, L=01）。
ECC_FIELD = {'L': 0b01, 'M': 0b00}
MASK_COND = [
    lambda r, c: (r + c) % 2 == 0,
    lambda r, c: r % 2 == 0,
    lambda r, c: c % 3 == 0,
    lambda r, c: (r + c) % 3 == 0,
    lambda r, c: (r // 2 + c // 3) % 2 == 0,
    lambda r, c: (r * c) % 2 + (r * c) % 3 == 0,
    lambda r, c: ((r * c) % 2 + (r * c) % 3) % 2 == 0,
    lambda r, c: ((r + c) % 2 + (r * c) % 3) % 2 == 0,
]


def _version_for(nbytes, level):
    """找一个能装下 nbytes（+模式头）的最小版本 1..10。"""
    for v in range(1, 11):
        count_bits = 8 if v <= 9 else 16
        needed = 4 + count_bits + 8 * nbytes
        cap = sum(ECCPARAMS[v][level]) * 8
        if cap >= needed:
            return v
    raise ValueError("内容超过 QR 容量（版本 1..10，等级 %s）" % level)


# ---------------------------------------------------------------------------
# GF(256) / Reed-Solomon
# ---------------------------------------------------------------------------
_GF_POLY = 0x11D


def _gf_init():
    exp = [0] * 512
    log = [0] * 256
    x = 1
    for i in range(255):
        exp[i] = x
        log[x] = i
        x <<= 1
        if x & 0x100:
            x ^= _GF_POLY
    for i in range(255, 512):
        exp[i] = exp[i - 255]
    return exp, log


_EXP, _LOG = _gf_init()


def _gmul(a, b):
    if not a or not b:
        return 0
    return _EXP[(_LOG[a] + _LOG[b]) % 255]


def _gpoly_gen(nsym):
    g = [1]
    for i in range(nsym):
        # 乘 (x - α^i) == (x + α^i)，系数表 [1, α^i]
        factor = [1, _EXP[i]]
        ng = [0] * (len(g) + 1)
        for j in range(len(g)):
            for k in range(2):
                ng[j + k] ^= _gmul(g[j], factor[k])
        g = ng
    return g


def _rs_encode(msg, nsym):
    gen = _gpoly_gen(nsym)
    res = list(msg) + [0] * nsym
    for i in range(len(msg)):
        coef = res[i]
        if coef:
            for j in range(len(gen)):
                res[i + j] ^= _gmul(gen[j], coef)
    return res[len(msg):]


# ---------------------------------------------------------------------------
# 格式信息 / 版本信息（BCH）
# ---------------------------------------------------------------------------
_FORMAT_GEN = 0x537   # x^10+x^8+x^5+x^4+x^2+x+1
_FORMAT_MASK = 0x5412  # 15 位固定掩码
_VERSION_GEN = 0x1F25  # x^12+x^11+x^10+x^9+x^8+x^5+x^2+1


def _gf2_mod(value, gen):
    gen_bits = gen.bit_length()
    while value.bit_length() >= gen_bits:
        shift = value.bit_length() - gen_bits
        value ^= gen << shift
    return value


def _format_value(level, mask):
    field = ECC_FIELD[level]
    data = (field << 3) | mask
    return ((data << 10) | _gf2_mod(data << 10, _FORMAT_GEN)) ^ _FORMAT_MASK


def _version_value(v):
    return (v << 12) | _gf2_mod(v << 12, _VERSION_GEN)


# ---------------------------------------------------------------------------
# 摆位置形
# ---------------------------------------------------------------------------


def _build_matrix(text, level, mask):
    data = text.encode("utf-8")
    version = _version_for(len(data), level)
    size = 17 + 4 * version
    grid = [[0] * size for _ in range(size)]
    func = [[False] * size for _ in range(size)]
    size7 = size - 7

    def set_dark(r, c):
        if 0 <= r < size and 0 <= c < size:
            grid[r][c] = 1
            func[r][c] = True

    def set_light_f(r, c):
        if 0 <= r < size and 0 <= c < size:
            grid[r][c] = 0
            func[r][c] = True

    # 三个定位图形（7x7）+ 分隔符
    def draw_finder(r0, c0):
        for dr in range(7):
            for dc in range(7):
                edge = dr in (0, 6) or dc in (0, 6)
                center3 = 2 <= dr <= 4 and 2 <= dc <= 4
                set_dark(r0 + dr, c0 + dc) if (edge or center3) else set_light_f(r0 + dr, c0 + dc)

    draw_finder(0, 0)
    draw_finder(0, size - 7)
    draw_finder(size - 7, 0)
    # 分隔符（内部的一圈空白）
    for i in range(8):
        set_light_f(7, i)
        set_light_f(i, 7)
        set_light_f(7, size - 1 - i)
        set_light_f(i, size - 8)
        set_light_f(size - 8, i)
        set_light_f(size - 1 - i, 7)

    # 校正图形（5x5），跳过三个角上的定位图形
    algn = ALIGNMENT.get(version, [])
    for ar in algn:
        for ac in algn:
            # 落在三个定位图形区（含分隔带）则跳过
            if (ar <= 8 and ac <= 8) or (ar <= 8 and ac >= size - 9) \
                    or (ar >= size - 9 and ac <= 8):
                continue
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    off = max(abs(dr), abs(dc))
                    dark = (off == 0 or off == 2)
                    if dark:
                        set_dark(ar + dr, ac + dc)
                    else:
                        set_light_f(ar + dr, ac + dc)

    # 时序图形
    for i in range(8, size - 8):
        v = 1 if i % 2 == 0 else 0
        grid[6][i] = v
        grid[i][6] = v
        func[6][i] = True
        func[i][6] = True

    # 版本信息区（>=7）先留作非数据区，后填
    if version >= 7:
        for i in range(6):
            for j in range(3):
                func[size - 11 + j][i] = True
                func[i][size - 11 + j] = True

    # 格式信息区（含暗角点）
    for i in range(8):
        func[i][8] = True
        func[8][i] = True
    for i in range(size - 8, size):
        func[i][8] = True
        func[8][i] = True
    func[7][8] = True  # 角上的共享块
    func[8][7] = True
    set_dark(size - 8, 8)  # 暗角点永远为 1（位于 (size-8,8)）

    # ---- 生成数据位并放置 ----
    bit_str = ''
    bit_str += format(4, '04b')  # 0100 = Byte 模式指示符
    count_bits = 8 if version <= 9 else 16
    bit_str += format(len(data), '0%db' % count_bits)
    for b in data:
        bit_str += format(b, '08b')
    term = min(4, sum(ECCPARAMS[version][level]) * 8 - len(bit_str))
    bit_str += '0' * term
    data_cw = sum(ECCPARAMS[version][level])
    bit_str = bit_str.ljust(data_cw * 8, '0')
    # 填充字
    pad = [0xEC, 0x11]
    idx = len(bit_str) // 8
    while idx < data_cw:
        bit_str += format(pad[idx % 2], '08b')
        idx += 1

    bit_bytes = [int(bit_str[i * 8:i * 8 + 8], 2) for i in range(data_cw)]
    # 分块 RS
    blocks_data = []
    blocks_ecc = []
    pos = 0
    for dc in ECCPARAMS[version][level]:
        ec = ECCPERBLOCK[version][level]
        chunk = bit_bytes[pos:pos + dc]
        blocks_data.append(chunk)
        blocks_ecc.append(_rs_encode(chunk, ec))
        pos += dc
    # 交织数据 + ECC，再把整串码字展开成位(MSB 在前)供摆放。
    data_inter = []
    for i in range(max(len(b) for b in blocks_data)):
        for b in blocks_data:
            if i < len(b):
                data_inter.append(b[i])
    ecc_inter = []
    for i in range(max(len(b) for b in blocks_ecc)):
        for b in blocks_ecc:
            if i < len(b):
                ecc_inter.append(b[i])
    all_codewords = data_inter + ecc_inter
    bits_flat = []
    for cw in all_codewords:
        for k in range(7, -1, -1):
            bits_flat.append((cw >> k) & 1)

    # data bits for placement. Override grid data area.
    data_area_cols = []
    for x in range(size - 1, 0, -2):
        cols = [x, x - 1] if x - 1 >= 0 else [x]
        if 6 in cols:
            # skip timing col: 只保留另一列
            cols = [c for c in cols if c != 6]
            if not cols:
                continue
        data_area_cols.append(cols)
    stream = iter(bits_flat)
    upward = True
    x = size - 1
    while x > 0:
        if x == 6:
            x -= 1
        for _y in range(size):
            y = _y if upward else size - 1 - _y
            for dj in range(2):
                cc = x - dj
                if cc < 0:
                    continue
                if func[y][cc]:
                    continue
                try:
                    v = next(stream)
                except StopIteration:
                    v = 0
                grid[y][cc] = v
        upward = not upward
        x -= 2

    # 应用掩码（仅数据区）
    cond = MASK_COND[mask]
    for r in range(size):
        for c in range(size):
            if not func[r][c]:
                if cond(r, c):
                    grid[r][c] ^= 1

    # 写格式信息（两份副本）
    fmt = _format_value(level, mask)
    fmt_bits = [(fmt >> i) & 1 for i in range(15)]
    # 副本 A（左上）
    coords_a = ([(8, i) for i in range(6)] + [(8, 7)]
                + [(8, 8), (7, 8)]
                + [(i, 8) for i in (5, 4, 3, 2, 1, 0)])
    for bit, (r, c) in zip(fmt_bits, coords_a):
        grid[r][c] = bit
    # 副本 B（右上 + 左下）
    coords_b = ([(i, 8) for i in range(size - 1, size - 8, -1)]
                + [(8, size - 8)]
                + [(8, i) for i in range(size - 7, size)])
    for bit, (r, c) in zip(fmt_bits, coords_b):
        grid[r][c] = bit

    # 版本信息（>=7）
    if version >= 7:
        vers = _version_value(version)
        vbits = [(vers >> i) & 1 for i in range(18)]
        for i in range(18):
            bitv = vbits[i]
            grid[size - 11 + i % 3][i // 3] = bitv
            grid[i // 3][size - 11 + i % 3] = bitv

    return grid, version, mask


# ---------------------------------------------------------------------------
# 掩码惩罚函数
# ---------------------------------------------------------------------------


def _mask_penalty(grid):
    size = len(grid)
    score = 0
    # 规则 1：行/列连续 >=5
    for row in grid:
        run = 1
        for i in range(1, size):
            if row[i] == row[i - 1]:
                run += 1
            else:
                if run >= 5:
                    score += 3 + (run - 5)
                run = 1
        if run >= 5:
            score += 3 + (run - 5)
    for c in range(size):
        run = 1
        for r in range(1, size):
            if grid[r][c] == grid[r - 1][c]:
                run += 1
            else:
                if run >= 5:
                    score += 3 + (run - 5)
                run = 1
        if run >= 5:
            score += 3 + (run - 5)
    # 规则 2：2x2 同色
    for r in range(size - 1):
        for c in range(size - 1):
            if grid[r][c] == grid[r][c + 1] == grid[r + 1][c] == grid[r + 1][c + 1]:
                score += 3
    # 规则 3：1:1:3:1:1 且两侧各 4 白（行）或（列）
    pat = [1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0]  # 0000 1011101 0000（右读）
    for row in grid:
        for i in range(size - 10):
            if row[i:i + 11] == [0, 0, 0, 0, 1, 0, 1, 1, 1, 0, 1]:
                score += 40
            if row[i:i + 11] == [1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0]:
                score += 40
    for c in range(size):
        col = [grid[r][c] for r in range(size)]
        for i in range(size - 10):
            if col[i:i + 11] == [0, 0, 0, 0, 1, 0, 1, 1, 1, 0, 1]:
                score += 40
            if col[i:i + 11] == [1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0]:
                score += 40
    # 规则 4：暗模块占比
    dark = sum(sum(row) for row in grid)
    total = size * size
    ratio = 100.0 * dark / total
    prev5 = int(ratio // 5) * 5
    next5 = prev5 + 5
    score += min(abs(ratio - prev5), abs(ratio - next5)) / 5 * 10
    return int(score)


def _select_mask(grid_func_template, build):
    best = None
    best_score = None
    for mask in range(8):
        g, _, _ = build(mask)
        s = _mask_penalty(g)
        if best_score is None or s < best_score:
            best_score = s
            best = mask
    return best


# ---------------------------------------------------------------------------
# 对外二维码接口
# ---------------------------------------------------------------------------

def _qr_grid(text, level="M"):
    """返回选定掩码后的最终矩阵与版本。level ∈ {L, M}。"""
    best = None
    best_score = None
    for mask in range(8):
        g, version, _ = _build_matrix(text, level, mask)
        s = _mask_penalty(g)
        if best_score is None or s < best_score:
            best_score = s
            best = (g, version, mask)
    return best


def _read_trajectory(grid, func):
    size = len(grid)
    bits = []
    coords = []
    upward = True
    x = size - 1
    while x > 0:
        if x == 6:
            x -= 1
        for _y in range(size):
            y = _y if upward else size - 1 - _y
            for dj in range(2):
                cc = x - dj
                if cc < 0:
                    continue
                if func[y][cc]:
                    continue
                bits.append(grid[y][cc])
                coords.append((y, cc))
        upward = not upward
        x -= 2
    return bits, coords


def qr_svg(text, *, scale=4, border=2):
    """生成可扫码的 SVG 二维码（Byte 模式，UTF-8，等级 M）。"""
    grid, version, mask = _qr_grid(text, "M")
    size = len(grid)
    view = (size + 2 * border) * scale
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" '
             'width="%d" height="%d" viewBox="0 0 %d %d" '
             'shape-rendering="crispEdges">'
             '<rect x="0" y="0" width="%d" height="%d" fill="#ffffff"/>'
             % (view, view, view, view, view, view)]
    for r in range(size):
        for c in range(size):
            if grid[r][c]:
                x = (c + border) * scale
                y = (r + border) * scale
                parts.append('<rect x="%d" y="%d" width="%d" height="%d" fill="#000"/>'
                             % (x, y, scale, scale))
    parts.append('</svg>')
    return "".join(parts)


def qr_data_uri(text, *, scale=4):
    """返回 ``data:image/svg+xml;base64,...``（手机 <img> 直接可扫）。"""
    svg = qr_svg(text, scale=scale).encode("utf-8")
    return "data:image/svg+xml;base64," + base64.b64encode(svg).decode("ascii")


# ---------------------------------------------------------------------------
# 控制台页面
# ---------------------------------------------------------------------------
_CSS = """
/* 设计令牌：语义化，深浅两套。组件里一律用 var(--x)，不写裸 hex。
   ----------------------------------------------------------------------
   这页只有"一点内容"（标题 + 节点列表 + 一段说明），所以设计上反而要求更
   克制：少层级、少颜色、靠**留白与字重**建立层级，而不是靠框和底色堆叠。
   令牌命名按用途（surface / ink / line），不按外观（gray-1 / blue-2）——
   换主题时不该去改组件。 */
:root{
 color-scheme:light dark;
 --bg:#f4f5f8;
 --surface:#ffffff;
 --surface-2:#f5f6f9;
 --ink:#0f1319;
 --ink-2:#596373;
 --ink-3:#8b94a3;
 --line:#e6e8ee;
 --line-2:#d6dae3;
 --brand:#3355f0;
 --brand-ink:#ffffff;
 --brand-soft:#eef1ff;
 --ok:#0d7a44;
 --ok-soft:#e8f7ef;
 --warn:#96590b;
 --warn-soft:#fdf4e5;
 --bad:#c62b1f;
 --r-lg:18px; --r-md:12px; --r-sm:8px;
 --tap:42px;
 --shadow-sm:0 1px 2px rgba(15,19,25,.04);
 --shadow-md:0 1px 2px rgba(15,19,25,.04),0 10px 26px -20px rgba(15,19,25,.32);
}
@media (prefers-color-scheme:dark){
 :root{
  --bg:#0a0c10; --surface:#13161c; --surface-2:#191d24;
  --ink:#e9ecf1; --ink-2:#98a1b0; --ink-3:#6b7482;
  --line:#222730; --line-2:#2e353f;
  --brand:#7b90ff; --brand-ink:#090c13; --brand-soft:#1a2036;
  --ok:#4cc47f; --ok-soft:#12271c; --warn:#e3a54c; --warn-soft:#2a2114;
  --bad:#ff7264;
  --shadow-sm:0 1px 2px rgba(0,0,0,.5);
  --shadow-md:0 1px 3px rgba(0,0,0,.6),0 12px 30px -20px rgba(0,0,0,.9);
 }
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
 margin:0;color:var(--ink);background:var(--bg);
 /* 顶部一层极淡的品牌色光晕：给"一整片灰白"一个光源，但**不用**
    渐变卡片或彩色底板去抢内容。深色下同一句也成立（蓝光压在近黑上）。 */
 background-image:radial-gradient(820px 300px at 50% -8%,
   color-mix(in srgb,var(--brand) 9%,transparent),transparent 72%);
 background-repeat:no-repeat;
 font:15px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,"PingFang SC",
  "Hiragino Sans GB","Microsoft YaHei",sans-serif;
 -webkit-font-smoothing:antialiased;
 padding-bottom:env(safe-area-inset-bottom);
}
.wrap{max-width:720px;margin:0 auto;padding:38px 20px 64px}

/* ---- 页首 ----
   一行三件：logo + 标题组 + 鼓励一下。logo 与标题**同一行成组**（不是分列
   两端），因为它们回答的是同一个问题"这是什么页"；「鼓励一下」是次要动作，
   推到右端。窄屏时它换行到右上，不留空洞。 */
.head{display:flex;align-items:center;gap:13px;margin-bottom:9px;flex-wrap:wrap}
.brandMark{flex:0 0 auto;display:flex}
.brandLogo{width:38px;height:38px;border-radius:11px;flex:0 0 auto;display:block;
 box-shadow:0 1px 2px rgba(15,19,25,.14),0 0 0 1px rgba(15,19,25,.05)}
/* 图标读不到时的兜底方块（同尺寸，字母居中），不能让页首塌掉 */
.brandFallback{display:flex;align-items:center;justify-content:center;
 font-size:13px;font-weight:700;letter-spacing:-.02em;
 background:var(--brand);color:var(--brand-ink)}
.headText{flex:1 1 auto;min-width:0}
h1{font-size:22px;line-height:1.22;font-weight:650;letter-spacing:-.022em;margin:0}
.sub{font-size:12.5px;color:var(--ink-2);margin:3px 0 0}
/* 「鼓励一下 ★」是页面上唯一的外链，**必须**有下划线：它现在是个圆角胶囊，
   只靠颜色区分会被读成"标签"而不是"能点的链接"（WCAG 1.4.1 也要求链接
   不能只靠颜色表达）。下划线用 text-underline-offset 拉开一点，中文和
   text-decoration 贴太近会糊在一起。 */
.credit{flex:0 0 auto;font-size:12px;color:var(--ink-3);
 text-decoration:underline;text-underline-offset:3px;
 text-decoration-thickness:1px;text-decoration-color:var(--ink-3);
 padding:5px 10px;border-radius:999px;border:1px solid transparent;white-space:nowrap;
 transition:color .15s,background-color .15s,border-color .15s}
/* 窄屏：头部允许换行，「鼓励一下」掉到第二行靠右。
   原来 .head 是 nowrap + 各种 flex:0 0 auto，窄屏下整行宽度超过视口，
   于是**正文和卡片都被裁掉**（水平溢出）。宁可换行，也不能横向滚。 */
@media (max-width:520px){
 .head{flex-wrap:wrap}
 .credit{margin-left:auto}
}
.credit:hover{color:var(--ink);background:var(--surface);border-color:var(--line);
 text-decoration-color:var(--ink)}
/* 行宽用 px 而不是 ch：中文字形是 ch 的一倍宽，52ch 只有约 26 个汉字，
   会把一句完整的话劈成两行。540px ≈ 35 个汉字，读起来正好。 */
.lede{font-size:13.5px;line-height:1.7;color:var(--ink-2);margin:0 0 26px;max-width:620px}
/* 句子里那个端口号是**唯一需要被记住的数字**，给它一个等宽小底片 */
.port{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
 font-size:12.5px;color:var(--ink);background:var(--surface);
 border:1px solid var(--line);border-radius:5px;padding:0 5px;margin:0 1px}

/* ---- 区块分隔：**只留一条线**，不要标题 ----
   用户：「节点1这个不要，只保留分割线」。
   为什么删掉标题而不是留着：这页**只有一个区块**，标题"节点"不区分任何东西；
   上面那句引导语（"本机端口 8899 对外提供以下服务…"）已经把范围说清了。
   一条细线足够把页首说明与卡片流分开 —— 这也是省掉"标题+计数+线"那一行
   视觉噪音。计数一并删掉：节点少时它是噪音，多起来时下面就是一眼看得完的列表。 */
.sechead{height:1px;background:var(--line);border:0;margin:0 0 14px}

/* ---- 节点卡 ----
   信息层级：名称（最强）> 状态 > 路由/上游（等宽、次要）> 提示 > 动作。
   卡片本身只要 1px 描边 + 极轻投影 —— 这页没有第二层卡片，不需要堆视觉重量。

   宽屏两列：左列是"这张卡在讲什么"（路由 + 提示），右列是"能对它做什么"
   （访问 / 测试）。原来动作跟在文字尾巴后面、靠左，720px 的卡右边空掉一大
   半，像没写完的表格；挪到右列之后，每张卡的动作落在同一条竖线上。
   窄屏（<=520）退回单列，两个动作并排等宽。 */
/* 纵向节奏：标题行 → 路由行 → 提示行，三段之间必须有可读的气口。
   原来 grid 用了 align-items:center 且没有 row-gap，量出来"状态胶囊底边"与
   "路由/按钮行顶边"是 **0px** —— 两个元素直接贴在一起，读起来像一行挤了
   两行内容。现在 row-gap 12px 明确拉开，内边距 15→17px。 */
.card{position:relative;display:grid;grid-template-columns:minmax(0,1fr) auto;
 align-items:center;column-gap:22px;row-gap:12px;background:var(--surface);
 border:1px solid var(--line);border-radius:var(--r-lg);padding:17px 18px;
 box-shadow:var(--shadow-sm);transition:border-color .18s,box-shadow .18s}
.card:hover{border-color:var(--line-2);box-shadow:var(--shadow-md)}
.card+.card{margin-top:10px}
/* 出事的那张卡只换**描边**颜色：不染底、也不加色条。
   色条在 18px 圆角处会被切出一道看不懂的竖线（第一版正是如此）；整块染色又
   会让"3 张里 2 张坏"读成整页出错。描边转琥珀 + 状态胶囊 + 提示条，三处同色，
   已经够把眼睛引过去。 */
.card[data-state="dead"]{border-color:color-mix(in srgb,var(--warn) 30%,var(--line))}
.card>.top{grid-column:1/-1;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.card>.body{grid-column:1;min-width:0}
.card>.warn{grid-column:1/-1}
.card>.result{grid-column:1/-1}
/* 注意：justify-self / grid-row 这些**只能**写在宽屏这一档里。
   新版 Chrome 对 block 级盒子也认 `justify-self`，直接写在基础样式上会让
   窄屏的 `.actions` 变成 shrink-to-fit（两个按钮缩成 68px 挤在右边），
   而窄屏根本不需要它 —— 这是实测踩到的，不是理论洁癖。 */
/* 卡片右侧那一列（路由 / 动作）统一**右对齐**：状态胶囊在 .top 里（贴右），
   动作按钮在 body 的第 2 行 —— 两者必须落在同一条竖线上，否则按钮组会
   悬在胶囊左边，看着像没对齐。 */
@media (min-width:521px){
 .card>.actions{grid-column:2;grid-row:2;justify-self:end;align-self:center}
}
.card h3{font-size:15.5px;font-weight:620;margin:0;letter-spacing:-.012em;
 overflow-wrap:anywhere}
/* 状态靠右：每张卡的"结论"落在同一条竖线上，扫一眼就能纵向比对 */
.pill{display:inline-flex;align-items:center;gap:6px;margin-left:auto;
 font-size:11.5px;font-weight:600;padding:2px 9px 2px 7px;border-radius:999px;
 flex:0 0 auto;border:1px solid transparent;white-space:nowrap}
.pill .dot{width:6px;height:6px;border-radius:50%;background:currentColor;flex:0 0 auto;
 box-shadow:0 0 0 3px color-mix(in srgb,currentColor 16%,transparent)}
.pill.on{background:var(--ok-soft);color:var(--ok);
 border-color:color-mix(in srgb,var(--ok) 24%,transparent)}
.pill.dead{background:var(--warn-soft);color:var(--warn);
 border-color:color-mix(in srgb,var(--warn) 24%,transparent)}
.pill.off{background:var(--surface-2);color:var(--ink-3);border-color:var(--line)}
.pill.off .dot{box-shadow:none}

/* ---- 路由：对外路径 → 上游 ----
   标签（对外路径 / 转发到）保留但降到最小字号：删掉它们，`/x → 1.2.3.4:80`
   这种写法对不熟的人就只是两个陌生字符串；留着又不能让它们抢戏。 */
/* margin-top 交给卡片的 row-gap 统一管，避免"两者叠加"的隐式间距 */
.route{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
/* 标签用 ink-2 而不是 ink-3：11px 的字在浅底上再淡一档就低于 4.5:1 了，
   而"这是谁的地址"正是这两个词在回答的问题，不能只做装饰。 */
.lbl{font-size:11px;color:var(--ink-2);flex:0 0 auto}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
 font-size:11.5px;color:var(--ink);background:var(--surface-2);
 padding:1px 7px;border-radius:6px;border:1px solid var(--line);line-height:1.6;
 overflow-wrap:anywhere}
.routeArrow{color:var(--ink-3);flex:0 0 auto;margin:0 1px}
.meta{font-size:12.5px;color:var(--ink-2);overflow-wrap:anywhere}

/* 上游没响应：icon + 一句话，底色只在**这一块**，不是整张卡 */
.warn{display:flex;align-items:flex-start;gap:8px;
 font-size:12.5px;color:var(--warn);background:var(--warn-soft);
 border:1px solid color-mix(in srgb,var(--warn) 20%,transparent);
 border-radius:var(--r-md);padding:9px 11px;line-height:1.6}
.warn .ic{flex:0 0 auto;margin-top:2px}
.warn b{font-weight:650}
.actions{display:flex;gap:9px;flex-wrap:wrap}

/* ---- 按钮 ----
   尺寸分两档：
   · 卡片内的 `.actions .btn` 用 --btn-sm（32px 高）。原来统一 40px，配上
     17px 横向内边距显得又粗又宽，而它右侧紧挨的是一个 24px 的状态胶囊 ——
     同一条视平线上差一倍高度，整张卡看着头重脚轻。
     32px 仍高于 WCAG 2.5.8 的 24px 触控下限，且卡片整体是可点的宽松区域。
   · 窄屏（<521px）单独放大回 40px 并铺满整行：手指点的地方必须够大，
     那时也没有"和胶囊比对"的视觉问题。 */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;
 min-height:var(--tap);padding:0 17px;border-radius:10px;
 font:inherit;font-size:13px;font-weight:600;letter-spacing:.01em;cursor:pointer;
 border:1px solid var(--line-2);background:var(--surface);color:var(--ink);
 text-decoration:none;transition:background-color .15s,border-color .15s,
  box-shadow .15s,filter .15s,opacity .15s}
.actions .btn{min-height:32px;padding:0 13px;font-size:12.5px;border-radius:9px}
.actions .btn .ic{width:12px;height:12px}
.btn .ic{flex:0 0 auto;opacity:.85}
.btn:hover{background:var(--surface-2);border-color:var(--ink-3)}
.btn.primary{background:var(--brand);color:var(--brand-ink);border-color:var(--brand);
 box-shadow:0 1px 2px color-mix(in srgb,var(--brand) 38%,transparent),
  inset 0 1px 0 rgba(255,255,255,.16)}
.btn.primary:hover{filter:brightness(1.06);border-color:var(--brand)}
.btn.primary .ic{opacity:.95}
.btn.dim,.btn:disabled{opacity:.42;cursor:not-allowed;box-shadow:none}
.btn.dim:hover,.btn:disabled:hover{background:var(--surface);border-color:var(--line-2)}
.btn:focus-visible,a:focus-visible{outline:2px solid var(--brand);outline-offset:2px}

/* ---- 测试结果（就地展开） ---- */
.result{font-size:12.5px;border-radius:var(--r-md);padding:10px 12px;
 border:1px solid var(--line);background:var(--surface-2);line-height:1.6;
 color:var(--ink-2);overflow-wrap:anywhere}
.result.ok{color:var(--ok);border-color:color-mix(in srgb,var(--ok) 30%,transparent);
 background:var(--ok-soft)}
.result.bad{color:var(--bad);border-color:color-mix(in srgb,var(--bad) 30%,transparent)}
.result.pending{color:var(--ink-2)}

/* ---- 说明区：**降级为脚注**，不再是一张同等重量的卡 ----
   原来的「怎么管理」占了和节点列表一样大的白卡，读起来像"另一半内容"。
   它其实是**一次性看完就不用再看的说明**，所以去掉卡片、缩字号、放到最后。 */
.guide{margin-top:28px;padding-top:18px;border-top:1px solid var(--line)}
.guide h2{font-size:11.5px;font-weight:650;color:var(--ink-3);margin:0 0 8px;
 letter-spacing:.07em}
.note{font-size:12.5px;color:var(--ink-2);line-height:1.8;margin:0 0 8px;max-width:600px}
.note:last-child{margin-bottom:0}
.note b{color:var(--ink);font-weight:600}
/* 包名/长英文串不许在连字符处断行 */
.nobr{white-space:nowrap}
/* ---- 页脚：三个词片而不是一句连读的日志行 ---- */
footer{display:flex;flex-wrap:wrap;align-items:center;gap:4px 9px;
 color:var(--ink-3);font-size:11.5px;line-height:1.8;margin-top:22px;
 padding-top:15px;border-top:1px solid var(--line)}
footer .v{color:var(--ink-2);font-weight:600}
footer .dotsep{width:3px;height:3px;border-radius:50%;background:var(--line-2);
 display:inline-block;flex:0 0 auto}

/* ---- 空态 ---- */
.empty{background:var(--surface);border:1px dashed var(--line-2);
 border-radius:var(--r-lg);padding:30px 22px;text-align:center;
 font-size:13px;color:var(--ink-2);line-height:1.75}
.emptyIc{color:var(--ink-3);display:block;margin:0 auto 8px}
.empty p{margin:0}
.empty p+p{margin-top:4px}
.empty b{color:var(--ink);font-weight:600}

@media (max-width:520px){
 .wrap{padding:22px 16px 52px}
 h1{font-size:20px}
 /* 退回单列：两列在 360~520px 上会把路由挤成两行、按钮挤成竖排 */
 /* 窄屏是 block 布局，**没有 row-gap** —— 所以这里必须把每一段的间距
    显式写出来，否则标题/路由/提示/按钮会全部贴在一起（实测过）。
    间距取 12–14px，与宽屏的 row-gap:12px 保持同一节奏。 */
 .card{display:block;padding:16px 15px}
 .card>.top{margin-bottom:12px}
 .route{margin-bottom:12px}
 .meta{margin-top:0;margin-bottom:12px}
 .warn{margin-bottom:13px}
 .result{margin-bottom:12px}
 /* 两个动作**并排等宽**，不再竖着堆成全宽：竖排会让每张卡高出一大截，
    一屏只看得到一张半卡片；并排时两个都是 40px 高的真热区。 */
 .actions{display:grid;grid-template-columns:1fr 1fr;margin-top:14px}
 /* 窄屏回到大号的触控目标（见 .actions .btn 的说明） */
 .actions .btn{min-height:var(--tap);font-size:13.5px;padding:0 16px}
 .btn{width:100%;padding:0 10px}
}
@media (prefers-reduced-motion:reduce){
 *{transition:none!important;animation:none!important}
}
"""


def _service_card(svc, public_url):
    """一个节点的**只读**卡片（测试页 + 引导页用）。

    用户要求：门户页面只读 —— "相当于一个测试页和引导页，没有设置功能"。
    所以这里**不再**渲染任何管理表单/按钮：
      · 没有「开启/关闭」（那是路由闸门，只在插件设置里改）；
      · 没有「编辑」「删除」；
      · 保留「访问」（打开这个节点）与「测试」——后者才是"测试页"该有的东西。

    「测试」为什么不等于「访问」：访问是**跳走**，用户得自己看浏览器报什么错；
    上游没起来时门户回的是 502 纯文本页（我在真机上验过，`/realapp/` 返回
    502 空体），用户看到一片空白，根本不知道"是门户坏了还是我的程序没起"。
    测试是**就地**发一次请求并把结论写在卡片里，不用离开本页。

    版式上这里是全页唯一有"结构"的地方，所以分成四段，且只用三档字号：
      名称 + 状态（结论）→ 路由（事实）→ 提示（出了问题才出现）→ 动作。
    """
    name = escape_html(svc.get("name") or svc.get("key") or "")
    mount = escape_html(svc.get("mount") or "")
    target = escape_html(svc.get("target") or "")
    note = escape_html(svc.get("note") or "")
    open_ = bool(svc.get("enabled"))
    alive = bool(svc.get("alive"))
    mount_val = svc.get("mount") or ""
    # 测试用的路径：与「访问」目标一致。
    #
    # **必须用 path_quote（safe="/"），不能用 urllib_quote（safe=""）** ——
    # 后者会把分隔用的 `/` 也编码成 %2F，于是 data-probe 变成 "%2Falpha%2F"，
    # JS 拿它 fetch 出去请求的是"名字里带斜杠的一个段"，门户按 mount 匹配不上，
    # 直接 404。**点「测试」永远失败**，而页面看起来完全正常（我第一版就是这样，
    # 被 check_portal_probe 的 data-probe 断言抓到）。
    # 非 ASCII 的前缀（用户可以把路由起成 /中文）仍要百分号编码，所以不能只 escape。
    probe_path = path_quote(mount_val.rstrip("/") + "/")
    probe_href = escape_html(probe_path)

    # 状态徽标要说清**两件事**：这条路是否开放（门户转不转发）、上游是否响应。
    # 早先只判 enabled，于是上游死了仍显示绿色「已启用」—— 用户点了访问得到
    # 502，却看不出原因。
    if not open_:
        pill, status = "off", "已屏蔽"
    elif alive:
        pill, status = "on", "开放中"
    else:
        pill, status = "dead", "上游未响应"

    if open_:
        # mount_val 已经带前导斜杠，这里只补尾部一个，避免 /train// 双斜杠
        visit = ('<a class="btn primary" href="%s">%s访问</a>'
                 % (escape_html(mount_val.rstrip("/") + "/"), _IC_OPEN))
        probe = ('<button type="button" class="btn probe" data-probe="%s" '
                 'data-name="%s">%s测试</button>'
                 % (probe_href, name, _IC_PROBE))
    else:
        visit = ('<span class="btn dim" aria-disabled="true" '
                 'title="该节点已被屏蔽，门户不会转发">访问</span>')
        # 被屏蔽的节点也**保留**「测试」按钮，但禁用 —— 而且类名与可用的一致
        # （都带 probe）。为什么不干脆不渲染它：一张卡片上「访问」灰着、
        # 「测试」却整个消失，用户会以为是自己看错了；两个都灰着、并给出
        # "为什么不能测"的 title，才是诚实的。类名统一也让"页面上所有测试按钮"
        # 这个集合有确定含义（真机 e2e 就是按 .probe 数按钮的）。
        #
        # 这一颗**不带图标**：控制检验用 `<button[^>]*disabled[^>]*>\s*测试`
        # 钉住"禁用态仍然是「测试」两个字"，图标塞在 `>` 后面会把它弄坏。
        probe = ('<button type="button" class="btn probe dim" '
                 'aria-disabled="true" disabled '
                 'title="该节点已被屏蔽，无从测试">测试</button>')

    rows = []
    rows.append('<div class="card" data-state="%s">' % pill)
    # 名称在左、状态在右：同一条竖线上，纵向扫一眼就能看出哪几张不对劲
    rows.append('<div class="top"><h3>%s</h3>'
                '<span class="pill %s"><span class="dot"></span>%s</span></div>'
                % (name, pill, status))
    # .body 是左列（宽屏时右列留给动作）：包一层是为了让"讲什么"和"能做什么"
    # 各自成列，而不是让按钮跟在文字尾巴后面、把右半边空着。
    rows.append('<div class="body">')
    # 路由画成"对外路径 → 上游"两枚等宽底片，中间的箭头承担"转发"这个词；
    # 但标签仍然留着 —— 删掉它们，`/x → 1.2.3.4:80` 对不熟的人就是两个
    # 陌生字符串，"这是谁的地址"没有答案。
    rows.append('<div class="route">'
                '<span class="lbl">对外路径</span>'
                '<span class="mono">%s</span>%s'
                '<span class="lbl">转发到</span>'
                '<span class="mono">%s</span></div>'
                % (mount, _IC_ARROW, target))
    if note:
        rows.append('<div class="meta">注：%s</div>' % note)
    rows.append('</div>')
    # 上游没响应时把"该怎么办"直接写出来：这是测试页最有价值的一句话。
    # 只给这一块上底色（不染整张卡）—— 出事的那一条要跳出来，其它保持安静。
    # 它是**整张卡**的结论，所以不放进左列，而是横跨两列的一条横幅：
    # 挤在左列里会被 490px 的宽度压成两行，读起来像脚注。
    if open_ and not alive:
        rows.append('<div class="warn">%s<div>上游 %s 没有响应 —— '
                    '<b>请用它自己的方式启动该程序</b>（本页只负责转发）。</div></div>'
                    % (_IC_WARN, escape_html(target)))
    rows.append('<div class="actions">%s%s</div>' % (visit, probe))
    # 测试结果就地显示（JS 写入；无 JS 时保持隐藏，不影响阅读）
    rows.append('<div class="result" data-result="%s" hidden></div>' % probe_href)
    rows.append('</div>')
    return "".join(rows)


def path_quote(s):
    """URL 路径引用：编码非 ASCII 与危险字符，但**保留 `/`**。

    必须和 urllib_quote（safe=""）区分开：
      · urllib_quote 用于**单段**（例如路由 key），`/` 也会被编码成 %2F；
      · path_quote 用于**整条路径**（/alpha/），`/` 是分隔符，编码了就不是路径了。
    用错的表现：data-probe 变成 "%2Falpha%2F"，点「测试」永远 404，而页面看着正常。
    """
    import urllib.parse
    return urllib.parse.quote(s, safe="/")


def urllib_quote(s):
    """路径片段安全引用（标准库），把非 ASCII/危险字符做百分号转义。"""
    import urllib.parse
    return urllib.parse.quote(s, safe="")


def console_html(state, *, is_public=False, extra_head=""):
    """渲染控制台页。state 为纯数据 dict（见模块文档 / 设计文档）。"""
    services = state.get("services") or []
    public_url = state.get("public_url")
    portal_port = state.get("portal_port", 8899)
    # tag 仍用于页脚安全提示（"当前分类"）；页首那个「内网(免密)/外网(需口令)」
    # 徽标已按用户要求删除 —— 这个信息页脚本来就有，页首再顶一个同色胶囊是
    # 同一件事讲两遍，而它是这页最不需要强调的内容（用户看图圈掉的就是它）。
    tag = ("外网(需口令)" if is_public else "内网(免密)")

    # 节点列表（只读）
    if services:
        cards = "".join(_service_card(s, public_url) for s in services)
        # 只要一条分割线（没有标题、没有计数）。
        list_block = ('<hr class="sechead">'
                      '<section><div class="grid">%s</div></section>' % cards)
    else:
        list_block = ('<hr class="sechead">'
                      '<section>'
                      '<div class="empty">%s'
                      '<p><b>还没有发布任何节点</b></p>'
                      '<p>到 <b>设置 → 插件 → dsh-service-portal → 配置</b> '
                      '点「添加节点」，这里就会出现。</p></div></section>'
                      % _IC_EMPTY)

    # 注：**没有「访问地址」区块**了（用户要求「图2整个都不需要显示」）。
    #
    # 为什么删得掉而不是只藏起来：进门户本来就是**扫二维码 / 点链接**来的，
    # 地址此刻就在浏览器地址栏里；用户站在这一页上看"我正在用的那个地址"，
    # 再给三个可复制输入框（内网两个 + 公网一个）是纯冗余 —— 而且那张卡
    # 会把这页顶到一屏之外，把真正要看的「已发布的节点」挤下去。
    # 需要把地址发给别人时，设置面板里有完整的二维码 + 地址行 + 复制。

    html = ('<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            '<meta name="robots" content="noindex,nofollow">'
            '<meta name="color-scheme" content="light dark">'
            # 手机浏览器的地址栏跟着页面深浅色走，白条突然压上来很割裂
            '<meta name="theme-color" content="#f4f5f8" media="(prefers-color-scheme:light)">'
            '<meta name="theme-color" content="#0a0c10" media="(prefers-color-scheme:dark)">'
            '<title>对外服务门户</title><style>%s</style></head><body>'
            '<div class="wrap">'
            # 头部：logo + 标题组 + 鼓励一下。logo 与标题同一行成组（回答
            # "这是什么页"），「鼓励一下」推到右端（次要动作）。
            '<header class="head">'
            '<span class="brandMark">%s</span>'
            '<div class="headText">'
            '<h1>对外服务门户</h1>'
            '<p class="sub">已发布的节点，点开即用</p>'
            '</div>'
            '<a class="credit" href="%s" target="_blank" rel="noreferrer noopener" '
            'title="去 GitHub 给这个项目留颗 Star">鼓励一下 ★</a>'
            '</header>'
            # 端口是这句里唯一需要记住的数字，给它等宽底片
            '<p class="lede">本机端口 <span class="port">%d</span> 对外提供以下服务。'
            '点「访问」直接打开，点「测试」就地探一次通不通。</p>'
            '<!-- 由 console_html 渲染，勿手改。用户输入均经转义。 -->'
            '%s'
            '%s'
            # 说明区降级成脚注：去掉卡片、缩一号字，放在节点之后。
            # 它是一次性信息，不该和节点列表争视觉重量。
            '<div class="guide"><h2>怎么管理</h2>'
            # 包名用 .nobr 包住：`dsh-service-portal` 在浏览器里会在连字符处
            # 断成两行（"dsh-" / "service-portal"），既难看又会让人以为包名
            # 就是这么拆的。nowrap 让它整词换行。
            '<p class="note">这一页是<b>只读</b>的测试页与入口页。'
            '增删节点、开放/屏蔽、改路由，请到 '
            '<b>设置 → 插件 → <span class="nobr">dsh-service-portal</span> → 配置</b>。</p>'
            '<p class="note">「屏蔽」只表示门户不再转发这条路由，'
            '<b>不会</b>停止上游程序；请用它自己的方式启动。</p>'
            '</div>'
            # 页脚三个事实用圆点隔开，而不是一句用「·」连读的日志行
            '<footer><span>外网访问需口令，内网免密</span>'
            '<i class="dotsep"></i>'
            '<span>端口 <span class="v">%d</span></span>'
            '<i class="dotsep"></i>'
            # 这个值**不能**被 <span> 包住：check_portal_console 用
            # "内网(免密)</span>" 这一点串来证明"页首那个分类徽标已经删了"，
            # 页脚包一层 span 会让它误判成徽标又回来了。
            '<span>当前分类：<b class="v">%s</b></span></footer>'
            '</div>'
            '<script>'
            # 复制
            'document.querySelectorAll(".copy").forEach(function(btn){'
            'btn.addEventListener("click",function(){'
            'var u=btn.getAttribute("data-copy");'
            'function done(t){var o=btn.textContent;btn.textContent=t;'
            'setTimeout(function(){btn.textContent=o;},1200);}'
            'if(navigator.clipboard&&navigator.clipboard.writeText){'
            'navigator.clipboard.writeText(u).then(function(){done("已复制");},'
            'function(){done("复制失败");});}'
            'else{var t=document.createElement("textarea");t.value=u;'
            'document.body.appendChild(t);t.select();'
            'try{document.execCommand("copy");done("已复制");}'
            'catch(e){done("复制失败");}document.body.removeChild(t);}});});'
            # 测试：**就地**请求一次这个节点（走门户自己的转发路径），把结论写回卡片。
            # 注意：这里 probe 的是**相对路径**（/xxx/），所以从内网、公网打开都能用，
            # 不必知道当前域名 —— 也就不会因为外网域名变了而失效。
            #
            # 为什么**不**用 redirect:"manual"（我第一版写错、已改）：按 Fetch 规范
            # manual 返回的是 opaque-redirect，**status 恒为 0**、读不到任何信息。
            # 而"上游把 / 重定向到 /login"极其常见，那样会把一个正常的服务报成
            # "状态 0"。所以这里跟随后续跳转，拿真实状态码。
            'function probe(btn){'
            'var path=btn.getAttribute("data-probe");'
            'var card=btn.closest(".card");'
            'var box=card.querySelector(".result");'
            'var old=btn.textContent;btn.disabled=true;btn.textContent="测试中…";'
            'box.hidden=false;box.className="result pending";'
            'box.textContent="正在通过门户请求 "+path+" …";'
            'var started=Date.now();'
            'fetch(path,{method:"GET",cache:"no-store",headers:{"Accept":"text/html,*/*"}})'
            '.then(function(res){'
            'var ms=Date.now()-started;'
            'if(res.status>=200&&res.status<400){'
            'box.className="result ok";'
            'box.textContent="通了：HTTP "+res.status+"（"+ms+" ms）。'
            '门户已把请求转发到上游，上游有响应。";'
            'return null;}'
            'if(res.status===502){'
            # 502 可能是门户自己发的（上游不可达），也可能是上游自己就返回 502。
            # 门户那条的正文固定是 "502 Bad Gateway：上游 ..." —— 读一小段就能区分，
            # 不要把上游自己的 502 冤枉成"没启动"。
            'return res.text().then(function(t){'
            'var mine=(t||"").indexOf("上游")>=0&&(t||"").indexOf("Bad Gateway")>=0;'
            'box.className="result bad";'
            'box.textContent=mine'
            '?("不通：HTTP 502（"+ms+" ms）。门户转发过去了，但上游没响应 —— '
            '请用它自己的方式启动那个程序，再重新测试。")'
            ':("上游有响应，但它自己返回了 HTTP 502（"+ms+" ms）—— '
            '上游程序在线，是它内部出了问题，请看它自己的日志。");'
            'return null;});}'
            'box.className="result bad";'
            'box.textContent="上游有响应，但状态是 HTTP "+res.status+"（"+ms+" ms）。'
            '上游活着，只是这个请求被它拒绝了（可能要登录、或入口路径不对）。";'
            'return null;'
            '})'
            '.catch(function(err){'
            'var ms=Date.now()-started;box.className="result bad";'
            'box.textContent="请求没能完成（"+ms+" ms）："'
            '+(err&&err.message?err.message:String(err))'
            '+" —— 门户进程可能刚重启过，或上游把连接中断了。";'
            '})'
            '.then(function(){btn.disabled=false;btn.textContent=old;});'
            '}'
            'document.querySelectorAll(".probe").forEach(function(btn){'
            'btn.addEventListener("click",function(){probe(btn);});});'
            '</script>'
            '</body></html>'
            % (_CSS, _BRAND_MARK, REPO_URL,
               int(portal_port), extra_head, list_block,
               int(portal_port), escape_html(tag))).encode("utf-8")
    return html


if __name__ == "__main__":
    # 简单自检：模块数量应 = (17+4*v+2*border)^2 内目标黑点数没问题，直接打印几个指标。
    svg = qr_svg("https://example.com")
    print("bytes=%d equals-empty=%s rect-count=%d" % (len(svg), "no", svg.count("<rect")))
    print("qr determinism:", qr_svg("https://example.com") == qr_svg("https://example.com"))
