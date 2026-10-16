// 客户端分发契约的控制检验（不在真实浏览器里，但验证可证伪的契约部分）。
//
// 拦的是这类 bug：
//   0. **包 exports 契约解析失败**（最重要）→ DSH 启动期致命错误、整个 host 起不来；
//   1. 产物没被 __ModuleLoader__ 包装 → DSH 客户端直接不加载设置页（静默缺失）；
//   2. loader id 与 package.json 的 name 不一致 → 加载器找不到模块；
//   3. 没有 require("react") 却用了 React → 渲染期 ReferenceError（白屏）；
//   4. apply/name/inject 没被导出 → 插槽注册不了；
//   5. 用了 ESM import/export 残留 → 工厂体语法错误；
//   6. 源码改了但产物没重建 → 界面是旧的（这类"看起来能用"的漂移最难查）；
//   7. 图标缺失/漂移 → 设置页图片裂开，家族外观不一致。
//
// 运行：node --test test/client.test.mjs

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync, statSync } from "node:fs";
import { join, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "..");
const CLIENT = join(ROOT, "lib", "client.js");
const SOURCE = join(ROOT, "client", "index.jsx");
const ICON_SRC = join(ROOT, "client", "icon.ts");
const PKG = join(ROOT, "package.json");

const bundle = readFileSync(CLIENT, "utf8");
const source = readFileSync(SOURCE, "utf8");
const iconSource = readFileSync(ICON_SRC, "utf8");
const pkg = JSON.parse(readFileSync(PKG, "utf8"));

// ---------------------------------------------------------------------------
// 最重要的一组：**包级 exports 契约**。
//
// 血的教训（poker-viewer 迁移时实测）：插件声明了 dsh.client.platform = "web"，
// 但 package.json 的 exports 里没有 "./client" 子路径，产物还错放在 client/。
// DSH 客户端加载器按 exports 解析 "./client" 时抛
// ERR_PACKAGE_PATH_NOT_EXPORTED —— 这是**启动期致命错误**，直接把整个 host
// 拖垮；WorkBuddy 用 cordis.patch.yml 里的 `disabled: true` 把插件隔离才救回启动。
// ---------------------------------------------------------------------------

const req = createRequire(import.meta.url);
// 解析包自身主入口需要用「包内文件」做锚点：Node 的 "." 指锚点所在包。
// 用 test/ 里的文件做锚点会解析到 test/ 目录（那不是包），所以单独锚在包根。
const reqFromRoot = createRequire(join(ROOT, "package.json"));

test("exports 契约：真实 Node 解析器能解析 '<包名>/client'（复现崩溃点）", () => {
  // DSH 客户端加载器解析的是 "<包名>/client"（不是相对路径 "./client"）。
  // Node 的**自引用**特性会拿包的 exports 来解析这个名字 —— 与加载器同一条路径。
  let resolved;
  assert.doesNotThrow(() => {
    resolved = reqFromRoot.resolve(`${pkg.name}/client`);
  }, `require.resolve('${pkg.name}/client') 必须成功——失败即 DSH 启动致命错误`);
  assert.equal(resolve(resolved), resolve(CLIENT));
});

test("exports 契约：package.json 声明了 ./client 子路径", () => {
  assert.ok(pkg.exports);
  assert.ok(pkg.exports["./client"], "exports 缺少 ./client");
  assert.equal(pkg.exports["./client"], "./lib/client.js");
});

test("exports 契约：cordis.patch.yml 子路径存在", () => {
  assert.ok(pkg.exports["./cordis.patch.yml"]);
});

test("dsh 声明：bundle.patch 指向存在的 cordis.patch.yml", () => {
  assert.ok(pkg.dsh?.bundle?.patch);
  assert.ok(existsSync(join(ROOT, pkg.dsh.bundle.patch)));
});

test("dsh 声明：client.platform 是 web", () => {
  assert.equal(pkg.dsh?.client?.platform, "web");
});

test("loader id 与 package.json name 一致", () => {
  const match = bundle.match(/id:\s*"([^"]+)"/);
  assert.ok(match, "产物里找不到 loader id");
  assert.equal(match[1], pkg.name);
  assert.equal(pkg.name, "dsh-service-portal");
});

