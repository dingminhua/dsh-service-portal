// dsh-service-portal 设置页客户端（手写 CommonJS，无需 esbuild/JSX 工具链）。
//
// 分发格式与 dsh-pocket / dsh-ldvh 一致：window.__ModuleLoader__.load({id, factory})，
// React 由 DSH 客户端模块系统提供（require("react")），绝不假设全局 React。
//
// 为什么手写而不上 JSX 构建：本机 profile 里没有 esbuild，且插件要能在
// 任何 DSH 安装上直接跑；用 React.createElement 别名 h() 可读性足够，
// 换来零构建依赖。产物由 client/build.mjs 生成到 lib/client.js —— 必须放
// lib/ 并与 package.json 的 exports["./client"] 一致（放错目录会让 DSH
// 启动期解析失败，poker-viewer 迁移时实测过一次）。
//
// 图标 SERVICE_PORTAL_PLUGIN_ICON 由构建脚本内联注入（来自 client/icon.ts，
// 与 LaoDing 插件家族同一张 64px 品牌图）。
//
// 界面职责：
//   · 一键开启 / 关闭外网入口（调宿主 /service-portal/api/start|stop）
//   · 显示连接地址与**明文口令**（与 poker-viewer 同款选型：直接明文显示）
//   · 明确警示：拿到口令 == 能启停被开放的服务

// 元素创建别名：**不能**从 props 里取（DSH 的 section props 不含 h，
// 取了会得到 undefined → 渲染期抛 "h is not a function" → 面板整片空白，
// 而左侧导航照常显示，极难定位）。模块级定义一次即可。
const h = React.createElement;

const name = "dsh-service-portal";
const inject = ["slots", "connection"];

