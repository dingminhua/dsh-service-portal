/* 真实组件渲染预览：直接 require lib/client.js，在无头 Chrome 里出图。
 *
 * 用途：改样式时肉眼核对层级与节奏。它不是控制检验（不进 check_*.py 那套），
 * 因为它需要**人工看图**，不能自动判过。
 *
 * 为什么不用手写 HTML mock：mock 只能证明"我照着数值画了一遍"，证明不了产物
 * 真的这么渲染。这个 harness 真的调用组件，已经抓到过两次真问题：
 *   · 未启动时两个地址因为 <code> 是行内元素而粘成一行（"...:8899http://..."）；
 *   · 「局域网访问密码」用了和「局域网访问」同级的字号（父子关系读成同级）。
 *
 * 一次只渲染**一种状态**：面板内部有 5 秒轮询，多个面板共用同一个假 fetch 时
 * 会互相串状态（第一版四个面板全渲染成了最后一份数据）。
 *
 * ⚠ 已知局限（别被它误导）：
 *   · 这里的 React 是最小替身，**文本排版不真实** —— 盒子高度按行高算，
 *     所以截图里标题和副标题会"看起来压在一起"。真实渲染不会（用户给的
 *     真实截图里两者本来就在两行）。判断行高/间距请以真实面板为准。
 *   · 它适合看：结构顺序、颜色、按钮胶囊形状、层级是否只差 1px。
 *     不适合看：行高、字距、精确间距。
 *
 * 运行：node tools/render_panel_preview.mjs
 *   然后访问 /?s=running|public|off[&dark=1]，用
 *   chrome --headless --screenshot=... 截图。
 */
import { readFileSync } from "node:fs";
import { createServer } from "node:http";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const clientSrc = readFileSync(join(ROOT, "lib", "client.js"), "utf8");

