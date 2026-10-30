window.__ModuleLoader__.load({
  id: "dsh-service-portal",
  factory: (require) => {
    var module = { exports: {} };
    var exports = module.exports;
    // React 由 DSH 客户端模块系统提供，绝不假设全局 React。
    var React = require("react");
    // 家族 64px 品牌图标（构建期从 client/icon.ts 内联，见 build.mjs 注释）。
    var SERVICE_PORTAL_PLUGIN_ICON = "data:image/png;base64,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";
// dsh-service-portal 设置页客户端（手写 CommonJS，无需 esbuild/JSX 工具链）。
//
// 分发格式与 dsh-pocket / dsh-ldvh 一致：window.__ModuleLoader__.load({id, factory})，
// React 由 DSH 客户端模块系统提供（require("react")），绝不假设全局 React。
//
// 为什么手写而不上 JSX 构建：本机 profile 里没有 esbuild，且插件要能在
// 任何 DSH 安装上直接跑；用 React.createElement 别名 h() 可读性足够，
// 换来零构建依赖。产物由 client/build.mjs 生成到 lib/client.js —— 必须放
// lib/ 并与 package.json 的 exports["./client"] 一致（放错目录会让 DSH
// 启动期解析失败，迁移时实测过一次）。
//
// 图标 SERVICE_PORTAL_PLUGIN_ICON 由构建脚本内联注入（来自 client/icon.ts，
// 与 LaoDing 插件家族同一张 64px 品牌图）。
//
// 界面形态（2026-10-15 重做，对齐 dsh-pocket 的设置页）：
//   · 局域网区块：总开关 + 二维码 + 地址（可复制）+ 访问密码（开关/刷新/自定义）+ 高级选地址
//   · 公网区块：开关 + 二维码 + 地址（可复制）+ 访问密码
//   · 扫码打开的就是门户控制台（在那里管理要开放的服务）
//
// 地址旁边同时给「复制」：扫码适合当面用手机接过去，复制适合把地址贴进聊天窗
// 发给别人 —— 两条路留给不同场景（用户要求地址可复制）。
//
// 与 dsh-pocket 的一个本质区别（诚实说明）：dsh-pocket 的二维码指向**一个目标**
// （DSH 的 web 界面），我们的二维码指向**门户控制台**——扫码后是一个可管理多个
// 服务的页面。所以这里显示的是「门户地址」，不是「某个服务地址」。

// 元素创建别名：**不能**从 props 里取（DSH 的 section props 不含 h，
// 取了会得到 undefined → 渲染期抛 "h is not a function" → 面板整片空白，
// 而左侧导航照常显示，极难定位）。模块级定义一次即可。
const h = React.createElement;

const name = "dsh-service-portal";
// 只注入**两条宿主线都有**的服务。教训（读 workbuddy 的注释得到）：
// Cordis 的 inject 是**硬依赖闸门** —— 列了一个本运行线不提供的服务，
// apply 就永远不会跑（整个插件静默失效，界面上什么都不出现）。
//   · `settingsScope` 在 0.1.7+ 已被 `configForms` 取代，**不能**列进 inject；
//   · 本插件的状态全靠自己的 HTTP 接口（宿主转发门户），不需要宿主的配置表单；
//   · 真要探一个可能不存在的服务，用 ctx.get()（缺失时返回 undefined），
//     绝不要写 ctx.settingsScope（未注入的 Service 属性访问会**抛异常**）。
const inject = ["slots", "connection"];

const API = "/service-portal/api";

// 项目仓库地址（右上角那句求 Star 的链接目标）
const REPO_URL = "https://github.com/dingminhua/dsh-service-portal";

// 局域网口令长度门槛 —— 与后端 portal_login.validate_lan_pin 一致。
// 前端先挡一层省一次往返；后端仍有权威校验（不信任前端）。
const LAN_PIN_MIN = 6;
const LAN_PIN_MAX = 12;

// 公网口令长度门槛 —— 与后端 portal_login.MIN_PASSWORD_LEN 一致（12）。
// 公网是对全互联网暴露的，所以**长度**门槛比局域网（6–12 位）严；
// 字符种类不限（用户要求体验与局域网一致：想设什么就设什么）。
const PUBLIC_PIN_MIN = 12;

// ============================================================================
// 排版与间距刻度
// ============================================================================
//
// 用户反馈「字大大小小，样式难看」。原因是字号从参考对象那儿一并抄了过来，
// 面板里同时混着 11/12/13/14 四种字号，而且没有层级规则：
//   · 标题 14、分区标题 13、正文 12、标签 12、徽标 11 —— 相邻级差只有 1px，
//     视觉上"忽大忽小"却看不出层级（1px 的差别只会显得脏，不会显得有层次）；
//   · 按钮 13、二维码说明 12、公告 12 —— 同一个"正文"概念在不同区块用了不同号。
//
// 现在收敛成一套 4 级刻度 + 8px 间距节奏，且**所有字号只能从这里取**：
//   title 16 页面标题 / section 14 分区标题 / body 13 正文与控件 / caption 12 说明与徽标
// 级差 ≥1px 且单调递减，字重跟着层级走（标题 600、分区 600、正文 400）。
// 12 是**下限**：再小的说明文字在 2 倍缩放下会糊（对齐 UX 规范
// 「关键文字不得低于 12pt」）。
const TYPE = {
  title: 16,
  section: 14,
  body: 13,
  caption: 12,
};

// 间距节奏：块间距 18、行间距 8。**只在结构骨架里插值**（.dsp-body / .dsp-sec /
// .dsp-row 的 gap）；控件内部的 4/6/10/12 是逐处的视觉微调，写在 CSS 里更直观。
const SPACE = {
  block: 18,
  row: 8,
};

// 行高不再单独列表：它是"字号刻度"的一部分（标题 24 / 正文 20 / 说明 18），
// 与字号写在同一个地方（下面 CSS 里紧挨着 font-size）就不容易出现
// "字号改了、行高忘了"的漂移 —— 上一轮那种各写各的局面正是这么来的。

// ============================================================================
// 一份真实的 CSS（照 workbuddy 的做法：模块加载时注入一个 <style>）
// ============================================================================
//
// 为什么必须有它而不是全靠内联 style：
//   · **hover / focus-visible / active 没法内联** —— 而 UX 规范明确要求
//     "所有可点击元素提供明确的按压反馈"「键盘导航焦点可见」。之前按钮点了
//     毫无反应，就是这个原因；
//   · **媒体查询没法内联** —— 窄屏要塌成单栏、二维码要缩小，只能靠 @media；
//   · `disabled` 的视觉弱化、`prefers-reduced-motion` 也都在这里。
//
// 类名一律加 `dsp-` 前缀，避免与宿主或其他插件的类名撞车
// （workbuddy 用 `dsm-`，同一个约定）。颜色只引用真实主题令牌。
const CSS_ID = "dsh-service-portal/client.css";
const CARD_CSS = `/* ==========================================================================
   dsh-service-portal 设置面板样式
   --------------------------------------------------------------------------
   本轮（1.0.9 视觉整改）修掉的是一个**真 bug**，不是审美问题：

   ① 主按钮的规则**整条被浏览器丢弃**了。
      CSS 注释**不能嵌套**。原先那段说明里写着一行带注释符的示例
      （形如 background: var(...) 后跟一段块注释），内层的注释结束符提前关掉了
      外层注释，于是后面那段中文说明被当成 CSS 解析，
      解析器一路吞到下一个 「}「，把紧随其后的 「.dsp-btn-primary{...}「 整条吃掉了。
      实测（Chrome DevTools Protocol 读 CSSOM）：
        · document.styleSheets 里**没有** 「.dsp-btn-primary「 这条规则；
        · 「开启公网访问」按钮的 computed background 是 rgba(0,0,0,0)（透明），
          看起来就是一个**没有底色的纯文字**，右侧空一块 —— 正是用户截图里的样子。
      所以下面所有注释一律**不嵌套**，并且有一条测试守着这件事（见 test/client.test.mjs
      「CSS 注释不得嵌套」）。

   ② 几何与配色逐项对齐宿主真实原语（照抄 app.asar 里的值，不是估计）：
        Button.module.css   H36/R12/pad 0 14/14px 字体 · .sm H28/R8/pad 0 10/12px
                            .primary = button-primary-fill + label-primary-foreground
                            .ghost:hover = interactive-bg-hover · .ghost:active = interactive-bg-active
                            .outline = border-l3 描边
        Input.module.css    H32/R12 · border-l4 · bg-layer-1
        Switch.module.css   36×20 轨道 · 16 圆钮 · 开=brand-primary · 钮=switch-thumb
        Pill.module.css     H24/R999/12px · **无描边**（靠底色分层）
        Tag.module.css      R999/pad 1px 8px · 无描边
        Dialog.module.css   R28(bg-layer-2) · elevation-prominent · 标题 16/24
        Toast.module.css    bg = alias-toast-bg · fg = alias-toast-label

   ③ 颜色**只用真实存在的宿主令牌**，且每个 var() 都带兜底。
      真实令牌表见 dsh-client-ui-theme/lib/client.js（浅色 body{} / 深色
      body[data-ds-dark-theme]{} 两块）。特别说明几处**踩过的坑**：
        · --dsw-alias-label-tertiary 是**存在**的（浅 #81858c / 深 #adb2b8），
          早先注释说它不存在是错的 —— 那时错的是拼写。
        · 浅色主题下 bg-layer-1/2/3 **都是同一个白**，拿它做层级等于没做；
          要"浮起来"用 interactive-bg-hover（浅 #2631480f / 深 #ffffff14）。
        · brand-primary 是"最高对比度前景色"，浅色是近黑、深色是近白；
          主按钮必须**成对**取 button-primary-fill + label-primary-foreground，
          否则深色下会出现白底白字。
      本文件里**不再出现**任何"直接写死"的颜色：所有颜色都来自 var()，
      兜底值写在 var() 的第二个参数里（且与宿主同档）。
   ========================================================================== */

/* 本地变量：把"令牌名 + 兜底"收在一处，明暗主题都由宿主令牌切换。 */
.dsp-root,.dsp-card{
  --dsp-r-sm:var(--dsw-radius-sm,8px);
  --dsp-r-md:var(--dsw-radius-md,12px);
  --dsp-r-lg:var(--dsw-radius-lg,16px);
  --dsp-r-xl:var(--dsw-radius-xl,20px);
  --dsp-r-panel:var(--dsw-radius-panel,28px);
  /* 描边：结构分隔一律 1px。
     宿主写的是 0.5px，但 DPR=1 的浏览器会把 0.5px 向上取整成 1px —— 写 0.5px
     只会让下一个人以为"发丝线"生效了。照实际渲染结果写 1px。 */
  --dsp-line:1px solid var(--dsw-alias-border-l2,rgba(0,0,0,.12));
  --dsp-line-strong:1px solid var(--dsw-alias-border-l3,rgba(0,0,0,.16));
  /* 内嵌层：宿主真正承担"悬浮/内嵌"的层。
     浅色 bg-layer-1/2/3 同为白，用它们分层等于没分 —— 这正是面板显得平的原因。 */
  --dsp-inset:var(--dsw-alias-interactive-bg-hover,#2631480f);
  --dsp-inset-solid:var(--dsw-alias-interactive-bg-hover-solid,#f1f3f5);
  --dsp-active:var(--dsw-alias-interactive-bg-active,#2631481a);
  --dsp-surface:var(--dsw-alias-bg-layer-2,#fff);
  --dsp-surface-1:var(--dsw-alias-bg-layer-1,#fff);
  --dsp-t1:var(--dsw-alias-label-primary,#0f1115);
  --dsp-t2:var(--dsw-alias-label-secondary,#61666b);
  /* label-tertiary 浅色 #81858c 对白底只有 3.71:1 —— 文字一律不用它（AA 正文要
     4.5:1），它只留给**非文字**的指示图形：1.4.11 对图形只要求 3:1。 */
  --dsp-t3:var(--dsw-alias-label-tertiary,#81858c);
  --dsp-ok:var(--dsw-alias-state-success-primary,#22c55e);
  --dsp-warn:var(--dsw-alias-state-warn-primary,#f59e0b);
  --dsp-err:var(--dsw-alias-state-error-primary,#ec1313);
  /* 语义色**直接当文字用会不合格**，实测（合成到实际底色后）：
       green-500  #22c55e 对白底 2.28:1、对 inset 2.05:1
       amber-500  #f59e0b 对白底 2.15:1
       red-400    #f25a5a 对深底卡片 4.24:1（深色下连 4.5 都不到）
     宿主自己也踩了这个坑：state-warn-label 两种主题都是 amber-600 #dd8629
     = 2.79:1。所以这里不照抄，改成**朝本主题的 label-primary 混合**：
     浅色被压深、深色被提亮，同一个表达式两种主题各自达标，且仍是同一个色相。
     比例按实测最低档定：ok 60%、warn 55%、err 70%（红要更深才够）。
     color-mix 是宿主自己在用的函数（label-deep-diving 等），不是新增依赖。 */
  --dsp-ok-text:color-mix(in srgb,var(--dsp-ok) 60%,var(--dsp-t1));
  --dsp-warn-text:color-mix(in srgb,var(--dsp-warn) 55%,var(--dsp-t1));
  --dsp-err-text:color-mix(in srgb,var(--dsp-err) 70%,var(--dsp-t1));
  /* 警示框左侧 3px 色条是图形，门槛是 3:1 不是 4.5:1，可以比正文更"亮"一档；
     但纯 amber-500 只有 2.15:1，画出来等于没画，所以取 75%（浅 #bc7b0e 3.53:1）。 */
  --dsp-warn-bar:color-mix(in srgb,var(--dsp-warn) 75%,var(--dsp-t1));
  /* 焦点/强调色：宿主焦点环用 state-business-primary（浅 #4176e6 / 深 #7aaaff）。
     不用 --dsw-focus-ring-color —— 宿主把它定义成了 transparent，取不到可见焦点环。 */
  --dsp-accent:var(--dsw-alias-state-business-primary,#4176e6);
  --dsp-focus:2px solid var(--dsw-alias-state-business-primary,#4176e6);
  --dsp-code:var(--ds-font-family-code,ui-monospace,SFMono-Regular,Menlo,monospace);
  --dsp-ease:var(--ds-ease-in-out,cubic-bezier(.4,0,.2,1));
  --dsp-fast:var(--ds-transition-duration-fast,.1s);
  color:var(--dsp-t1);
}

/* ---- 面板容器：与宿主设置卡同一材质（bg-layer-2 + 1px 描边 + R20）---- */
.dsp-card{
  box-sizing:border-box;width:100%;max-width:960px;
  padding:22px 24px 24px;
  background:var(--dsp-surface);
  border:1px solid var(--dsw-alias-border-l4,rgba(0,0,0,.16));
  border-radius:var(--dsp-r-xl);
  color:var(--dsp-t1);
}
.dsp-card,.dsp-card *{box-sizing:border-box}
.dsp-card h4,.dsp-card h5,.dsp-card p,.dsp-card ul{margin:0}

/* ---- 顶部：图标 + 身份 + 状态 ---- */
.dsp-hero{display:flex;align-items:flex-start;gap:14px;flex-wrap:wrap}
.dsp-logo{width:44px;height:44px;border-radius:var(--dsp-r-md);flex:0 0 auto;display:block}
.dsp-heroText{flex:1 1 200px;min-width:0}
.dsp-title{font-size:${TYPE.title}px;line-height:24px;font-weight:600;letter-spacing:-.01em}
.dsp-sub{margin-top:4px;font-size:${TYPE.body}px;line-height:20px;color:var(--dsp-t2)}
.dsp-heroMeta{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-left:auto;padding-top:4px}
/* 链接必须有**常驻**下划线：颜色不是唯一的信息载体，hover 才出现的下划线不成立。 */
.dsp-link{display:inline-flex;align-items:center;min-height:28px;padding:0 2px;
  font-size:${TYPE.caption}px;line-height:18px;color:var(--dsp-t2);
  text-decoration:underline;text-underline-offset:2px;white-space:nowrap}
.dsp-link:hover{color:var(--dsp-t1)}
.dsp-link:focus-visible{outline:var(--dsp-focus);outline-offset:2px;border-radius:var(--dsp-r-sm)}

/* ---- 状态胶囊 / 状态点（照宿主 Pill：H24/R999/12px，**无描边**，靠底色分层）---- */
.dsp-pill{display:inline-flex;align-items:center;gap:6px;height:24px;padding:0 10px;
  border:none;border-radius:999px;background:var(--dsp-inset);
  font-size:${TYPE.caption}px;line-height:18px;color:var(--dsp-t2);white-space:nowrap}
.dsp-pill--on{color:var(--dsp-ok-text);
  background:color-mix(in srgb,var(--dsp-ok) 12%,transparent)}
.dsp-dot{width:6px;height:6px;border-radius:50%;background:var(--dsp-t3);flex:0 0 auto}
.dsp-dot--on,.dsp-pill--on .dsp-dot{background:currentColor}
.dsp-dot--on{color:var(--dsp-ok-text)}

/* ---- 分区骨架：块间距 18、行间距 8（4 的倍数网格）---- */
.dsp-body{display:flex;flex-direction:column;gap:${SPACE.block}px;margin-top:${SPACE.block}px}
.dsp-sec{display:flex;flex-direction:column;gap:10px}
.dsp-secHead{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap}
.dsp-secTitle{font-size:${TYPE.section}px;line-height:20px;font-weight:600}
.dsp-secNote{font-size:${TYPE.caption}px;line-height:18px;color:var(--dsp-t2)}
.dsp-hint{font-size:${TYPE.caption}px;line-height:18px;color:var(--dsp-t2)}
.dsp-row{display:flex;align-items:center;gap:${SPACE.row}px;flex-wrap:wrap}
.dsp-stack{display:flex;flex-direction:column;gap:${SPACE.row}px}
.dsp-actions{display:flex;align-items:center;gap:${SPACE.row}px;flex-wrap:wrap;margin-top:12px}

/* ---- 空态（门户未启动）---- */
.dsp-cta{background:var(--dsp-inset);border-radius:var(--dsp-r-lg);padding:20px}
.dsp-ctaGrid{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,.85fr);gap:24px}
/* 左栏是一个**等距**竖列：标题、说明、地址、按钮、脚注之间一律 12px。 */
.dsp-ctaMain{display:flex;flex-direction:column;gap:12px;min-width:0}
.dsp-ctaMain .dsp-actions{margin-top:0}
.dsp-lede{font-size:${TYPE.body}px;line-height:20px;color:var(--dsp-t2);max-width:52ch}
.dsp-asideLabel{font-size:${TYPE.caption}px;line-height:18px;font-weight:600;
  color:var(--dsp-t2);letter-spacing:.02em}
.dsp-steps{display:flex;flex-direction:column;gap:12px;margin-top:12px;padding:0;list-style:none}
.dsp-step{display:flex;align-items:flex-start;gap:10px}
/* 序号圆点：20px 圆里放 12px 数字（12 是本文件自己的字号下限）。 */
.dsp-stepNum{flex:0 0 auto;width:20px;height:20px;border-radius:999px;
  background:var(--dsp-inset-solid);color:var(--dsp-t2);
  font-size:${TYPE.caption}px;line-height:20px;text-align:center;font-variant-numeric:tabular-nums}
.dsp-stepTitle{display:block;font-size:${TYPE.caption}px;line-height:18px;font-weight:600;color:var(--dsp-t1)}
.dsp-stepDesc{display:block;font-size:${TYPE.caption}px;line-height:18px;color:var(--dsp-t2)}

/* ---- 地址块：内嵌底色 + 等宽地址 + 复制/访问 ----
   地址可以很长（公网是 https://xxx.trycloudflare.com），所以**地址负责收缩
   换行、按钮组不换行**。底色用内嵌层而不是白底描边：白底在白卡片上只剩
   一圈灰框，是"盒子感"的主要来源。 */
.dsp-addr{display:flex;align-items:center;gap:8px;min-height:40px;
  padding:4px 6px 4px 12px;border:none;border-radius:var(--dsp-r-md);
  background:var(--dsp-inset);flex-wrap:nowrap}
.dsp-addr code{flex:1 1 auto;min-width:0;font-family:var(--dsp-code);
  font-size:${TYPE.caption}px;line-height:18px;color:var(--dsp-t1);word-break:break-all}
.dsp-addrBtns{display:flex;align-items:center;gap:6px;flex:0 0 auto}

/* ---- 两栏：局域网 / 公网（等高；内容填满，不靠空白补齐）---- */
.dsp-duo{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));
  gap:16px;align-items:stretch}
.dsp-pane{display:flex;flex-direction:column;min-width:0;overflow:hidden;
  border:var(--dsp-line);border-radius:var(--dsp-r-lg);background:var(--dsp-surface-1)}
.dsp-paneHead{display:flex;align-items:center;gap:10px;padding:10px 12px 10px 14px;
  border-bottom:var(--dsp-line);background:var(--dsp-inset)}
.dsp-paneTitle{display:flex;align-items:center;gap:8px;flex:1 1 auto;min-width:0;
  font-size:${TYPE.section}px;line-height:20px;font-weight:600}
.dsp-paneBody{display:flex;flex-direction:column;gap:14px;padding:16px 14px}
/* 二维码只能在白底上扫：这块底色两种主题下都固定为白，是语义要求不是偷懒。 */
.dsp-qrTile{align-self:center;display:grid;place-items:center;padding:8px;
  border:var(--dsp-line);border-radius:var(--dsp-r-md);background:#fff}
.dsp-qr{width:168px;height:168px;display:block;image-rendering:pixelated}
.dsp-qrEmpty{width:168px;height:168px;display:flex;flex-direction:column;
  align-items:center;justify-content:center;gap:6px;padding:0 12px;text-align:center;
  color:var(--dsp-t2);font-size:${TYPE.caption}px}
/* 关闭态：底色换成内嵌灰、描边改虚线 —— 一眼看出"这里现在没有码"。 */
.dsp-qrTile--off{background:var(--dsp-inset);border-style:dashed}
.dsp-qrOffTitle{font-size:${TYPE.body}px;line-height:20px;font-weight:600}
.dsp-qrOffNote{font-size:${TYPE.caption}px;line-height:18px}

/* ---- 表单行：标签 + 说明，1px 分隔线 ---- */
.dsp-field{display:flex;flex-direction:column;gap:8px;padding-top:14px;border-top:var(--dsp-line)}
.dsp-fieldHead{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
.dsp-label{font-size:${TYPE.body}px;line-height:20px;font-weight:500}
/* 小标记（路由、口令形态）：无描边，靠内嵌底色分层（照宿主 Tag 的做法）。 */
.dsp-chip{display:inline-flex;align-items:center;height:22px;padding:0 8px;
  border-radius:var(--dsp-r-sm);background:var(--dsp-inset-solid);
  color:var(--dsp-t2);font-family:var(--dsp-code);font-size:${TYPE.caption}px;line-height:18px;
  white-space:nowrap}
.dsp-tag{display:inline-flex;align-items:center;height:22px;padding:0 8px;
  border-radius:var(--dsp-r-sm);background:var(--dsp-inset);
  color:var(--dsp-t2);font-size:${TYPE.caption}px;line-height:18px;white-space:nowrap}
.dsp-value{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.dsp-value code{font-family:var(--dsp-code);font-size:${TYPE.body}px;line-height:20px;
  color:var(--dsp-t1);word-break:break-all}

/* ---- 输入控件：几何照宿主 Input（H32 / R12 / border-l4 描边 / bg-layer-1）---- */
.dsp-input,.dsp-select{height:32px;padding:0 10px;min-width:0;flex:1 1 160px;
  border:var(--dsp-line-strong);border-radius:var(--dsp-r-md);
  background:var(--dsp-surface-1);color:var(--dsp-t1);
  font:inherit;font-size:${TYPE.body}px;line-height:20px;
  transition:border-color var(--dsp-fast) var(--dsp-ease)}
/* placeholder：提示文字不该和已填内容同等重量，但必须**看得清** ——
   用 label-secondary（浅色 #61666b 约 7:1），不用更浅的一档。 */
.dsp-input::placeholder{color:var(--dsp-t2);opacity:1}
.dsp-input:hover:not(:disabled),.dsp-select:hover:not(:disabled){
  border-color:var(--dsw-alias-border-l4,rgba(0,0,0,.16))}
.dsp-input:focus,.dsp-select:focus{outline:none;border-color:var(--dsp-accent)}
.dsp-input:disabled,.dsp-select:disabled{opacity:.5;cursor:not-allowed}

/* ---- 开关：几何照宿主 Switch（36×20 轨道 / 16 圆钮 / 开=品牌色）---- */
.dsp-switch{position:relative;flex:0 0 auto;width:36px;height:20px;padding:2px;border:0;
  /* 关态轨道用宿主的 border-l3（浅 #0000001f / 深 #ffffff29）。 */
  border-radius:999px;
  background:var(--dsw-alias-border-l3,rgba(0,0,0,.16));cursor:pointer;
  transition:background-color var(--dsp-fast) var(--dsp-ease)}
.dsp-switch[aria-checked="true"]{background:var(--dsw-alias-brand-primary,var(--dsp-t1))}
/* 命中区外扩：轨道仍是宿主的 36×20，但可点范围撑到 44×32。
   用 ::before 而不是加大轨道本身 —— 尺寸是设计语言的一部分，命中区不是。 */
.dsp-switch::before{content:"";position:absolute;inset:-6px -4px;border-radius:999px}
.dsp-switch:disabled{opacity:.5;cursor:not-allowed}
/* 圆钮分两态，这条是照抄宿主时**漏掉的一半**：
     关态 → --dsw-alias-switch-thumb（浅 #fff / 深 #adb2b8）压在 l3 灰轨上
     开态 → --dsw-alias-label-primary-foreground（浅 #fff / 深 #0f1115）压在
            品牌色轨上（浅轨近黑→白钮 18.9:1；深轨近白→黑钮 17.9:1）
   之前两种状态都用 switch-thumb，深色主题下开态是 #adb2b8 压 #f9fafb = **2.04:1**
   —— 圆钮几乎融进轨道，只剩位置能猜出开关是开是关。 */
.dsp-knob{display:block;width:16px;height:16px;border-radius:50%;
  background:var(--dsw-alias-switch-thumb,#fff);
  transition:transform 120ms var(--dsp-ease)}
.dsp-switch[aria-checked="true"] .dsp-knob{
  background:var(--dsw-alias-label-primary-foreground,#fff);transform:translateX(16px)}

/* ---- 按钮：几何与层级照抄宿主 Button 原语 ----
   宿主 Button.module.css 的权威形态：
     .button  { border:none; border-radius:md; font-size:14px; line-height:22px;
                padding:0 14px; background:transparent; color:label-primary }
     .md      { height:36px }   .sm { height:28px; font-size:12px; line-height:18px;
                                     padding:0 10px; border-radius:sm }
     .primary { background:button-primary-fill; color:label-primary-foreground }
     .ghost:hover { background:interactive-bg-hover }
     .ghost:active { background:interactive-bg-active }
     .outline { border:.5px solid border-l3 }

   规则分工：**几何**写在联合选择器里，**底色/字色**每个变体各自一条 ——
   这样任何一条变体规则出问题，都只影响那一个变体，不会让整排按钮集体变透明
   （本轮之前正是"整条 .dsp-btn-primary 被注释吃掉"导致主按钮变成纯文字）。 */
.dsp-btn,.dsp-btn-primary,.dsp-btn-ghost,.dsp-btn-danger,.dsp-btn-outline{
  display:inline-flex;align-items:center;justify-content:center;gap:6px;
  height:36px;padding:0 14px;border:none;border-radius:var(--dsp-r-md);
  background:transparent;color:var(--dsp-t1);cursor:pointer;white-space:nowrap;
  font:inherit;font-size:${TYPE.section}px;line-height:22px;text-decoration:none;
  transition:background-color var(--dsp-fast) var(--dsp-ease),
    border-color var(--dsp-fast) var(--dsp-ease),color var(--dsp-fast) var(--dsp-ease)}
/* 默认按钮 = 宿主 .ghost：透明底，hover 才出底色。 */
.dsp-btn:hover:not(:disabled){background:var(--dsp-inset)}
.dsp-btn:active:not(:disabled){background:var(--dsp-active)}
/* 主按钮：底色与文字色**必须成对**取自宿主的两个令牌。
   --dsw-alias-brand-primary 的语义是"最高对比度的前景色"，两种主题下取值相反：
   浅色是近黑 #0f1115、深色是近白 #f9fafb。所以不能只拿底色再写死白字 ——
   深色下会变成白压白（约 1.02:1），视觉上只剩一个白色方块。
   宿主自己的 .button.primary 正是成对用的：
   background: var(--dsw-alias-button-primary-fill)
   color:      var(--dsw-alias-label-primary-foreground)  */
.dsp-btn-primary{background:var(--dsw-alias-button-primary-fill,var(--dsw-alias-brand-primary,#111318));
  color:var(--dsw-alias-label-primary-foreground,#fff)}
.dsp-btn-primary:hover:not(:disabled){
  background:var(--dsw-alias-button-primary-hover,var(--dsw-alias-brand-primary,#111318))}
.dsp-btn-ghost{color:var(--dsp-t2)}
.dsp-btn-ghost:hover:not(:disabled){background:var(--dsp-inset);color:var(--dsp-t1)}
.dsp-btn-ghost:active:not(:disabled){background:var(--dsp-active);color:var(--dsp-t1)}
/* 描边档（宿主 .outline）：底色仍透明，描边用 border-l3。
   层级由**填充**表达：实心 = 主操作，描边 = 次要操作。
   已知取舍：border-l3 在白底实测 1.32:1，够不上 WCAG 1.4.11 对图形的 3:1 —— 但这也是
   宿主自己 .outline 按钮的取值。拉到 3:1 要约 45% 的黑，等于换掉整套发丝线设计语言；
   而这一档的身份由填充与标签文字承担，不单独靠这条线。所以**跟随宿主**，在此记录。 */
.dsp-btn-outline{border:var(--dsp-line-strong)}
.dsp-btn-outline:hover:not(:disabled):not(.is-disabled){background:var(--dsp-inset)}
.dsp-btn-outline:active:not(:disabled):not(.is-disabled){background:var(--dsp-active)}
/* 危险档：保留描边。删节点 / 关公网是**不可逆**动作，只靠颜色区分对色觉障碍
   用户不成立（"颜色不是唯一信息载体"），描边是它唯一的非颜色线索。
   描边取 **err-text 的 70%**（不是原始的 err）：1px 边框属于图形，WCAG 1.4.11
   要求 ≥3:1，实测原始色 45% 只有 L 2.18 / D 1.88，等于画了条看不见的线。 */
.dsp-btn-danger{border:1px solid color-mix(in srgb,var(--dsp-err-text) 70%,transparent);
  color:var(--dsp-err-text)}
.dsp-btn-danger:hover:not(:disabled){background:color-mix(in srgb,var(--dsp-err) 10%,transparent)}
.dsp-btn-danger:active:not(:disabled){background:color-mix(in srgb,var(--dsp-err) 16%,transparent)}
.dsp-btn:disabled,.dsp-btn-primary:disabled,.dsp-btn-ghost:disabled,
.dsp-btn-danger:disabled,.dsp-btn-outline:disabled{opacity:.4;cursor:not-allowed}
/* <a> 没有 :disabled —— 用 .is-disabled 复刻"点不动"的观感与光标。
   为什么是 <a> 而不是 <button>：能点的时候它必须能**新开标签页 / 复制链接 /
   中键打开**，这些是 <button> + location.href 拼不出来的原生行为。 */
.dsp-btn.is-disabled{opacity:.4;cursor:not-allowed;pointer-events:auto}
.dsp-btn.is-disabled:hover{background:transparent}
/* 紧凑档：宿主 .sm（H28 / 12px / R8 / padding 0 10）—— 逐项对齐，不取近似值。 */
.dsp-btn-sm{height:28px;padding:0 10px;border-radius:var(--dsp-r-sm);
  font-size:${TYPE.caption}px;line-height:18px}
.dsp-btn:focus-visible,.dsp-btn-primary:focus-visible,.dsp-btn-ghost:focus-visible,
.dsp-btn-danger:focus-visible,.dsp-btn-outline:focus-visible,.dsp-switch:focus-visible,
.dsp-input:focus-visible,.dsp-select:focus-visible{
  outline:var(--dsp-focus);outline-offset:2px}

/* ---- 节点卡（对外发布的每条路由）---- */
.dsp-node{display:flex;flex-direction:column;gap:8px;padding:12px 14px;
  border:var(--dsp-line);border-radius:var(--dsp-r-md);
  transition:border-color var(--dsp-fast) var(--dsp-ease)}
.dsp-node:hover{border-color:var(--dsw-alias-border-l4,rgba(0,0,0,.16))}
.dsp-nodeHead{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap}
.dsp-nodeName{font-size:${TYPE.body}px;line-height:20px;font-weight:600}
.dsp-nodeMeta{font-size:${TYPE.caption}px;line-height:18px;color:var(--dsp-t2);word-break:break-all}
/* 上游地址用等宽：它是 127.0.0.1:8810 这种要逐字符核对的东西 */
.dsp-target{font-family:var(--dsp-code);color:var(--dsp-t1)}
.dsp-state{display:inline-flex;align-items:center;gap:6px;
  font-size:${TYPE.caption}px;line-height:18px;color:var(--dsp-t2)}
.dsp-state--on{color:var(--dsp-ok-text)}

/* ---- 警示 / 报错 / 输出 ---- */
.dsp-warn{display:flex;flex-direction:column;gap:4px;padding:12px 14px;
  border:var(--dsp-line);border-left:3px solid var(--dsp-warn-bar);
  border-radius:var(--dsp-r-md);
  background:color-mix(in srgb,var(--dsp-warn) 6%,transparent);
  font-size:${TYPE.caption}px;line-height:18px;color:var(--dsp-t2)}
.dsp-warnTitle{font-size:${TYPE.caption}px;font-weight:600;color:var(--dsp-warn-text)}
.dsp-inlineWarn{font-size:${TYPE.caption}px;line-height:18px;color:var(--dsp-warn-text)}
.dsp-error{font-size:${TYPE.caption}px;line-height:18px;color:var(--dsp-err-text);white-space:pre-wrap}
.dsp-pre{margin-top:6px;font-family:var(--dsp-code);font-size:${TYPE.caption}px;
  line-height:18px;color:var(--dsp-t2);white-space:pre-wrap;max-height:180px;overflow:auto}

/* ---- 确认弹框：照宿主 Dialog（R28 / bg-layer-2 / elevation-prominent）----
   只有代价重大的动作才用：关掉局域网会让同一 WiFi 下**已经打开**的手机立刻被
   403 挡在外面，而那一端的人不是决策者。 */
.dsp-modalMask{position:fixed;inset:0;z-index:1200;display:flex;
  align-items:center;justify-content:center;padding:24px;
  background:var(--dsw-alias-bg-mask-1,rgba(0,0,0,.24));
  backdrop-filter:var(--dsw-mask-blur,blur(2px))}
.dsp-modal{width:100%;max-width:420px;padding:22px 24px 24px;
  border:none;border-radius:var(--dsp-r-panel);
  background:var(--dsp-surface);
  box-shadow:var(--dsw-elevation-prominent,0 8px 32px rgba(0,0,0,.18))}
.dsp-modalTitle{font-size:${TYPE.title}px;line-height:24px;font-weight:600;margin-bottom:12px}
.dsp-modalTitle--warn{color:var(--dsp-warn-text)}
/* 肯定语气用 --dsp-ok（宿主 state-success），不是 brand-primary：
   brand-primary 的语义是"最高对比度前景色"，深浅两套主题下取值相反。 */
.dsp-modalTitle--ok{color:var(--dsp-ok-text)}
.dsp-modalBody{font-size:${TYPE.body}px;line-height:22px;color:var(--dsp-t1)}
.dsp-modalBody p{margin:0 0 8px}
.dsp-modalBody p:last-child{margin-bottom:0}
.dsp-modalActions{display:flex;gap:8px;margin-top:20px}
/* 两个按钮等宽、同一高度：确认键的主次由**填充**表达（实心 vs 描边），
   不由宽度表达 —— 宽度不等会被读成"一个主操作 + 一个附属链接"。 */
.dsp-modalActions > .dsp-btn,
.dsp-modalActions > .dsp-btn-primary,
.dsp-modalActions > .dsp-btn-danger{flex:1 1 0;min-width:0;justify-content:center}
/* 取消键直接用 .dsp-btn-outline（描边档）：默认档是透明底，在弹框上几乎看不见
   边界，和实心的确认键并排时像"取消这两个字掉在空白里"。
   原先这里是 bespoke 的 .dsp-modalCancel，三条规则与 .dsp-btn-outline 完全重复
   —— 重复的档位会各自漂移，所以只留 outline 一份。 */
/* 确认键的"中性未就绪"档：前置条件没满足（比如免责声明还没勾）。
   用 inset 底 + 次级字色 —— 明显不是主操作，但也不带危险语义。 */
.dsp-modalConfirmMuted{background:var(--dsp-inset);color:var(--dsp-t2)}
/* 勾选行：文案与勾选框一行，14px 正文（照宿主 .acknowledgement 的行高 22）。 */
.dsp-checkline{display:flex;align-items:flex-start;gap:8px;margin-top:12px;
  cursor:pointer;line-height:22px;font-size:${TYPE.body}px}
.dsp-checkline input{flex:0 0 auto;width:16px;height:16px;margin:3px 0 0;
  accent-color:var(--dsw-alias-brand-primary,var(--dsp-accent));cursor:pointer}
.dsp-checkline:focus-within{outline:var(--dsp-focus);outline-offset:2px;border-radius:var(--dsp-r-sm)}

/* ---- Toast：逐项照宿主 Toast（顶部居中 / R16 / 14px 22 / shadow-lv3）----
   宿主原文：
     ._toast\{ position:fixed; top:40px; left:50%; z-index:1100; pointer-events:none;
       display:flex; align-items:center; gap:10px; width:max-content;
       max-width:min(640px, calc(100vw - 48px)); padding:12px 16px;
       border-radius:var(--dsw-radius-lg); background:var(--dsw-alias-toast-bg);
       color:var(--dsw-alias-toast-label); font-size:14px; line-height:22px;
       box-shadow:var(--dsw-shadow-lv3); transform:translate(-50%); \}
   兜底值取宿主 --dsw-shadow-lv3 的真实值（不是随手写的黑阴影）。 */
.dsp-toast{position:fixed;top:40px;left:50%;transform:translate(-50%);z-index:1100;
  pointer-events:none;display:flex;align-items:center;gap:10px;
  width:max-content;max-width:min(640px,calc(100vw - 48px));
  padding:12px 16px;border-radius:var(--dsp-r-lg);
  background:var(--dsw-alias-toast-bg,#353638);
  color:var(--dsw-alias-toast-label,#fff);
  font-size:${TYPE.section}px;line-height:22px;
  box-shadow:var(--dsw-shadow-lv3,0 0 1px 0 rgba(0,0,0,.2),0 0 4px 0 rgba(0,0,0,.02),0 12px 32px 0 rgba(0,0,0,.08));
  animation:dsp-toast-in 160ms ease-out}
@keyframes dsp-toast-in{from{opacity:0;transform:translate(-50%,-6px)}
  to{opacity:1;transform:translate(-50%,0)}}

/* ---- 窄屏：面板在窄栏 / 手机上塌成单栏，二维码缩小 ---- */
@media (max-width:760px){
  .dsp-card{padding:16px}
  .dsp-heroMeta{margin-left:0;width:100%}
  .dsp-ctaGrid{grid-template-columns:1fr;gap:16px}
  .dsp-duo{grid-template-columns:1fr}
  .dsp-qr,.dsp-qrEmpty{width:148px;height:148px}
}
@media (prefers-reduced-motion:reduce){
  .dsp-switch,.dsp-knob,.dsp-node,.dsp-input,.dsp-select,
  .dsp-btn,.dsp-btn-primary,.dsp-btn-ghost,.dsp-btn-danger,.dsp-btn-outline{transition:none}
  .dsp-toast{animation:none}
}
`;

// 注入（或刷新）本插件的 <style>。为什么查重而不是直接 append：
// 面板可能被重新挂载（切页面/改设置），无脑 append 会越堆越多；
// workbuddy 用同一个 data-plugin-css 标记做幂等，这里照做。
if (typeof document !== "undefined") {
  try {
    const existing = document.querySelector('style[data-plugin-css="' + CSS_ID + '"]');
    if (existing) {
      existing.textContent = CARD_CSS;
    } else {
      const tag = document.createElement("style");
      tag.dataset.plugin = name;
      tag.dataset.pluginCss = CSS_ID;
      tag.textContent = CARD_CSS;
      document.head.appendChild(tag);
    }
  } catch (err) {
    // 注入失败不能让整个面板挂掉（样式没了也能用，只是不好看）
    if (typeof console !== "undefined" && console.error) {
      console.error("[dsh-service-portal] 注入样式失败（面板仍可用）:", err);
    }
  }
}

// ============================================================================
// 颜色与几何**不再有 JS 侧常量**
// ============================================================================
//
// 改由上面那份注入的 CARD_CSS 独占。为什么把它从 JS 里搬走：内联样式的优先级
// 高于类选择器 —— 内联一旦写了底色，CSS 里的 :hover / :disabled /
// [aria-checked] 规则就成了**死代码**。早先四个按钮"点了没反应"、开关"切了没
// 过渡"、disabled 只变淡不变灰，根因都是这个；而"路径改了但内联没改"这类漂移
// 只有真的渲染出来才看得见。
//
// 令牌的坑记在这里（原 COLOR 常量的注释，删常量时一并保留下来）：
//   · 面板里用过的 4 个令牌里有**不存在**的拼写（`-label-tertiary`、
//     `-state-warning-primary`），它们永远命不中，于是一直吃写死的**浅色**兜底，
//     深色模式下就成了浅色主题的颜色（对比度不足、按钮发白）。
//   · `--dsw-alias-bg-layer-1/2/3` 在浅色主题里是**同一个白**，拿它做层级等于
//     没做。要"浮起来"用 `--dsw-alias-interactive-bg-hover` 这类带透明的层，
//     或者干脆用 0.5px 发丝线 + 白底。
//   · 圆角只用 `--dsw-radius-*` 六档（4/8/12/16/20/28），尺寸照宿主原语：
//     Button H36/R12（紧凑 H28/R8）、Input H32/R12、Switch 36×20。

function fmtTime(text) {
  if (!text) return "";
  return String(text);
}

// 开关（对齐宿主的 Switch 原语：36×20 轨道 + 16 圆钮，开=品牌色）。
//
// 几何与状态色全在 .dsp-switch / .dsp-knob 里，靠 `aria-checked` 选外观 ——
// 这样"视觉状态"与"屏幕阅读器读到的状态"不可能不一致（宿主 Switch 同样的做法）。
// 这里只传一个**无障碍名字**：labels 由调用点给，组件本身没有默认值，
// 免得出现一个只有视觉、没有名字的开关。
//
// `aria-checked` 显式写成字符串 "true"/"false"（不是布尔）：CSS 的
// [aria-checked="true"] 只认字符串，而把布尔交给渲染层去转是**看不出差别**的
// 一层间接 —— 预览 harness 正好在这一点上与真实 React 不同（它把 true 渲染成
// 空属性），于是"开着的开关画成关"这种错会一路骗到截图。显式写死，两边都对。
function Switch(on, onClick, label, disabled) {
  return h("button", {
    type: "button", role: "switch",
    "aria-checked": on ? "true" : "false",
    "aria-label": label, title: label,
    disabled: !!disabled,
    className: "dsp-switch",
    onClick: disabled ? undefined : onClick,
  }, h("span", { className: "dsp-knob" }));
}

/**
 * 确认弹框（默认导出为 null，只在 open 时渲染）。
 *
 * 只给**代价重大且会波及他人**的动作用（目前只有"关闭局域网访问"）：
 * 关掉之后，同一 WiFi 下已经打开着的手机立刻被 403 挡在外面，而那一端的人
 * 既不是决策者、也看不到开关。普通设置项的改错当场可逆，不该弹框稀释它。
 *
 * tone 决定标题颜色：warn = 正在收窄访问（关闭），ok = 正在放开（开启）。
 *
 * 正文用 `lines`（字符串数组）+ 可选 `extra`（额外节点），不用 children：
 * 数组直接当 children 会变成嵌套数组 —— React 能渲染，但预览 harness 的
 * render() 不处理嵌套数组，截图里正文就是空的。产品本身没错，但"预览看不见
 * 内容"会让以后每次核对话框都在盲改，所以这里统一拍平后再逐个渲染。
 */
function ConfirmDialog({ open, title, lines, extra, tone, confirmTone, confirmLabel, busy, onConfirm, onCancel }) {
  if (!open) return null;
  const body = [];
  (lines || []).forEach((text, i) => {
    if (text) body.push(h("p", { key: "ln" + i }, text));
  });
  if (extra) body.push(h("div", { key: "extra" }, extra));
  return h("div", {
    className: "dsp-modalMask",
    role: "presentation",
    // 点遮罩 = 取消（不变更任何东西）。键盘用户走「取消」按钮。
    onClick: (e) => { if (e.target === e.currentTarget && !busy) onCancel(); },
  },
    h("div", {
      className: "dsp-modal", role: "dialog", "aria-modal": "true",
      "aria-label": title,
      onKeyDown: (e) => {
        if (e.key === "Escape" && !busy) onCancel();
      },
    },
      h("div", {
        className: "dsp-modalTitle"
          + (tone === "ok" ? " dsp-modalTitle--ok" : "")
          + (tone === "warn" ? " dsp-modalTitle--warn" : ""),
      }, title),
      h("div", { className: "dsp-modalBody" }, body),
      h("div", { className: "dsp-modalActions" },
        h("button", {
          type: "button", className: "dsp-btn dsp-btn-outline", disabled: !!busy,
          onClick: onCancel,
        }, "取消"),
        h("button", {
          type: "button",
          // 确认按钮**永远**是实心，主次一眼分开：安全出口（取消）是描边，
          // 真正动手的那个是实心。
          //
          // 早先这里是 tone === "ok" ? primary : "dsp-btn" —— 于是"关闭局域网"
          // 的确认按钮落到了**默认透明档**，和「取消」长得一模一样（用户截图
          // 反馈「两个按钮看不清」）。
          //
          // 颜色由 confirmTone 单独决定，**不复用标题 tone**：
          // 标题在说"这件事的性质"（warn = 有风险），按钮在说"按下它会发生
          // 什么"。开公网那个框标题是 warn，但未勾选时按钮应是**禁用的中性
          // 态** —— 画成红色会被读成"点它很危险"，实际是"现在点不了"。
          //
          // muted（未满足前置条件）：用 inset 底色，和"能点的实心主操作"
          // 一眼区分，又不带危险语义。
          className: (function () {
            const t = confirmTone || tone;
            if (t === "muted") return "dsp-btn dsp-modalConfirmMuted";
            if (t === "warn") return "dsp-btn dsp-btn-danger";
            return "dsp-btn dsp-btn-primary";
          })(),
          // 前置条件没满足（muted）时它就该**真的点不动**，不只是看起来灰：
          // 否则用户点了没反应，会以为是 bug。onConfirm 里另有一道硬校验。
          disabled: !!busy || confirmTone === "muted", onClick: onConfirm,
        }, busy || confirmLabel || "确定"),
      ),
    ),
  );
}

function ServicePortalSettingsTab(props) {
  // 插件页会给 `view`：
  //   · `summary` —— 只渲染一行摘要（列表折叠态、或行入口的预览）
  //   · `page`    —— 渲染完整配置页（含保存控件）
  // 这里两种都要能出东西，否则折叠态是一个空壳。
  const view = props && typeof props.view === "string" ? props.view : "page";
  const [status, setStatus] = React.useState(null);
  const [busy, setBusy] = React.useState("");
  const [error, setError] = React.useState(null);
  const [output, setOutput] = React.useState(null);
  const [showPassword, setShowPassword] = React.useState(true);

  // 二维码：按地址缓存（地址不变就不重复要，避免每次轮询都打门户口）
  const [qrs, setQrs] = React.useState({});

  // 地址「复制」后的短暂反馈（"已复制" → 1.5 秒后恢复）
  const [copied, setCopied] = React.useState("");
  const copyTimer = React.useRef(null);
  const copyText = (key, text) => {
    const done = () => {
      setCopied(key);
      if (copyTimer.current) clearTimeout(copyTimer.current);
      copyTimer.current = setTimeout(() => setCopied(""), 1500);
    };
    // 面板可能跑在非安全上下文（http 内网地址）里，clipboard API 会不可用 ——
    // 那种情况退回 execCommand，保证「复制」按钮永远真的能复制。
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, () => fallbackCopy(text) && done());
        return;
      }
    } catch { /* 落到 fallback */ }
    if (fallbackCopy(text)) done();
  };
  const fallbackCopy = (text) => {
    try {
      const area = document.createElement("textarea");
      area.value = text;
      area.setAttribute("readonly", "");
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      const ok = document.execCommand("copy");
      document.body.removeChild(area);
      return ok;
    } catch { return false; }
  };
  // 局域网访问密码开关（默认关 = 免密）
  const [lanAuth, setLanAuth] = React.useState(null);
  // 局域网访问总开关（默认开）
  const [lanEnabled, setLanEnabled] = React.useState(true);
  // **局域网口令**（与公网口令分开）：内网短数字好输，公网长随机串抗爆破。
  // 早先这里显示的是公网 password，于是手机在 WiFi 下要输 16 位随机串。
  const [lanPassword, setLanPassword] = React.useState("");
  // 是否已自定义（自定义后开启公网不再自动轮换，要告知用户）
  const [lanPinCustom, setLanPinCustom] = React.useState(false);
  // 自定义局域网口令输入态
  const [customOpen, setCustomOpen] = React.useState(false);
  const [customValue, setCustomValue] = React.useState("");
  const [customErr, setCustomErr] = React.useState("");
  // 公网口令：是否用户自定义的（自定义后开启公网不再自动轮换，要提示）
  const [publicPinCustom, setPublicPinCustom] = React.useState(false);
  // 自定义**公网**口令输入态（与局域网那套并列、互不干扰）
  const [pubCustomOpen, setPubCustomOpen] = React.useState(false);
  const [pubCustomValue, setPubCustomValue] = React.useState("");
  const [pubCustomErr, setPubCustomErr] = React.useState("");
  // 高级：手动选地址
  const [advOpen, setAdvOpen] = React.useState(false);
  // 局域网访问开关的待确认状态：null = 没有弹框，true/false = 准备切到的目标状态。
  // 开关本身**先不改**——点一下只是打开确认框，改了再回滚会让同一 WiFi 上的
  // 手机在确认之前就已经被 403 挡了一瞬。
  const [lanToggleAsk, setLanToggleAsk] = React.useState(null);
  // 开启公网的免责声明：必须**勾选**才能开（框里的说明文字不算数，勾选才算）。
  // 与局域网的确认框刻意强度不同——见 requestPublicStart 的注释。
  const [pubDisclaimerOpen, setPubDisclaimerOpen] = React.useState(false);
  const [pubDisclaimerOk, setPubDisclaimerOk] = React.useState(false);
  // 手动选定的网卡地址（'' = 自动按网卡评分选）
  const [lanIp, setLanIp] = React.useState("");
  // 地址提示（"选定的地址不在当前网卡上"等）—— 不能静默吞掉
  const [lanNote, setLanNote] = React.useState("");
  // ============ 服务管理（原控制台的功能，搬进设置页）============
  //
  // 用户要求：在插件设置里管理"节点"（对外发布的路由），不再需要独立控制台。
  //
  // 状态说明：
  //   services  —— 节点清单（来自 status.services，随 5 秒轮询自动更新）
  //   addOpen   —— 手动添加表单是否展开
  //
  // 已按用户要求删掉的：自动发现（"取消自动发现服务的功能"）、
  // 「刷新」按钮（"不用刷新也不用搜索"）。清单本来就会自动更新。
  const [addOpen, setAddOpen] = React.useState(false);
  const [addForm, setAddForm] = React.useState(
    { name: "", mount: "", target: "", note: "" });
  const [addErr, setAddErr] = React.useState("");
  const [editKey, setEditKey] = React.useState("");
  const [editForm, setEditForm] = React.useState(
    { name: "", mount: "", target: "", note: "" });
  const [editErr, setEditErr] = React.useState("");
  // Toast：操作后的即时反馈
  const [toast, setToast] = React.useState("");

  // Toast：操作后的即时反馈（2.6 秒自动消失，与 dsh-pocket 一致）。
  // 没有它的时候，开关一切换界面就变，用户不确定「到底保存成功没有」。
  const toastTimer = React.useRef(null);
  const showToast = (text) => {
    setToast(String(text));
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(""), 2600);
  };

  const request = async (path, method, body) => {
    const res = await fetch(API + path, {
      method: method || "GET",
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const text = await res.text();
    let json = null;
    try { json = JSON.parse(text); } catch { /* 非 JSON */ }
    if (!res.ok && !json) throw new Error(`HTTP ${res.status}: ${text.slice(0, 200)}`);
    return json;
  };

  const load = async () => {
    try {
      const s = await request("/status");
      setStatus(s);
      if (s && s.ok === false && s.problem) setError(s.problem);
      else setError(null);
      if (s && s.kind === "portal") {
        setLanAuth(Boolean(s.lanAuthEnabled));
        setLanEnabled(s.lanEnabled !== false);
        setLanPassword(s.lanPassword || "");
        setLanPinCustom(Boolean(s.lanPinCustom));
        setPublicPinCustom(Boolean(s.publicPinCustom));
        setLanIp(s.lanIpOverride || "");
        setLanNote(s.lanNote || "");
      }
    } catch (e) {
      setError(String(e && e.message ? e.message : e));
    }
  };

  const loadQr = async (url) => {
    if (!url) return;
    try {
      const r = await request("/qr?url=" + encodeURIComponent(url));
      if (r && r.ok && r.qr) {
        setQrs((prev) => (prev[url] ? prev : Object.assign({}, prev, { [url]: r.qr })));
      }
    } catch { /* 二维码取不到不影响主要功能 */ }
  };

  React.useEffect(() => {
    load();
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, []);

  // 地址一出来就取二维码（只取没取过的）
  const lanPrimary = status && status.lanUrls && status.lanUrls[0];
  const publicUrl = status && status.publicUrl;
  React.useEffect(() => { if (lanPrimary && !qrs[lanPrimary]) loadQr(lanPrimary); },
    [lanPrimary]);
  React.useEffect(() => { if (publicUrl && !qrs[publicUrl]) loadQr(publicUrl); },
    [publicUrl]);

  // ---- 节点管理：添加 / 开放屏蔽 / 编辑 / 删除 ----
  //
  // 全部走宿主的转发路由（宿主再转给门户）。为什么不让面板直接打门户：
  // 面板在 DSH 的浏览器上下文里，而门户可能因为「局域网访问已关闭」或
  // 口令而被拦；走宿主就没这层不确定性（宿主永远从 127.0.0.1 调门户）。
  const services = (status && status.services) || [];

  // 节点的**两条入口**：内网（局域网地址）与公网（隧道地址）。
  // 为什么用门户地址拼而不是上游地址：用户要的是"点一下就能用这个服务"，
  // 而对外可用的入口是**门户的路由**（上游 127.0.0.1:2460 只有本机能开）。
  //
  // 为什么必须分成两个按钮（用户要求）：一个「访问」只能猜"用哪条"，而两条
  // 通道的开关**互相独立** —— 关掉局域网后内网打不开但公网仍可用，没开公网
  // 时公网按钮则毫无意义。合成一个按钮就只能要么给死链、要么给一条不一定是
  // 用户想走的路。
  const serviceUrls = (svc) => {
    const mount = String((svc && svc.mount) || "").replace(/^\//, "");
    const path = mount ? "/" + mount + "/" : "/";
    // 内网用当前选中的局域网地址（lanPrimary）；没探测到就退回本机回环
    // （本机访问永远可用，见后端 lane 判定）。
    const lanBase = lanPrimary || ("http://127.0.0.1:" + port);
    return {
      lan: lanBase + path,
      pub: publicUrl ? publicUrl + path : "",
    };
  };

  const submitAdd = async () => {
    setAddErr("");
    const name = addForm.name.trim();
    const mount = addForm.mount.trim();
    const target = addForm.target.trim();
    // 本地先挡一层，省一次往返（服务端仍有权威校验）
    if (!name) { setAddErr("名称不能为空"); return; }
    if (!mount) { setAddErr("路由路径不能为空（以 / 开头）"); return; }
    if (!/^[^:]+:\d+$/.test(target)) {
      setAddErr("上游地址要写成 host:端口，例如 127.0.0.1:8810");
      return;
    }
    setBusy("svc-add");
    try {
      const r = await request("/services/add", "POST",
        { name, mount, target, note: addForm.note.trim() });
      if (!r || r.ok !== true) throw new Error((r && r.error) || "添加失败");
      setAddForm({ name: "", mount: "", target: "", note: "" });
      setAddOpen(false);
      showToast("已添加服务 " + name);
      await load();
    } catch (e) {
      setAddErr(String(e && e.message ? e.message : e));
    } finally { setBusy(""); }
  };

  const serviceAction = async (key, action, label) => {
    setBusy("svc-" + key);
    try {
      const r = await request("/services/" + encodeURIComponent(key) + "/" + action,
        "POST", action === "update" ? editForm : {});
      if (!r || r.ok !== true) throw new Error((r && r.error) || (label + "失败"));
      showToast(label + "成功");
      if (action === "update") setEditKey("");
      await load();
    } catch (e) {
      setError(String(e && e.message ? e.message : e));
    } finally { setBusy(""); }
  };

  // ---- 局域网访问密码开关（立即生效，不重启门户）----
  const setLanAuthEnabled = async (on) => {
    setLanAuth(on);            // 乐观更新，失败再回滚
    try {
      const r = await request("/settings", "POST", { lanAuthEnabled: on });
      if (!r || !r.ok) throw new Error((r && r.error) || "保存失败");
      showToast(on ? "局域网已需要口令" : "局域网已改为免密");
      await load();
    } catch (e) {
      setLanAuth(!on);
      setError(String(e && e.message ? e.message : e));
    }
  };

  // ---- 局域网访问总开关（关掉后同一 WiFi 也进不来；公网不受影响）----
  //
  // 两步：点开关 -> 弹确认框（见 requestLanToggle）-> 确认后才真正 POST。
  // 为什么要确认：关掉之后，同一 WiFi 下**已经打开着的手机**立刻被 403 挡在
  // 外面，而那一端的人既不是决策者、也看不到这个开关。开启方向提示的是
  // "手机将可以扫码访问"，同样值得说明 —— 两个方向各一套文案，不是一句
  // "确定吗"。
  const requestLanToggle = (on) => setLanToggleAsk(on);

  const setLanEnabledFlag = async (on) => {
    setLanToggleAsk(null);
    setBusy("lan-enabled");
    setLanEnabled(on);         // 乐观更新，失败再回滚
    try {
      const r = await request("/settings", "POST", { lanEnabled: on });
      if (!r || !r.ok) throw new Error((r && r.error) || "保存失败");
      showToast(on ? "已开启局域网访问" : "已关闭局域网访问");
      await load();
    } catch (e) {
      setLanEnabled(!on);
      setError(String(e && e.message ? e.message : e));
    } finally { setBusy(""); }
  };

  // ---- 手动选地址（空 = 回自动）----
  const setLanIpOverride = async (value) => {
    const previous = lanIp;
    setLanIp(value);
    try {
      const r = await request("/settings", "POST", { lanIpOverride: value });
      if (!r || !r.ok) throw new Error((r && r.error) || "保存失败");
      showToast(value ? ("已固定为 " + value) : "已回到自动选择");
      await load();
    } catch (e) {
      setLanIp(previous);
      setError(String(e && e.message ? e.message : e));
    }
  };

  // 保存自定义**局域网**口令（6–12 位数字）。
  // 与公网口令分开：早先这里设的是公网 fixedPassword，改的其实是公网口令 ——
  // 用户在「局域网访问密码」区块里操作，改到的却是另一个东西。
  const saveCustomPin = async () => {
    setCustomErr("");
    const value = customValue.trim();
    // 本地先挡一层，省一次往返；服务端仍有权威校验（不信任前端）
    if (!/^\d+$/.test(value)) {
      setCustomErr("只能是数字（手机上好输入）");
      return;
    }
    if (value.length < LAN_PIN_MIN || value.length > LAN_PIN_MAX) {
      setCustomErr("需要 " + LAN_PIN_MIN + "–" + LAN_PIN_MAX + " 位数字");
      return;
    }
    setBusy("lan-custom");
    try {
      const r = await request("/lan-pin/custom", "POST", { value });
      if (!r || r.ok !== true) throw new Error((r && r.error) || "保存失败");
      setLanPassword(r.lan_password);
      setLanPinCustom(true);
      setCustomOpen(false);
      setCustomValue("");
      setShowPassword(true);
      showToast("已设置自定义局域网口令");
      await load();
    } catch (e) {
      setCustomErr(String(e && e.message ? e.message : e));
    } finally { setBusy(""); }
  };

  // 保存自定义**公网**口令。体验与局域网对称（对齐 dsh-pocket issue #33）：
  // 局域网是 6–12 位手输数字，公网同样"想设什么就设什么"，只是**更长**
  // （≥12 位，公网面对整个互联网）。不限制字符种类 —— 用户要求体验一致。
  const savePublicPin = async () => {
    setPubCustomErr("");
    const value = pubCustomValue.trim();
    // 本地先挡（省一次往返）；服务端仍有权威校验（不信任前端）
    if (value.length < PUBLIC_PIN_MIN) {
      setPubCustomErr("至少 " + PUBLIC_PIN_MIN + " 位（公网要求比局域网长）");
      return;
    }
    setBusy("pub-custom");
    try {
      const r = await request("/public-pin/custom", "POST", { value });
      if (!r || r.ok !== true) throw new Error((r && r.error) || "保存失败");
      setShowPassword(true);
      setPubCustomOpen(false);
      setPubCustomValue("");
      showToast("已设置自定义公网密码");
      await load();
    } catch (e) {
      setPubCustomErr(String(e && e.message ? e.message : e));
    } finally { setBusy(""); }
  };

  // 换回随机轮换（取消自定义）。没有这个出口，用户自定义一次之后
  // 「每次开启公网自动换新」就永远回不来了。
  const backToRandomPublic = async () => {
    setPubCustomErr("");
    setBusy("pub-random");
    try {
      const r = await request("/public-pin/random", "POST", {});
      if (!r || r.ok !== true) throw new Error((r && r.error) || "操作失败");
      setPublicPinCustom(false);
      setShowPassword(true);
      showToast("已换回随机口令（每次开公网自动换新）");
      await load();
    } catch (e) {
      setPubCustomErr(String(e && e.message ? e.message : e));
    } finally { setBusy(""); }
  };

  // 开启公网：**必须勾选免责声明**才执行。
  //
  // 为什么这个比局域网的确认框更重（一处勾选 + 按钮禁用）：
  // 两个方向的代价根本不对等。关局域网是"收窄"，影响的是同一 WiFi 里那几个人，
  // 而且改回来只要一次点击；开公网是**把一台能执行代码的机器暴露到整个互联网**，
  // 且地址可能被别人复用。所以：
  //   · 局域网 = 读两行字点「确定」（轻确认，防手滑）；
  //   · 公网   = 必须主动勾选才能点「开启」（重确认，防没读就点）。
  // 这不是"体验不一致"，而是让确认强度随代价增长——反过来（公网随便点、
  // 局域网反而弹框）才是真的不一致。
  const requestPublicStart = () => {
    setPubDisclaimerOk(false);
    setPubDisclaimerOpen(true);
  };

  const confirmPublicStart = () => {
    if (!pubDisclaimerOk) return;      // 未勾选：按钮本来就 disabled，这里再挡一层
    setPubDisclaimerOpen(false);
    doStart(false);
  };

  const doStart = async (lanOnly) => {
    setBusy(lanOnly ? "start-lan" : "start"); setError(null); setOutput(null);
    try {
      // 公网启动必须带 disclaimer:true —— 宿主侧会**校验**它（防绕过前端）。
      // 只内网启动不暴露公网，所以不带也不需要。
      const r = await request("/start", "POST",
        lanOnly ? { lanOnly: true } : { disclaimer: true });
      setOutput(r);
      if (r && r.status) setStatus(r.status);
      if (!r || r.ok !== true) {
        setError("启动失败（退出码 " + (r && r.exitCode) + "）"
          + (r && r.stderr ? "\n" + String(r.stderr).slice(-600) : ""));
      } else { await load(); }
    } catch (e) {
      setError(String(e && e.message ? e.message : e));
    } finally { setBusy(""); }
  };

  // 关闭公网：**只关隧道**，内网访问继续可用。
  // 早先这里调 doStop（停掉整个门户）—— 语义错了：用户点「关闭公网」是想收起
  // 对外暴露，不该顺带把内网的二维码也弄失效。
  const doStopTunnel = async () => {
    setBusy("tunnel-stop"); setError(null);
    try {
      const r = await request("/tunnel/stop", "POST", {});
      if (!r || r.ok !== true) throw new Error((r && (r.error || r.detail)) || "关闭失败");
      showToast("已关闭公网访问");
      await load();
    } catch (e) {
      setError(String(e && e.message ? e.message : e));
    } finally { setBusy(""); }
  };

  // doStop 已删除：它唯一的调用方是「门户进程」那块 UI，而那块已按用户要求移除。
  // 现在门户随 DSH 退出自动收尾（lib/index.js registerPortalTeardown），
  // 前端不再有"停掉整个门户"这个动作。
  // 「关闭公网访问」仍在，走 doStopTunnel（见上），语义不同：只收隧道、不碰门户。

  const running = Boolean(status && status.running);
  const password = status && status.password;
  const port = (status && status.portalPort) || 8899;

  // ---- view=summary：插件列表行只要一行摘要 ----------------------------------
  //
  // 行入口（plugins.row.config）与 bundle 卡片的折叠态都用它；在那里渲染完整
  // 表单会很怪，所以先判掉。
  if (view === "summary") {
    if (!status) return h("span", { className: "dsp-hint" }, "对外服务门户");
    const n = ((status && status.services) || []).length;
    const bits = [];
    bits.push(status.port ? ("对外服务门户（" + status.port + " 端口）") : "对外服务门户");
    if (running) {
      bits.push(n + " 个节点");
      if (status.publicUrl) bits.push("公网已开");
      else if ((status.lanUrls || []).length) bits.push("局域网可用");
      // 口令形态要按字符串判：宿主给的是 "random"/"fixed" 两个字面量，
      // 写成 truthy 判断的话**两种形态都会显示"固定口令"**（本轮顺手修掉）。
      bits.push(status.passwordMode === "fixed" ? "固定口令" : "随机口令");
    } else {
      bits.push("未运行");
    }
    return h("span", null, bits.join(" · "));
  }

  // ---- 两个入口栏共用的小件 ------------------------------------------------
  //
  // 地址块的形态只做一套：等宽地址 + 「访问」+「复制」。局域网与公网只是内容
  // 不同，形态必须一致，否则同一屏里两种地址块会被读成两种东西。
  const addrRow = (url, copyKey, withAccess, hint) => [
    h("div", { key: "addr-" + copyKey, className: "dsp-addr" },
      h("code", null, url),
      // 按钮组整体不换行：地址再长也只换地址自己，两个按钮始终并排。
      h("span", { className: "dsp-addrBtns" },
        withAccess
          ? h("a", {
              key: "go", className: "dsp-btn dsp-btn-primary dsp-btn-sm",
              href: url, target: "_blank", rel: "noreferrer",
            }, "访问")
          : null,
        h("button", {
          key: "copy", type: "button", className: "dsp-btn dsp-btn-sm",
          onClick: () => copyText(copyKey, url),
        }, copied === copyKey ? "已复制" : "复制"),
      ),
    ),
    hint ? h("p", { key: "hint-" + copyKey, className: "dsp-hint" }, hint) : null,
  ];

  // 二维码块：取不到时也必须占住同样大小，否则加载完成后面板会跳一下。
  //
  // `off`：局域网访问被关掉时**不能照常显示二维码** —— 那张码扫了必然打不开
  // （门户会拒绝），显示它就等于误导用户去扫一个死码。旧版在这里显示"已关闭"
  // 并淡化；改造中一度退回"二维码生成中…"（缓存命中时甚至会把旧码显示出来），
  // 所以把这个状态显式做成一个参数，而不是靠调用点自己判断。
  const qrTile = (url, alt, off) => h("div", {
    key: "qr-" + url,
    className: off ? "dsp-qrTile dsp-qrTile--off" : "dsp-qrTile",
  },
    off
      ? h("div", { className: "dsp-qrEmpty" },
          h("span", { className: "dsp-qrOffTitle" }, "已关闭"),
          h("span", { className: "dsp-qrOffNote" }, "打开右上角开关后出现二维码"))
      : (qrs[url]
          ? h("img", { src: qrs[url], alt, className: "dsp-qr" })
          : h("div", { className: "dsp-qrEmpty" }, "二维码生成中…")));

  // 空态右栏的三条清单（"启动后你会得到什么"）。
  const stepItem = (num, title, desc) => h("li", { key: "step-" + num, className: "dsp-step" },
    h("span", { className: "dsp-stepNum" }, num),
    h("span", null,
      h("b", { className: "dsp-stepTitle" }, title),
      h("span", { className: "dsp-stepDesc" }, desc),
    ),
  );

  // 换一个新的**随机数字**局域网口令（对齐 dsh-pocket 的 lanTokenRefresh）。
  // 提成具名函数只是为可读性，行为与原来内联时一致。
  const refreshLanPin = async () => {
    setBusy("lan-pin");
    try {
      const r = await request("/lan-pin/refresh", "POST", {});
      if (!r || r.ok !== true) throw new Error((r && r.error) || "刷新失败");
      setLanPassword(r.lan_password);
      setLanPinCustom(false);
      setShowPassword(true);
      showToast("已生成新的局域网口令");
      await load();
    } catch (e) {
      setError(String(e && e.message ? e.message : e));
    } finally { setBusy(""); }
  };

  const children = [];

  // ============ 顶部：身份 + 当前状态 ============
  //
  // 标题是本插件的身份文案：**「对外服务门户」**。别照抄 dsh-pocket 的标题 ——
  // 它叫「手机访问」是因为它整个插件就是干这个的；我们的使命是"把本机服务对外
  // 发布并统一管理"，扫码只是其中一种入口（上一轮"对齐参考对象"时抄错过一次）。
  children.push(h("div", { key: "hero", className: "dsp-hero" },
    h("img", {
      key: "logo", src: SERVICE_PORTAL_PLUGIN_ICON, alt: "对外服务门户",
      width: 44, height: 44, className: "dsp-logo",
    }),
    h("div", { key: "text", className: "dsp-heroText" },
      h("h4", { className: "dsp-title" }, "对外服务门户"),
      h("p", { className: "dsp-sub" },
        "手机扫码打开的就是门户控制台，在那里管理要开放的服务"),
    ),
    h("div", { key: "meta", className: "dsp-heroMeta" },
      // 状态放右上：打开这一页最先要知道的就是"它到底在不在跑"。
      h("span", { key: "state", className: running ? "dsp-pill dsp-pill--on" : "dsp-pill" },
        h("span", { className: "dsp-dot" }),
        running ? "运行中" : "已停止"),
      // 这里**不显示端口号**（用户要求）：端口在地址里已经写着（http://…:8899），
      // 单独再挂一个"端口 8899"胶囊是同一件事说两遍，而且它既不是状态、用户也
      // 改不了（改端口要改插件配置，不在这页）。端口仍然保留在状态数据里：
      // 下面的地址、摘要行、以及"没探测到局域网地址"时的本机回环提示都用它。
      // 「启动于」只在运行中显示：停着的时候写"启动于 …"自相矛盾。
      running && status && status.startedAt
        ? h("span", { key: "since", className: "dsp-pill" },
            "启动于 " + fmtTime(status.startedAt))
        : null,
      h("a", {
        key: "star", className: "dsp-link", href: REPO_URL,
        target: "_blank", rel: "noreferrer",
        title: "去 GitHub 给这个项目留颗 Star",
      }, "鼓励一下 ★"),
    ),
  ));

  const body = [];

  // ============ 前置条件：缺什么、怎么装，动手之前就说 ============
  //
  // 用户反馈的核心就是这一块此前**完全不存在**：装好插件什么都不说，
  // 点「启动并开公网」才失败，只留一句"找不到 cloudflared"。
  //
  // 分级呈现（不是所有缺失都同等严重）：
  //   · 缺 python  -> 内网都起不来，用警示块（红黄系），这是硬阻塞；
  //   · 缺 cloudflared -> 只影响公网，内网照常，用行内提示（更轻）。
  // 混成一种样式会让"其实只是没装隧道工具"看起来像"整个插件坏了"。
  //
  // 判定来源是服务端的 checkPrereqs（/status 里带出来），前端不自己探 ——
  // 探测逻辑只写一处，否则两边结论不一致时用户不知道该信谁。
  const prereqs = status && status.prereqs;
  // 没拿到 prereqs（老宿主/状态还没回来）时一律认作"可用"：
  // 宁可让用户点了去试，也不能因为探测本身没跑出来就把按钮锁死 ——
  // 那是把"不知道"当成"不行"，比不检测更糟。
  const pyReady = !prereqs || !prereqs.python || prereqs.python.ok !== false;
  const cfReady = !prereqs || !prereqs.cloudflared || prereqs.cloudflared.ok !== false;
  if (prereqs && Array.isArray(prereqs.missing) && prereqs.missing.length) {
    if (!prereqs.python || !prereqs.python.ok) {
      body.push(h("div", { key: "pre-python", className: "dsp-warn" },
        h("div", { className: "dsp-warnTitle" }, "缺少 Python 3，门户无法启动"),
        h("div", null, String(prereqs.python.detail || "")),
      ));
    }
    if (!prereqs.cloudflared || !prereqs.cloudflared.ok) {
      body.push(h("p", { key: "pre-cf", className: "dsp-inlineWarn" },
        String(prereqs.cloudflared.detail || "找不到 cloudflared")));
    }
  } else if (prereqs && prereqs.python && prereqs.python.detail) {
    // 全部就绪、但配置里填的路径有问题（比如填了不存在的 python 路径，
    // 已自动回落）。这种"能用但不完全是你以为的那个"必须说出来，
    // 否则用户不知道自己指定的解释器其实没被用上。
    body.push(h("p", { key: "pre-note", className: "dsp-inlineWarn" },
      String(prereqs.python.detail)));
  }

  // ============ 未启动：讲清"会发生什么"，只留该做的事 ============
  //
  // 未启动时**不画**局域网/公网两栏：那时候栏里只有一句"门户未启动"，两块并排
  // 的空盒子比一句话更占地方、也更像没做完。
  //
  // 也**不预告地址**（用户要求："没有启动的时候，这两个不要显示，显示也没意义"）。
  // 这条是对的，而且不只是"没意义"——那些地址是**猜**的：状态文件里存的是上次
  // 启动时选的网卡，而真正用哪个地址要等启动后按网卡评分重算。实测这一屏会把
  // 198.18.0.1（VPN/虚拟网卡，插件自己的评分规则把它排在最后）也列出来，用户
  // 照着它去配手机，那就是一条查不出来的错线索。地址一律"启动后再说"。
  if (!running) {
    body.push(h("div", { key: "off", className: "dsp-cta" },
      h("div", { className: "dsp-ctaGrid" },
        h("div", { className: "dsp-ctaMain" },
          h("h5", { className: "dsp-secTitle" }, "门户未启动"),
          h("p", { className: "dsp-lede" },
            "启动后，手机连上同一 WiFi 打开门户控制台就能管理要开放的服务；"
            + "也可以同时开一个公网地址，人不在家时用。内网地址与二维码会在"
            + "启动后显示在这块位置。"),
          h("div", { className: "dsp-actions" },
            // 缺 Python 时**禁用**启动，而不是让用户点了再失败。
            // 判定已经在上面显示成警示块了；按钮还亮着等于邀请用户去撞墙，
            // 撞完得到的错误（spawn ENOENT / "拉不起门户"）远不如上面那句
            // "请安装 Python 3" 有用。禁用时用 title 说明原因 —— 灰按钮
            // 不说话的话，用户会以为是插件卡住了。
            h("button", {
              key: "start-lan", type: "button", className: "dsp-btn dsp-btn-primary",
              disabled: !!busy || !pyReady,
              title: pyReady ? undefined : "缺少可用的 Python 3，无法启动门户",
              onClick: () => doStart(true),
            }, busy === "start-lan" ? "启动中…" : "启动（只内网）"),
            // 缺 cloudflared 只挡"开公网"这一条路。内网那条必须留着 ——
            // 没装隧道工具不影响本机/局域网使用，不能因此把主功能也判死。
            h("button", {
              key: "start-pub", type: "button", className: "dsp-btn",
              disabled: !!busy || !pyReady || !cfReady,
              title: !pyReady ? "缺少可用的 Python 3，无法启动门户"
                : (!cfReady ? "缺少 cloudflared，无法开启公网访问（可先只启动内网）" : undefined),
              onClick: () => doStart(false),
            }, busy === "start" ? "启动中…" : "启动并开公网"),
            h("button", {
              key: "refresh", type: "button", className: "dsp-btn dsp-btn-ghost",
              onClick: load,
            }, "刷新"),
          ),
          h("p", { className: "dsp-hint" },
            "启动后是常驻进程；停止后地址失效，设置与口令保留。"),
          // 状态与"下次会不会自己回来"是两件事，必须分开说（否则用户停完门户，
          // 下次开 DSH 看到它又起来了，会以为插件在自作主张）。
          // 宿主没透出 autoStart（老版本）时整句不出现 —— 不猜、不编。
          status && typeof status.autoStart === "boolean"
            ? h("p", { className: "dsp-hint" },
                status.autoStart
                  ? "下次打开 DSH 会自动启动（只开内网，公网仍要手动开）。"
                  : "你上次停掉了它：下次打开 DSH 不会自动启动，需要时点上面的按钮。")
            : null,
        ),
        h("div", null,
          h("div", { className: "dsp-asideLabel" }, "启动后你会得到"),
          h("ul", { className: "dsp-steps" },
            stepItem("1", "局域网地址 + 二维码", "同一 WiFi 下扫码即开，默认免密"),
            stepItem("2", "公网随机域名", "自带口令，人不在家也能打开"),
            stepItem("3", "扫码进入控制台", "在那里增删要开放的节点"),
          ),
        ),
      ),
    ));
  }

  // ============ 运行中：局域网 / 公网两条入口并排 ============
  if (running) {
    // 手动选地址的候选网卡（自动选择按网卡性质评分，选错了手机连不上）
    const candidates = (status && status.lanCandidates) || [];

    // ---- 局域网栏 ----
    const lanBody = [];

    // 关闭态：**整块换掉内容**，不保留二维码/地址/口令/高级那一整套。
    //
    // 为什么是替换而不是灰掉（学 dsh-pocket 的 issue #54 做法）：
    //   · 灰掉之后，用户看到的是一堆"不可用"的东西 + 一句解释说明它们为什么
    //     不可用 —— 屏幕上三分之二是死的，他还得自己在两处之间建立联系；
    //   · 现在后端是真的 403，二维码扫出来只会得到一张"已关闭"的页面。
    //     把一个确定打不开的二维码继续摆在最显眼的位置，是在骗人。
    // 所以关闭态只有三件事：说清现状、说清影响范围、给回开关的入口。
    if (lanEnabled !== true) {
      lanBody.push(h("div", { key: "lan-off", className: "dsp-warn" },
        h("div", { className: "dsp-warnTitle" }, "局域网访问已关闭"),
        h("div", null,
          "同一 WiFi 下的手机现在打开会直接看到「已关闭」，"
          + "不是口令错误。公网访问不受这个开关影响。"),
        h("div", null,
          "已打开的手机页面不会自动恢复，重新开启后刷新即可。"),
      ));
      if (lanPrimary) {
        lanBody.push(h("p", { key: "lan-off-url", className: "dsp-hint" },
          "恢复后地址仍是 " + lanPrimary + "（地址不随开关变化）。"));
      }
      // **内容区不放"开启"按钮** —— 与公网栏统一：开关只有一个入口，
      // 就在标题行右角。
      //
      // 之前这里放过一个「开启局域网访问」实心按钮，用户在同一屏里看到
      // 两个能开启它的东西（顶栏开关 + 这个按钮），读起来像两个不同的功能。
      // 公网栏的形态是：标题行右侧 = 动作，内容区 = 说明与结果。两边照这个来。
      // 与公网栏同一个句式（"点右上…"）：两边都是"动作在标题行、说明在内容区"。
      lanBody.push(h("p", { key: "lan-off-act", className: "dsp-hint" },
        "点右上角的开关即可重新开启。"));
    } else if (lanPrimary) {
      lanBody.push(qrTile(lanPrimary, "局域网二维码"));
      lanBody.push(...addrRow(lanPrimary, "lan", true,
        "手机连接同一 WiFi 后扫码即可打开"));
    } else {
      lanBody.push(h("p", { key: "lan-none", className: "dsp-hint" },
        "没探测到局域网地址（可能没连 WiFi 或只有回环）。"
        + "本机可用 http://127.0.0.1:" + port));
    }

    // 以下三项只在**开启态**才渲染：关着的时候它们既不可用、也不需要被看见。
    if (lanEnabled === true) {
    // 局域网访问密码：默认关（内网免密），开了才显示口令。
    // **与公网口令分开**：内网要短数字好手输，公网要长随机串抗爆破。
    lanBody.push(h("div", { key: "lan-pin", className: "dsp-field" },
      h("div", { className: "dsp-fieldHead" },
        h("div", null,
          h("div", { className: "dsp-label" }, "局域网访问密码"),
          h("div", { className: "dsp-hint" },
            lanAuth === true
              ? "已开启：同一 WiFi 打开也要输口令"
              : "已关闭：同一 WiFi 扫码直连（公网仍要口令）"),
        ),
        Switch(lanAuth === true, () => setLanAuthEnabled(lanAuth !== true), "局域网访问密码"),
      ),
      lanAuth === true
        ? h("div", { key: "lan-pin-value", className: "dsp-value" },
            h("code", null, showPassword
              ? (lanPassword || "(无)")
              : "•".repeat((lanPassword || "").length)),
            h("button", {
              type: "button", className: "dsp-btn dsp-btn-sm",
              onClick: () => setShowPassword(!showPassword),
            }, showPassword ? "隐藏" : "显示"),
            h("button", {
              type: "button", className: "dsp-btn dsp-btn-sm",
              disabled: busy === "lan-pin", onClick: refreshLanPin,
            }, busy === "lan-pin" ? "刷新中…" : "刷新"),
            !customOpen
              ? h("button", {
                  type: "button", className: "dsp-btn dsp-btn-sm",
                  onClick: () => { setCustomOpen(true); setCustomErr(""); },
                }, "自定义")
              : null,
          )
        : null,
      // 自定义后不再自动轮换 —— 明确告知，否则用户会疑惑"为什么开启公网没换掉它"
      lanAuth === true && lanPinCustom
        ? h("p", { key: "lan-pin-note", className: "dsp-inlineWarn" },
            "自定义后开启公网不再自动换。")
        : null,
      customOpen
        ? h("div", { key: "lan-custom", className: "dsp-row" },
            h("input", {
              type: "text", className: "dsp-input", value: customValue,
              placeholder: "局域网新口令（6–12 位数字）", autoComplete: "off",
              inputMode: "numeric", maxLength: LAN_PIN_MAX, autoFocus: true,
              "aria-label": "局域网新口令",
              // 只留数字：局域网口令是给人拿手机手输的，允许字母/符号只会让人输错
              onChange: (e) => setCustomValue(e.target.value.replace(/\D/g, "")),
              onKeyDown: (e) => {
                if (e.key === "Enter") saveCustomPin();
                if (e.key === "Escape") { setCustomOpen(false); setCustomErr(""); }
              },
            }),
            h("button", {
              type: "button", className: "dsp-btn dsp-btn-primary dsp-btn-sm",
              disabled: busy === "lan-custom", onClick: saveCustomPin,
            }, busy === "lan-custom" ? "保存中…" : "保存"),
            h("button", {
              type: "button", className: "dsp-btn dsp-btn-sm",
              onClick: () => { setCustomOpen(false); setCustomErr(""); },
            }, "取消"),
            customErr ? h("span", { className: "dsp-error" }, customErr) : null,
          )
        : null,
    ));

    // 高级：手动选地址。多网卡机器（VPN / 虚拟网卡 / WSL）上自动选也可能选错，
    // 而症状是"扫码打不开"——极难自查，所以给候选 + 网卡名，用户一眼能认。
    lanBody.push(h("div", { key: "lan-adv", className: "dsp-field" },
      h("div", { className: "dsp-fieldHead" },
        h("button", {
          type: "button", className: "dsp-btn dsp-btn-ghost dsp-btn-sm",
          "aria-expanded": advOpen ? "true" : "false",
          onClick: () => setAdvOpen(!advOpen),
        }, "高级 · 手动选地址 " + (advOpen ? "▾" : "›")),
        h("span", { className: "dsp-hint" }, lanIp || "自动（推荐）"),
      ),
      advOpen
        ? h("div", { className: "dsp-row" },
            h("span", { className: "dsp-label" }, "局域网地址"),
            h("select", {
              className: "dsp-select", value: lanIp || "", "aria-label": "局域网地址",
              onChange: (e) => setLanIpOverride(e.target.value),
            },
              h("option", { value: "" }, "自动（推荐）"),
              candidates.map((ip) => h("option", { key: ip, value: ip }, ip)),
            ),
          )
        : null,
      advOpen && !candidates.length
        ? h("p", { key: "adv-none", className: "dsp-hint" },
            "没探测到可用的局域网地址（可能没连网线 / WiFi）。")
        : null,
      advOpen
        ? h("p", { key: "adv-note", className: "dsp-hint" },
            "自动选择会按网卡性质评分：物理网卡优先，VPN / 虚拟网卡（如 198.18.x）"
            + "排后。选错了手机就连不上。")
        : null,
    ));
    }  // if (lanEnabled === true)

    // ---- 公网栏 ----
    const pubBody = [];
    if (publicUrl) {
      pubBody.push(qrTile(publicUrl, "公网二维码"));
      pubBody.push(...addrRow(publicUrl, "public", true, "人在外面也能打开（需要口令）"));
      pubBody.push(h("div", { key: "pub-pin", className: "dsp-field" },
        h("div", { className: "dsp-fieldHead" },
          h("div", null,
            h("div", { className: "dsp-label" }, "公网访问密码"),
            h("div", { className: "dsp-hint" },
              publicPinCustom
                ? "已自定义：开启公网不再自动换新（只有你知道它）"
                : "每次开启公网都会换新（想固定就点「自定义」）"),
          ),
          h("span", { className: "dsp-tag" },
            publicPinCustom ? "自定义" : "本次随机"),
        ),
        password
          ? h("div", { key: "pub-pin-value", className: "dsp-value" },
              h("code", null, showPassword ? password : "•".repeat(password.length)),
              h("button", {
                type: "button", className: "dsp-btn dsp-btn-sm",
                onClick: () => setShowPassword(!showPassword),
              }, showPassword ? "隐藏" : "显示"),
              h("button", {
                type: "button", className: "dsp-btn dsp-btn-sm",
                onClick: () => copyText("pub-pin", password),
              }, copied === "pub-pin" ? "已复制" : "复制"),
              // 与局域网对称：口令行末尾一个「自定义」
              !pubCustomOpen
                ? h("button", {
                    type: "button", className: "dsp-btn dsp-btn-sm",
                    onClick: () => { setPubCustomOpen(true); setPubCustomErr(""); },
                  }, "自定义")
                : null,
              // 自定义后回不去 —— 给出「换回随机」出口，否则这个状态是单向的
              publicPinCustom && !pubCustomOpen
                ? h("button", {
                    type: "button", className: "dsp-btn dsp-btn-sm",
                    disabled: busy === "pub-random", onClick: backToRandomPublic,
                  }, busy === "pub-random" ? "换回中…" : "换回随机")
                : null,
            )
          : null,
        pubCustomOpen
          ? h("div", { key: "pub-custom", className: "dsp-stack" },
              h("div", { className: "dsp-row" },
                h("input", {
                  type: "text", className: "dsp-input", value: pubCustomValue,
                  placeholder: "公网新密码（至少 " + PUBLIC_PIN_MIN + " 位，含字母或符号）",
                  autoComplete: "off", maxLength: 64, autoFocus: true,
                  "aria-label": "公网新密码",
                  onChange: (e) => setPubCustomValue(e.target.value.replace(/\s/g, "")),
                  onKeyDown: (e) => {
                    if (e.key === "Enter") savePublicPin();
                    if (e.key === "Escape") { setPubCustomOpen(false); setPubCustomErr(""); }
                  },
                }),
                h("button", {
                  type: "button", className: "dsp-btn dsp-btn-primary dsp-btn-sm",
                  disabled: busy === "pub-custom", onClick: savePublicPin,
                }, busy === "pub-custom" ? "保存中…" : "保存"),
                h("button", {
                  type: "button", className: "dsp-btn dsp-btn-sm",
                  onClick: () => { setPubCustomOpen(false); setPubCustomErr(""); },
                }, "取消"),
              ),
              pubCustomErr ? h("p", { className: "dsp-error" }, pubCustomErr) : null,
              // 公网自定密码的风险提示：不用 emoji 当结构图标（规范要求），
              // "这是警告"由左侧色条 + 加粗标题承担。
              h("div", { className: "dsp-warn" },
                h("div", { className: "dsp-warnTitle" }, "公网密码会被互联网上的人尝试"),
                h("div", null,
                  "请勿使用你在别处用过的密码，也不要太短。改完立即生效，"
                  + "不用重开公网（地址与二维码不变）；但已登录的设备不会被踢下线，"
                  + "要彻底作废旧密码请点「关闭公网」再重新开启。"),
              ),
            )
          : null,
      ));
    } else {
      // 未开启时的右栏：说清"怎么开""开出来是什么"以及"它有什么风险"。
      // 不写"点上方按钮"——它就在这一栏的右上角，说"右上"更准。
      //
      // 为什么这里要写到三块而不是两句话：两栏现在**等高**（见 .dsp-duo 的注释），
      // 左栏有二维码占位，内容天然高；右栏若只有两行字，等高之后下半截就是一片
      // 空白。与其让盒子不一样高（那会露出 324px 的缺口，实测过），不如把这块
      // 空间用来讲清"开启公网"到底意味着什么 —— 这几条本来就是用户开启前
      // 应该知道、而原先藏在上方通栏警告里的话。
      pubBody.push(h("p", { key: "pub-none", className: "dsp-hint" },
        "未开启。点右上「开启公网访问」建立一个随机公网地址（需本机有 cloudflared）。"));
      pubBody.push(h("p", { key: "pub-none-2", className: "dsp-hint" },
        "给的不是固定域名：每次开启都会变，关闭或重启后失效，所以每次都要扫这一次的二维码。"));
      // 未开启时也把"开启后要注意什么"摆在眼前：开公网是**对外暴露**，
      // 把风险留到开启之后再显示，等于让用户先做完决定才看到代价。
      pubBody.push(h("div", { key: "pub-none-steps", className: "dsp-field" },
        h("div", { className: "dsp-label" }, "开启前你需要知道"),
        h("ul", { className: "dsp-steps" },
          stepItem("1", "地址会被互联网上的人访问到",
            "拿到口令的人可以增删、开放或屏蔽你发布的节点。"),
          stepItem("2", "口令每次开启都会换新",
            "只有你知道当前口令；想固定下来可以点「自定义」。"),
          stepItem("3", "不用时请关掉",
            "关闭公网只收起对外入口，同一 WiFi 的访问不受影响。"),
        ),
      ));
    }

    body.push(h("div", { key: "duo", className: "dsp-duo" },
      h("section", { key: "lan", className: "dsp-pane" },
        h("div", { className: "dsp-paneHead" },
          h("div", { className: "dsp-paneTitle" },
            h("span", { className: lanEnabled ? "dsp-dot dsp-dot--on" : "dsp-dot" }),
            "局域网访问",
          ),
          // 开关只**打开确认框**，不直接改状态：关掉会让同一 WiFi 下已经打开
          // 的手机立刻被 403 挡住，而那一端的人看不到这个开关。
          Switch(lanEnabled, () => requestLanToggle(!lanEnabled), "局域网访问",
            busy === "lan-enabled"),
        ),
        h("div", { className: "dsp-paneBody" }, lanBody),
      ),
      h("section", { key: "pub", className: "dsp-pane" },
        h("div", { className: "dsp-paneHead" },
          h("div", { className: "dsp-paneTitle" },
            h("span", { className: publicUrl ? "dsp-dot dsp-dot--on" : "dsp-dot" }),
            "公网访问",
          ),
          // 门户没在跑时不放这个按钮（那时该做的是先启动门户），所以这里
          // 只可能是"开公网"或"关公网"两种真实动作。
          publicUrl
            ? h("button", {
                type: "button", className: "dsp-btn dsp-btn-danger dsp-btn-sm",
                disabled: !!busy, onClick: doStopTunnel,
              }, busy === "tunnel-stop" ? "关闭中…" : "关闭公网")
            : h("button", {
                type: "button", className: "dsp-btn dsp-btn-primary dsp-btn-sm",
                disabled: !!busy,
                // 先弹免责声明，勾选后才真开 —— 见 requestPublicStart 的注释
                onClick: requestPublicStart,
              }, busy === "start" ? "开启中…" : "开启公网访问"),
        ),
        h("div", { className: "dsp-paneBody" }, pubBody),
      ),
    ));

    // 公网风险：通栏放在两栏**下面**，不塞进公网那一栏 —— 塞进去会把那栏撑高、
    // 左边留一大片空白，读起来还像是"公网栏的一部分"。
    //
    // 这里**不能**写"可以启停你开放的服务"：启停能力在 0.8.2 已按用户要求取消
    // （只做路由闸门），照抄旧文案会夸大风险、也让人以为插件能操作进程。
    if (publicUrl) {
      body.push(h("div", { key: "pub-risk", className: "dsp-warn" },
        h("div", { className: "dsp-warnTitle" }, "公网暴露风险"),
        h("div", null,
          "地址是随机 trycloudflare 域名，每次开启都会变、关闭或重启后失效，"
          + "并可能被他人复用为陌生网站 —— 请勿收藏，每次从本页扫「当前」二维码。"
          + "拿到口令的人可以增删、开放或屏蔽你发布的节点，但动不了上游程序。"
          + "不用时请点上方「关闭公网」。"),
      ));
    }

    // ============ 对外发布的节点 ============
    //
    // 用户的要求（原话）："每个节点都有屏蔽和开放的开关，不是服务开启的开关"
    // "启动服务是服务本身的事情，这里只是负责可以路由" "每个设置的服务都要有一个
    // 点击直接打开的功能叫做访问" "取消自动发现服务的功能，不用刷新也不用搜索"。
    // 所以这一块只有三件事：添加节点 / 开放或屏蔽 / 访问。
    const blocked = services.filter((s) => s && s.enabled !== true).length;
    const down = services.filter(
      (s) => s && s.enabled === true && s.alive === false).length;
    const svcRows = [];

    if (!services.length) {
      svcRows.push(h("p", { key: "svc-none", className: "dsp-hint" },
        "还没有节点。点下面的「添加节点」把本机的一个端口发布出去。"));
    }

    // 每个节点一张卡：名称 + 路由 + 上游 + 访问 / 开放屏蔽 / 编辑 / 删除
    for (const svc of services) {
      const key = svc.key || svc.name || "";
      const open = svc.enabled === true;
      const alive = svc.alive !== false;
      const editing = editKey === key;

      svcRows.push(h("div", { key: "svc-" + key, className: "dsp-node" },
        h("div", { className: "dsp-nodeHead" },
          h("div", { className: "dsp-row" },
            h("span", { className: "dsp-nodeName" }, String(svc.name || key)),
            h("span", { className: "dsp-chip" }, String(svc.mount || "")),
          ),
          // 状态只说**路由**的开放与否；上游通不通另用一行提示，两者不混。
          h("span", { className: open ? "dsp-state dsp-state--on" : "dsp-state" },
            h("span", { className: open ? "dsp-dot dsp-dot--on" : "dsp-dot" }),
            open ? "开放中" : "已屏蔽",
          ),
        ),
        h("div", { className: "dsp-nodeMeta" },
          "转发到 ",
          h("span", { className: "dsp-target" }, String(svc.target || "")),
          svc.note ? " · " + String(svc.note) : ""),
        // 上游没响应只是**提示**：它解释"为什么访问打不开"，
        // 但不影响这条路由本身的开放/屏蔽（那是两件事）。
        open && !alive
          ? h("p", { key: "svc-down", className: "dsp-inlineWarn" },
              "上游没响应 —— 请先把 " + String(svc.target || "")
              + " 上的程序启动起来（本插件不负责启动它）。")
          : null,
        editing
          ? h("div", { key: "svc-edit", className: "dsp-stack" },
              h("div", { className: "dsp-row" },
                h("input", {
                  className: "dsp-input", value: editForm.name, placeholder: "名称",
                  "aria-label": "节点名称",
                  onChange: (e) => setEditForm(Object.assign({}, editForm,
                    { name: e.target.value })),
                }),
                h("input", {
                  className: "dsp-input", value: editForm.mount, placeholder: "/路由",
                  "aria-label": "路由路径",
                  onChange: (e) => setEditForm(Object.assign({}, editForm,
                    { mount: e.target.value })),
                }),
              ),
              h("div", { className: "dsp-row" },
                h("input", {
                  className: "dsp-input", value: editForm.target,
                  placeholder: "127.0.0.1:8810", "aria-label": "上游地址",
                  onChange: (e) => setEditForm(Object.assign({}, editForm,
                    { target: e.target.value })),
                }),
                h("input", {
                  className: "dsp-input", value: editForm.note,
                  placeholder: "备注（可选）", "aria-label": "备注",
                  onChange: (e) => setEditForm(Object.assign({}, editForm,
                    { note: e.target.value })),
                }),
              ),
              editErr ? h("p", { className: "dsp-error" }, editErr) : null,
              h("div", { className: "dsp-row" },
                h("button", {
                  type: "button", className: "dsp-btn dsp-btn-primary dsp-btn-sm",
                  disabled: busy === "svc-" + key,
                  onClick: async () => {
                    setEditErr("");
                    if (!editForm.name.trim() || !editForm.mount.trim()
                        || !editForm.target.trim()) {
                      setEditErr("名称、路由、上游都不能为空");
                      return;
                    }
                    await serviceAction(key, "update", "保存");
                  },
                }, busy === "svc-" + key ? "保存中…" : "保存"),
                h("button", {
                  type: "button", className: "dsp-btn dsp-btn-sm",
                  onClick: () => { setEditKey(""); setEditErr(""); },
                }, "取消"),
              ),
            )
          : h("div", { key: "svc-act", className: "dsp-row" },
              // 两条入口各一个按钮，**各自判断自己的开关**。
              //
              // 禁用而不是隐藏：隐藏的话用户会以为"这个节点没有公网入口"，
              // 而实际是"公网还没开"。禁用 + 一个说得清的 title，用户才知道
              // 该去哪里把那个开关打开。
              //
              // 屏蔽时两个都不给（路由确实不转发，给了就是死链）。
              open
                ? h("a", {
                    key: "go-lan",
                    className: lanEnabled === true
                      ? "dsp-btn dsp-btn-primary dsp-btn-sm"
                      : "dsp-btn dsp-btn-sm is-disabled",
                    href: lanEnabled === true ? serviceUrls(svc).lan : undefined,
                    target: "_blank", rel: "noreferrer",
                    "aria-disabled": lanEnabled === true ? "false" : "true",
                    title: lanEnabled === true
                      ? "内网打开：同一 WiFi 下可用（" + serviceUrls(svc).lan + "）"
                      : "局域网访问已关闭 —— 先在「局域网访问」里打开开关",
                    onClick: lanEnabled === true ? undefined
                      : (e) => e.preventDefault(),
                  }, "内网访问")
                : null,
              open
                ? h("a", {
                    key: "go-pub",
                    className: publicUrl
                      ? "dsp-btn dsp-btn-sm dsp-btn-outline"
                      : "dsp-btn dsp-btn-sm is-disabled",
                    href: publicUrl ? serviceUrls(svc).pub : undefined,
                    target: "_blank", rel: "noreferrer",
                    "aria-disabled": publicUrl ? "false" : "true",
                    title: publicUrl
                      ? "公网打开：任何网络可用（需要公网口令）"
                      : "公网访问未开启 —— 先点「开启公网访问」",
                    onClick: publicUrl ? undefined : (e) => e.preventDefault(),
                  }, "公网访问")
                : null,
              h("button", {
                key: "gate", type: "button", className: "dsp-btn dsp-btn-sm",
                disabled: !!busy,
                onClick: () => serviceAction(key,
                  open ? "block" : "open", open ? "屏蔽" : "开放"),
              }, open ? "屏蔽" : "开放"),
              h("button", {
                key: "edit", type: "button", className: "dsp-btn dsp-btn-sm",
                disabled: !!busy,
                onClick: () => {
                  setEditKey(key);
                  setEditErr("");
                  setEditForm({
                    name: String(svc.name || ""), mount: String(svc.mount || ""),
                    target: String(svc.target || ""), note: String(svc.note || ""),
                  });
                },
              }, "编辑"),
              h("button", {
                key: "del", type: "button", className: "dsp-btn dsp-btn-danger dsp-btn-sm",
                disabled: !!busy,
                onClick: () => {
                  // 删除是不可撤销的：必须确认
                  if (typeof window !== "undefined" && window.confirm
                      && !window.confirm("删除节点「" + (svc.name || key)
                        + "」？路由 " + (svc.mount || "") + " 会立即失效。")) {
                    return;
                  }
                  serviceAction(key, "delete", "删除");
                },
              }, "删除"),
            ),
      ));
    }

    body.push(h("section", { key: "services", className: "dsp-sec" },
      h("div", { className: "dsp-secHead" },
        h("h5", { className: "dsp-secTitle" }, "对外发布的节点"),
        h("span", { className: "dsp-secNote" },
          services.length + " 个"
          + (blocked ? " · " + blocked + " 个已屏蔽" : "")
          + (down ? " · " + down + " 个上游未响应" : "")),
      ),
      h("p", { className: "dsp-hint" },
        "这里只管门户要不要把请求转过去；上游程序请用它自己的方式启动。"),
      ...svcRows,
      // 工具行只剩「添加节点」（用户要求去掉刷新与自动发现）
      h("div", { key: "svc-tools", className: "dsp-actions" },
        h("button", {
          type: "button",
          className: addOpen ? "dsp-btn" : "dsp-btn dsp-btn-primary",
          disabled: !!busy,
          onClick: () => { setAddOpen(!addOpen); setAddErr(""); },
        }, addOpen ? "取消" : "添加节点"),
      ),
      addOpen
        ? h("div", { key: "add", className: "dsp-node" },
            h("div", { className: "dsp-label" }, "添加节点"),
            h("div", { className: "dsp-row" },
              h("input", {
                className: "dsp-input", value: addForm.name,
                placeholder: "名称，例如：训练配置台", "aria-label": "节点名称",
                autoFocus: true,
                onChange: (e) => setAddForm(Object.assign({}, addForm,
                  { name: e.target.value })),
              }),
              h("input", {
                className: "dsp-input", value: addForm.mount,
                placeholder: "/rltrain（对外路径）", "aria-label": "路由路径",
                onChange: (e) => setAddForm(Object.assign({}, addForm,
                  { mount: e.target.value })),
              }),
            ),
            h("div", { className: "dsp-row" },
              h("input", {
                className: "dsp-input", value: addForm.target,
                placeholder: "127.0.0.1:8810（本机端口）", "aria-label": "上游地址",
                onKeyDown: (e) => { if (e.key === "Enter") submitAdd(); },
                onChange: (e) => setAddForm(Object.assign({}, addForm,
                  { target: e.target.value })),
              }),
              h("input", {
                className: "dsp-input", value: addForm.note,
                placeholder: "备注（可选）", "aria-label": "备注",
                onChange: (e) => setAddForm(Object.assign({}, addForm,
                  { note: e.target.value })),
              }),
            ),
            addErr ? h("p", { className: "dsp-error" }, addErr) : null,
            h("div", { className: "dsp-row" },
              h("button", {
                type: "button", className: "dsp-btn dsp-btn-primary dsp-btn-sm",
                disabled: busy === "svc-add", onClick: submitAdd,
              }, busy === "svc-add" ? "添加中…" : "添加节点"),
            ),
            h("p", { className: "dsp-hint" },
              "添加后默认就是「开放」；上游程序要你自己启动（这里只负责路由）。"),
          )
        : null,
    ));

    // ============ 门户进程：整块已删除 ============
    //
    // 用户："这个服务本身就随 dsh 打开和关闭的，不需要再有设置，太啰嗦。"
    //
    // 原来这里有一块「门户进程」：`停止门户` + `刷新` + 一句后果说明。
    // 它存在的前提是**门户脱离 DSH 独立常驻** —— 那时能开不能关就只能去杀进程，
    // 所以必须给个入口。现在这个前提没了：插件在 dispose / SIGINT / SIGTERM
    // 时会把门户一起收掉（见 lib/index.js 的 registerPortalTeardown），
    // 生命周期完全跟随 DSH，用户不再需要（也不该）手动管这个进程。
    //
    // 「刷新」也一并删：面板本来就在轮询 /status，没有它也能自动更新；
    // 留一个手动兜底入口只会让用户以为"状态是手动拉才准"。
    //
    // 注意：**不是**删掉"关闭公网访问"—— 那个按钮在上面公网栏里，语义是
    // "收起对外暴露"，与"停掉本机门户进程"是两件不同的事。

    // 「局域网免密」是**跨栏**的全局安全姿态（不属于某一个入口栏），放页尾。
    // 公网风险已经写在上面通栏里了，这里不重复。
    if (lanAuth === false) {
      body.push(h("div", { key: "warn", className: "dsp-warn" },
        h("div", { className: "dsp-warnTitle" }, "局域网免密"),
        h("div", null,
          "同一 WiFi 下的设备无需口令即可打开，仅建议在可信网络下使用。"
          + "需要口令请打开上方「局域网访问密码」。"),
      ));
    }
  }

  // ---- 错误 / 提示 / 启动器输出：都放面板最后，按严重度排 ----
  if (error) {
    body.push(h("p", { key: "err", className: "dsp-error" }, String(error)));
  }
  // 地址提示（比如"选定的地址不在当前网卡上"）：不静默吞，用户要能看见
  if (lanNote) {
    body.push(h("p", { key: "lannote", className: "dsp-inlineWarn" }, String(lanNote)));
  }
  if (output && output.stdout && !running) {
    body.push(h("section", { key: "out", className: "dsp-sec" },
      h("div", { className: "dsp-label" }, "启动器输出"),
      h("pre", { className: "dsp-pre" }, String(output.stdout).slice(-1200)),
    ));
  }
  // status.problem 有两种性质，**不能一种样式糊过去**：
  //   · 还在跑 —— 只是提醒（比如"上游没响应"），一行提示就够；
  //   · 已经停了 —— 说明上次**没正常退出**（宿主的判定：只有没写 stoppedClean 才
  //     会带 problem；用户主动停掉的不算）。这是异常，得用警示块，别让用户
  //     在一堆灰字里把它读丢。
  if (status && status.problem) {
    body.push(running
      ? h("p", { key: "prob", className: "dsp-inlineWarn" }, String(status.problem))
      : h("div", { key: "prob", className: "dsp-warn" },
          h("div", { className: "dsp-warnTitle" }, "上次没有正常退出"),
          h("div", null, String(status.problem)),
        ));
  }

  children.push(h("div", { key: "body", className: "dsp-body" }, body));

  const card = h("div", { className: "dsp-card" }, children);

  // ---- 两个确认框 + Toast：都挂在根上（弹框用 fixed 定位，不受卡片布局影响）----
  //
  // 局域网：正在**收窄**访问 -> 警告色标题；正在**放开** -> 品牌色。
  // 两个方向各一套文案（照 dsh-pocket 的 lanToggleTitleOn/Off），不是一句
  // "确定吗"—— 用户需要在点之前知道对面那台手机会发生什么。
  const lanConfirm = h(ConfirmDialog, {
    open: lanToggleAsk !== null,
    tone: lanToggleAsk ? "ok" : "warn",
    title: lanToggleAsk ? "开启局域网访问" : "关闭局域网访问",
    confirmLabel: lanToggleAsk ? "开启" : "关闭",
    busy: busy === "lan-enabled",
    onCancel: () => setLanToggleAsk(null),
    onConfirm: () => setLanEnabledFlag(lanToggleAsk === true),
    lines: lanToggleAsk
      ? [
          "开启后，同一 WiFi 下的手机扫码即可打开门户控制台。",
          lanAuth === true
            ? "当前「局域网访问密码」是开启的，打开时仍要输口令。"
            : "当前「局域网访问密码」是关闭的：扫码直连，不再需要口令。",
          "公网访问不受这个开关影响。",
        ]
      : [
          "关闭后，同一 WiFi 下的手机打开会直接看到「已关闭」——"
            + "不是口令错误，输什么口令都进不来。",
          "已经打开着的手机会在下一次请求时被拦下；重新开启后刷新即可恢复。",
          "公网访问不受这个开关影响。",
        ],
  });

  // 公网：必须勾选才能点「开启」（比局域网重一档，理由见 requestPublicStart）
  const pubConfirm = h(ConfirmDialog, {
    open: pubDisclaimerOpen,
    tone: "warn",
    // 未勾选：按钮走中性禁用态（不是红色 —— 红色会被读成"点了有危险"，
    // 而实际是"现在根本点不了"）。勾选后才是真正的主操作（品牌实心）。
    confirmTone: pubDisclaimerOk ? "ok" : "muted",
    title: "开启公网访问前请确认",
    confirmLabel: pubDisclaimerOk ? "我已知情，开启公网" : "请先勾选",
    busy: busy === "start",
    onCancel: () => setPubDisclaimerOpen(false),
    onConfirm: confirmPublicStart,
    lines: [
      "开启公网 = 把这台电脑上的门户暴露到整个互联网。拿到地址和口令的人，"
        + "可以增删、开放或屏蔽你发布的节点。",
      "地址是随机域名，每次开启都会变、关闭或重启后失效，"
        + "并可能被他人复用为陌生网站 —— 请勿收藏，每次从本页扫当前二维码。",
      "不用时请及时关闭公网（关闭只收起对外入口，同一 WiFi 不受影响）。",
    ],
    // 勾选框：必须真勾上才能点「开启」—— 公网比局域网重一档，见 requestPublicStart
    // 样式走类名而不是内联：内联样式优先级高于类选择器，写死了就再也改不动
    // （而且与本文件"颜色/几何只出现在 CARD_CSS 里"的约定冲突）。
    extra: h("label", { key: "agree", className: "dsp-checkline" },
      h("input", {
        type: "checkbox", checked: pubDisclaimerOk,
        onChange: (e) => setPubDisclaimerOk(e.target.checked),
      }),
      h("span", null, "我了解上述风险，同意开启公网访问"),
    ),
  });

  const root = (children2) => h("div", { className: "dsp-root" }, children2);

  if (!toast && lanToggleAsk === null && !pubDisclaimerOpen) return card;
  return root([
    card,
    lanConfirm,
    pubConfirm,
    toast
      ? h("div", {
          key: "toast", className: "dsp-toast", role: "status", "aria-live": "polite",
        }, toast)
      : null,
  ]);
}

function apply(ctx) {
  // ============ 注册位置：插件页的「插件配置」，不是宿主设置导航 ============
  //
  // 用户要求：「插件设置要放到插件设置里，而不是出现在宿主的设置里，你看看
  // workbuddy 是怎么做的」。
  //
  // 我原来注册的是 `settings.section` —— 那是**宿主设置左侧导航的一整页**，
  // 于是「对外服务门户」和「通用 / 模型 / 插件 / 智能体预设」并列，看起来像
  // 宿主自带的功能，而不是这个插件的设置。
  //
  // 参照 workbuddy（以及本地兄弟 dsh-subagent-default-model）的注册方式：
  // 它们**完全不用** `settings.section`，而是注册到插件页的两个 keyed 槽位：
  //   · `plugins.bundle.config`  —— 该 bundle 的页面上，描述与行之间（view:'page'）
  //   · `plugins.row.config`     —— 该 bundle 声明的某一"行"的配置页，
  //                                 键是 `<包名>#<行 id>`，该行会多一个配置入口
  //
  // 键要注册**每种拼写**：插件页按 key 精确匹配库存里的包名，而部署可以
  // 用任意名字挂载（workbuddy 的 issue #55 就是只注册了裸名、实际挂在
  // `include:` 前缀下，结果**整页空白且不报任何错**）。
  //
  // 两个槽位都注册是**互补而非冲突**：它们在不同的 cell 里，各自独立渲染 ——
  // bundle 页给一个内嵌配置区，行入口给一个独立配置页。
  const PKG = name;
  const CARD_KEYS = [PKG, `include:${PKG}`];

  const registerCard = (slotName, key) => {
    try {
      ctx.slots.inject(slotName, () =>
        ctx.slots.register(
          {
            name: slotName,
            key,
            priority: 30,
            inject: () => ({}),
          },
          ServicePortalSettingsTab,
        ),
      );
    } catch (error) {
      // 逐个槽位隔离：一个注册失败不能把另一个也带下去
      // （workbuddy 用同样的 try/catch 让"没卡片"和"成功了"可区分）
      console.error(
        `[${PKG}] 槽位 "${slotName}"（key=${key}）注册失败（宿主的 provider 不受影响）:`,
        error,
      );
    }
  };

  for (const key of CARD_KEYS) {
    registerCard("plugins.bundle.config", key);
    registerCard("plugins.row.config", `${key}#${key}`);
  }
}


    exports.apply = apply;
    exports.name = name;
    exports.inject = inject;
    return module.exports;
  }
});