test("产物被 __ModuleLoader__ 包装", () => {
  assert.match(bundle, /window\.__ModuleLoader__\.load\(\{/);
});

test("工厂体 require('react') 存在", () => {
  assert.match(bundle, /var React = require\("react"\)/);
});

test("源码与产物导出一致（apply/name/inject）", () => {
  for (const exp of ["apply", "name", "inject"]) {
    const re = new RegExp(`export\\s+(?:function\\s+)?${exp}\\b|export\\s*\\{[^}]*\\b${exp}\\b`);
    assert.match(source, re, `源码缺少 ${exp}`);
    assert.match(bundle, new RegExp(`exports\\.${exp}\\s*=`), `产物缺少 ${exp}`);
  }
});

test("产物没有残留 ESM export 语法", () => {
  assert.doesNotMatch(bundle, /^\s*export\s/m);
});

test("产物比源码新（构建未漂移）", () => {
  const srcTime = statMs(SOURCE);
  const bundleTime = statMs(CLIENT);
  assert.ok(
    bundleTime >= srcTime - 1000,
    "lib/client.js 比 client/index.jsx 旧：忘了跑 node client/build.mjs？"
  );
});

test("图标内联：产物里含 PNG data URI", () => {
  assert.match(bundle, /data:image\/png;base64,[A-Za-z0-9+/=]+/);
});

test("图标契约：icon.ts 里的 data URI 与产物一致", () => {
  const srcUri = iconSource.match(/'data:image\/png;base64,([A-Za-z0-9+/=]+)'/);
  assert.ok(srcUri, "client/icon.ts 里找不到 PNG data URI");
  const bundleUri = bundle.match(/data:image\/png;base64,([A-Za-z0-9+/=]+)/);
  assert.ok(bundleUri, "产物里找不到图标 data URI");
  assert.equal(bundleUri[1], srcUri[1], "产物图标与 icon.ts 漂移");
});

test("家族一致性：图标与同族 dsh-connect-workbuddy 相同", () => {
  // 家族图标源在 dsh-connect-workbuddy（同作者插件家族）；本插件与它逐字节一致。
  const sibling = join(
    process.env.LOCALAPPDATA ?? "",
    "Programs", "DeepSeek Harness", "resources", "app.asar", "dsh",
    "..", "..", "..", "profiles", "desktop", "node_modules",
    "dsh-connect-workbuddy", "client", "icon.ts",
  );
  if (!existsSync(sibling)) return; // 家族插件不在本机时跳过，不算失败
  const theirs = readFileSync(sibling, "utf8");
  const a = iconSource.match(/'data:image\/png;base64,([A-Za-z0-9+/=]+)'/);
  const b = theirs.match(/'data:image\/png;base64,([A-Za-z0-9+/=]+)'/);
  assert.ok(a && b, "同族插件缺 data URI");
  assert.equal(a[1], b[1], "家族图标漂移：与 dsh-connect-workbuddy 的图标不一致");
});

// ---------------------------------------------------------------------------
// 渲染契约：section 组件必须能真正渲染出来。
//
// 血的教训（2026-10-15 实测）：客户端原本写 `const h = props.h`，但 DSH 把
// section 组件渲染时**不传 h**（真实 ownerProps 只有 close，另外是一组
// use*/snapshot hook）。于是 h === undefined，render 期抛
// "h is not a function"，React 把整棵子树吞掉 —— 设置页左侧照常列出
// 「对外服务门户」，点进去**右侧整片空白**，且没有任何可见错误。
//
// 下面几条就是对它的直接复现与防回归。
// ---------------------------------------------------------------------------

test("元素工厂不得从 props 取（DSH 的 section props 没有 h）", () => {
  assert.doesNotMatch(
    source,
    /props\s*\.\s*h\b/,
    "不能从 props 取 h：DSH 不给 section 组件这个 prop，"
    + "取了会得到 undefined → 渲染期抛错 → 设置页空白",
  );
  assert.doesNotMatch(
    bundle,
    /props\s*\.\s*h\b/,
    "产物里仍有 props.h：渲染会抛 'h is not a function'，面板空白",
  );
});

test("元素工厂必须由模块级 React.createElement 定义", () => {
  assert.match(
    bundle,
    /(?:var|const|let)\s+h\s*=\s*React\.createElement/,
    "缺少模块级 h = React.createElement 定义",
  );
  assert.match(source, /const\s+h\s*=\s*React\.createElement/,
    "源码缺少模块级 h 定义");
});

test("设置组件注册进插件页的插槽（不是死代码，也不注册进宿主设置导航）", () => {
  // 用户要求：「插件设置要放到插件设置里，而不是出现在宿主的设置里」。
  // 参照 workbuddy：注册 plugins.bundle.config / plugins.row.config。
  assert.match(bundle, /"plugins\.bundle\.config"/,
    "缺少 plugins.bundle.config 注册");
  assert.match(bundle, /"plugins\.row\.config"/,
    "缺少 plugins.row.config 注册");
  assert.match(bundle, /ServicePortalSettingsTab/,
    "组件没有被注册（成了死代码）");
  // 反向断言：不能再注册进宿主设置的左侧导航
  assert.ok(!/inject\("settings\.section"/.test(bundle),
    "不应再注册 settings.section（那是宿主设置导航的一整页）");
});

// ---------------------------------------------------------------------------
// 真正把 `apply()` 跑起来，用一个**假的 ctx** 抓住它到底注册了什么。
//
// 为什么不能只做源码正则（上面那条）：正则只能证明"字符串在文件里"，
// 证明不了"注册真的发生了、键真的是那个形状"。本轮就是栽在这 ——
// 我原来注册的是 `settings.section`，正则测试一路绿灯，**位置却是错的**
// （出现在宿主设置导航里，而不是插件页）。所以这里用行为断言：
// 调 apply(ctx)，看 ctx.slots.register 收到什么 name/key。
// ---------------------------------------------------------------------------
function runApply() {
  // 产物的形态是 `window.__ModuleLoader__.load({ id, factory: (require) => {...} })`
  // —— 不是"一堆模块的字典"。第一版我按字典去取 `mods[pkg.name]`，
  // 结果永远取不到，测试报"产物没有可调用的 apply"（是我读错了形状，
  // 不是产物有问题）。这里按真实形状：调 load 拿到那个对象，再跑它的 factory。
  const src = bundle;
  let loaded = null;
  const sandboxWindow = {
    __ModuleLoader__: { load(m) { loaded = m; return m; } },
  };
  let reactStub = null;
  const requireShim = (req) => {
    if (req === "react") {
      if (!reactStub) {
        reactStub = {
          createElement: () => null,
          useState: () => [null, () => {}],
          useEffect: () => {},
          useRef: () => ({ current: null }),
          useCallback: (f) => f,
          Fragment: "F",
        };
      }
      return reactStub;
    }
    throw new Error("unexpected require: " + req);
  };
  // eslint-disable-next-line no-new-func
  const run = new Function("window", "require",
    src + "\n;return window.__ModuleLoader__.__last;");
  sandboxWindow.__ModuleLoader__ = {
    load(m) { loaded = m; return m; },
    get __last() { return loaded; },
  };
  const entry = run(sandboxWindow, requireShim);
  assert.ok(entry && typeof entry.factory === "function",
    "产物没有 __ModuleLoader__.load({ factory }) 形状");
  return { entry, exports: entry.factory(requireShim) };
}

test("apply() 实际注册到插件页槽位（行为断言，不是源码正则）", () => {
  const { exports: mod } = runApply();
  assert.equal(typeof mod.apply, "function", "产物没有可调用的 apply");
  assert.equal(mod.name, pkg.name, "导出 name 与包名不一致");

  const calls = [];
  const ctx = {
    slots: {
      inject(slotName, cb) { calls.push({ kind: "inject", slotName }); cb(); },
      register(opts) {
        calls.push({ kind: "register", name: opts.name, key: opts.key,
                     id: opts.id, priority: opts.priority });
        return () => {};
      },
    },
    effect() {}, get() { return undefined; },
    logger: { info() {}, warn() {}, error() {} },
  };
  mod.apply(ctx);

  const regs = calls.filter((c) => c.kind === "register");
  const names = new Set(regs.map((r) => r.name));
  assert.ok(names.has("plugins.bundle.config"),
    "没有注册 plugins.bundle.config；实际=" + JSON.stringify([...names]));
  assert.ok(names.has("plugins.row.config"),
    "没有注册 plugins.row.config；实际=" + JSON.stringify([...names]));
  assert.ok(!names.has("settings.section"),
    "仍注册到宿主设置导航 settings.section（用户要求挪走）");
});

test("两种包名拼写都注册（裸名 + include: 前缀）", () => {
  const { exports: mod } = runApply();
  const calls = [];
  const ctx = {
    slots: {
      inject(slotName, cb) { calls.push({ kind: "inject", slotName }); cb(); },
      register(opts) {
        calls.push({ kind: "register", name: opts.name, key: opts.key });
        return () => {};
      },
    },
    effect() {}, get() { return undefined; },
    logger: { info() {}, warn() {}, error() {} },
  };
  mod.apply(ctx);
  const regs = calls.filter((c) => c.kind === "register");
  const keys = regs.map((r) => r.key);
  assert.ok(keys.includes(pkg.name),
    "缺少裸包名注册；实际=" + JSON.stringify(keys));
  assert.ok(keys.includes(`include:${pkg.name}`),
    "缺少 include: 前缀注册（只注册裸名会让 include: 挂载下整页空白）；实际="
    + JSON.stringify(keys));
  // 行入口的键必须是 `<包名>#<行 id>` 形状，否则插件页的行上不会出现配置入口
  const rowKeys = regs.filter((r) => r.name === "plugins.row.config").map((r) => r.key);
  assert.ok(rowKeys.length > 0 && rowKeys.every((k) => k.includes("#")),
    "plugins.row.config 的键必须是 <包名>#<行 id>；实际=" + JSON.stringify(rowKeys));
});

function statMs(path) {
  return statSync(path).mtimeMs;
}
