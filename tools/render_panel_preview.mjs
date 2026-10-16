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
  },
};

const QR_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 21 21" width="164" height="164" shape-rendering="crispEdges"><rect width="21" height="21" fill="#fff"/><g fill="#111"><rect x="0" y="0" width="7" height="7"/><rect x="14" y="0" width="7" height="7"/><rect x="0" y="14" width="7" height="7"/><rect x="2" y="2" width="3" height="3" fill="#fff"/><rect x="16" y="2" width="3" height="3" fill="#fff"/><rect x="2" y="16" width="3" height="3" fill="#fff"/><rect x="9" y="9" width="3" height="3"/><rect x="13" y="9" width="2" height="2"/><rect x="9" y="13" width="2" height="2"/><rect x="16" y="16" width="3" height="3"/></g></svg>';

function page(stateKey, dark) {
  const state = STATES[stateKey] || STATES.running;
  return `<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>panel-${stateKey}${dark ? "-dark" : ""}</title><style>
  body { margin:0; padding:22px; background:${dark ? "#0b0d11" : "#eceef2"};
         font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;
    --dsw-alias-bg-layer-1:${dark ? "#1a1d23" : "#fff"};
    --dsw-alias-bg-layer-2:${dark ? "#23262d" : "#f3f4f6"};
    --dsw-alias-border-l2:${dark ? "#33373f" : "#e5e7eb"};
    --dsw-alias-brand-primary:${dark ? "#6b86ff" : "#4f6ef7"};
    --dsw-alias-label-primary:${dark ? "#f2f4f8" : "#111827"};
    --dsw-alias-label-secondary:${dark ? "#a4abb8" : "#6b7280"};
    --dsw-alias-state-error-primary:${dark ? "#f87171" : "#dc2626"};
    --dsw-alias-state-idle-primary:${dark ? "#6b7280" : "#9ca3af"};
    --dsw-alias-state-success-primary:${dark ? "#4ade80" : "#16a34a"};
    --dsw-alias-state-warn-primary:${dark ? "#fbbf24" : "#b45309"}; }
</style></head><body><div id="root"></div>
<script>
const STATE = ${JSON.stringify(state)};
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
        root.appendChild(render(React.createElement(Comp, {}), this));
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
  res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
  res.end(page(s, dark));
}).listen(0, "127.0.0.1", function () {
  const p = this.address().port;
  console.log(`http://127.0.0.1:${p}/?s=running`);
  console.log(`http://127.0.0.1:${p}/?s=public`);
  console.log(`http://127.0.0.1:${p}/?s=off`);
});
