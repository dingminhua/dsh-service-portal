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


def _strip_comments(text):
    """剥掉 CSS / JS 注释，只留可执行内容。

    为什么需要它：很多断言是"某东西**不再出现**"。而那些东西的名字往往
    正该留在注释里（记录踩过的坑、写"为什么不能这么写"）。按裸文本判会
    把详尽的注释判成违规 —— 注释越诚实，检验越"失败"。
    """
    text = re.sub(r"/\*[\s\S]*?\*/", "", text)
    text = re.sub(r"^\s*//.*$", "", text, flags=re.M)
    return text

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
    # 标题行结构在 0.8.x 重构里从 `key: "head"` 改成了 `key: "hero"` 骨架
    # （head/headText → hero/heroText/heroMeta）。断言跟着改成按 hero 定位：
    # 钉的是"★ 链接在同一行内、不是页面底部"这个**意图**，不是某个旧 key 名。
    # （原先钉死 "head"，重构后 client.index() 直接抛 ValueError，
    #   整份检验在 ① 就中断了 —— 它已经过期，不是在保护什么。）
    check("区块在标题行内（不是页面底部）",
          0 < client.index('}, "鼓励一下 ★"),')
          - client.index('key: "hero"') < 1400,
          "（距离标题行 1400 字符内）")
    # 灰色 + 下划线（用户要的是低调灰，不要品牌蓝）。
    # 注意：这里原来钉的是 `var(--dsw-alias-label-tertiary,#8b93a1)` —— 而那个
    # 令牌**根本不存在**，等于一直在吃写死的灰。改用真实令牌 label-secondary 后，
    # 断言改成看"意图"（灰 + 下划线 + 不是品牌蓝），不绑具体令牌名。
    #
    # 外观已迁到注入的 CARD_CSS（.dsp-link）—— 内联样式做不了 :hover。
    # 所以这里同时接受两种写法：类里定义，或内联定义。
    _link_css = ".dsp-link{" in client and "text-decoration:underline" in client
    check("灰色（非品牌蓝）+ 下划线（与截图一致）",
          _link_css
          or ('color: COLOR.textMuted' in client
              and 'textDecoration: "underline"' in client),
          "（不要品牌蓝 —— 用户要的是低调灰）")
    check("「鼓励一下」链接有 hover 反馈（内联做不到，必须在类里）",
          ".dsp-link:hover" in client)
    check("没有长鼓励文案残留",
          "顺手留颗 Star" not in client and "高兴一整天" not in client
          and "给你一颗 Star" not in client and "开发者：" not in client,
          "（用户三次要求精简，别再加回去）")
    check("没有多行容器样式残留（credit / creditLine 已清理）",
          "creditLine" not in client and "styles.credit," not in client)
    check("链接不换行不压缩（窄面板下不被挤掉）",
          # 外观已迁到注入的 CARD_CSS：nowrap 在 .dsp-link 里，flexShrink 在
          # .dsp-heroMeta 的 flex 简写里（flex:0 0 auto 同样是"不压缩"）。
          # 钉字面量 'flexShrink: 0' 是在钉旧的内联写法，重构后必然假失败。
          (".dsp-link{" in client and "white-space:nowrap" in client)
          and ("flex:0 0 auto" in client or "flex-shrink:0" in client))
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
    # 复制按钮已收敛成 addrRow 一个通用件：copyText(键, 地址)，键按调用点传
    # "lan" / "public"。所以这里断言"两个调用点都走了 addrRow 且各带自己的键"，
    # 而不是去匹配某一行写死的 copyText("lan", lanPrimary) 字面量。
    check("地址复制按钮走统一的 addrRow（局域网 + 公网各一处）",
          "const addrRow = (url, copyKey, withAccess, hint)" in client
          and 'addrRow(lanPrimary, "lan"' in client
          and 'addrRow(publicUrl, "public"' in client)
    check("复制动作与反馈都按 copyKey 走（不是写死某一个键）",
          "copyText(copyKey, url)" in client
          and 'copied === copyKey ? "已复制"' in client)
    check("剪贴板不可用时有兜底（内网 http 非安全上下文会没有 clipboard API）",
          "execCommand" in client and "fallbackCopy" in client,
          "（没有兜底时按钮点了会静默失效）")
    check("地址行样式 addrRow 在（长 URL 可换行、按钮不被挤走）",
          # 外观迁到 CARD_CSS：.dsp-addr 负责换行，.dsp-addrBtns 负责"按钮不被挤走"
          ".dsp-addr{" in client and "word-break:break-all" in client
          and ".dsp-addrBtns{" in client and "flex:0 0 auto" in client)

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
    # 引导块：有标题 + 有说明 + 有启动按钮。
    # ② "预告将用哪些地址"这一版**已被推翻**（用户："没有启动的时候，这两个不要
    #   显示，显示也没意义"）—— 因为那地址是猜的（按上次网卡），照着配手机会
    #   连不上。现在文案明确说"启动后显示在这块位置"。所以这里断言的是**不预告
    #   地址**这个新意图，而不是旧的"启动后会使用这些地址"。
    check("未启动有专门的引导块（标题 + 说明 + 启动按钮）",
          '"门户未启动"' in client and "启动后显示在这块位置" in client
          and "启动（只内网）" in client)
    check("未启动时**不预告**地址（那是猜的，会给出查不出来的错线索）",
          "启动后会使用这些地址" not in client
          and "没有启动的时候" in client)
    # 未启动时整页都不画局域网/公网两栏（见 if (!running) 那条注释），所以
    # "公网区块里有没有按钮"这件事已经不存在了 —— 那两栏只在 running 时渲染。
    check("未启动时不画两栏（整块在 if (running) 里，不会有死按钮）",
          'if (!running) {' in client and 'name: "if (running)"' not in client
          and "if (running) {" in client,
          "（两栏只在运行中渲染，从结构上就没有 disabled 死按钮）")
    # ③ "还没探测过网卡地址"这句兜底已随"不预告地址"一起删除 —— 不预告地址，
    #    自然也不需要解释"为什么还没有地址"。
    check("未启动时不再解释「怎么还没有地址」（不显示地址了）",
          "还没探测过网卡地址" not in client)
    check("启动按钮在未启动引导块里（不再散落在页面下方）",
          "启动（只内网）" in client and "启动并开公网" in client)
    # 「停止门户」整块 UI 已按用户要求**删除**（原话："这个服务本身就随 dsh
    # 打开和关闭的，不需要再有设置，太啰嗦"）。门户改为随 DSH 退出自动收尾。
    # 所以这几条从"检查停止按钮做得对不对"改成"检查停止按钮没有回来"——
    # 功能删了而断言还在查它，就是断言在守一个已经不存在的东西（假失败）。
    _code = _strip_comments(client)
    check("「停止门户」按钮没有回来（门户随 DSH 退出自动收尾）",
          # 注意不能直接找 "doStop"：doStopTunnel 里含这个子串。用词边界匹配。
          re.search(r"\bdoStop\b", _code) is None,
          "（回调 doStop 已删；只剩 doStopTunnel，语义=只收隧道。"
          "注释里仍保留 doStop 的说明，所以判据是剥注释后的代码）")
    check("停隧道与停门户是两件事（doStopTunnel 存在且注释写明语义）",
          "const doStopTunnel" in client
          and "只关隧道" in client)
    check("不再有「停止门户」的后果说明（按钮都不在了）",
          "停止后内网 / 公网地址都会失效" not in client)
    check("未启动时 problem 是普通说明（不是红字报警）",
          # 样式已从内联 styles.warn/styles.muted 迁到 dsp-warn / dsp-inlineWarn，
          # 断言按"停着时用普通提示、且节点仍在"的新实现来定。
          'key: "prob"' in client
          and "上次没有正常退出" in client,
          "（用户自己停的也算正常状态）")
    check("未启动时不显示公网风险警示（还轮不到）",
          # 警示按**实际状态**出现，且公网风险已合并进「公网访问」区块
          # （用户管理公网的地方），页尾只留"局域网免密"这一条跨区块全局提示。
          #
          # 文案在 0.8.2 改过：原文写「拿到口令的人可以**启停**你开放的服务」，
          # 而启停能力已按用户要求取消（只做路由闸门）—— 照抄旧文案会**夸大风险**，
          # 也会让人以为这个插件能操作进程。现在如实说"增删/开放/屏蔽节点，
          # 但动不了上游程序"。
          #
          # 判据必须是**字符串字面量**而不是裸文本：旧说法还留在注释里
          # （用来说明"为什么不能这么写"），按裸文本判会误报。
          # 这段原来还断言了两件事，现在都**已被推翻**，所以改判新的结构：
          #   · 底部"局域网免密"全局警示已删（并入局域网栏自己的密码说明）；
          #   · 公网文案在未开启态是「开启前你需要知道」三条、开启态是风险条，
          #     分属互斥分支，不是"重复讲"，上面 ⑤ 已按结构断言。
          '"公网暴露风险"' in client
          and "pub-none-steps" in client
          and "if (running && lanAuth === false) {" not in client)
    check("关闭公网失败要报出来（宿主回非 ok 时不能静默）",
          # 原来钉的是 doStop（停门户）里的 'if (r && r.ok === false)' 与
          # "没能停止门户"。停门户已删除，**同样的两道保护**现由 doStopTunnel
          # 承担：失败抛错 → setError 显示；成功 → 重新拉状态。
          "const doStopTunnel" in client
          and 'if (!r || r.ok !== true) throw new Error' in client
          and "setError(String(e && e.message" in client,
          "（否则点了关闭没反应，用户以为点错了）")
    check("操作成功后一律重新拉状态（不信返回里的状态快照）",
          "await load();" in client)

    # ---- 排版：字号只能来自统一刻度，颜色只能用**真实存在**的主题令牌 ----
    #
    # 用户反馈「设置页面的字大大小小，样式难看」。查出来两个原因：
    #   1. 字号从参考对象那儿一并抄了：面板里混着 11/12/13/14 四种，而相邻级差
    #      只有 1px —— 看不出层级，只觉得忽大忽小；
    #   2. 用了 4 个**不存在**的 --dsw-alias-* 令牌，它们永远不命中，于是一直
    #      吃写死的浅色兜底：深色模式下文字和按钮就变成了浅色主题的颜色。
    print("\n[排版：统一字号刻度 + 只用真实令牌]")
    _re = re  # 兼容旧写法；re 已在模块级 import

    # 真实令牌清单来自宿主主题（cordis inspect Theme.listTokens），写死在这里做守卫：
    # 以后谁再引用不存在的令牌，这条会拦下来。
    #
    # 只校验 **alias 命名空间**（--dsw-alias-* / --dsw-specific-*）。radius /
    # shadow / focus-ring / --ds-* 属于另外几套命名空间，宿主确实提供（已在
    # app.asar 里核实），不能一并判假 —— 早先这条规则把整份用户样式判成"可疑"，
    # 反而让真正该拦的假 token 混在噪音里没人看。
    real_alias_tokens = {
        "--dsw-alias-bg-base", "--dsw-alias-bg-layer-1", "--dsw-alias-bg-layer-2",
        "--dsw-alias-bg-overlay", "--dsw-alias-border-l1", "--dsw-alias-border-l2",
        "--dsw-alias-brand-primary", "--dsw-alias-label-primary",
        "--dsw-alias-label-secondary", "--dsw-alias-state-error-primary",
        "--dsw-alias-state-idle-primary", "--dsw-alias-state-success-primary",
        "--dsw-alias-state-warn-primary", "--dsw-specific-sidebar-fill",
    }
    used_alias = set(_re.findall(
        r"var\((--dsw-(?:alias|specific)-[a-z0-9-]+)", client))
    fake = sorted(used_alias - real_alias_tokens)
    check("只引用真实存在的**别名**令牌（不存在的会静默吃浅色兜底）",
          not fake, "可疑令牌=%r" % (fake,))
    # 本轮修掉的假令牌，逐个钉死（防止换个写法又混回来）。
    #
    # 判据是"**被当作 CSS 值引用**"，不是"这段文字出现过"：假令牌的名字
    # 本来就该允许出现在注释里（记录踩过的坑），否则注释越详细越判失败。
    # 所以这里剥掉注释再查（_strip_comments 定义在模块级，见文件开头）。
    code_only = _strip_comments(client)
    for gone in ("--dsw-alias-label-tertiary", "--dsw-alias-state-warning-primary",
                 "--dsw-alias-button-primary-fill",
                 "--dsw-alias-label-primary-foreground",
                 # 下面这些是 2026-10 这轮从"看着有兜底"里挖出来的：
                 "--dsw-alias-label-dimmed",      # placeholder 太淡的直接原因
                 "--dsw-alias-border-l3", "--dsw-alias-border-l4",
                 "--dsw-alias-state-business-primary",
                 "--dsw-alias-interactive-bg-hover",
                 "--dsw-alias-interactive-bg-hover-solid",
                 "--dsw-alias-interactive-bg-active",
                 "--dsw-alias-markdown-inline-code",
                 "--dsw-alias-settings-card-fill",
                 "--dsw-alias-settings-card-stroke",
                 "--dsw-alias-state-warn-label",
                 "--dsw-alias-switch-thumb",
                 "--dsw-alias-toast-bg", "--dsw-alias-toast-label",
                 "--dsw-alias-button-primary-hover"):
        check("假令牌 %s 不再被引用（注释里说明无妨）" % gone,
              gone not in code_only)

    # placeholder 必须看得清：只允许 label-secondary（或更深），且不允许走
    # --dsp-t3 那档（它曾经指向不存在的 label-tertiary，兜底 #8b95a5 在白底上
    # 只有 ~2.9:1，用户反馈"输入框内的字看不清"）。
    ph = _re.search(r"\.dsp-input::placeholder\{([^}]*)\}", client)
    check("placeholder 颜色用真实且清晰的令牌（label-secondary）",
          ph is not None and "label-secondary" in ph.group(1)
          and "label-dimmed" not in ph.group(1)
          and "dsp-t3" not in ph.group(1))

    # 字号刻度：只允许 TYPE.*（刻度本身定义在 TYPE 里）
    raw_sizes = _re.findall(r"fontSize:\s*(\d+)", client)
    check("没有裸的数字字号（只能从 TYPE 刻度取）",
          not raw_sizes, "裸字号=%r" % (raw_sizes,))
    check("刻度是 4 级且单调（16/14/13/12）",
          _re.search(r"title:\s*16[\s\S]{0,80}section:\s*14[\s\S]{0,80}"
                     r"body:\s*13[\s\S]{0,80}caption:\s*12", client) is not None)
    check("说明文字不小于 12（再小在缩放屏上会糊）",
          "caption: 12" in client)
    check("取色统一走令牌层（不再逐屏硬编码 hex）",
          # COLOR 常量已按"内联样式压死 :hover"的整体重构**删除**，取色改为
          # CARD_CSS 里的 --dsp-* 别名层（其值再指向真实 --dsw-alias-*）。
          # 所以这里断言的是**同一意图**：不再有散落的硬编码 rgba/hex 颜色。
          (":root{" in client or "--dsp-t1:" in client)
          and client.count("rgba(22,163,74") == 0
          and client.count("rgba(107,114,128") == 0,
          "（颜色只能从 --dsp-* / --dsw-* 取）")
    check("间距用 SPACE 刻度或 CSS gap，行内不写裸 marginTop 数字",
          ("const SPACE = {" in client or "gap:18px" in client)
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
    check("有**成块**的公网风险警示（警示块，不是一行灰字）",
          # warnBox 已迁到注入 CSS：成块警示统一用 .dsp-warn（左色条 + 浅底
          # + 加粗标题），对应旧的内联 styles.warnBox。
          ('className: "dsp-warn"' in client)
          and ".dsp-warn{" in client
          and "border-left:3px solid" in client)
    check("警示讲到了「拿到口令的人就能启停你开放的服务」",
          # 断言**含义**而不是某一版措辞：这条被改写/润色过两次，
          # 绑字面量会让"改进文案"变成"检验失败"，把人逼回去改文案。
          # 另外 0.8.2 已取消"启停服务"能力（只做路由闸门），原文案是**夸大的**，
          # 现在的措辞是"增删、开放或屏蔽节点，但动不了上游程序"—— 这条要断言
          # 的是"讲清了拿到口令能做什么"，而不是那个已被推翻的"启停"。
          "拿到口令的人" in client
          and ("增删、开放或屏蔽你发布的节点" in client)
          and "启停你开放的服务" not in _strip_comments(client),
          "（不能夸大：插件只管路由，动不了上游进程）")
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
          # actionRow 已迁到 CARD_CSS 的 .dsp-row；"动作行"与"说明行"仍然是
          # 两种节点（h("div", {className:"dsp-row"}) vs dsp-hint/dsp-warn）。
          'className: "dsp-row"' in client and ".dsp-row{" in client)
    # 「停止门户」整块 UI 已删（门户随 DSH 退出收尾），它的后果说明自然也不该在。
    check("不再有「停止门户」及其后果说明（功能已删）",
          "停止后内网 / 公网地址都会失效" not in client
          and "const doStop =" not in client)
    check("不再有「门户进程」小节（功能已删）",
          # 注释里还留着"为什么删"的记录，所以先剥注释再判
          '"门户进程"' not in _re.sub(r"/\*[\s\S]*?\*/", "", client)
          .replace("// ============ 门户进程", ""))
    check("公网风险只讲一处（未开启讲「须知」、开启后才显示风险条，两者互斥）",
          # 早先这条要求整份客户端只出现一次。现在它出现在**两个互斥分支**里：
          #   · publicUrl 为空 → 「开启前你需要知道」三条（pub-none-steps）
          #   · publicUrl 存在 → 底部「公网暴露风险」条（pub-risk）
          # 同一时刻只会渲染其中一个，所以不是"重复讲"。断言改成**结构**：
          # 两处分别挂在对应分支上，而不是数总次数。
          "pub-none-steps" in client and "pub-risk" in client
          and client.count("地址是随机 trycloudflare 域名，每次开启都会变") == 1)
    check("未开公网时不再教用户「点关闭公网」（那个按钮那时不在）",
          "不用时请点上方「关闭公网」" in client
          and "children.push(h(\"div\", { key: \"warn\", style: styles.warn }," not in client)
    check("警示不再用 emoji 当结构标记（改用色条 + 加粗标题）",
          "⚠️ 公网暴露风险" not in client and "⚠ 公网开启后" not in client)
    check("底部不再有「局域网免密」全局警示（已并入局域网栏内的密码说明）",
          # 那一块原在页面最底部，条件是 running && lanAuth === false。
          # 局域网栏现在自己就说清了"已关闭：同一 WiFi 扫码直连"，底部再说一遍
          # 是同一件事讲两遍。断言它没有回来。
          "if (running && lanAuth === false) {" not in client)

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
          'className: "dsp-node"' in client and '"对外发布的节点"' in client,
          "（样式类从 styles.svc 迁到 .dsp-node）")
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
    # ---- 节点卡片的访问入口：内网 / 公网各一个，各自判断自己的开关 ----
    #
    # 用户要求：「这里要有内网访问、公网访问 2 个访问按钮，各自判断当前是否
    # 开启，开启才能点击」。为什么要两个：两条通道的开关互相独立（关掉局域网
    # 后公网仍可用；没开公网时公网按钮没有意义），合成一个就只能给死链或靠猜。
    check("每个节点有「内网访问」与「公网访问」两个入口",
          '"内网访问"' in client and '"公网访问"' in client)
    check("两个入口各自算自己的地址（不再是单一 serviceUrl）",
          "const serviceUrls = (svc)" in client
          and "lan: lanBase + path" in client
          and "pub: publicUrl ? publicUrl + path" in client,
          "（serviceUrl 已删，避免两个按钮共用一条地址）")
    check("内网按钮按 lanEnabled 判断能否点",
          "lanEnabled === true" in client
          and "serviceUrls(svc).lan : undefined" in client)
    check("公网按钮按 publicUrl 判断能否点",
          "publicUrl ? serviceUrls(svc).pub : undefined" in client)
    check("未开启的那个**不给 href**（<a> 没有 :disabled，只能这样真禁掉）",
          client.count("href: ") >= 2
          and ": undefined," in client)
    check("未开启时点它也不会跳走（preventDefault 兜一层）",
          client.count("(e) => e.preventDefault()") >= 2)
    check("未开启时给出「去哪开」的原因（不能只是灰掉）",
          "先在「局域网访问」里打开开关" in client
          and "先点「开启公网访问」" in client)
    check("禁用态有 .is-disabled 外观（<a> 没有 :disabled）",
          ".dsp-btn.is-disabled{" in client)
    # 用户明确的一个组合：内网没开、公网也没开 -> **两个按钮都必须是禁用的**，
    # 但节点卡与「屏蔽 / 编辑 / 删除」仍要完整可用（"打不开"不等于"不能管理"）。
    # 这一条靠预览状态 svcnone 出图核对过，这里把它钉成结构：两处判据分别绑在
    # 自己的状态上，且**没有任何一条**回退成"只要有节点就给 href"。
    check("两边都没开时，两个按钮各自独立变灰（不是共用一条判据）",
          client.count("is-disabled") >= 2
          and client.count(": undefined,") >= 2)
    check("节点被屏蔽时两个访问入口都不出现（路由不转发，给了就是死链）",
          "open\n                ? h(\"a\", {" in client
          and client.count("open\n                ? h(\"a\", {") >= 2)


    # ---- 宽度适配 + 交互态（用户：「宽度变了…设计美观的细节完善一下」）----
    #
    # 背景：注册位置从「宿主设置的一整页」改成「插件页的配置区」后，可用宽度
    # 从 560 变成约 900–1000。原来写死的 maxWidth:560 于是在宽栏里缩成一条窄柱
    # （二维码挤中间、右侧大片留白）——用户截图就是这个。
    print("\n[⑤b 宽度适配：用满插件页宽度 + 交互态与响应式]")
    check("卡片**不再**写死 maxWidth 560（宽栏里会缩成窄柱）",
          "maxWidth: 560" not in client)
    check("卡片用满可用宽度且有上限（避免行长过长）",
          # 上限从 880 调到 960（两栏 + 二维码在这个宽度下更舒展），断言改成
          # "有上限、且不是内联写死的"——这不是在钉某个具体像素。
          "max-width:960px" in client and "maxWidth: 880" not in client
          and "maxWidth: 960" not in client)
    check("局域网/公网两栏并排（原来在窄柱里竖着叠，两个二维码要滚很久）",
          ".dsp-duo{" in client and "grid-template-columns" in client
          and "auto-fit" in client)
    check("窄屏塌成单栏（窄面板/手机上不能两栏硬挤）",
          # 断点从 720 调到了 760（两栏最小 300 时 720 会提前塌）。断言按"有单栏
          # 兜底"来定，不绑断点数值 —— 断点属于调参，不是契约。
          _re.search(r"@media \(max-width:\d+px\)\{[\s\S]{0,200}?\.dsp-duo\{grid-template-columns:1fr\}",
                     client) is not None)
    check("窄屏二维码缩小（176 在手机上会占掉半屏）",
          # 值从 132 调到 148（桌面 168）。同样只断言"窄屏里确实变小了"。
          _re.search(r"\.dsp-qr,\.dsp-qrEmpty\{width:(\d+)px;height:\1px\}",
                     client) is not None,
          "（窄屏档存在且宽高一致）")
    check("注入的是真实 <style>（内联做不了 hover/@media）",
          "document.createElement(\"style\")" in client
          and "document.head.appendChild" in client)
    check("样式注入是幂等的（重新挂载不会越堆越多）",
          "data-plugin-css" in client and "querySelector" in client)
    check("**按钮有 hover 与 disabled 视觉**（规范：可点击元素要有按压反馈）",
          # 类名从 .dsp-primary 改名为 .dsp-btn-primary（与宿主 Button 对齐）。
          # ":disabled" 仍然要有，且 hover 规则必须挂在会变色的那个按钮类上。
          ".dsp-btn-primary:hover" in client and ":disabled" in client)
    check("**键盘焦点可见**（规范：focus-visible）",
          # 焦点环的写法从写死的 outline:2px solid 变成 --dsp-focus（令牌化：
          # 2px solid 品牌色）。断言意图：有 focus-visible 规则且轮廓可见。
          ":focus-visible" in client
          and ("outline:2px solid" in client
               or ("--dsp-focus:" in client and "solid" in client)))
    check("尊重 prefers-reduced-motion（规范要求）",
          "prefers-reduced-motion:reduce" in client)
    check("类名统一 dsp- 前缀（不与宿主/别的插件撞车）",
          client.count("dsp-") >= 20)
    check("**按钮外观不再内联**（内联会压死类里的 hover，白写）",
          # 只针对需要交互态的按钮原语：底部背景/描边必须只在类里。
          # warnBox/tag/svcMount 那些是静态装饰（没有 hover 语义），
          # 内联它们的底色是合理的，不在此列。
          #
          # 0.8.x 重构把这些内联样式表整个删了（连 `primary: {}` 这种空占位
          # 都不留），改为 CARD_CSS 一元化。所以断言从"空占位对象还在"改成
          # 真正要守的两条**意图**：
          #   · 不得出现内联品牌底色（会盖掉 :hover / :disabled）；
          #   · 四个按钮原语的外观必须由类选择器提供（.dsp-btn 系列在 CSS 里）。
          client.count("background: COLOR.brand") == 0
          and "background: COLOR.brand" not in client
          and ".dsp-btn-primary{" in client
          and ".dsp-btn-danger{" in client)
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