const STATES = {
  running: {
    ok: true, kind: "portal", running: true, portalPort: 8899,
    portalUrl: "http://127.0.0.1:8899",
    lanUrls: ["http://192.168.71.10:8899", "http://10.198.75.60:8899"],
    lanPassword: "57457404", lanPinCustom: false, lanAuthEnabled: true,
    lanEnabled: true, lanCandidates: ["192.168.71.10", "10.198.75.60", "198.18.0.1"],
    startedAt: "2026-10-16 02:53:03", password: "5cqmIVOWr7T3j1Nz",
    passwordMode: "random", publicUrl: null, problem: null, stoppedClean: false,
  },
  public: {
    ok: true, kind: "portal", running: true, portalPort: 8899,
    portalUrl: "http://127.0.0.1:8899",
    lanUrls: ["http://192.168.71.10:8899", "http://10.198.75.60:8899"],
    lanPassword: "57457404", lanPinCustom: true, lanAuthEnabled: true,
    lanEnabled: true, lanCandidates: ["192.168.71.10", "10.198.75.60"],
    startedAt: "2026-10-16 02:53:03", password: "5cqmIVOWr7T3j1Nz",
    passwordMode: "fixed",
    publicUrl: "https://warm-dawn-1234.trycloudflare.com",
    problem: null, stoppedClean: false,
  },
  off: {
    ok: true, kind: "portal", running: false, portalPort: 8899,
    portalUrl: "http://127.0.0.1:8899",
    lanUrls: ["http://192.168.71.10:8899", "http://10.198.75.60:8899"],
    lanCandidates: ["192.168.71.10", "10.198.75.60"], lanEnabled: true,
    lanAuthEnabled: false, lanPassword: "", publicUrl: null, problem: null,
    stoppedClean: true, codeStamp: "0.7.5",
    // 前置条件齐备的真形态（字段与 lib/index.js checkPrereqs 返回**完全一致**，
    // mock 一旦走形，"预览正常但真机报错"就会再次发生 —— 1.0.1 的假令牌
    // 事故就是这么来的，这里必须照真数据写）。
    prereqs: { ok: true, missing: [],
      python: { ok: true, path: "/usr/bin/python3", configured: null, detail: null },
      cloudflared: { ok: true, path: "/opt/homebrew/bin/cloudflared", detail: null } },
    // 用户主动停过：下次打开 DSH 不该自动起（设置页据此显示那句提示）
    autoStart: false,
    // 点「启动」后 /start 返回的就是这份对象（假 fetch 一律回状态），
    // 所以这里塞一段 stdout 就能把「启动器输出」那一块也画出来。
    stdout: "[portal] 端口 8899 已在听\n[portal] 局域网地址 http://192.168.71.10:8899\n[portal] 已写入 runs/portal_state.json\n",
    exitCode: 0,
  },
  // 缺 cloudflared：内网照常、只有公网受影响 —— 必须是**轻提示**，不是红色警告块。
  misscf: {
    ok: true, kind: "portal", running: false, portalPort: 8899,
    portalUrl: "http://127.0.0.1:8899",
    lanUrls: [], lanCandidates: ["192.168.71.10"], lanEnabled: true,
    lanAuthEnabled: false, lanPassword: "", publicUrl: null, problem: null,
    stoppedClean: true, autoStart: false,
    prereqs: { ok: true, missing: ["cloudflared"],
      python: { ok: true, path: "/usr/bin/python3", configured: null, detail: null },
      cloudflared: { ok: false, path: null,
        detail: "找不到 cloudflared，开启公网访问会失败（内网访问不受影响）。"
          + "请安装：macOS `brew install cloudflared`；Windows `winget install Cloudflare.cloudflared`。"
          + "装好后若仍探测不到，在设置页填写「cloudflared 路径」。" } },
  },
  // 缺 Python：硬阻塞，内网都起不来 —— 用警示块。
  misspy: {
    ok: true, kind: "portal", running: false, portalPort: 8899,
    portalUrl: "http://127.0.0.1:8899",
    lanUrls: [], lanCandidates: ["192.168.71.10"], lanEnabled: true,
    lanAuthEnabled: false, lanPassword: "", publicUrl: null, problem: null,
    stoppedClean: true, autoStart: false,
    prereqs: { ok: false, missing: ["python"],
      python: { ok: false, path: null, configured: null,
        detail: "找不到可用的 Python 3。内网门户由 Python 脚本拉起，没有它门户起不来。"
          + "请安装 Python 3（macOS: brew install python3；Windows: 从 python.org 安装并勾选 Add to PATH），"
          + "或在设置页填写「Python 路径」。" },
      cloudflared: { ok: true, path: "/usr/local/bin/cloudflared", detail: null } },
  },
  // 前置条件都齐、但填的 python 路径不存在已回落：能用，但不是用户以为的那个。
  pyfallback: {
    ok: true, kind: "portal", running: false, portalPort: 8899,
    portalUrl: "http://127.0.0.1:8899",
    lanUrls: [], lanCandidates: ["192.168.71.10"], lanEnabled: true,
    lanAuthEnabled: false, lanPassword: "", publicUrl: null, problem: null,
    stoppedClean: true, autoStart: false,
    prereqs: { ok: true, missing: [],
      python: { ok: true, path: "/usr/bin/python3", configured: "/nope/python",
        detail: "设置页填写的 Python 路径不存在：/nope/python，已自动改用 /usr/bin/python3。" },
      cloudflared: { ok: true, path: "/usr/local/bin/cloudflared", detail: null } },
  },
  // 有节点：三种真实形态各一条（开放且上游在 / 开放但上游死 / 已屏蔽）。
  services: {
    ok: true, kind: "portal", running: true, portalPort: 8899,
    portalUrl: "http://127.0.0.1:8899",
    lanUrls: ["http://192.168.71.10:8899"],
    lanPassword: "57457404", lanPinCustom: false, lanAuthEnabled: true,
    lanEnabled: true, lanCandidates: ["192.168.71.10", "10.198.75.60"],
    startedAt: "2026-10-16 02:53:03", password: "5cqmIVOWr7T3j1Nz",
    passwordMode: "random", publicUrl: null, problem: null, stoppedClean: false,
    services: [
      { key: "rltrain", name: "训练配置台", mount: "/rltrain",
        target: "127.0.0.1:8810", note: "本机 RL 训练面板", enabled: true, alive: true },
      { key: "grafana", name: "监控看板", mount: "/grafana",
        target: "127.0.0.1:3000", note: "", enabled: true, alive: false },
      { key: "files", name: "文件浏览", mount: "/files",
        target: "127.0.0.1:8081", note: "临时给同事拷东西", enabled: false, alive: null },
    ],
  },
  // 局域网访问被关掉：二维码位置显示"已关闭"（不能显示一张扫了打不开的码）。
  lanoff: {
    ok: true, kind: "portal", running: true, portalPort: 8899,
    portalUrl: "http://127.0.0.1:8899",
    lanUrls: ["http://192.168.71.10:8899"],
    lanPassword: "57457404", lanPinCustom: false, lanAuthEnabled: true,
    lanEnabled: false, lanCandidates: ["192.168.71.10", "10.198.75.60"],
    startedAt: "2026-10-16 02:53:03", password: "5cqmIVOWr7T3j1Nz",
    passwordMode: "random", publicUrl: null, problem: null, stoppedClean: false,
  },
  // 内网也没开、公网也没开，且**有节点** —— 用户明确要的这个状态：
  // 两个访问按钮都应该是灰的（各自判断自己的开关），节点卡仍完整可见。
  svcnone: {
    ok: true, kind: "portal", running: true, portalPort: 8899,
    portalUrl: "http://127.0.0.1:8899",
    lanUrls: ["http://192.168.71.10:8899"],
    lanPassword: "57457404", lanPinCustom: false, lanAuthEnabled: true,
    lanEnabled: false, lanCandidates: ["192.168.71.10", "10.198.75.60"],
    startedAt: "2026-10-16 02:53:03", password: "5cqmIVOWr7T3j1Nz",
    passwordMode: "random", publicUrl: null, problem: null, stoppedClean: false,
    services: [
      { key: "rltrain", name: "RL 训练台", mount: "/rltrain",
        target: "127.0.0.1:8800", note: "", enabled: true, alive: false },
    ],
  },
  // 公网已开 + 有节点：用来看"内网访问 / 公网访问"两个按钮同时可点的形态，
  // 以及关掉公网后后者变灰的对比（节点卡的启用/禁用只能这样并排核）。
  svcboth: {
    ok: true, kind: "portal", running: true, portalPort: 8899,
    portalUrl: "http://127.0.0.1:8899",
    lanUrls: ["http://192.168.71.10:8899"],
    lanPassword: "57457404", lanPinCustom: false, lanAuthEnabled: true,
    lanEnabled: true, lanCandidates: ["192.168.71.10", "10.198.75.60"],
    startedAt: "2026-10-16 02:53:03", password: "5cqmIVOWr7T3j1Nz",
    passwordMode: "random", problem: null, stoppedClean: false,
    publicUrl: "https://warm-dawn-1234.trycloudflare.com",
    services: [
      { key: "rltrain", name: "训练配置台", mount: "/rltrain",
        target: "127.0.0.1:8810", note: "本机 RL 训练面板", enabled: true, alive: true },
      { key: "grafana", name: "监控看板", mount: "/grafana",
        target: "127.0.0.1:3000", note: "", enabled: true, alive: false },
    ],
  },
  // 局域网关 + 公网开：验证「内网访问」灰、「公网访问」仍可点（两条通道独立）
  svclanoff: {
    ok: true, kind: "portal", running: true, portalPort: 8899,
    portalUrl: "http://127.0.0.1:8899",
    lanUrls: ["http://192.168.71.10:8899"],
    lanPassword: "57457404", lanPinCustom: false, lanAuthEnabled: true,
    lanEnabled: false, lanCandidates: ["192.168.71.10", "10.198.75.60"],
    startedAt: "2026-10-16 02:53:03", password: "5cqmIVOWr7T3j1Nz",
    passwordMode: "random", problem: null, stoppedClean: false,
    publicUrl: "https://warm-dawn-1234.trycloudflare.com",
    services: [
      { key: "rltrain", name: "训练配置台", mount: "/rltrain",
        target: "127.0.0.1:8810", note: "", enabled: true, alive: true },
    ],
  },
  // 异常退出：凭据还在、端口没人听 —— 这条分支以前只能靠真机复现。
  problem: {
    ok: true, kind: "portal", running: false, portalPort: 8899,
    portalUrl: "http://127.0.0.1:8899",
    lanUrls: ["http://192.168.71.10:8899"],
    lanCandidates: ["192.168.71.10"], lanEnabled: true, lanAuthEnabled: false,
    lanPassword: "", publicUrl: null, stoppedClean: false, codeStamp: "0.8.9",
    problem: "凭据文件还在，但 8899 端口没有进程在听（上次可能是被强杀或崩溃）。",
    autoStart: true,
  },
};

