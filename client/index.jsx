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

// 8px 间距节奏：块间距 16、行间距 8、控件内部 4（对齐 UX 规范 4/8dp）
const SPACE = {
  block: 16,
  row: 8,
  inline: 4,
};

// 行高：正文 1.6 读起来松快，标题 1.3 收紧（对齐排版规范）
const LINE = {
  title: 1.3,
  body: 1.6,
};

/**
 * 面板里所有颜色都必须走这里。`--dsw-alias-*` 是宿主主题令牌，
 * 深浅色各一套；写死 hex 只当令牌缺失时的兜底。
 *
 * 踩过的坑：以前用了 **4 个不存在的令牌**（`-label-tertiary`、
 * `-state-warning-primary`、`-button-primary-fill`、`-label-primary-foreground`），
 * 它们从来不会命中，于是一直吃写死的浅色兜底 —— 深色模式下文字和按钮
 * 就成了浅色主题的颜色（对比度不够、按钮发白）。改用**真实存在**的令牌。
 */
const COLOR = {
  textPrimary: "var(--dsw-alias-label-primary,inherit)",
  textSecondary: "var(--dsw-alias-label-secondary,#6b7280)",
  // 说明文字用 secondary：它是真实令牌；tertiary 不存在，硬编码的灰在深色下不可读
  textMuted: "var(--dsw-alias-label-secondary,#6b7280)",
  border: "var(--dsw-alias-border-l2,#e5e7eb)",
  surface: "var(--dsw-alias-bg-layer-1,#fff)",
  surfaceSubtle: "var(--dsw-alias-bg-layer-2,#f3f4f6)",
  brand: "var(--dsw-alias-brand-primary,#4f6ef7)",
  success: "var(--dsw-alias-state-success-primary,#16a34a)",
  idle: "var(--dsw-alias-state-idle-primary,#9ca3af)",
  warn: "var(--dsw-alias-state-warn-primary,#b45309)",
  error: "var(--dsw-alias-state-error-primary,#dc2626)",
};

