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

# 项目仓库地址：页脚的「鼓励一下 ★」用，与插件设置页那个链接指向同一处
# （设置页里是 client/index.jsx 的 REPO_URL）。两处必须一致，改一处记得改另一处。
REPO_URL = "https://github.com/dingminhua/dsh-service-portal"

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
/* 语义令牌：一处改，整页跟着变；深浅色各一套。禁止在组件里写裸 hex。 */
:root{
 color-scheme:light dark;
 --bg:#f4f5f7; --panel:#fff; --panel-2:#f8f9fb; --ink:#16181d; --ink-2:#5b6472;
 --line:#e4e7ed; --line-2:#ccd3dc; --brand:#3355f0; --brand-ink:#fff;
 --brand-soft:#eceffe; --ok:#128049; --warn:#a25e00; --bad:#cf2f24;
 --r:14px; --r-sm:10px; --tap:44px;
 --shadow:0 1px 2px rgba(16,20,28,.05),0 10px 26px -16px rgba(16,20,28,.28);
}
@media (prefers-color-scheme:dark){
 :root{--bg:#0e1014; --panel:#161920; --panel-2:#1b1f27; --ink:#e9ecf1;
  --ink-2:#98a1af; --line:#252a33; --line-2:#333a45; --brand:#7189ff;
  --brand-ink:#0a0d13; --brand-soft:#1a2240; --ok:#3fbf72; --warn:#e0a02f;
  --bad:#ff6f61; --shadow:0 1px 2px rgba(0,0,0,.45),0 12px 30px -16px rgba(0,0,0,.75);}
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font-size:15px;line-height:1.6;
 font-family:system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
 padding-bottom:env(safe-area-inset-bottom)}
.wrap{max-width:720px;margin:0 auto;padding:28px 18px 56px}
.top{display:flex;align-items:center;gap:10px;justify-content:space-between;flex-wrap:wrap}
h1{font-size:22px;margin:0;letter-spacing:-.01em}
.badge{font-size:12px;font-weight:600;padding:5px 10px;border-radius:999px;
 background:var(--brand-soft);color:var(--brand)}
p.sub{font-size:13px;color:var(--ink-2);margin:6px 0 24px}
section{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);
 padding:18px;margin-bottom:18px;box-shadow:var(--shadow)}
section>h2{font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;
 color:var(--ink-2);margin:0 0 14px}
.addr{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:5px 0}
.addr .url{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
 font-size:13px;word-break:break-all;background:var(--panel-2);
 border:1px solid var(--line-2);border-radius:var(--r-sm);padding:11px 12px;
 flex:1;min-width:170px}
button,.btn{font:inherit;font-size:14px;min-height:var(--tap);border-radius:var(--r-sm);
 border:1px solid var(--line-2);background:var(--panel-2);color:var(--ink);
 padding:10px 16px;cursor:pointer;text-decoration:none;display:inline-flex;
 align-items:center;justify-content:center;gap:6px;
 transition:background .15s ease,border-color .15s ease,transform .12s ease}
button:hover,.btn:hover{border-color:var(--ink-2);background:var(--panel)}
button:active,.btn:active{transform:translateY(1px)}
:focus-visible{outline:2px solid var(--brand);outline-offset:2px}
button[disabled],.btn.dim{opacity:.5;cursor:not-allowed;transform:none}
.btn.primary{background:var(--brand);border-color:var(--brand);color:var(--brand-ink)}
.btn.primary:hover{background:var(--brand);filter:brightness(1.08)}
.copy{font-size:13px;padding:10px 14px}
.qr{display:block;width:172px;height:172px;image-rendering:pixelated;background:#fff;
 border:1px solid var(--line-2);border-radius:var(--r-sm);margin-top:12px}
.grid{display:grid;grid-template-columns:1fr;gap:14px}
.card{background:var(--panel-2);border:1px solid var(--line);border-radius:var(--r-sm);
 padding:15px}
.card h3{margin:0;font-size:15px}
.card .top{justify-content:flex-start}
.pill{font-size:12px;padding:3px 9px;border-radius:999px;background:var(--panel);
 border:1px solid var(--line-2);color:var(--ink-2);white-space:nowrap}
.pill.on{color:var(--ok);border-color:currentColor}
.pill.dead{color:var(--warn);border-color:currentColor}
.pill.off{color:var(--ink-2)}
.meta{font-size:12.5px;color:var(--ink-2);margin:8px 0}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.warn{display:block;font-size:12.5px;color:var(--warn);margin-top:8px;line-height:1.55}
.actions{display:flex;flex-wrap:wrap;gap:10px;margin-top:14px}
.result{margin-top:10px;font-size:12.5px;border-radius:var(--r-sm);padding:10px 12px;
 border:1px solid var(--line-2);background:var(--panel);line-height:1.55}