const QR_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 21 21" width="164" height="164" shape-rendering="crispEdges"><rect width="21" height="21" fill="#fff"/><g fill="#111"><rect x="0" y="0" width="7" height="7"/><rect x="14" y="0" width="7" height="7"/><rect x="0" y="14" width="7" height="7"/><rect x="2" y="2" width="3" height="3" fill="#fff"/><rect x="16" y="2" width="3" height="3" fill="#fff"/><rect x="2" y="16" width="3" height="3" fill="#fff"/><rect x="9" y="9" width="3" height="3"/><rect x="13" y="9" width="2" height="2"/><rect x="9" y="13" width="2" height="2"/><rect x="16" y="16" width="3" height="3"/></g></svg>';

function page(stateKey, dark, view, click) {
  const state = STATES[stateKey] || STATES.running;
  return `<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>panel-${stateKey}${dark ? "-dark" : ""}</title><style>
  body { margin:0; padding:22px; background:${dark ? "#0b0d11" : "#eceef2"};
         font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;
    /* 以下令牌**逐条取自宿主 dsh-client-ui-theme 的真实定义**
       （body{...} 与 body[data-ds-dark-theme]{...}），不是手写近似值。
       手写值让预览看不见真 bug：brand-primary 曾被填成 #4f6ef7/#6b86ff（蓝），
       而宿主深色下其实是 #f9fafb —— 预览里主按钮永远正常，真实面板却白底白字。
       预览骗人比没有预览更糟。 */
    --dsw-alias-bg-layer-1:${dark ? "#232324" : "#fff"};
    --dsw-alias-bg-layer-2:${dark ? "#2c2c2e" : "#fff"};
    --dsw-alias-bg-layer-3:${dark ? "#353638" : "#fff"};
    --dsw-alias-border-l1:${dark ? "#ffffff0f" : "#0000000a"};
    --dsw-alias-border-l2:${dark ? "#ffffff1f" : "#0000001a"};
    --dsw-alias-border-l3:${dark ? "#ffffff29" : "#0000001f"};
    --dsw-alias-border-l4:${dark ? "#ffffff33" : "#00000029"};
    --dsw-alias-brand-primary:${dark ? "#f9fafb" : "#0f1115"};
    --dsw-alias-button-primary-fill:${dark ? "#f9fafb" : "#0f1115"};
    --dsw-alias-button-primary-hover:${dark ? "#ebeef2" : "#43454a"};
    --dsw-alias-label-primary:${dark ? "#f9fafb" : "#0f1115"};
    --dsw-alias-label-secondary:${dark ? "#cfd3d6" : "#61666b"};
    --dsw-alias-label-tertiary:${dark ? "#adb2b8" : "#81858c"};
    --dsw-alias-label-dimmed:${dark ? "#43454a" : "#e1e5ee"};
    --dsw-alias-label-primary-foreground:${dark ? "#0f1115" : "#fff"};
    --dsw-alias-state-error-primary:${dark ? "#f25a5a" : "#ec1313"};
    --dsw-alias-state-idle-primary:${dark ? "#545557" : "#d4d4d4"};
    --dsw-alias-state-success-primary:${dark ? "#22c55e" : "#22c55e"};
    --dsw-alias-state-warn-primary:${dark ? "#f59e0b" : "#f59e0b"};
    --dsw-alias-state-business-primary:${dark ? "#7aaaff" : "#4176e6"};
    --dsw-alias-switch-thumb:${dark ? "#adb2b8" : "#fff"};
    --dsw-alias-interactive-bg-hover:${dark ? "#ffffff14" : "#2631480f"};
    --dsw-alias-interactive-bg-hover-solid:${dark ? "#353638" : "#f1f3f5"};
    --dsw-alias-interactive-bg-active:${dark ? "#ffffff24" : "#2631481a"};
    --dsw-alias-toast-bg:${dark ? "#43454a" : "#353638"};
    --dsw-alias-toast-label:#fff;
    --dsw-alias-bg-mask-1:${dark ? "#00000080" : "#0000003d"};
    --dsw-mask-blur:blur(2px);
    --dsw-elevation-prominent:0 1px 2px rgba(0,0,0,.04),0 3px 8px rgba(0,0,0,.04),0 0 20px rgba(0,0,0,.05);
    --dsw-shadow-lv3:0 0 1px 0 #0003,0 0 4px 0 #00000005,0 12px 32px 0 #00000014;
    --dsw-radius-xs:4px; --dsw-radius-sm:8px; --dsw-radius-md:12px;
    --dsw-radius-lg:16px; --dsw-radius-xl:20px; --dsw-radius-panel:28px;
    --ds-ease-in-out:cubic-bezier(.4,0,.2,1); --ds-transition-duration-fast:.1s;
    --dsw-alias-bg-base:${dark ? "#151517" : "#fff"} };
</style></head><body><div id="root"></div>
<script>
const STATE = ${JSON.stringify(state)};
const VIEW = ${JSON.stringify(view)};
const CLICK = ${JSON.stringify(click || "")};
const QR_SVG = ${JSON.stringify(QR_SVG)};
const fakeJson = (obj) => Promise.resolve({
  ok:true, status:200, text: async () => JSON.stringify(obj),
  json: async () => JSON.parse(JSON.stringify(obj)),
});
window.fetch = (url) => String(url).includes("/qr")
  ? fakeJson({ ok:true, qr:"data:image/svg+xml;base64," + btoa(QR_SVG) })
  : fakeJson(STATE);

let CURRENT = null;
const React = {
  createElement: (type, props, ...kids) => ({ type, props: props || {}, kids }),
  useState(init) {
    const inst = CURRENT, i = inst.cursor++;
    if (!(i in inst.hooks)) inst.hooks[i] = typeof init === "function" ? init() : init;
    const set = (v) => {
      inst.hooks[i] = typeof v === "function" ? v(inst.hooks[i]) : v;
      inst.schedule();
    };
    return [inst.hooks[i], set];
  },
  useEffect(fn, deps) {
    const inst = CURRENT, i = inst.cursor++;
    const prev = inst.effects[i];
    const changed = !prev || !deps || deps.some((d, k) => d !== prev.deps[k]);
    if (changed) {
      if (prev && prev.cleanup) { try { prev.cleanup(); } catch (e) {} }
      inst.effects[i] = { deps: deps || [], cleanup: fn() };
    }
  },
  useRef(v) {
    const inst = CURRENT, i = inst.cursor++;
    if (!(i in inst.refs)) inst.refs[i] = { current: v };
    return inst.refs[i];
  },
};
window.__ModuleLoader__ = { load: ({ factory }) => { window.__FACTORY__ = factory; } };
</script>
<script>${clientSrc}</script>
<script>
function render(v, inst) {
  if (v === null || v === undefined || v === false || v === true) return document.createTextNode("");
  if (typeof v === "string" || typeof v === "number") return document.createTextNode(String(v));
  if (Array.isArray(v)) {
    const f = document.createDocumentFragment();
    v.forEach((k) => f.appendChild(render(k, inst)));
    return f;
  }
  if (typeof v.type === "function") {
    CURRENT = inst; inst.cursor = 0;
    return render(v.type(v.props), inst);
  }
  const el = document.createElement(v.type);
  const p = v.props || {};
  if (p.style) {
    el.setAttribute("style", Object.entries(p.style)
      .filter(([, val]) => val !== undefined && val !== null)
      .map(([k, val]) => {
        const prop = k.replace(/[A-Z]/g, (m) => "-" + m.toLowerCase());
        return prop + ":" + styleValue(prop, val);
      })
      .join(";"));
  }
  for (const [k, val] of Object.entries(p)) {
    if (["style", "children", "key"].includes(k)) continue;
    if (val === undefined || val === null || val === false) continue;
    if (k.startsWith("on") && typeof val === "function") el.addEventListener(k.slice(2).toLowerCase(), val);
    // 注意：className 必须映射成 class，否则会变成一个**字面量 className 属性**，
    // 样式类完全不生效 —— 本仓库改成"外观走注入 CSS + className"之后，
    // 预览就会画出一个**和真实渲染完全不同**的页面（栅格不并排、hover 没有）。
    // 这种"预览骗人"比没有预览更糟，所以这里必须与 React 的行为一致。
    else if (k === "className") el.setAttribute("class", val);
    else el.setAttribute(k, val === true ? "" : val);
  }
  (v.kids || []).forEach((k) => el.appendChild(render(k, inst)));
  return el;
}
const mod = window.__FACTORY__((n) => {
  if (n === "react") return React;
  throw new Error("unexpected require: " + n);
});
// React 会给数值型样式自动加 px（borderRadius:999 → border-radius:999px）。
// 这个 harness 必须照做，否则会得出错误结论：少了单位 CSS 直接丢弃，
// 按钮看起来是直角而不是胶囊 —— 那是 harness 的错，不是组件的错。
const UNITLESS = new Set(["lineHeight","flex","flexGrow","flexShrink","opacity","zIndex",
  "fontWeight","order","zoom","aspectRatio","tabSize","columnCount","scale",
  "animationIterationCount","strokeWidth","strokeOpacity","strokeDasharray",
  "strokeDashoffset","strokeMiterlimit","fillOpacity","floodOpacity","stopOpacity",
  "borderImageSlice","gridRow","gridColumn"]);
function styleValue(prop, val) {
  if (typeof val === "number" && val !== 0 && !UNITLESS.has(prop)) return val + "px";
  return val;
}
(async () => {
  try {
    let Comp = null;
    const ctx = { slots: { inject: (s, fn) => fn(), register: (c, comp) => { Comp = comp; } } };
    const root = document.getElementById("root");
    const inst = {
      hooks: {}, effects: {}, refs: {}, cursor: 0, pending: false, draw() {
        root.innerHTML = "";
        root.appendChild(render(
          React.createElement(Comp, VIEW ? { view: VIEW } : {}), this));
      }, schedule() {
        if (this.pending) return;
        this.pending = true;
        Promise.resolve().then(() => { this.pending = false; this.draw(); });
      },
    };
    mod.apply(ctx);
    inst.draw();
    await new Promise((r) => setTimeout(r, 50));
    inst.draw();
    // click=<selector>：点一下再画一次（确认框是 setState 之后才出现的）
    if (CLICK) {
      const target = document.querySelector(CLICK);
      if (target) {
        target.click();
        await new Promise((r) => setTimeout(r, 50));
      } else {
        document.title = "CLICK_MISS::" + CLICK;
      }
    }
    // 调试：把关键元素的**实测盒子**写到 title 里，用来判断"看起来重叠"
    // 到底是真重叠还是只是行距紧（截图靠肉眼判断会误判）。
    if (new URLSearchParams(location.search).get("debug") === "1") {
      const boxes = [...root.querySelectorAll("div,span,code")].slice(0, 14).map((el) => {
        const r = el.getBoundingClientRect();
        return (el.textContent || "").slice(0, 14).replace(/\s+/g, " ") +
          " [x=" + Math.round(r.x) + " y=" + Math.round(r.y) +
          " w=" + Math.round(r.width) + " h=" + Math.round(r.height) + "]";
      });
      document.title = "BOXES::" + JSON.stringify(boxes);
    } else {
      document.title = "RENDER_OK";
    }
  } catch (err) {
    document.title = "RENDER_FAIL";
    const box = document.createElement("pre");
    box.style.color = "#dc2626";
    box.textContent = "RENDER ERROR: " + (err && err.stack ? err.stack : err);
    document.body.insertBefore(box, document.body.firstChild);
  }
})();
</script>
</body></html>`;
}

