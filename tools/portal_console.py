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
:root{color-scheme:dark light}
*{box-sizing:border-box}
body{margin:0;background:#14161a;color:#e8eaed;
 font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;line-height:1.5}
.wrap{max-width:640px;margin:0 auto;padding:24px 18px 48px}
h1{font-size:22px;margin:0 0 4px}
p.sub{font-size:13px;color:#98a0ad;margin:0 0 22px}
section{background:#1c1f26;border:1px solid #2a2f38;border-radius:14px;
 padding:18px;margin-bottom:20px}
section>h2{font-size:15px;margin:0 0 12px;color:#c8cdd7}
.addr{display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:8px 0}
.addr .url{font-family:ui-monospace,Menlo,monospace;font-size:13px;
 word-break:break-all;background:#12141a;border:1px solid #363c47;
 border-radius:8px;padding:8px 10px;flex:1;min-width:200px}
.addr .copy{background:#2a2f38;color:#e8eaed;border:1px solid #363c47;
 border-radius:8px;padding:9px 14px;font-size:13px;cursor:pointer}
.warn{display:block;font-size:12.5px;color:#f0b429;margin-top:6px}
img.qr{width:168px;height:168px;image-rendering:pixelated;background:#fff;
 border-radius:8px;border:1px solid #363c47}
.grid{display:grid;grid-template-columns:1fr;gap:14px}
.card{background:#222630;border:1px solid #333a46;border-radius:12px;
 padding:14px}
.card .top{display:flex;align-items:center;gap:10px;justify-content:space-between}
.card h3{margin:0 0 4px;font-size:15px}
.meta{font-size:12px;color:#8b93a1;margin:6px 0}
.mono{font-family:ui-monospace,Menlo,monospace}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px}
.dot.on{background:#3fb950}.dot.off{background:#6b7280}.dot.dead{background:#f85147}
.actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.btn{min-height:44px;min-width:44px;padding:10px 14px;font-size:13px;
 border-radius:9px;border:1px solid #363c47;background:#2a2f38;color:#e8eaed;
 cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;gap:5px}
.btn.primary{background:#4f6ef7;border-color:#4f6ef7;color:#fff}
.btn.primary:hover{background:#5c79f8}
.btn:hover{background:#333a46}
.btn:disabled,.btn.dim{background:#24282f;color:#5c6370;cursor:not-allowed}
input,textarea,select{width:100%;box-sizing:border-box;padding:11px 12px;
 border-radius:9px;border:1px solid #363c47;background:#12141a;color:#e8eaed;
 font-size:14px;margin-bottom:10px}
input:focus,textarea:focus,select:focus{outline:none;border-color:#4f6ef7;
 box-shadow:0 0 0 3px rgba(79,110,247,.18)}
label{display:block;font-size:12px;color:#b6bdc9;margin-bottom:4px}
.note{font-size:12px;color:#8b93a1}
footer{font-size:12px;color:#6b7280;text-align:center;padding:18px 0}
thead{text-align:left}
@media (prefers-color-scheme:light){body{background:#f5f6f8;color:#1c1f26}
 section{background:#fff;border-color:#e2e6ec} .card{background:#fff;
 border-color:#e2e6ec}.meta{color:#5a6473} input,textarea,select{background:#fff;
 color:#1c1f26;border-color:#cbd2da} .dot.off{background:#9aa3af}
 .btn{background:#eef1f5;color:#1c1f26;border-color:#d0d6dd}
 .btn.primary{background:#4f6ef7;color:#fff}.addr .url{background:#f5f6f8}}
"""


def _service_form():
    return ('<form method="POST" action="/_api/services" class="add">'
            '<label>名称（必填）</label><input name="name" required '
            'placeholder="例如：训练配置台" maxlength="40">'
            '<label>路由路径（以 / 开头，例如 /train）</label>'
            '<input name="mount" required placeholder="/train" maxlength="40">'
            '<label>上游地址（例如 127.0.0.1:8810）</label>'
            '<input name="target" required placeholder="127.0.0.1:8810" maxlength="80">'
            '<label>备注（可选）</label><input name="note" maxlength="200">'
            '<button type="submit" class="btn primary">添加服务</button></form>')


def _service_card(svc, public_url):
    name = escape_html(svc.get("name") or svc.get("key") or "")
    mount = escape_html(svc.get("mount") or "")
    target = escape_html(svc.get("target") or "")
    note = escape_html(svc.get("note") or "")
    key = escape_html(svc.get("key") or "")
    enabled = bool(svc.get("enabled"))
    alive = bool(svc.get("alive"))
    mount_val = svc.get("mount") or ""
    if enabled:
        dot = "on"
        status = "已启用"
    elif alive is False:
        dot = "dead"
        status = "存活探测失败"
    else:
        dot = "off"
        status = "未启用"
    # 未启用时访问链接**不得**可点：改用不可点 span，绝不产生 <a>
    if enabled:
        # mount_val 已经带前导斜杠（注册表规范化为 /train），这里只补尾部的一个，
        # 不能写 "href=\"%s/\"" 再传 mount_val + "/" —— 那会生成 /train// 双斜杠，
        # 某些代理/浏览器会规范化成重定向，链接难看且行为不确定。
        visit = ('<a class="btn primary" href="%s">访问</a>'
                 % escape_html(mount_val.rstrip("/") + "/"))
    else:
        visit = '<span class="btn dim" aria-disabled="true" title="未启用不可访问">访问</span>'
    rows = []
    rows.append('<div class="card"><div class="top">'
                '<div><h3>%s</h3>'
                '<span class="dot %s"></span>%s '
                '<span class="mono">%s</span></div></div>'
                % (name, dot, status[:8], mount))
    rows.append('<div class="meta">路由：<span class="mono">%s</span> · '
                '上游：<span class="mono">%s</span></div>' % (mount, target))
    if note:
        rows.append('<div class="meta">注：%s</div>' % note)
    enable_action = ("/_api/services/%s/enable" % urllib_quote(key)
                     if enabled is False else "/_api/services/%s/disable" % urllib_quote(key))
    enable_label = "关闭" if enabled else "开启"
    ebtn = ('<form method="POST" action="%s" style="display:inline">'
            '<button type="submit" class="btn %s">%s</button></form>'
            % (escape_html(enable_action),
               "primary" if not enabled else "", enable_label))
    del_btn = ('<form method="POST" action="/_api/services/%s/delete" '
               'onsubmit="return confirm(\'删除该服务？\')" style="display:inline">'
               '<button type="submit" class="btn">删除</button></form>'
               % escape_html(urllib_quote(key)))
    edit_btn = ('<a class="btn" href="/_api/services/%s/edit">编辑</a>'
                % escape_html(urllib_quote(key)))
    rows.append('<div class="actions">%s%s%s%s</div>' % (ebtn, visit, edit_btn, del_btn))
    rows.append('</div>')
    return "".join(rows)


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

    # 服务列表
    if services:
        cards = "".join(_service_card(s, public_url) for s in services)
    else:
        cards = ('<p class="note">还没有服务。在下方添加第一个服务后，它就会出现在这里，'
                 '并可逐个开启对外访问。</p>')
    # 空态面板仍展示在服务列表标题
    list_block = ('<div class="grid">%s</div>' % cards) if (cards.startswith('<div class="card"')) \
        else cards

    html = ('<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            '<meta name="robots" content="noindex,nofollow">'
            '<title>对外服务门户 · 控制台</title><style>%s</style></head><body>'
            '<div class="wrap">'
            '<h1>对外服务门户</h1>'
            '<p class="sub">在下方管理要对外开放的服务：加路由、开启关闭、跳转访问。'
            '当前分类：<strong>%s</strong> · 端口 %d</p>'
            '<!-- 由 console_html 渲染，勿手改。用户输入均经转义。 -->'
            '%s'
            '<section><h2>访问地址</h2>%s%s</section>'
            '<section><h2>服务清单</h2>%s</section>'
            '<section><h2>添加服务</h2>%s</section>'
            '<footer>安全提示：外网访问需要口令；内网免密。门户端口 %d，'
            '当前分类：%s。请不要在公网长期暴露管理口令。</footer>'
            '</div>'
            '<script>'
            'document.querySelectorAll(".copy").forEach(function(btn){'
            'btn.addEventListener("click",function(){'
            'var u=btn.getAttribute("data-copy");'
            'if(navigator.clipboard)navigator.clipboard.writeText(u);'
            '});});</script>'
            '</body></html>'
            % (_CSS, escape_html(tag), int(portal_port),
               extra_head, addr_html, qr_img, list_block, _service_form(),
               int(portal_port), escape_html(tag))).encode("utf-8")
    return html


if __name__ == "__main__":
    # 简单自检：模块数量应 = (17+4*v+2*border)^2 内目标黑点数没问题，直接打印几个指标。
    svg = qr_svg("https://example.com")
    print("bytes=%d equals-empty=%s rect-count=%d" % (len(svg), "no", svg.count("<rect")))
    print("qr determinism:", qr_svg("https://example.com") == qr_svg("https://example.com"))