const API = "/service-portal/api";

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
  block: {
    borderTop: "1px solid var(--dsw-alias-border-l2,#e5e7eb)",
    marginTop: 14, paddingTop: 14,
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
  errInline: {
    color: "var(--dsw-alias-state-error-primary,#dc2626)", fontSize: 12,
  },
  err: {
    color: "var(--dsw-alias-state-error-primary,#dc2626)",
    fontSize: 12, lineHeight: 1.5, marginTop: 8, whiteSpace: "pre-wrap",
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
};

function fmtTime(text) {
  if (!text) return "";
  return String(text);
}

function ServicePortalSettingsTab() {
  const [status, setStatus] = React.useState(null);
  const [busy, setBusy] = React.useState("");
  const [error, setError] = React.useState(null);
  const [output, setOutput] = React.useState(null);
  const [showPassword, setShowPassword] = React.useState(true);
  // 口令形态设置（从宿主读回，改后写回）
  const [pwMode, setPwMode] = React.useState(null);
  const [pwValue, setPwValue] = React.useState("");
  const [pwSaved, setPwSaved] = React.useState("");
  const [pwError, setPwError] = React.useState("");

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
    } catch (e) {
      setError(String(e && e.message ? e.message : e));
    }
  };

  // 读回口令形态配置（只在首次与保存后刷新，避免覆盖用户正在输入的内容）
  const loadSettings = async () => {
    try {
      const cfg = await request("/settings");
      if (cfg && cfg.ok) {
        setPwMode(cfg.passwordMode === "fixed" ? "fixed" : "random");
        setPwValue(cfg.fixedPassword || "");
      }
    } catch { /* 设置读不回来不影响主要功能 */ }
  };

  React.useEffect(() => {
    load();
    loadSettings();
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, []);

  const savePassword = async () => {
    setPwSaved(""); setPwError("");
    try {
      const r = await request("/settings", "POST", {
        passwordMode: pwMode || "random",
        fixedPassword: pwValue,
      });
      if (r && r.ok) { setPwSaved("ok"); setPwError(""); }
      else { setPwSaved("err"); setPwError((r && r.error) || "保存失败"); }
    } catch (e) {
      setPwSaved("err");
      setPwError(String(e && e.message ? e.message : e));
    }
  };

  const doStart = async () => {
    setBusy("start"); setError(null); setOutput(null);
    try {
      const r = await request("/start", "POST");
      setOutput(r);
      if (r && r.status) setStatus(r.status);
      if (!r || r.ok !== true) {
        setError(
          "启动失败（退出码 " + (r && r.exitCode) + "）" +
          (r && r.stderr ? "\n" + String(r.stderr).slice(-600) : "")
        );
      }
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
      if (!r || r.ok !== true) setError("停止未成功，请查看下方输出");
    } catch (e) {
      setError(String(e && e.message ? e.message : e));
    } finally { setBusy(""); }
  };

  const running = !!(status && status.running);
  const password = status && status.password;

  const children = [];

  // 标题行：家族图标 + 名称（与 dsh-connect-* 系列的卡片外观一致）。
  // SERVICE_PORTAL_PLUGIN_ICON 由构建脚本从 client/icon.ts 内联进产物，
  // 用的是 LaoDing 插件家族的同一张 64px 品牌图。
  children.push(h("div", { key: "head", style: styles.head },
    h("img", {
      src: SERVICE_PORTAL_PLUGIN_ICON, alt: "", width: 32, height: 32,
      style: styles.icon,
    }),
    h("div", null,
      h("div", { style: styles.title }, "对外服务门户"),
      h("div", { style: styles.muted }, "一个域名 + 一个口令，按需开放本机服务"),
    ),
  ));

  // 状态行
  children.push(h("div", { key: "status", style: styles.row },
    h("span", { style: styles.badge(running) },
      h("span", { style: styles.dot(running) }),
      running ? "运行中" : "已停止"),
    status && status.mode
      ? h("span", { style: styles.muted },
          status.mode === "single-domain" ? "单域名 + 路径" : "两个独立域名")
      : null,
    status && status.startedAt
      ? h("span", { style: styles.muted }, "启动于 " + fmtTime(status.startedAt))
      : null,
  ));

  // 连接信息
  if (status && status.ok !== false) {
    const rows = [];
    if (status.baseUrl) {
      rows.push(h("div", { key: "base", style: styles.row },
        h("span", { style: styles.label }, "入口"),
        h("a", {
          href: status.baseUrl, target: "_blank", rel: "noreferrer",
          style: Object.assign({}, styles.code, { color: "var(--dsw-alias-brand-primary,#4f6ef7)" }),
        }, status.baseUrl),
      ));
    }
    for (const ep of status.endpoints || []) {
      rows.push(h("div", { key: "ep-" + ep.key, style: styles.row },
        h("span", { style: styles.label }, ep.name || ep.key),
        h("a", {
          href: ep.url, target: "_blank", rel: "noreferrer",
          style: Object.assign({}, styles.code, { color: "var(--dsw-alias-brand-primary,#4f6ef7)" }),
        }, ep.url || "(无地址)"),
      ));
    }
    if (password) {
      rows.push(h("div", { key: "pass", style: styles.row },
        h("span", { style: styles.label }, "口令"),
        h("code", { style: styles.code }, showPassword ? password : "•".repeat(password.length)),
        h("span", { style: styles.tag },
          status.passwordMode === "fixed" ? "固定口令" : "本次随机"),
        h("button", {
          style: styles.btn, type: "button",
          onClick: () => setShowPassword(!showPassword),
        }, showPassword ? "隐藏" : "显示"),
        h("button", {
          style: styles.btn, type: "button",
          onClick: () => {
            try { navigator.clipboard.writeText(password); } catch { /* 忽略 */ }
          },
        }, "复制"),
      ));
      rows.push(h("div", { key: "login-hint", style: styles.muted },
        "打开上面的地址后，只需输入这一个口令（没有账号）。"));
    }
    if (rows.length) {
      children.push(h("div", { key: "conn", style: styles.block }, rows));
    }
  }

  // 口令形态（两选一）：每次随机 / 固定口令
  const mode = pwMode || "random";
  children.push(h("div", { key: "pwsection", style: styles.block },
    h("div", { style: styles.label, marginBottom: 8 }, "口令形态"),
    h("div", { style: styles.row },
      h("label", { style: styles.radio },
        h("input", {
          type: "radio", name: "sp-pw-mode", checked: mode === "random",
          disabled: running,
          onChange: () => setPwMode("random"),
        }),
        "每次开启自动生成新口令",
      ),
      h("label", { style: styles.radio },
        h("input", {
          type: "radio", name: "sp-pw-mode", checked: mode === "fixed",
          disabled: running,
          onChange: () => setPwMode("fixed"),
        }),
        "固定口令",
      ),
    ),
    mode === "fixed"
      ? h("div", { style: Object.assign({}, styles.row, { marginTop: 8 }) },
          h("input", {
            type: "password", value: pwValue, placeholder: "至少 12 个字符",
            disabled: running, autoComplete: "new-password",
            style: styles.input,
            onChange: (event) => setPwValue(event.target.value),
          }),
          h("button", {
            style: styles.btn, type: "button", disabled: running,
            onClick: savePassword,
          }, "保存"),
          pwSaved === "ok"
            ? h("span", { style: styles.tag }, "已保存")
            : (pwSaved === "err" ? h("span", { style: styles.errInline }, pwError || "保存失败") : null),
        )
      : h("div", { style: styles.muted },
          "每次开启都会换一个新口令；域名也是随机的。"),
    running
      ? h("div", { style: styles.muted }, "（运行中不能改口令形态，先点「关闭」）")
      : null,
  ));

  // 操作按钮
  children.push(h("div", { key: "actions", style: Object.assign({}, styles.row, { marginTop: 14 }) },
    h("button", {
      style: styles.primary, type: "button",
      disabled: !!busy || running,
      onClick: doStart,
    }, busy === "start" ? "启动中…" : (running ? "已开启" : "开启外网访问")),
    h("button", {
      style: styles.danger, type: "button",
      disabled: !!busy || !running,
      onClick: doStop,
    }, busy === "stop" ? "停止中…" : "关闭"),
    h("button", { style: styles.btn, type: "button", onClick: load }, "刷新"),
  ));

  // 警示（明文口令的后果必须讲清楚）
  children.push(h("div", { key: "warn", style: styles.warn },
    "⚠ 该入口使本机服务可从外网访问：拿到口令的人可以启停被开放的服务。" +
    (running && status && status.passwordMode === "fixed"
      ? "当前用的是**固定口令**：多次开启口令不变，一旦泄漏就是长期有效。"
      : "口令每次开启都会更新。") +
    "不用时请点「关闭」。"
  ));

  if (error) {
    children.push(h("div", { key: "err", style: styles.err }, String(error)));
  }
  if (output && output.stdout && !running) {
    children.push(h("div", { key: "out", style: styles.block },
      h("div", { style: styles.muted }, "启动器输出"),
      h("pre", { style: Object.assign({}, styles.code, { whiteSpace: "pre-wrap", maxHeight: 180, overflow: "auto" }) },
        String(output.stdout).slice(-1200)),
    ));
  }
  if (status && status.problem) {
    children.push(h("div", { key: "prob", style: styles.err }, String(status.problem)));
  }

  return h("div", { style: styles.card }, children);
}

export function apply(ctx) {
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

export { name, inject };