const styles = {
  card: {
    background: COLOR.surface,
    border: "1px solid " + COLOR.border,
    borderRadius: 12, padding: "16px 20px", maxWidth: 560,
    color: COLOR.textPrimary, fontSize: TYPE.body, lineHeight: LINE.body,
  },
  head: {
    display: "flex", alignItems: "center", gap: 10,
    marginBottom: SPACE.block,
  },
  icon: { borderRadius: 8, display: "block", flex: "0 0 auto" },
  title: {
    fontSize: TYPE.title, lineHeight: LINE.title, fontWeight: 600,
    color: COLOR.textPrimary,
  },
  // 标题下的副标题（与标题同块，所以不额外加 margin）
  subtitle: { fontSize: TYPE.caption, lineHeight: LINE.body, color: COLOR.textMuted },
  row: { display: "flex", gap: SPACE.row, alignItems: "center", flexWrap: "wrap" },
  rowBetween: {
    display: "flex", gap: SPACE.row, alignItems: "center",
    justifyContent: "space-between", flexWrap: "wrap",
  },
  block: {
    borderTop: "1px solid " + COLOR.border,
    marginTop: SPACE.block, paddingTop: SPACE.block,
  },
  sectionTitle: {
    fontSize: TYPE.section, lineHeight: LINE.title, fontWeight: 600,
    marginBottom: SPACE.row, color: COLOR.textPrimary,
  },
  // 嵌套在分区里的子标题（比如"公网访问密码"）：比 sectionTitle 小一级，
  // 不用 sectionTitle 那样的大间距 —— 否则同一块里两级标题抢视线。
  cardTitle: {
    fontSize: TYPE.body, lineHeight: LINE.title, fontWeight: 600,
    color: COLOR.textPrimary,
  },
  muted: { color: COLOR.textMuted, fontSize: TYPE.caption, lineHeight: LINE.body },
  // 与 muted 同字号，但用于"字段名"这种需要稍强一点的位置
  label: { color: COLOR.textSecondary, fontSize: TYPE.body, minWidth: 64 },
  code: {
    fontFamily: "ui-monospace,Menlo,monospace", fontSize: TYPE.caption,
    lineHeight: LINE.body, wordBreak: "break-all", margin: `${SPACE.inline}px 0`,
    color: COLOR.textPrimary,
  },
  // 地址块里的每个地址占一行（<code> 是行内元素，并排会粘成一条）
  codeBlock: {
    display: "block",
    fontFamily: "ui-monospace,Menlo,monospace", fontSize: TYPE.caption,
    lineHeight: LINE.body, wordBreak: "break-all", margin: 0,
    color: COLOR.textPrimary,
  },
  primary: {
    font: "inherit", cursor: "pointer", border: "none",
    background: COLOR.brand,
    // 品牌色是深蓝，前景用白色；真实令牌里没有 foreground，用 #fff 兜底是安全的
    color: "#fff",
    height: 32, padding: "0 14px", borderRadius: 999,
    fontSize: TYPE.body, lineHeight: 1, fontWeight: 500,
  },
  btn: {
    font: "inherit", cursor: "pointer",
    border: "1px solid " + COLOR.border,
    background: COLOR.surface,
    color: COLOR.textPrimary,
    height: 32, padding: "0 14px", borderRadius: 999,
    fontSize: TYPE.body, lineHeight: 1,
  },
  danger: {
    font: "inherit", cursor: "pointer",
    border: "1px solid " + COLOR.error,
    background: "transparent", color: COLOR.error,
    height: 32, padding: "0 14px", borderRadius: 999,
    fontSize: TYPE.body, lineHeight: 1,
  },
  warn: {
    color: COLOR.warn, fontSize: TYPE.caption,
    lineHeight: LINE.body, marginTop: SPACE.row,
  },
  err: {
    color: COLOR.error, fontSize: TYPE.caption, lineHeight: LINE.body,
    marginTop: SPACE.row, whiteSpace: "pre-wrap",
  },
  errInline: { color: COLOR.error, fontSize: TYPE.caption },
  // 「自定义后不再自动轮换」这类提示：要显眼但不能像报错
  warnInline: { color: COLOR.warn, fontSize: TYPE.caption },
  // 公网风险警示块（学 dsh-pocket 的 wanEphemeralWarn 形态：左侧粗色条 + 浅底）。
  // 为什么用块而不是一行小字：公网暴露是本项目里风险最高的动作，
  // 一行灰字会被直接略过；色条块在视觉上"挡"一下，用户才会读到。
  warnBox: {
    borderLeft: "4px solid " + COLOR.warn,
    background: COLOR.surfaceSubtle,
    borderRadius: 8, padding: "8px 10px",
    fontSize: TYPE.caption, lineHeight: LINE.body, color: COLOR.textSecondary,
    marginTop: SPACE.row,
  },
  // 警示块里的标题行（如「公网暴露风险」）：加粗 + 警示色，
  // 让"这是警告"由结构（色条 + 加粗标题）承担，而不是 emoji。
  warnBoxTitle: { color: COLOR.warn, fontWeight: 600 },
  // 右上角「鼓励一下 ★」：一句灰色下划线短链接（用户指定的最终形态）
  creditLink: {
    color: COLOR.textMuted, fontSize: TYPE.caption, lineHeight: LINE.body,
    textDecoration: "underline", whiteSpace: "nowrap", flexShrink: 0,
    marginLeft: 12,
  },
  tag: {
    fontSize: TYPE.caption, lineHeight: 1, padding: "3px 8px", borderRadius: 999,
    background: COLOR.surfaceSubtle, color: COLOR.textSecondary,
  },
  radio: {
    display: "inline-flex", alignItems: "center", gap: 6,
    fontSize: TYPE.body, cursor: "pointer", color: COLOR.textSecondary,
  },
  input: {
    font: "inherit", fontSize: TYPE.body,
    fontFamily: "ui-monospace,Menlo,monospace",
    height: 32, padding: "0 10px", borderRadius: 8, minWidth: 220,
    border: "1px solid " + COLOR.border,
    background: COLOR.surface, color: COLOR.textPrimary,
  },
  badge: (on) => ({
    display: "inline-flex", alignItems: "center", gap: 5,
    fontSize: TYPE.caption, lineHeight: 1, padding: "4px 9px", borderRadius: 999,
    background: on
      ? "color-mix(in srgb, " + COLOR.success + " 14%, transparent)"
      : COLOR.surfaceSubtle,
    color: on ? COLOR.success : COLOR.textSecondary,
  }),
  dot: (on) => ({
    width: 7, height: 7, borderRadius: 999,
    background: on ? COLOR.success : COLOR.idle,
  }),
  qrBox: {
    display: "flex", flexDirection: "column", alignItems: "center",
    margin: `${SPACE.row}px 0 ${SPACE.inline}px`,
  },
  // 地址行：长 URL 要能换行（窄面板里不能撑破），复制按钮不被挤走
  addrRow: {
    display: "flex", gap: SPACE.row, alignItems: "center",
    justifyContent: "center", flexWrap: "wrap", marginTop: SPACE.row,
  },
  qrImg: {
    width: 176, height: 176, imageRendering: "pixelated",
    borderRadius: 8, background: "#fff", padding: 6,
    border: "1px solid " + COLOR.border,
  },
  // 说明文字：用于"启动后会使用这些地址"这种小标题
  addrLabel: {
    fontSize: TYPE.caption, color: COLOR.textMuted,
    lineHeight: LINE.body, marginBottom: SPACE.inline,
  },
  // iOS 风格小开关（与 dsh-pocket 的观感一致）
  switch: (on) => ({
    position: "relative", width: 44, height: 26, borderRadius: 999,
    border: "none", cursor: "pointer", flex: "0 0 auto", padding: 0,
    background: on ? COLOR.success : COLOR.border,
    transition: "background .15s",
  }),
  knob: (on) => ({
    position: "absolute", top: 3, left: on ? 21 : 3,
    width: 20, height: 20, borderRadius: 999, background: "#fff",
    transition: "left .15s", boxShadow: "0 1px 3px rgba(0,0,0,.25)",
  }),
  // 启动器输出：等宽小字，限高可滚
  pre: {
    fontFamily: "ui-monospace,Menlo,monospace", fontSize: TYPE.caption,
    lineHeight: LINE.body, whiteSpace: "pre-wrap", maxHeight: 180,
    overflow: "auto", margin: `${SPACE.inline}px 0 0`,
    color: COLOR.textSecondary,
  },
  // 按钮行：动作只放动作，说明文字**另起一行**。
  // 踩过的坑：原来把「停止后内网/公网地址都会失效…」那句跟在按钮同一行，
  // 窄面板下被按钮挤成两行，读起来像按钮标签的一部分；而且一行里既有
  // "可以做什么"又有"会有什么后果"，主次不分。现在动作与说明垂直分层。
  actionRow: {
    display: "flex", gap: SPACE.row, alignItems: "center", flexWrap: "wrap",
    marginTop: SPACE.row, marginBottom: SPACE.inline,
  },
  // 间距助手：行内不再写裸的 marginTop 数字，统一从这里取，
  // 免得同一个面板里出现 8/10/14 三种"差不多"的间距。
  gapTopSm: { marginTop: SPACE.row },
  gapTopMd: { marginTop: SPACE.block },
  // 分组容器：内部条目之间给一点呼吸
  stack: { display: "flex", flexDirection: "column", gap: SPACE.inline },
  // 详情行（标签 + 值）
  detailRow: {
    display: "flex", gap: SPACE.row, alignItems: "baseline",
    flexWrap: "wrap", marginTop: SPACE.inline,
  },
  // ---- 服务卡（设置页里管理服务用；原来只有控制台页面有）----
  svc: {
    border: "1px solid " + COLOR.border, borderRadius: 10,
    padding: `${SPACE.row}px ${SPACE.row + 2}px`,
    background: COLOR.surfaceSubtle, marginTop: SPACE.row,
  },
  svcHead: {
    display: "flex", alignItems: "baseline", gap: SPACE.row,
    flexWrap: "wrap", justifyContent: "space-between",
  },
  svcName: {
    fontSize: TYPE.body, fontWeight: 600, lineHeight: LINE.title,
    color: COLOR.textPrimary,
  },
  // 路由路径：等宽小字，放在名称旁边当"标识"
  svcMount: {
    fontFamily: "ui-monospace,Menlo,monospace", fontSize: TYPE.caption,
    color: COLOR.textSecondary, background: COLOR.surface,
    border: "1px solid " + COLOR.border, borderRadius: 6,
    padding: "1px 6px", whiteSpace: "nowrap",
  },
  // 「访问」链接：沿用 btn 的观感但用 brand 色描边，与「复制」区分开
  // （复制是"拿走地址"，访问是"点开看"，两者不同）
  accessLink: {
    font: "inherit", cursor: "pointer", textDecoration: "none",
    border: "1px solid " + COLOR.brand, background: "transparent",
    color: COLOR.brand,
    height: 32, padding: "0 14px", borderRadius: 999,
    fontSize: TYPE.body, lineHeight: 1,
    display: "inline-flex", alignItems: "center", whiteSpace: "nowrap",
  },
};