createServer((req, res) => {
  const u = new URL(req.url, "http://127.0.0.1");
  const s = u.searchParams.get("s") || "running";
  const dark = u.searchParams.get("dark") === "1";
  // view=summary：插件列表行/折叠态用的一行摘要。它也是产品的一部分，
  // 因此和面板一样要能单独看（不传 view 就是完整面板）。
  const view = u.searchParams.get("view") || "";
  // click=<selector>：渲染完成后点一下再截图。
  // 确认框是**组件局部状态**（setState 之后才出现），不在 status 里，
  // 所以没法用 s= 造出来 —— 只能真的点。用它来核对话框的形态与文案。
  const click = u.searchParams.get("click") || "";
  res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
  res.end(page(s, dark, view, click));
}).listen(0, "127.0.0.1", function () {
  const p = this.address().port;
  console.log(`http://127.0.0.1:${p}/?s=running`);
  console.log(`http://127.0.0.1:${p}/?s=public`);
  console.log(`http://127.0.0.1:${p}/?s=off`);
  console.log(`http://127.0.0.1:${p}/?s=services`);
  console.log(`http://127.0.0.1:${p}/?s=problem`);
  console.log(`http://127.0.0.1:${p}/?s=lanoff`);
  console.log(`http://127.0.0.1:${p}/?s=misscf`);
  console.log(`http://127.0.0.1:${p}/?s=misspy`);
  console.log(`http://127.0.0.1:${p}/?s=pyfallback`);
});