.result.ok{color:var(--ok);border-color:currentColor}
.result.bad{color:var(--bad);border-color:currentColor}
.result.pending{color:var(--ink-2)}
.note{font-size:12.5px;color:var(--ink-2)}
footer{color:var(--ink-2);font-size:12px;text-align:center;padding:6px 0 0;line-height:1.7}
footer a{color:inherit}
.credit{display:inline-block;margin-top:6px;color:var(--ink-2);font-size:12.5px}
.credit:hover{color:var(--ink)}
@media (max-width:420px){
 .wrap{padding:20px 14px 44px}
 .qr{width:140px;height:140px}
 section{padding:14px}
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
        visit = ('<a class="btn primary" href="%s">访问</a>'
                 % escape_html(mount_val.rstrip("/") + "/"))
        probe = ('<button type="button" class="btn probe" data-probe="%s" '
                 'data-name="%s">测试</button>' % (probe_href, name))
    else:
        visit = ('<span class="btn dim" aria-disabled="true" '
                 'title="该节点已被屏蔽，门户不会转发">访问</span>')
        # 被屏蔽的节点也**保留**「测试」按钮，但禁用 —— 而且类名与可用的一致
        # （都带 probe）。为什么不干脆不渲染它：一张卡片上「访问」灰着、
        # 「测试」却整个消失，用户会以为是自己看错了；两个都灰着、并给出
        # "为什么不能测"的 title，才是诚实的。类名统一也让"页面上所有测试按钮"
        # 这个集合有确定含义（真机 e2e 就是按 .probe 数按钮的）。
        probe = ('<button type="button" class="btn probe dim" '
                 'aria-disabled="true" disabled '
                 'title="该节点已被屏蔽，无从测试">测试</button>')

    rows = []
    rows.append('<div class="card"><div class="top">'
                '<h3>%s</h3>'
                '<span class="pill %s">%s</span>'
                '</div>'
                % (name, pill, status))
    rows.append('<div class="meta">对外路径：<span class="mono">%s</span> · '
                '转发到：<span class="mono">%s</span></div>' % (mount, target))
    if note:
        rows.append('<div class="meta">注：%s</div>' % note)
    # 上游没响应时把"该怎么办"直接写出来：这是测试页最有价值的一句话
    if open_ and not alive:
        rows.append('<div class="warn">上游 %s 没有响应 —— 请用它自己的方式'
                    '启动该程序（本页只负责转发）。</div>'
                    % escape_html(target))
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
    lan_urls = state.get("lan_urls") or []
    public_url = state.get("public_url")
    portal_port = state.get("portal_port", 8899)
    hide_lan = state.get("hide_lan", False)
    tag = ("外网(需口令)" if is_public else "内网(免密)")

    # 访问地址区
    addr_items = []
    if lan_urls and not hide_lan:
        for u in lan_urls:
            addr_items.append(
                '<div class="addr"><span class="url">%s</span>'
                '<button type="button" class="copy" data-copy="%s">复制</button></div>'
                % (escape_html(u), escape_html(u)))
    elif hide_lan and lan_urls:
        addr_items.append('<span class="note">内网地址已隐藏（本机登录后可见）</span>')
    if public_url:
        addr_items.append(
            '<div class="addr"><span class="url">%s</span>'
            '<button type="button" class="copy" data-copy="%s">复制</button></div>'
            % (escape_html(public_url), escape_html(public_url)))
    else:
        addr_items.append(
            '<span class="warn">外网地址未开启：需要先建隧道（cloudflared），本区域会自动出现可扫码的外网链接。</span>')
    addr_html = "".join(addr_items)

    qr_target = public_url or (lan_urls[0] if lan_urls else "")
    if qr_target:
        qr_img = '<img class="qr" src="%s" alt="二维码">' % (qr_data_uri(qr_target),)
    else:
        qr_img = '<p class="note">暂无地址，未生成二维码。</p>'

    # 节点列表（只读）
    if services:
        cards = "".join(_service_card(s, public_url) for s in services)
    else:
        cards = ('<p class="note">还没有节点。到 DSH 的'
                 '「设置 → 插件 → dsh-service-portal → 配置」里'
                 '点「添加节点」把本机的一个端口发布出来，这里就会列出来。</p>')
    # 空态面板仍展示在服务列表标题
    list_block = ('<div class="grid">%s</div>' % cards) if (cards.startswith('<div class="card"')) \
        else cards

    html = ('<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            '<meta name="robots" content="noindex,nofollow">'
            '<title>对外服务门户</title><style>%s</style></head><body>'
            '<div class="wrap">'
            '<div class="top"><h1>对外服务门户</h1>'
            '<span class="badge">%s</span></div>'
            '<p class="sub">这里能打开本机已发布的节点，也能就地测每个节点通不通。'
            '端口 %d</p>'
            '<!-- 由 console_html 渲染，勿手改。用户输入均经转义。 -->'
            '%s'
            '<section><h2>访问地址</h2>%s%s</section>'
            '<section><h2>已发布的节点</h2>%s</section>'
            '<section><h2>怎么管理</h2>'
            '<p class="note">这个页面是<b>只读</b>的测试页与入口页：点「测试」就地看每个'
            '节点通不通，点「访问」直接打开它。<br>'
            '要<b>添加节点、开放或屏蔽、改路由</b>，请到 DSH 里打开'
            '<b>设置 → 插件 → dsh-service-portal → 配置</b>'
            ' —— 那里是唯一的设置入口。</p>'
            '<p class="note">「屏蔽」只表示门户不再转发这条路由，'
            '<b>不会</b>停止上游程序；上游请用它自己的方式启动。</p>'
            '</section>'
            '<footer>安全提示：外网访问需要口令；内网免密。门户端口 %d，'
            '当前分类：%s。请不要在公网长期暴露管理口令。<br>'
            '<a class="credit" href="%s" target="_blank" rel="noreferrer noopener" '
            'title="去 GitHub 给这个项目留颗 Star">鼓励一下 ★</a></footer>'
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
            % (_CSS, escape_html(tag), int(portal_port),
               extra_head, addr_html, qr_img, list_block,
               int(portal_port), escape_html(tag), REPO_URL)).encode("utf-8")
    return html


if __name__ == "__main__":
    # 简单自检：模块数量应 = (17+4*v+2*border)^2 内目标黑点数没问题，直接打印几个指标。
    svg = qr_svg("https://example.com")
    print("bytes=%d equals-empty=%s rect-count=%d" % (len(svg), "no", svg.count("<rect")))
    print("qr determinism:", qr_svg("https://example.com") == qr_svg("https://example.com"))