function fmtTime(text) {
  if (!text) return "";
  return String(text);
}

function Switch(on, onClick, disabled) {
  return h("button", {
    type: "button", role: "switch", "aria-checked": !!on,
    disabled: !!disabled,
    style: Object.assign({}, styles.switch(on),
      disabled ? { opacity: 0.5, cursor: "not-allowed" } : null),
    onClick: disabled ? undefined : onClick,
  }, h("span", { style: styles.knob(on) }));
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

  // 节点的「访问」地址：门户地址 + 路由路径。
  // 为什么用门户地址拼而不是上游地址：用户要的是"点一下就能用这个服务"，
  // 而对外可用的入口是**门户的路由**（上游 127.0.0.1:2460 只有本机能开）。
  const serviceUrl = (svc) => {
    const base = (status && status.portalUrl) || ("http://127.0.0.1:" + port);
    const mount = String((svc && svc.mount) || "").replace(/^\//, "");
    return mount ? base + "/" + mount + "/" : base;
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
  const setLanEnabledFlag = async (on) => {
    setLanEnabled(on);         // 乐观更新，失败再回滚
    try {
      const r = await request("/settings", "POST", { lanEnabled: on });
      if (!r || !r.ok) throw new Error((r && r.error) || "保存失败");
      showToast(on ? "已开启局域网访问" : "已关闭局域网访问");
      await load();
    } catch (e) {
      setLanEnabled(!on);
      setError(String(e && e.message ? e.message : e));
    }
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

  const doStart = async (lanOnly) => {
    setBusy(lanOnly ? "start-lan" : "start"); setError(null); setOutput(null);
    try {
      const r = await request("/start", "POST", lanOnly ? { lanOnly: true } : {});
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

  const doStop = async () => {
    setBusy("stop"); setError(null); setOutput(null);
    try {
      const r = await request("/stop", "POST");
      setOutput(r);
      // 停不掉时宿主回 502 + ok:false + stderr（比如环境不让杀进程）：
      // 必须让用户看见，而不是点完什么都不变、以为自己点错了。
      if (r && r.ok === false) {
        const why = [r.stdout, r.stderr].filter(Boolean).join("\n").trim();
        setError("没能停止门户" + (why ? "：" + why : "（看下方启动器输出）"));
      }
      // 一律重新拉状态：不要用返回里的 status 快照（那个可能早于进程真正退出）
      await load();
    } catch (e) {
      setError(String(e && e.message ? e.message : e));
    } finally { setBusy(""); }
  };

  const running = Boolean(status && status.running);
  const password = status && status.password;
  const port = (status && status.portalPort) || 8899;

  const children = [];

  // 标题行 + 右上角「鼓励一下 ★」。
  //
  // 标题是本插件的身份文案：**「对外服务门户」**。
  // 注意别照抄 dsh-pocket 的标题 —— 它叫「手机访问」是因为它整个插件的使命就是
  // 手机访问；我们是「把你本机的服务对外发布并统一管理」，扫码只是其中一种入口。
  // （这是踩过的坑：上一轮「对齐参考对象」时把标题也一起抄了。）
  children.push(h("div", { key: "head", style: styles.head },
    h("img", {
      src: SERVICE_PORTAL_PLUGIN_ICON, alt: "", width: 32, height: 32,
      style: styles.icon,
    }),
    h("div", { style: { flex: 1, minWidth: 0 } },
      h("div", { style: styles.title }, "对外服务门户"),
      h("div", { style: styles.subtitle },
        "手机扫码打开的就是门户控制台，在那里管理要开放的服务"),
    ),
    h("a", {
      href: REPO_URL, target: "_blank", rel: "noreferrer",
      style: styles.creditLink, title: "去 GitHub 给这个项目留颗 Star",
    }, "鼓励一下 ★"),
  ));

  // 状态行：运行中才显示「启动于」。
  // 停着的时候写「启动于 01:39:42」是自相矛盾的（那次早就结束了），
  // 用户看截图第一反应就是「这什么逻辑」。
  children.push(h("div", { key: "status", style: styles.row },
    h("span", { style: styles.badge(running) },
      h("span", { style: styles.dot(running) }),
      running ? "运行中" : "已停止"),
    h("span", { style: styles.muted }, "端口 " + port),
    running && status && status.startedAt
      ? h("span", { style: styles.muted }, "启动于 " + fmtTime(status.startedAt))
      : null,
  ));

  // ============ 未启动：先把「会发生什么」和「唯一的动作」讲清楚 ============
  //
  // 为什么单独做这一块：未启动时原先直接把「公网访问」区块顶在最前面，配一个
  // 点不动的「开启公网访问」按钮，下面再堆三个按钮 —— 顺序是反的、动作是死的，
  // 用户完全看不出该先干什么。现在改成：一句说明 → 将要使用的地址 → 启动按钮。
  if (!running) {
    const planned = (status && status.lanUrls) || [];
    const startRows = [
      h("div", { key: "off-title", style: styles.sectionTitle },
        "门户未启动"),
      h("div", { key: "off-desc", style: styles.muted },
        "启动后，手机连上同一 WiFi 用下面的地址就能打开门户控制台"
        + "（也可以同时开一个公网地址，人不在家时用）。"),
    ];
    if (planned.length) {
      // 每个地址单独一行。踩过的坑：`<code>` 是行内元素，直接并列会连成
      // "...:8899http://...:8899" —— 两个地址粘在一起，根本没法看。
      // 真渲染出图才发现的（纯 HTML mock 发现不了，因为 mock 是手写的结构）。
      startRows.push(h("div", { key: "off-addrs", style: styles.gapTopSm },
        h("div", { style: styles.addrLabel }, "启动后会使用这些地址"),
        h("div", { style: styles.stack },
          ...planned.map((url, i) =>
            h("code", { key: "off-addr-" + i, style: styles.codeBlock }, url))),
      ));
    } else {
      startRows.push(h("div", { key: "off-noaddr",
        style: Object.assign({}, styles.muted, styles.gapTopSm) },
        "还没探测过网卡地址：启动时会自动选一个（内网地址和二维码随后显示在这里）。"));
    }
    startRows.push(h("div", { key: "off-btns",
      style: Object.assign({}, styles.row, styles.gapTopSm) },
      h("button", {
        style: styles.primary, type: "button", disabled: !!busy,
        onClick: () => doStart(true),
      }, busy === "start-lan" ? "启动中…" : "启动（只内网）"),
      h("button", {
        style: styles.btn, type: "button", disabled: !!busy,
        onClick: () => doStart(false),
      }, busy === "start" ? "启动中…" : "启动并开公网"),
      h("button", { style: styles.btn, type: "button", onClick: load }, "刷新"),
    ));
    children.push(h("div", { key: "off", style: styles.block }, startRows));
  }

  // ============ 局域网区块 ============
  if (running) {
    const lanRows = [];
    lanRows.push(h("div", { key: "lan-head", style: styles.rowBetween },
      h("div", { style: styles.sectionTitle, marginBottom: 0 }, "局域网访问"),
      Switch(lanEnabled, () => setLanEnabledFlag(!lanEnabled)),
    ));

    if (lanPrimary) {
      lanRows.push(h("div", { key: "lan-qr", style: styles.qrBox },
        lanEnabled
          ? (qrs[lanPrimary]
              ? h("img", { src: qrs[lanPrimary], alt: "局域网二维码",
                           style: styles.qrImg })
              : h("div", { style: Object.assign({}, styles.qrImg, {
                  display: "flex", alignItems: "center", justifyContent: "center" }),
                }, h("span", { style: styles.muted }, "二维码生成中…")))
          : h("div", { style: Object.assign({}, styles.qrImg, {
              display: "flex", alignItems: "center", justifyContent: "center",
              opacity: 0.4 }),
            }, h("span", { style: styles.muted }, "已关闭")),
        // 地址 + 复制：扫码是「用手机接过去」，复制是「贴到聊天窗发出去」，
        // 两条路都要留（用户明确要求地址可复制）。
        // 「访问」放在「复制」旁边（用户要求）：复制是贴给别人，访问是自己点开看。
        h("div", { style: styles.addrRow },
          h("code", { style: styles.code }, lanPrimary),
          h("a", {
            href: lanPrimary, target: "_blank", rel: "noreferrer",
            style: styles.accessLink,
          }, "访问"),
          h("button", {
            style: styles.btn, type: "button",
            onClick: () => copyText("lan", lanPrimary),
          }, copied === "lan" ? "已复制" : "复制"),
        ),
        h("div", { style: styles.muted },
          lanEnabled
            ? "手机连接同一 WiFi 后扫码即可打开"
            : "🔒 局域网访问已关闭：手机扫码/链接均不可用（公网不受影响）。点右上开关恢复。"),
      ));
    } else {
      lanRows.push(h("div", { key: "lan-none", style: styles.muted },
        "没探测到局域网地址（可能没连 WiFi 或只有回环）。"
        + "本机可用 http://127.0.0.1:" + port));
    }

    // 局域网访问密码行
    lanRows.push(h("div", { key: "lan-pin", style: styles.rowBetween },
      h("div", null,
        h("div", { style: styles.cardTitle }, "局域网访问密码"),
        h("div", { style: styles.muted },
          lanAuth
            ? "已开启：同一 WiFi 打开也要输口令"
            : "已关闭：同一 WiFi 扫码直连（公网仍要口令）"),
      ),
      Switch(lanAuth === true, () => setLanAuthEnabled(lanAuth !== true)),
    ));

    if (lanAuth) {
      lanRows.push(h("div", { key: "lan-pin-value", style: styles.row },
        h("code", { style: styles.code },
          showPassword ? (lanPassword || "(无)")
            : "•".repeat((lanPassword || "").length)),
        h("button", {
          style: styles.btn, type: "button",
          onClick: () => setShowPassword(!showPassword),
        }, showPassword ? "隐藏" : "显示"),
        // 刷新：换一个新的**随机数字**局域网口令（对齐 dsh-pocket 的 lanTokenRefresh）
        h("button", {
          style: styles.btn, type: "button",
          onClick: async () => {
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
          },
        }, busy === "lan-pin" ? "刷新中…" : "刷新"),
        !customOpen
          ? h("button", {
              style: styles.btn, type: "button",
              onClick: () => { setCustomOpen(true); setCustomErr(""); },
            }, "自定义")
          : null,
        // 自定义后不再自动轮换 —— 明确告知，否则用户会疑惑「为什么开启公网没换掉它」
        lanPinCustom
          ? h("span", { style: styles.warnInline }, "自定义后开启公网不再自动换")
          : null,
      ));
    }

    if (customOpen) {
      lanRows.push(h("div", { key: "lan-custom", style: styles.row },
        h("input", {
          type: "text", value: customValue, style: styles.input,
          placeholder: "局域网新口令（6–12 位数字）", autoComplete: "off",
          inputMode: "numeric", maxLength: LAN_PIN_MAX, autoFocus: true,
          // 只留数字：局域网口令是给手机手输的，允许字母/符号只会让人输错
          onChange: (e) => setCustomValue(e.target.value.replace(/\D/g, "")),
          onKeyDown: (e) => {
            if (e.key === "Enter") saveCustomPin();
            if (e.key === "Escape") { setCustomOpen(false); setCustomErr(""); }
          },
        }),
        h("button", { style: styles.primary, type: "button",
                      disabled: busy === "lan-custom",
                      onClick: saveCustomPin },
          busy === "lan-custom" ? "保存中…" : "保存"),
        h("button", { style: styles.btn, type: "button",
                      onClick: () => { setCustomOpen(false); setCustomErr(""); } },
          "取消"),
        customErr ? h("span", { style: styles.errInline }, customErr) : null,
      ));
    }

    // 高级：手动选地址（下拉框选网卡，默认自动）
    //
    // 为什么需要它：多网卡机器（VPN / 虚拟网卡 / WSL）上自动选也可能选错，
    // 而症状是「扫码打不开」——极难自查。给出候选 + 网卡名，用户一眼能认。
    const candidates = status.lanCandidates || [];
    lanRows.push(h("div", { key: "lan-adv", style: styles.rowBetween },
      h("button", {
        style: Object.assign({}, styles.btn, { border: "none", padding: 0,
          background: "transparent", color: "var(--dsw-alias-label-secondary,#6b7280)" }),
        type: "button",
        onClick: () => setAdvOpen(!advOpen),
      }, "高级 · 手动选地址 " + (advOpen ? "▾" : "›")),
      h("span", { style: styles.muted }, lanIp || "自动（推荐）"),
    ));
    if (advOpen) {
      lanRows.push(h("div", { key: "adv-label", style: styles.row },
        h("span", { style: styles.label }, "局域网地址"),
        h("select", {
          value: lanIp || "",
          style: styles.input,
          onChange: (e) => setLanIpOverride(e.target.value),
        },
          h("option", { value: "" }, "自动（推荐）"),
          candidates.map((ip) =>
            h("option", { key: ip, value: ip }, ip)),
        ),
      ));
      if (!candidates.length) {
        lanRows.push(h("div", { key: "adv-none", style: styles.muted },
          "没探测到可用的局域网地址（可能没连网线/WiFi）。"));
      }
      lanRows.push(h("div", { key: "adv-note", style: styles.muted },
        "自动选择会按网卡性质评分：物理网卡优先，VPN/虚拟网卡（如 198.18.x）排后。"
        + "选错了手机就连不上。"));
    }

    children.push(h("div", { key: "lan", style: styles.block }, lanRows));
  }

  // ============ 公网区块 ============
  const pubRows = [];
  pubRows.push(h("div", { key: "pub-head", style: styles.rowBetween },
    h("div", { style: styles.sectionTitle, marginBottom: 0 }, "公网访问"),
    // 门户没在跑时**不放按钮**：那个「开启公网访问」既点不动、又不是当前该做的
    // 事情（得先启动门户）。之前它顶在面板最上面，看着像主操作，实际是死按钮。
    publicUrl
      ? h("button", { style: styles.danger, type: "button",
                      disabled: !!busy, onClick: doStopTunnel },
          busy === "tunnel-stop" ? "关闭中…" : "关闭公网")
      : running
        ? h("button", {
            style: styles.primary, type: "button",
            disabled: !!busy,
            onClick: () => doStart(false),
          }, busy === "start" ? "开启中…" : "开启公网访问")
        : null,
  ));

  if (publicUrl) {
    pubRows.push(h("div", { key: "pub-qr", style: styles.qrBox },
      qrs[publicUrl]
        ? h("img", { src: qrs[publicUrl], alt: "公网二维码",
                     style: styles.qrImg })
        : h("div", { style: Object.assign({}, styles.qrImg, {
            display: "flex", alignItems: "center", justifyContent: "center" }),
          }, h("span", { style: styles.muted }, "二维码生成中…")),
      h("div", { style: styles.addrRow },
        h("code", { style: styles.code }, publicUrl),
        // 「访问」与「复制」并排（用户要求），公网这边同样
        h("a", {
          href: publicUrl, target: "_blank", rel: "noreferrer",
          style: styles.accessLink,
        }, "访问"),
        h("button", {
          style: styles.btn, type: "button",
          onClick: () => copyText("public", publicUrl),
        }, copied === "public" ? "已复制" : "复制"),
      ),
      h("div", { style: styles.muted }, "人在外面也能打开（需要口令）"),
    ));
    pubRows.push(h("div", { key: "pub-pin", style: styles.rowBetween },
      h("div", null,
        h("div", { style: styles.cardTitle }, "公网访问密码"),
        h("div", { style: styles.muted },
          publicPinCustom
            ? "已自定义：开启公网不再自动换新（只有你知道它）"
            : "每次开启公网都会换新（想固定就点「自定义」）"),
      ),
      h("span", { style: styles.tag },
        publicPinCustom ? "自定义" : "本次随机"),
    ));
    if (password) {
      pubRows.push(h("div", { key: "pub-pin-value", style: styles.row },
        h("code", { style: styles.code },
          showPassword ? password : "•".repeat(password.length)),
        h("button", {
          style: styles.btn, type: "button",
          onClick: () => setShowPassword(!showPassword),
        }, showPassword ? "隐藏" : "显示"),
        h("button", {
          style: styles.btn, type: "button",
          onClick: () => copyText("pub-pin", password),
        }, copied === "pub-pin" ? "已复制" : "复制"),
        // 与局域网对称：密码行末尾一个「自定义」（dsh-pocket 的 customBtn 同位置）
        !pubCustomOpen
          ? h("button", {
              style: styles.btn, type: "button",
              onClick: () => { setPubCustomOpen(true); setPubCustomErr(""); },
            }, "自定义")
          : null,
        // 自定义后回不去了 —— 给出「换回随机」出口，否则这个状态是单向的
        publicPinCustom && !pubCustomOpen
          ? h("button", {
              style: styles.btn, type: "button",
              disabled: busy === "pub-random",
              onClick: backToRandomPublic,
            }, busy === "pub-random" ? "换回中…" : "换回随机")
          : null,
      ));
    }

    // 自定义公网密码输入态（与局域网那套并列、互不干扰）
    if (pubCustomOpen) {
      pubRows.push(h("div", { key: "pub-custom", style: styles.stack },
        h("div", { style: styles.row },
          h("input", {
            type: "text", value: pubCustomValue, style: styles.input,
            placeholder: "公网新密码（至少 " + PUBLIC_PIN_MIN + " 位，含字母或符号）",
            autoComplete: "off", maxLength: 64, autoFocus: true,
            onChange: (e) => setPubCustomValue(e.target.value.replace(/\s/g, "")),
            onKeyDown: (e) => {
              if (e.key === "Enter") savePublicPin();
              if (e.key === "Escape") { setPubCustomOpen(false); setPubCustomErr(""); }
            },
          }),
          h("button", { style: styles.primary, type: "button",
                        disabled: busy === "pub-custom",
                        onClick: savePublicPin },
            busy === "pub-custom" ? "保存中…" : "保存"),
          h("button", { style: styles.btn, type: "button",
                        onClick: () => { setPubCustomOpen(false); setPubCustomErr(""); } },
            "取消"),
        ),
        pubCustomErr ? h("div", { style: styles.errInline }, pubCustomErr) : null,
        // 公网自定密码的风险提示（用户要求：公网必须有警告，学 dsh-pocket）
        //
        // 不再用 ⚠️ 当结构图标（设计规范：结构标记要用矢量图标，不用 emoji）；
        // 这里的"这是警告"由左侧色条承担，标题本身就是提示语。
        h("div", { style: styles.warnBox },
          h("div", { style: styles.warnBoxTitle }, "公网密码会被互联网上的人尝试"),
          h("div", { style: styles.gapTopSm },
            "请勿使用你在别处用过的密码，也不要太短。改完**立即生效**，"
            + "不用重开公网（地址与二维码不变）；但已登录的设备不会被踢下线，"
            + "要彻底作废旧密码请点「关闭公网」再重新开启。"),
        ),
      ));
    }

    // 公网风险警示 —— 学 dsh-pocket 的 wanEphemeralWarn：一块讲完公网的风险。
    //
    // 为什么合并到一块：原来底部还有一条"公网开启后，拿到口令的人可以启停你开放
    // 的服务…"，与这条是同**一个主题**（公网暴露），分散在页面首尾两处，用户读到
    // 第一处时看不到第二处。两条并成一条、放在用户管理公网的地方（本区块），
    // 底部就只剩动作，页尾不再有孤立的黄色段落。
    pubRows.push(h("div", { key: "pub-risk", style: styles.warnBox },
      h("div", { style: styles.warnBoxTitle }, "公网暴露风险"),
      h("div", { style: styles.gapTopSm },
        "地址是随机 trycloudflare 域名，每次开启都会变、关闭或重启后失效，"
        + "并可能被他人复用为陌生网站 —— 请勿收藏，每次从本页扫「当前」二维码。"
        + "拿到口令的人可以启停你开放的服务，不用时请点上方「关闭公网」。"),
    ));
    pubRows.push(h("div", { key: "pub-hint", style: styles.muted },
      "地址是随机 trycloudflare 域名，每次开启都会变。"));
  } else {
    pubRows.push(h("div", { key: "pub-none", style: styles.muted },
      running
        ? "未开启。点右上「开启公网访问」建立一个随机公网地址（需本机有 cloudflared）。"
        : "门户未启动。启动后可以再开一个公网地址（自带口令，域名随机、每次都会变）。"));
  }

  children.push(h("div", { key: "pub", style: styles.block }, pubRows));

  // ============ 节点管理（对外发布的路由，就在设置页里）============
  //
  // 用户的要求（原话）：
  //   · 「我们添加的节点是做在插件设置里的，每个节点都有屏蔽和开放的开关，
  //      不是服务开启的开关」—— 开关是**路由闸门**，不是启停上游程序；
  //   · 「启动服务是服务本身的事情，这里只是负责可以路由」；
  //   · 「每个设置的服务都要有一个点击直接打开的功能叫做访问」；
  //   · 「取消自动发现服务的功能，不用刷新也不用搜索，就是人手动添加端口」。
  //
  // 所以这一块只有三件事：添加节点 / 开放或屏蔽 / 访问。
  // 「屏蔽」= 门户不再把这条路由转过去（上游照跑不误），不是停掉那个程序。
  if (running) {
    const svcRows = [];
    const blocked = services.filter((s) => s && s.enabled !== true).length;
    const down = services.filter(
      (s) => s && s.enabled === true && s.alive === false).length;

    svcRows.push(h("div", { key: "svc-head", style: styles.rowBetween },
      h("div", { style: styles.sectionTitle, marginBottom: 0 }, "对外发布的节点"),
      h("span", { style: styles.muted },
        services.length + " 个"
        + (blocked ? " · " + blocked + " 个已屏蔽" : "")
        + (down ? " · " + down + " 个上游未响应" : "")),
    ));
    svcRows.push(h("div", { key: "svc-tip", style: styles.muted },
      "这里只管门户要不要把请求转过去；上游程序请用它自己的方式启动。"));

    if (!services.length) {
      svcRows.push(h("div", { key: "svc-none", style: styles.muted },
        "还没有节点。点下面的「添加节点」把本机的一个端口发布出去。"));
    }

    // 每个节点一张卡：名称 + 路由 + 上游 + 访问 / 开放屏蔽 / 编辑 / 删除
    for (const svc of services) {
      const key = svc.key || svc.name || "";
      const open = svc.enabled === true;
      const alive = svc.alive !== false;
      const editing = editKey === key;

      svcRows.push(h("div", { key: "svc-" + key, style: styles.svc },
        h("div", { style: styles.svcHead },
          h("div", { style: styles.row },
            h("span", { style: styles.svcName }, String(svc.name || key)),
            h("span", { style: styles.svcMount }, String(svc.mount || "")),
          ),
          // 状态只说**路由**的开放与否；上游通不通另用一小行提示（不混淆两者）
          h("span", { style: { color: open ? COLOR.success : COLOR.idle,
                               fontSize: TYPE.caption, whiteSpace: "nowrap" } },
            h("span", { style: Object.assign({}, styles.dot(open), {
              background: open ? COLOR.success : COLOR.idle }) }),
            open ? "开放中" : "已屏蔽"),
        ),
        h("div", { style: styles.muted },
          "转发到 " + String(svc.target || "")
          + (svc.note ? " · " + String(svc.note) : "")),
        // 上游没响应只作为**提示**：它解释"为什么访问打不开"，
        // 但绝不影响这条路由本身的开放/屏蔽（那是两件事）。
        open && !alive
          ? h("div", { key: "svc-down", style: styles.warnInline },
              "上游没响应 —— 请先把 " + String(svc.target || "")
              + " 上的程序启动起来（本插件不负责启动它）。")
          : null,

        editing
          ? h("div", { key: "svc-edit", style: styles.stack },
              h("div", { style: styles.row },
                h("input", { style: styles.input, value: editForm.name,
                  placeholder: "名称",
                  onChange: (e) => setEditForm(Object.assign({}, editForm,
                    { name: e.target.value })) }),
                h("input", { style: styles.input, value: editForm.mount,
                  placeholder: "/路由",
                  onChange: (e) => setEditForm(Object.assign({}, editForm,
                    { mount: e.target.value })) }),
              ),
              h("div", { style: styles.row },
                h("input", { style: styles.input, value: editForm.target,
                  placeholder: "127.0.0.1:8810",
                  onChange: (e) => setEditForm(Object.assign({}, editForm,
                    { target: e.target.value })) }),
                h("input", { style: styles.input, value: editForm.note,
                  placeholder: "备注（可选）",
                  onChange: (e) => setEditForm(Object.assign({}, editForm,
                    { note: e.target.value })) }),
              ),
              editErr ? h("div", { style: styles.errInline }, editErr) : null,
              h("div", { style: styles.row },
                h("button", { style: styles.primary, type: "button",
                  disabled: busy === "svc-" + key,
                  onClick: async () => {
                    setEditErr("");
                    if (!editForm.name.trim() || !editForm.mount.trim()
                        || !editForm.target.trim()) {
                      setEditErr("名称、路由、上游都不能为空");
                      return;
                    }
                    await serviceAction(key, "update", "保存");
                  } },
                  busy === "svc-" + key ? "保存中…" : "保存"),
                h("button", { style: styles.btn, type: "button",
                  onClick: () => { setEditKey(""); setEditErr(""); } }, "取消"),
              ),
            )
          : h("div", { key: "svc-act", style: styles.actionRow },
              // 「访问」：用户要求"每个设置的服务都要有一个点击直接打开的功能叫访问"。
              // 屏蔽时不给链接（打不开），这是唯一不给的情况 —— 因为它确实不转发。
              open
                ? h("a", {
                    href: serviceUrl(svc),
                    target: "_blank", rel: "noreferrer",
                    style: Object.assign({}, styles.primary,
                      { textDecoration: "none" }),
                  }, "访问")
                : null,
              // 这就是用户说的「屏蔽 / 开放」：只改路由是否转发，不动上游进程
              h("button", { style: styles.btn, type: "button",
                disabled: !!busy,
                onClick: () => serviceAction(key,
                  open ? "block" : "open", open ? "屏蔽" : "开放"),
              }, open ? "屏蔽" : "开放"),
              h("button", { style: styles.btn, type: "button",
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
              h("button", { style: styles.danger, type: "button",
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

    // 工具行：只剩「添加节点」（用户要求去掉刷新与自动发现）
    svcRows.push(h("div", { key: "svc-tools", style: styles.actionRow },
      h("button", { style: addOpen ? styles.btn : styles.primary, type: "button",
        disabled: !!busy,
        onClick: () => { setAddOpen(!addOpen); setAddErr(""); },
      }, addOpen ? "取消" : "添加节点"),
    ));

    // 添加节点表单（手动填写，不扫描）
    if (addOpen) {
      svcRows.push(h("div", { key: "add", style: styles.svc },
        h("div", { style: styles.cardTitle }, "添加节点"),
        h("div", { style: styles.stack },
          h("div", { style: styles.row },
            h("input", { style: styles.input, value: addForm.name,
              placeholder: "名称，例如：训练配置台", autoFocus: true,
              onChange: (e) => setAddForm(Object.assign({}, addForm,
                { name: e.target.value })) }),
            h("input", { style: styles.input, value: addForm.mount,
              placeholder: "/rltrain（对外路径）",
              onChange: (e) => setAddForm(Object.assign({}, addForm,
                { mount: e.target.value })) }),
          ),
          h("div", { style: styles.row },
            h("input", { style: styles.input, value: addForm.target,
              placeholder: "127.0.0.1:8810（本机端口）",
              onKeyDown: (e) => { if (e.key === "Enter") submitAdd(); },
              onChange: (e) => setAddForm(Object.assign({}, addForm,
                { target: e.target.value })) }),
            h("input", { style: styles.input, value: addForm.note,
              placeholder: "备注（可选）",
              onChange: (e) => setAddForm(Object.assign({}, addForm,
                { note: e.target.value })) }),
          ),
        ),
        addErr ? h("div", { style: styles.errInline }, addErr) : null,
        h("div", { style: styles.actionRow },
          h("button", { style: styles.primary, type: "button",
            disabled: busy === "svc-add", onClick: submitAdd },
            busy === "svc-add" ? "添加中…" : "添加节点"),
        ),
        h("div", { style: styles.muted },
          "添加后默认就是「开放」；上游程序要你自己启动（这里只负责路由）。"),
      ));
    }

    children.push(h("div", { key: "services", style: styles.block }, svcRows));
  }

  // ============ 门户进程控制 ============
  //
  // 运行中必须能**停**（否则启停不对称：能开不能关，只能去控制台或杀进程）。
  // 未启动时的启动按钮已经在上面「门户未启动」块里了，这里不重复。
  //
  // 排版意图：危险动作（停止门户）与轻动作（刷新）**同一行**但视觉权重分明
  // （描边红 vs 灰描边）；"停止会发生什么"作为副文本放下面 —— 它是后果说明，
  // 不是按钮的一部分。
  if (running) {
    children.push(h("div", { key: "actions", style: styles.block },
      h("div", { style: styles.sectionTitle }, "门户进程"),
      h("div", { style: styles.actionRow },
        h("button", { style: styles.danger, type: "button", disabled: !!busy,
                      onClick: doStop },
          busy === "stop" ? "停止中…" : "停止门户"),
        h("button", { style: styles.btn, type: "button", onClick: load }, "刷新"),
      ),
      h("div", { style: styles.muted },
        "停止后内网 / 公网地址都会失效，设置与口令保留。"),
    ));
  }

  // 底部警示：**只**留"局域网免密"这一条。
  //
  // 为什么公网风险不在这里：它已经写在上面「公网访问」区块里了（用户管理公网的
  // 地方），这里再写一遍是同主题重复。而"局域网免密"是个**跨区块**的全局安全
  // 状态：它影响的是整个门户的安全姿态，不属于某一个区块，放页尾合适。
  // 三条被删掉的冗余：公网风险（上移）、"局域网也要口令"（开着就无需说）、
  // 以及"点「关闭公网」"（未开公网时那个按钮根本不在，属于自相矛盾的指引）。
  if (running && lanAuth === false) {
    children.push(h("div", { key: "warn", style: styles.warnBox },
      h("div", { style: styles.warnBoxTitle }, "局域网免密"),
      h("div", { style: styles.gapTopSm },
        "同一 WiFi 下的设备无需口令即可打开，仅建议在可信网络下使用。"
        + "需要口令请打开上方「局域网访问密码」。"),
    ));
  }

  if (error) {
    children.push(h("div", { key: "err", style: styles.err }, String(error)));
  }
  // 地址提示（比如"选定的地址不在当前网卡上"）：不静默吞，用户要能看见
  if (lanNote) {
    children.push(h("div", { key: "lannote", style: styles.warn }, String(lanNote)));
  }
  if (output && output.stdout && !running) {
    children.push(h("div", { key: "out", style: styles.block },
      h("div", { style: styles.muted }, "启动器输出"),
      h("pre", { style: styles.pre }, String(output.stdout).slice(-1200)),
    ));
  }
  // status.problem：**没在跑**时是普通说明（用户自己停的也算，不该红字报警）；
  // 只有真异常（ok:false）才由上面的 error 分支用红字显示。
  if (status && status.problem) {
    children.push(h("div", { key: "prob",
      style: running ? styles.warn : styles.muted }, String(status.problem)));
  }

  // `view === "summary"` 时只回一行摘要（插件页折叠态 / 行预览用完整表单会很怪）
  if (view === "summary") {
    if (!status) return h("span", { style: styles.muted }, "对外服务门户");
    const n = ((status && status.services) || []).length;
    const bits = [];
    bits.push(status.port ? ("对外服务门户（" + status.port + " 端口）") : "对外服务门户");
    if (running) {
      bits.push(n + " 个节点");
      if (status.publicUrl) bits.push("公网已开");
      else if ((status.lanUrls || []).length) bits.push("局域网可用");
      bits.push(status.passwordMode ? "固定口令" : "随机口令");
    } else {
      bits.push("未运行");
    }
    return h("span", null, bits.join(" · "));
  }

  const card = h("div", { style: styles.card }, children);
  if (!toast) return card;
  // Toast：固定屏幕中央，2.6 秒自动消失（与 dsh-pocket 的反馈方式一致）
  return h("div", null, card, h("div", {
    style: {
      position: "fixed", left: "50%", top: "50%",
      transform: "translate(-50%, -50%)", zIndex: 10001,
      background: "rgba(17,24,39,.92)", color: "#fff",
      padding: "10px 18px", borderRadius: 10, fontSize: TYPE.body,
      boxShadow: "0 8px 24px rgba(0,0,0,.28)", pointerEvents: "none",
    },
  }, toast));
}

export function apply(ctx) {
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

export { name, inject };
