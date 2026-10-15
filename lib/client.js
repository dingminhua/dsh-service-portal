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
//   · 局域网区块：总开关 + 二维码 + 地址 + 访问密码（开关/刷新/自定义）+ 高级选地址
//   · 公网区块：开关 + 二维码 + 地址 + 访问密码
//   · 扫码打开的就是门户控制台（在那里管理要开放的服务）
//
// 与 dsh-pocket 的一个本质区别（诚实说明）：dsh-pocket 的二维码指向**一个目标**
// （DSH 的 web 界面），我们的二维码指向**门户控制台**——扫码后是一个可管理多个
// 服务的页面。所以这里显示的是「门户地址」，不是「某个服务地址」。

// 元素创建别名：**不能**从 props 里取（DSH 的 section props 不含 h，
// 取了会得到 undefined → 渲染期抛 "h is not a function" → 面板整片空白，
// 而左侧导航照常显示，极难定位）。模块级定义一次即可。
const h = React.createElement;

const name = "dsh-service-portal";
const inject = ["slots", "connection"];

const API = "/service-portal/api";

// 项目仓库地址（右上角那句求 Star 的链接目标）
const REPO_URL = "https://github.com/dingminhua/dsh-service-portal";

// 局域网口令长度门槛 —— 与后端 portal_login.validate_lan_pin 一致。
// 前端先挡一层省一次往返；后端仍有权威校验（不信任前端）。
const LAN_PIN_MIN = 6;
const LAN_PIN_MAX = 12;

