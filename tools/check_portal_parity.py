# -*- coding: utf-8 -*-
"""设置页三处对齐 dsh-pocket 的控制检验（源码级 + 数据链）。

用户指出的三处差异：
  ① 右上角缺「开发者 / 求颗 Star」鼓励区
  ② 局域网缺独立的随机/自定义口令（原来是公网口令）
  ③ 「自动设置」（手动选地址）没效果

这个检验钉住实现，防止以后被改回去。
"""
import io
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
results = []


def check(label, cond, detail=""):
    results.append(bool(cond))
    print("%s  %s %s" % ("PASS" if cond else "FAIL", label, detail))


def read(path):
    return io.open(os.path.join(ROOT, path), encoding="utf-8").read()


def main():
    client = read("client/index.jsx")
    host = read("lib/index.js")
    run = read("tools/portal_run.py")
    proxy = read("tools/portal_proxy.py")
    login = read("tools/portal_login.py")

    # ================= ① 右上角鼓励区 =================
    # 用户最终指定的形态：**就三个字 + 一个星**，灰色下划线短链接。
    # 这里断言的是这个最终形态 —— 别再扩写文案、别再改成品牌色。
    print("[① 右上角「鼓励一下 ★」]")
    check("有仓库地址常量", "const REPO_URL =" in client)
    check("文案就是「鼓励一下 ★」", '"鼓励一下 ★"' in client)
    check("是可点链接（指向仓库，新窗口打开）",
          "href: REPO_URL" in client and 'target: "_blank"' in client
          and '"noreferrer"' in client,
          "（dsh-pocket 也是 <a>，不是纯文字）")
    check("区块在标题行内（不是页面底部）",
          0 < client.index('}, "鼓励一下 ★"),')
          - client.index('key: "head"') < 900,
          "（距离标题行 900 字符内）")
    # 灰色 + 下划线（用户要的是低调灰，不要品牌蓝）。
    # 注意：这里原来钉的是 `var(--dsw-alias-label-tertiary,#8b93a1)` —— 而那个
    # 令牌**根本不存在**，等于一直在吃写死的灰。现在改用真实令牌 label-secondary，
    # 所以这条断言改成看"意图"（灰 + 下划线 + 不是品牌蓝），不再绑具体令牌名。
    check("灰色（非品牌蓝）+ 下划线（与截图一致）",
          'color: COLOR.textMuted' in client
          and 'textDecoration: "underline"' in client
          and "creditLink" in client,
          "（不要品牌蓝 —— 用户要的是低调灰）")
    check("没有长鼓励文案残留",
          "顺手留颗 Star" not in client and "高兴一整天" not in client
          and "给你一颗 Star" not in client and "开发者：" not in client,
          "（用户三次要求精简，别再加回去）")
    check("没有多行容器样式残留（credit / creditLine 已清理）",
          "creditLine" not in client and "styles.credit," not in client)
    check("链接不换行不压缩（窄面板下不被挤掉）",
          'whiteSpace: "nowrap"' in client and "flexShrink: 0" in client)
    check("外链带 rel=noreferrer（防 window.opener 泄漏）",
          '"noreferrer"' in client)
    check("有 title 提示（短文案也能让人知道点了做什么）",
          'title: "去 GitHub' in client)

    # ---- 访问地址：二维码 + 可复制，两条路都要在 ----
    # 用户先说「不要二维码了，地址可复制」，随后改口「还是恢复之前的二维码吧」。
    # 最终形态 = 二维码 + 地址 + 复制按钮：扫码适合当面把手机接过去，
    # 复制适合把地址贴进聊天窗发人。两条路对应不同场景，都留着。
    print("\n[访问地址：二维码 + 复制按钮]")
    check("局域网二维码还在", "局域网二维码" in client and "qrs[lanPrimary]" in client)
    check("公网二维码还在", "公网二维码" in client and "qrs[publicUrl]" in client)
    check("地址有复制按钮（局域网）",
          'copyText("lan", lanPrimary)' in client)
    check("地址有复制按钮（公网）",
          'copyText("public", publicUrl)' in client)
    check("复制后有「已复制」反馈（不是点了没反应）",
          'copied === "lan" ? "已复制"' in client
          and 'copied === "public" ? "已复制"' in client)
    check("剪贴板不可用时有兜底（内网 http 非安全上下文会没有 clipboard API）",
          "execCommand" in client and "fallbackCopy" in client,
          "（没有兜底时按钮点了会静默失效）")
    check("地址行样式 addrRow 在（长 URL 可换行、按钮不被挤走）",
          "addrRow:" in client and 'flexWrap: "wrap"' in client)

    # ---- 未启动状态：不能乱（用户：「初始未开启的状态很乱，感觉没有逻辑」）----
    #
    # 截图里的三处硬伤：
    #   1. 「启动于 01:39:42」出现在"已停止"旁边 —— 自相矛盾
    #   2. 一个**点不动**的「开启公网访问」按钮顶在最上面，看着像主操作
    #   3. 全局看不到局域网地址（整块在 if (running) 里），只能看到一个红字报错
    print("\n[未启动状态：逻辑要通]")
    check("「启动于」只在运行中显示（停着的时候显示它是自相矛盾）",
          "running && status && status.startedAt" in client
          and "status && status.startedAt" in client,
          "（原来是无条件显示）")
    check("未启动有专门的引导块（说明 + 将用地址 + 启动按钮）",
          '"门户未启动"' in client and "启动后会使用这些地址" in client)
    check("未启动时公网区块**不放按钮**（那个按钮点不动）",
          ": running\n        ? h(\"button\"" in client
          or "running\n        ? h(" in client,
          "（原来公网按钮 disabled=!running，等于死按钮）")
    check("未启动时明确说明「启动后可开公网」",
          "门户未启动。启动后可以再开一个公网地址" in client)
    check("未启动时有「还没探测过网卡地址」的兜底文案（首次使用）",
          "还没探测过网卡地址" in client)
    check("启动按钮在未启动引导块里（不再散落在页面下方）",
          "启动（只内网）" in client and "启动并开公网" in client)
    check("运行中**能停**门户（原来只有 doStop 死代码，启停不对称）",
          'onClick: doStop' in client and '"停止门户"' in client,
          "（以前面板只能开不能关）")
    check("未启动时 problem 是普通说明（不是红字报警）",
          "running ? styles.warn : styles.muted" in client
          and "key: \"prob\"" in client,
          "（用户自己停的也算正常状态）")
    check("未启动时不显示「拿到口令的人可以…」警示（还轮不到）",
          # 现在警示按**实际状态**出现，且公网风险已合并进「公网访问」区块
          # （用户管理公网的地方），页尾只留"局域网免密"这一条跨区块的全局提示。
          # 断言它的守卫与去重：底部只在 running && 免密 时出现，且不重复提公网。
          client.count("拿到口令的人可以启停你开放的服务") == 1
          and "if (running && lanAuth === false) {" in client
          and "公网暴露风险" in client)
    check("停止失败要报出来（宿主回 ok:false + stderr 时不能静默）",
          'if (r && r.ok === false)' in client
          and "没能停止门户" in client,
          "（否则点了停止没反应，用户以为点错了）")
    check("停止后一律重新拉状态（不信返回里的状态快照）",
          "await load();" in client
          and "// 一律重新拉状态" in client)

    # ---- 排版：字号只能来自统一刻度，颜色只能用**真实存在**的主题令牌 ----
    #
    # 用户反馈「设置页面的字大大小小，样式难看」。查出来两个原因：
    #   1. 字号从参考对象那儿一并抄了：面板里混着 11/12/13/14 四种，而相邻级差
    #      只有 1px —— 看不出层级，只觉得忽大忽小；
    #   2. 用了 4 个**不存在**的 --dsw-alias-* 令牌，它们永远不命中，于是一直
    #      吃写死的浅色兜底：深色模式下文字和按钮就变成了浅色主题的颜色。
    print("\n[排版：统一字号刻度 + 只用真实令牌]")
    import re as _re

    # 真实令牌清单来自宿主主题（cordis inspect Theme.listTokens），写死在这里做守卫：
    # 以后谁再引用不存在的令牌，这条会拦下来。
    real_tokens = {
        "--dsw-alias-bg-base", "--dsw-alias-bg-layer-1", "--dsw-alias-bg-layer-2",
        "--dsw-alias-bg-overlay", "--dsw-alias-border-l1", "--dsw-alias-border-l2",
        "--dsw-alias-brand-primary", "--dsw-alias-label-primary",
        "--dsw-alias-label-secondary", "--dsw-alias-state-error-primary",
        "--dsw-alias-state-idle-primary", "--dsw-alias-state-success-primary",
        "--dsw-alias-state-warn-primary", "--dsw-specific-sidebar-fill",
    }
    used_tokens = set(_re.findall(r"var\((--dsw-[a-z0-9-]+)", client))
    fake = sorted(used_tokens - real_tokens)
    check("只引用真实存在的主题令牌（不存在的会静默吃浅色兜底）",
          not fake, "可疑令牌=%r" % (fake,))
    # 已知曾经踩过的四个，单独钉一遍（含"别名"写法，防止换个名字又混进来）
    for gone in ("--dsw-alias-label-tertiary", "--dsw-alias-state-warning-primary",
                 "--dsw-alias-button-primary-fill",
                 "--dsw-alias-label-primary-foreground"):
        check("假令牌 %s 不再出现" % gone, gone not in client)

    # 字号刻度：只允许 TYPE.*（刻度本身定义在 TYPE 里）
    raw_sizes = _re.findall(r"fontSize:\s*(\d+)", client)
    check("没有裸的数字字号（只能从 TYPE 刻度取）",
          not raw_sizes, "裸字号=%r" % (raw_sizes,))
    check("刻度是 4 级且单调（16/14/13/12）",
          _re.search(r"title:\s*16[\s\S]{0,80}section:\s*14[\s\S]{0,80}"
                     r"body:\s*13[\s\S]{0,80}caption:\s*12", client) is not None)
    check("说明文字不小于 12（再小在缩放屏上会糊）",
          "caption: 12" in client)
    check("用 COLOR.* 统一取色（不再逐屏硬编码 hex）",
          "const COLOR = {" in client
          and client.count("rgba(22,163,74") == 0
          and client.count("rgba(107,114,128") == 0)
    check("间距用 SPACE 刻度，行内不写裸 marginTop 数字",
          "const SPACE = {" in client
          and not _re.search(r"marginTop:\s*\d", client),
          "裸间距=%r" % (_re.findall(r"marginTop:\s*\d+", client),))

    # ---- 标题：本插件的身份文案，**不能照抄参考对象** ----
    # 踩过的坑：对齐 dsh-pocket 那轮把标题也一起抄了（「对外服务门户」→「手机访问」），
    # 副标题也换成了它的「实时同步」。用户一眼看出不对。
    # 「对齐能力」≠「替换身份」：dsh-pocket 叫「手机访问」是因为它整个插件的使命
    # 就是手机访问；我们是「把本机服务对外发布并统一管理」，扫码只是入口之一。
    print("\n[标题：本插件身份，不照抄参考对象]")
    check("标题是「对外服务门户」", '"对外服务门户"' in client)
    check("标题**不是** dsh-pocket 的「手机访问」",
          'styles.title }, "手机访问"' not in client,
          "（这是踩过的坑，别再抄）")
    check("副标题说明本插件的用途（管理要开放的服务）",
          "在那里管理要开放的服务" in client)
    check("副标题**不是** dsh-pocket 的「实时同步」",
          "实时同步" not in client)
    check("标题文案统一（面板内多处一致）",
          client.count('"对外服务门户"') >= 2,
          "出现次数=%d" % client.count('"对外服务门户"'))

    # ================= ①b 注册位置：插件页，不是宿主设置导航 =================
    #
    # 用户要求：「插件设置要放到插件设置里，而不是出现在宿主的设置里，
    # 你看看 workbuddy 是怎么做的」。
    #
    # 实测（cordis_inspect Slots）：
    #   · `settings.section` 的 occupants 里原先有 `service-portal`，
    #     也就是说它出现在**宿主设置左侧导航**（和通用/模型/插件并列）；
    #   · workbuddy / dsh-subagent-default-model **完全不用** settings.section，
    #     只注册 `plugins.bundle.config` 与 `plugins.row.config`。
    print("\n[①b 注册在插件页的插件配置里，不在宿主设置导航]")
    check("**不再**注册 settings.section",
          'inject("settings.section"' not in client
          and 'name: "settings.section"' not in client)
    check("注册到 plugins.bundle.config（插件自己的配置区）",
          'plugins.bundle.config' in client)
    check("注册到 plugins.row.config（行入口的配置页）",
          'plugins.row.config' in client)
    check("键按 `<包名>#<行 id>` 拼（行入口的 keyDomain 就要求这个形状）",
          "`${key}#${key}`" in client or "#${key}" in client)
    check("两种包名拼写都注册（裸名 + include: 前缀）",
          "CARD_KEYS" in client and "include:${PKG}" in client,
          "（只注册裸名会让 include: 挂载下**整页空白且不报错**）")
    check("一次注册失败不影响另一个（每个槽位独立 try/catch）",
          "槽位" in client and "注册失败" in client)
    check("**不把 settingsScope 列进 inject**（0.1.7+ 已移除，"
          "硬依赖会导致 apply 永不执行）",
          '"settingsScope"' not in client.split("const inject")[1].split(";")[0]
          if "const inject" in client else True)
    check("处理 view='summary'（插件页折叠态要有一行摘要，不能是空壳）",
          '"summary"' in client and "view ===" in client)

    # ================= ② 局域网口令独立 =================
    print("\n[② 局域网口令：随机 + 自定义，与公网分开]")
    check("后端有局域网随机口令生成器（数字，便于手机输入）",
          "def gen_lan_password" in login and 'secrets.choice("0123456789")' in login)
    check("后端有自定义局域网口令的校验（6–12 位数字）",
          "def validate_lan_pin" in login and "LAN_PIN_MIN" in login
          and "LAN_PIN_MAX" in login)
    check("拒绝非数字（手机手输场景，允许字母只会让人输错）",
          "只能是数字" in login)
    check("门户有刷新接口",
          'route == "/lan-pin/refresh"' in run)
    check("门户有自定义接口",
          'route == "/lan-pin/custom"' in run)
    check("刷新后标记为非自定义（回到自动轮换）",
          '"lan_pin_custom"] = False' in run)
    check("自定义后打标记（开启公网不再自动换）",
          '"lan_pin_custom"] = True' in run)
    check("局域网口令落盘（重启后延续）",
          'st["lan_password"]' in run)
    check("认证层优先用动态 provider（改完立即生效，不重启门户）",
          "lan_password_provider" in proxy and "def _lan_password" in proxy)
    check("按来源选口令：内网用局域网口令、公网用公网口令",
          'kind in ("loopback", "lan") and lan_pin' in proxy)
    check("公网**不能**用局域网口令（安全边界）",
          # 原来是钉字面量 `expected = self.password`；现在公网口令走 _password()
          # 动态取（为了自定义后立即生效）。断言改成**语义**：公网分支取的必须是
          # 公网口令，而不是局域网那条。
          "expected = self._password()" in proxy and "self._password()" in proxy)
    check("启动时恢复上次的局域网口令（不是每次重启都换）",
          'saved.get("lan_password")' in run or '_saved_pw.get("lan_password")' in run)
    check("宿主把 lanPassword / lanPinCustom 透给设置页",
          "lanPassword: state.lan_password" in host
          and "lanPinCustom: Boolean(state.lan_pin_custom)" in host)
    check("宿主有 /lan-pin/refresh 与 /lan-pin/custom 路由",
          'route === "/lan-pin/refresh"' in host
          and 'route === "/lan-pin/custom"' in host)
    check("宿主是**转发**给门户进程（不是自己改 —— 否则两处真相）",
          "postPortalJson" in host and '"/_api/lan-pin/refresh"' in host)
    check("设置页显示的是局域网口令（不再是公网 password）",
          "lanPassword || \"(无)\"" in client
          and "password || \"(无)\"" not in client)
    check("设置页刷新走 /lan-pin/refresh",
          'request("/lan-pin/refresh", "POST"' in client)
    check("设置页自定义走 /lan-pin/custom（不再是改公网 fixedPassword）",
          'request("/lan-pin/custom", "POST"' in client
          and "fixedPassword: value" not in client)
    check("自定义后给用户明确提示「开启公网不再自动换」",
          "自定义后开启公网不再自动换" in client)
    check("输入框只收数字（onChange 过滤非数字）",
          "replace(/\\D/g" in client)
    check("前端与后端门槛一致（6–12）",
          "LAN_PIN_MIN" in client and "LAN_PIN_MAX" in client)

    # ================= ③ 手动选地址真正生效 =================
    print("\n[③ 「自动设置」真正生效]")
    check("候选列表写进状态文件（下拉框的数据源）",
          '"lan_candidates": state_snapshot()' in run,
          "（早先没写 -> 下拉框恒为空 -> 看起来「没效果」）")
    check("候选明细也落盘（显示网卡名）",
          '"lan_candidate_detail": state_snapshot()' in run)
    check("认证层认「手动选的地址」为内网（优先于按网段判定）",
          "def is_lan_override_host" in proxy
          and "def resolve_request_kind" in proxy)
    check("覆盖逻辑只比主机名（忽略端口与大小写）",
          "name == want" in proxy)
    check("覆盖 provider 已接到门户",
          "lan_ip_override_provider" in run and "lan_ip_override_provider" in proxy)
    check("host 判定走 resolve_request_kind（不是裸 classify_host）",
          "resolve_request_kind(self.headers.get(\"Host\", \"\"), override)" in proxy)
    check("公网域名**不**被覆盖影响（只有选定的那个地址按内网）",
          "hostNameOnly" in proxy or "x.trycloudflare.com" in proxy
          or "name == want" in proxy)
    check("设置页下拉框用 status.lanCandidates",
          "lanCandidates" in host and "lanCandidates" in client)

    # 真实数据链：resolve_request_kind 的判定
    print("\n[数据链：resolve_request_kind 真实调用]")
    script = (
        "import sys; sys.path.insert(0, %r)\n"
        "import portal_proxy as pp\n"
        "out = []\n"
        "for host, ov in [('26.1.2.3:8899','26.1.2.3'), ('26.1.2.3:8899',''),\n"
        "                 ('1.2.3.4:8899','26.1.2.3'), ('garbage value','')]:\n"
        "    out.append([host, ov, pp.resolve_request_kind(host, ov)])\n"
        "import json; print(json.dumps(out))\n"
    ) % os.path.join(ROOT, "tools")
    proc = subprocess.run([sys.executable, "-X", "utf8", "-c", script],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=60)
    rows = []
    for line in (proc.stdout or "").splitlines():
        if line.strip().startswith("["):
            try:
                rows = json.loads(line.strip())
            except ValueError:
                pass
    by_key = {(r[0], r[1]): r[2] for r in rows}
    check("非 RFC1918 的 overlay 地址：选中后判成 lan",
          by_key.get(("26.1.2.3:8899", "26.1.2.3")) == "lan",
          "（Radmin 26.x 就是这个坑）")
    check("同一个 overlay 地址：没选时仍是 public",
          by_key.get(("26.1.2.3:8899", "")) == "public")
    check("公网域名不受覆盖影响",
          by_key.get(("1.2.3.4:8899", "26.1.2.3")) == "public")
    check("畸形 Host 仍 fail-closed（public）",
          by_key.get(("garbage value", "")) == "public")

    # ================= ④ 公网密码也能自定义（体验对齐局域网）=================
    #
    # 用户要求：「公网也要能设置自定义密码，体验和局域网一样，但是公网要有警告提示」，
    # 并指定学习 dsh-pocket 的体验。这里钉住四件事，防止以后被改回去：
    #   · 公网密码行有「自定义」入口（与局域网同一个位置/同一套交互）；
    #   · 有「换回随机」出口（否则自定义之后是单向的，永远回不到自动轮换）；
    #   · 公网有**成块的**风险警示（不是一行灰字 —— 一行会被略过）；
    #   · 改了口令**立即生效**（走 provider，不重启门户 —— 重启会换域名）。
    print("\n[④ 公网密码自定义 + 警告提示]")
    check("公网密码行有「自定义」入口", 'setPubCustomOpen(true)' in client
          and '"自定义"' in client)
    check("有「换回随机」出口（自定义不是单向状态）",
          'backToRandomPublic' in client and '"/public-pin/random"' in client)
    check("公网自定义有独立输入态（不串到局域网那套）",
          'pubCustomOpen' in client and 'pubCustomValue' in client
          and 'customOpen' in client)
    check("本地门槛与后端一致（≥12 位）",
          "const PUBLIC_PIN_MIN = 12" in client
          and "MIN_PASSWORD_LEN = 12" in login)
    check("有**成块**的公网风险警示（warnBox，不是一行灰字）",
          "warnBox:" in client and 'styles.warnBox' in client)
    check("警示讲到了「拿到口令的人就能启停你开放的服务」",
          # 断言**含义**而不是某一版措辞：这条被改写/润色过两次，
          # 绑字面量会让"改进文案"变成"检验失败"，把人逼回去改文案。
          "拿到口令的人" in client and "启停你开放的服务" in client)
    check("警示提醒了「地址会变 / 勿收藏」（学 dsh-pocket 的临时性警示）",
          "请勿收藏" in client and "每次开启都会变" in client)
    check("自定义输入态里也有警告（用户是在这里输入密码的）",
          "公网密码会被互联网上的人尝试" in client)
    check("改完立即生效（不要求重开公网）—— 文案说清",
          "立即生效" in client)
    check("宿主有转发路由 /public-pin/custom",
          '"/public-pin/custom"' in host)
    check("宿主有转发路由 /public-pin/random",
          '"/public-pin/random"' in host)
    check("门户侧用的是公网专用校验（不是启动路径那条）",
          "validate_public_pin" in run and "validate_public_pin" in login)
    check("公网口令走 provider（立即生效，不重启门户）",
          "password_provider" in run and "password_provider" in proxy)
    check("公网口令经密码比较（时序安全），不是明文直接比",
          "password_matches(candidate, expected)" in proxy)
    check("拒绝「公网密码 = 局域网口令」（不能把内网口令升级成公网凭据）",
          "不能和局域网口令相同" in run)
    check("自定义公网密码会落盘（重启不丢）",
          '_internals' not in run and '"public_password"' in run
          and '"public_password"' in run)
    check("停止门户时保留公网自定义口令（KEEP_ON_STOP）",
          '"public_password", "public_pin_custom"' in run)

    # ================= ⑤ 动作区排版：按钮与说明分层 =================
    #
    # 用户指那一块「设计的好看点」。原样是：按钮右边紧跟一句说明，窄面板下被
    # 挤断、读起来像按钮标签的一部分；一行里既有"能做什么"又有"会有什么后果"。
    # 现在动作行只放动作，说明**另起一行**当副文本；每个动作区都有小标题。
    print("\n[⑤ 动作区排版：按钮与说明分层]")
    check("有专门的按钮行样式（动作不与说明混排）",
          "actionRow:" in client and "styles.actionRow" in client)
    check("「停止门户」的后果说明另起一行",
          '"停止后内网 / 公网地址都会失效，设置与口令保留。"' in client)
    check("门户进程那段有小标题（与「服务」同级，读起来是两块）",
          '"门户进程"' in client)
    check("底部不再重复公网风险（与公网区块同主题，去重）",
          client.count("拿到口令的人可以启停你开放的服务") == 1)
    check("未开公网时不再教用户「点关闭公网」（那个按钮那时不在）",
          "不用时请点上方「关闭公网」" in client
          and "children.push(h(\"div\", { key: \"warn\", style: styles.warn }," not in client)
    check("警示不再用 emoji 当结构标记（改用色条 + 加粗标题）",
          "⚠️ 公网暴露风险" not in client and "⚠ 公网开启后" not in client)
    check("底部警示只在「免密」时出现（跨区块的全局安全提示）",
          "if (running && lanAuth === false) {" in client)

    # ================= ⑥ 节点管理在设置页（门户页只读）=================
    #
    # 用户的要求（原话）：
    #   · 「我们添加的节点是做在插件设置里的，每个节点都有屏蔽和开放的开关，
    #      不是服务开启的开关」；
    #   · 「启动服务是服务本身的事情，这里只是负责可以路由」；
    #   · 「每个设置的服务都要有一个点击直接打开的功能叫做访问」；
    #   · 「局域网和公网地址的路径旁边的复制功能边上也加上访问」；
    #   · 「取消自动发现服务的功能，不用刷新也不用搜索，就是人手动添加端口」；
    #   · 「门户页面只读 —— 相当于一个测试页和引导页，没有设置功能」。
    print("\n[⑥ 节点管理在设置页 · 门户页只读]")
    check("设置页有节点清单渲染",
          "styles.svc" in client and '"对外发布的节点"' in client)
    check("数据来自宿主 /status 的 services",
          "status.services" in client and "services" in host)
    check("**开关是「开放 / 屏蔽」**（不是服务启停）",
          '"屏蔽"' in client and '"开放"' in client
          and 'open ? "block" : "open"' in client)
    check("**不再启停上游进程**：门户侧 enable/disable 只改注册表",
          # 断言"没有可执行代码"，而不是"这个词不出现"：注释里写
          # 「原 ServiceSupervisor 已整块删掉」「早先这里会 supervisor.start()」
          # 都是正当的说明，不该被当成残留代码。
          "只改注册表的 enabled" in run
          and "import portal_registry" not in run.split("def main", 1)[-1]
          and "creationflags=_detached_flags()" in run)
    check("上游进程管理器整块删掉（没有可实例化的类）",
          "class ServiceSupervisor" not in run)
    check("删掉了自动拉起进程的整个类（不再管别人程序）",
          "class ServiceSupervisor" not in run)
    check("启动时不再自动拉起服务", 'entry.get("autoStart")' not in run)
    check("删除节点时不再顺手停上游进程",
          "registry.remove(key)" in run and "supervisor.stop" not in run)
    check("每个节点有「访问」", '"访问"' in client and "serviceUrl" in client)
    check("地址行「复制」旁也有「访问」（局域网 + 公网共 2 处）",
          client.count("style: styles.accessLink") == 2)
    check("「访问」链接用品牌色描边（与「复制」区分开）",
          "accessLink:" in client and "border: \"1px solid \" + COLOR.brand" in client)
    check("**自动发现已删掉**（界面/接口都没了）",
          "discover" not in client.lower() and "discover" not in host.lower()
          and "/discover" not in run)
    check("**「刷新」按钮已删掉**", "reloadServices" not in client)
    check("只保留「添加节点」（手动填）",
          '"添加节点"' in client and "submitAdd" in client)
    check("宿主有转发路由 /services/add", '"/services/add"' in host)
    check("宿主转发节点动作（含 open/block）",
          "svcMatch" in host and '"open"' in host and '"block"' in host)
    check("存放动作不再包含 restart（那是启停语义）", '"restart"' not in host)
    check("删除有二次确认（不可撤销的动作）", "window.confirm" in client)
    check("上游没响应时说明「本插件不负责启动它」",
          "本插件不负责启动" in client)

    # ---- 门户页：只读测试页 + 引导页 ----
    console = read("tools/portal_console.py")
    check("门户页**没有**添加表单（<form 不再渲染）",
          "_service_form" not in console)
    check("门户页没有「删除 / 编辑」按钮",
          # 断言的是"没有生成这些按钮"，而不是"这两个词不出现" ——
          # 说明性注释里写「没有『编辑』『删除』」是正当的，不该被当成按钮。
          'class="btn">删除' not in console
          and 'href="/_api/services/' not in console
          and '_service_form' not in console)
    check("门户页没有开关按钮（enable/disable 的 form）",
          "services/%s/enable" not in console
          and "services/%s/disable" not in console)
    check("门户页保留「访问」（这就是测试页的用处）",
          'class="btn primary" href=' in console and "访问" in console)
    check("门户页说明自己是只读 + 去哪管理（引导）",
          "只读" in console and "设置 → 插件 → dsh-service-portal → 配置" in console)
    check("门户页讲清「屏蔽」不停止上游程序",
          "不会</b>停止上游程序" in console or "不会停止上游程序" in console)
    check("门户页能显示「已屏蔽」与「上游未响应」两种状态",
          "已屏蔽" in console and "上游未响应" in console)

    passed = sum(1 for ok in results if ok)
    print("\n设置页三处对齐控制检验：%d/%d" % (passed, len(results)))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