const styles = {
  card: {
    background: "var(--dsw-alias-bg-layer-1,#fff)",
    border: "1px solid var(--dsw-alias-border-l2,#e5e7eb)",
    borderRadius: 12, padding: "16px 20px", maxWidth: 560,
  },
  head: { display: "flex", alignItems: "center", gap: 10, marginBottom: 12 },
  icon: { borderRadius: 8, display: "block", flex: "0 0 auto" },
  title: {
    fontSize: 14, fontWeight: 600,
    color: "var(--dsw-alias-label-primary,inherit)",
  },
  row: { display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" },
  rowBetween: {
    display: "flex", gap: 8, alignItems: "center",
    justifyContent: "space-between", flexWrap: "wrap",
  },
  block: {
    borderTop: "1px solid var(--dsw-alias-border-l2,#e5e7eb)",
    marginTop: 14, paddingTop: 14,
  },
  sectionTitle: {
    fontSize: 13, fontWeight: 600, marginBottom: 10,
    color: "var(--dsw-alias-label-primary,inherit)",
  },
  muted: {
    color: "var(--dsw-alias-label-tertiary,#8b93a1)",
    fontSize: 12, lineHeight: 1.5,
  },
  label: {
    color: "var(--dsw-alias-label-secondary,#6b7280)",
    fontSize: 12, minWidth: 64,
  },
  code: {
    fontFamily: "ui-monospace,Menlo,monospace", fontSize: 12,
    wordBreak: "break-all", margin: "4px 0",
    color: "var(--dsw-alias-label-primary,inherit)",
  },
  primary: {
    font: "inherit", cursor: "pointer", border: "none",
    background: "var(--dsw-alias-button-primary-fill,var(--dsw-alias-brand-primary,#4f6ef7))",
    color: "var(--dsw-alias-label-primary-foreground,#fff)",
    height: 32, padding: "0 14px", borderRadius: 999,
    fontSize: 13, fontWeight: 500,
  },
  btn: {
    font: "inherit", cursor: "pointer",
    border: "1px solid var(--dsw-alias-border-l2,#d1d5db)",
    background: "var(--dsw-alias-bg-layer-1,#fff)",
    color: "var(--dsw-alias-label-primary,inherit)",
    height: 32, padding: "0 14px", borderRadius: 999, fontSize: 13,
  },
  danger: {
    font: "inherit", cursor: "pointer",
    border: "1px solid var(--dsw-alias-state-error-primary,#dc2626)",
    background: "transparent",
    color: "var(--dsw-alias-state-error-primary,#dc2626)",
    height: 32, padding: "0 14px", borderRadius: 999, fontSize: 13,
  },
  warn: {
    color: "var(--dsw-alias-state-warn-primary,#b45309)",
    fontSize: 12, lineHeight: 1.6, marginTop: 8,
  },
  err: {
    color: "var(--dsw-alias-state-error-primary,#dc2626)",
    fontSize: 12, lineHeight: 1.5, marginTop: 8, whiteSpace: "pre-wrap",
  },
  errInline: {
    color: "var(--dsw-alias-state-error-primary,#dc2626)", fontSize: 12,
  },
  // 「自定义后不再自动轮换」这类提示：要显眼但不能像报错
  warnInline: {
    color: "var(--dsw-alias-state-warning-primary,#d97706)", fontSize: 12,
  },
  // 右上角「鼓励一下 ★」：一句灰色下划线短链接（用户指定的最终形态）
  creditLink: {
    color: "var(--dsw-alias-label-tertiary,#8b93a1)", fontSize: 12,
    lineHeight: 1.6, textDecoration: "underline",
    whiteSpace: "nowrap", flexShrink: 0, marginLeft: 12,
  },
  tag: {
    fontSize: 11, padding: "1px 7px", borderRadius: 999,
    background: "rgba(107,114,128,.14)",
    color: "var(--dsw-alias-label-tertiary,#8b93a1)",
  },
  radio: {
    display: "inline-flex", alignItems: "center", gap: 6,
    fontSize: 13, cursor: "pointer",
    color: "var(--dsw-alias-label-secondary,#6b7280)",
  },
  input: {
    font: "inherit", fontFamily: "ui-monospace,Menlo,monospace",
    height: 32, padding: "0 10px", borderRadius: 8, minWidth: 220,
    border: "1px solid var(--dsw-alias-border-l2,#d1d5db)",
    background: "var(--dsw-alias-bg-layer-1,#fff)",
    color: "var(--dsw-alias-label-primary,inherit)",
  },
  badge: (on) => ({
    display: "inline-flex", alignItems: "center", gap: 5,
    fontSize: 12, padding: "2px 9px", borderRadius: 999,
    background: on ? "rgba(22,163,74,.12)" : "rgba(107,114,128,.14)",
    color: on ? "#16a34a" : "var(--dsw-alias-label-tertiary,#8b93a1)",
  }),
  dot: (on) => ({
    width: 7, height: 7, borderRadius: 999,
    background: on ? "#16a34a" : "#9ca3af",
  }),
  qrBox: {
    display: "flex", flexDirection: "column", alignItems: "center",
    margin: "10px 0 6px",
  },
  qrImg: {
    width: 168, height: 168, imageRendering: "pixelated",
    borderRadius: 8, background: "#fff", padding: 6,
    border: "1px solid var(--dsw-alias-border-l2,#e5e7eb)",
  },
  // iOS 风格小开关（与 dsh-pocket 的观感一致）
  switch: (on) => ({
    position: "relative", width: 44, height: 26, borderRadius: 999,
    border: "none", cursor: "pointer", flex: "0 0 auto", padding: 0,
    background: on ? "#16a34a" : "var(--dsw-alias-border-l2,#d1d5db)",
    transition: "background .15s",
  }),
  knob: (on) => ({
    position: "absolute", top: 3, left: on ? 21 : 3,
    width: 20, height: 20, borderRadius: 999, background: "#fff",
    transition: "left .15s", boxShadow: "0 1px 3px rgba(0,0,0,.25)",
  }),
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

function ServicePortalSettingsTab() {
  const [status, setStatus] = React.useState(null);
  const [busy, setBusy] = React.useState("");
  const [error, setError] = React.useState(null);
  const [output, setOutput] = React.useState(null);
  const [showPassword, setShowPassword] = React.useState(true);

  // 二维码：按地址缓存（地址不变就不重复要，避免每次轮询都打门户口）
  const [qrs, setQrs] = React.useState({});
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
  // 高级：手动选地址
  const [advOpen, setAdvOpen] = React.useState(false);
  // 手动选定的网卡地址（'' = 自动按网卡评分选）
  const [lanIp, setLanIp] = React.useState("");
  // 地址提示（"选定的地址不在当前网卡上"等）—— 不能静默吞掉
  const [lanNote, setLanNote] = React.useState("");
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
    setBusy("stop"); setError(null);
    try {
      const r = await request("/stop", "POST");
      setOutput(r);
      if (r && r.status) setStatus(r.status);
      else await load();
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
      h("div", { style: styles.muted },
        "手机扫码打开的就是门户控制台，在那里管理要开放的服务"),
    ),
    h("a", {
      href: REPO_URL, target: "_blank", rel: "noreferrer",
      style: styles.creditLink, title: "去 GitHub 给这个项目留颗 Star",
    }, "鼓励一下 ★"),
  ));

  // 状态行
  children.push(h("div", { key: "status", style: styles.row },
    h("span", { style: styles.badge(running) },
      h("span", { style: styles.dot(running) }),
      running ? "运行中" : "已停止"),
    h("span", { style: styles.muted }, "端口 " + port),
    status && status.startedAt
      ? h("span", { style: styles.muted }, "启动于 " + fmtTime(status.startedAt))
      : null,
  ));

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
        h("code", { style: Object.assign({}, styles.code, { marginTop: 8 }) },
          lanPrimary),
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
        h("div", { style: styles.sectionTitle, marginBottom: 2 }, "局域网访问密码"),
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
    publicUrl
      ? h("button", { style: styles.danger, type: "button",
                      disabled: !!busy, onClick: doStopTunnel },
          busy === "tunnel-stop" ? "关闭中…" : "关闭公网")
      : h("button", {
          style: styles.primary, type: "button",
          disabled: !!busy || !running,
          onClick: () => doStart(false),
        }, busy === "start" ? "开启中…" : "开启公网访问"),
  ));

  if (publicUrl) {
    pubRows.push(h("div", { key: "pub-qr", style: styles.qrBox },
      qrs[publicUrl]
        ? h("img", { src: qrs[publicUrl], alt: "公网二维码",
                     style: styles.qrImg })
        : h("div", { style: Object.assign({}, styles.qrImg, {
            display: "flex", alignItems: "center", justifyContent: "center" }),
          }, h("span", { style: styles.muted }, "二维码生成中…")),
      h("code", { style: Object.assign({}, styles.code, { marginTop: 8 }) },
        publicUrl),
      h("div", { style: styles.muted }, "人在外面也能打开（需要口令）"),
    ));
    pubRows.push(h("div", { key: "pub-pin", style: styles.rowBetween },
      h("div", null,
        h("div", { style: styles.sectionTitle, marginBottom: 2 }, "公网访问密码"),
        h("div", { style: styles.muted }, "每次开启公网都会换新；也可在控制台里改"),
      ),
      h("span", { style: styles.tag },
        status && status.passwordMode === "fixed" ? "固定口令" : "本次随机"),
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
          onClick: () => { try { navigator.clipboard.writeText(password); } catch { /* 忽略 */ } },
        }, "复制"),
      ));
    }
    pubRows.push(h("div", { key: "pub-hint", style: styles.muted },
      "地址是随机 trycloudflare 域名，每次开启都会变。"));
  } else {
    pubRows.push(h("div", { key: "pub-none", style: styles.muted },
      running
        ? "未开启。点右上「开启公网访问」建立一个随机公网地址（需本机有 cloudflared）。"
        : "门户未运行。"));
  }

  children.push(h("div", { key: "pub", style: styles.block }, pubRows));

  // ============ 控制台入口 ============
  if (running) {
    children.push(h("div", { key: "console", style: styles.block },
      h("div", { style: styles.sectionTitle }, "服务控制台"),
      h("div", { style: styles.row },
        h("a", {
          href: status.portalUrl || ("http://127.0.0.1:" + port),
          target: "_blank", rel: "noreferrer",
          style: Object.assign({}, styles.primary, { textDecoration: "none" }),
        }, "打开控制台"),
        h("span", { style: styles.muted },
          "在控制台里添加服务、设置路由路径、逐个开关"),
      ),
    ));
  }

  // ============ 门户进程控制 ============
  children.push(h("div", { key: "actions",
    style: Object.assign({}, styles.row, { marginTop: 14 }) },
    !running
      ? h("button", {
          style: styles.primary, type: "button", disabled: !!busy,
          onClick: () => doStart(true),
        }, busy === "start-lan" ? "启动中…" : "开启门户（只内网）")
      : null,
    !running
      ? h("button", {
          style: styles.primary, type: "button", disabled: !!busy,
          onClick: () => doStart(false),
        }, busy === "start" ? "启动中…" : "开启门户（内网 + 公网）")
      : null,
    h("button", { style: styles.btn, type: "button", onClick: load }, "刷新"),
  ));

  // 警示
  children.push(h("div", { key: "warn", style: styles.warn },
    "⚠ 公网开启后，拿到口令的人可以启停你开放的服务。" +
    (lanAuth === false
      ? "局域网免密：仅建议在可信网络下使用。"
      : "局域网也要口令。") +
    "不用时请点「关闭公网」。"
  ));

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
      h("pre", { style: Object.assign({}, styles.code,
        { whiteSpace: "pre-wrap", maxHeight: 180, overflow: "auto" }) },
        String(output.stdout).slice(-1200)),
    ));
  }
  if (status && status.problem) {
    children.push(h("div", { key: "prob", style: styles.err }, String(status.problem)));
  }

  const card = h("div", { style: styles.card }, children);
  if (!toast) return card;
  // Toast：固定屏幕中央，2.6 秒自动消失（与 dsh-pocket 的反馈方式一致）
  return h("div", null, card, h("div", {
    style: {
      position: "fixed", left: "50%", top: "50%",
      transform: "translate(-50%, -50%)", zIndex: 10001,
      background: "rgba(17,24,39,.92)", color: "#fff",
      padding: "10px 18px", borderRadius: 10, fontSize: 13,
      boxShadow: "0 8px 24px rgba(0,0,0,.28)", pointerEvents: "none",
    },
  }, toast));
}

function apply(ctx) {
  ctx.slots.inject("settings.section", () =>
    ctx.slots.register(
      {
        name: "settings.section",
        id: "service-portal",
        order: 40,
        label: () => "对外服务门户",
        inject: () => ({}),
      },
      ServicePortalSettingsTab,
    ),
  );
}


    exports.apply = apply;
    exports.name = name;
    exports.inject = inject;
    return module.exports;
  }
});
