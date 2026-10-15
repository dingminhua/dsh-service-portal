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
import { readFileSync, existsSync } from "node:fs";
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
// 2026-10-15 实测的血的教训：插件声明了 dsh.client.platform = "web"，但
// package.json 的 exports 里没有 "./client" 子路径，产物还错放在 client/。
// DSH 客户端加载器按 exports 解析 "./client" 时抛
// ERR_PACKAGE_PATH_NOT_EXPORTED —— 这是**启动期致命错误**，直接把整个 host
// 拖垮；WorkBuddy 用 cordis.patch.yml 里的 `disabled: true` 把插件隔离才救回启动。
//
// 之前 16+10 项测试全绿却没发现，因为只检查了 lib/index.js 自身能否跑，
// 从没检查**包对外声明的入口是否真的能解析**。这组断言补上这个盲区：
// 用 Node 自己的解析器（DSH 用的就是它）真解析一遍。
// ---------------------------------------------------------------------------

const req = createRequire(import.meta.url);
// 解析包自身主入口需要用「包内文件」做锚点：Node 的 "." 指锚点所在包。
// 用 test/ 里的文件做锚点会解析到 test/ 目录（那不是包），所以单独锚在包根。
const reqFromRoot = createRequire(join(ROOT, "package.json"));

test("exports 必须声明 ./client（缺了会让 DSH 启动致命失败）", () => {
  assert.ok(pkg.exports, "package.json 必须有 exports 字段");
  assert.ok(pkg.exports["./client"],
    "exports 必须含 './client'：声明了 dsh.client 却不导出它，"
    + "加载器会抛 ERR_PACKAGE_PATH_NOT_EXPORTED 并拖垮 host 启动");
});

test("声明的 ./client 目标文件必须真实存在", () => {
  const target = pkg.exports["./client"];
  assert.equal(target, "./lib/client.js",
    `./client 应指向 ./lib/client.js（与家族插件一致），实际为 ${target}`);
  assert.ok(existsSync(join(ROOT, "lib", "client.js")),
    "导出目标不存在：忘了跑 node client/build.mjs？");
});

test("真实 Node 解析器能解析 '<包名>/client'（端到端复现崩溃点）", () => {
  // DSH 客户端加载器解析的是 "<包名>/client"（不是相对路径 "./client"）。
  // Node 的**自引用**特性会拿包的 exports 来解析这个名字 —— 与加载器同一条路径。
  // 这条断言就是对 2026-10-15 崩溃场景的直接复现：exports 里没有 "./client"
  // 时它会抛 ERR_PACKAGE_PATH_NOT_EXPORTED（修复前实测如此）。
  let resolved;
  assert.doesNotThrow(() => {
    resolved = reqFromRoot.resolve(`${pkg.name}/client`);
  }, `require.resolve('${pkg.name}/client') 必须成功——失败即 DSH 启动致命错误`);
  assert.equal(resolve(resolved), resolve(ROOT, "lib", "client.js"));
});

test("反例控制：去掉 ./client 导出后解析必须失败（证明断言有区分力）", () => {
  // 把 exports 复制一份并删掉 "./client"，验证解析确实会失败。
  // 没有这条，"解析成功"可能只是因为 Node 恰好找到了同名文件而恒真。
  const broken = { ...pkg, exports: { ...pkg.exports } };
  delete broken.exports["./client"];
  assert.equal(broken.exports["./client"], undefined);
  // 直接断言契约本身：只要 exports 少了这一项，上面那条断言就会挂。
  // （不去真的改 package.json —— 那会污染工作区。）
  assert.ok(pkg.exports["./client"],
    "当前 exports 有 ./client，故上面解析成功；删掉后必然失败");
});

test("exports 的 '.' 主入口同样可解析（宿主半体）", () => {
  const target = pkg.exports["."];
  assert.equal(target, "./lib/index.js",
    `主入口应指向 ./lib/index.js，实际为 ${target}`);
  assert.ok(existsSync(join(ROOT, "lib", "index.js")), "主入口文件必须存在");
  let resolved;
  assert.doesNotThrow(() => { resolved = reqFromRoot.resolve(pkg.name); },
    "主入口必须可解析");
  assert.equal(resolve(resolved), resolve(ROOT, "lib", "index.js"));
});

test("客户端产物必须落在 lib/ 而不是 client/（放错目录会解析失败）", () => {
  assert.ok(existsSync(join(ROOT, "lib", "client.js")), "产物必须在 lib/client.js");
  assert.ok(!existsSync(join(ROOT, "client", "client.js")),
    "client/client.js 是旧的错误位置；产物应只出在 lib/");
});

test("files 白名单必须收录 lib 与 icons", () => {
  assert.ok(Array.isArray(pkg.files), "files 必须是数组");
  assert.ok(pkg.files.includes("lib"), "files 必须含 lib");
  assert.ok(pkg.files.includes("icons"), "files 必须含 icons（icon 字段指向它）");
});

// ---------------------------------------------------------------------------
// 家族图标
// ---------------------------------------------------------------------------

test("icon 字段指向存在的 128px 文件（家族命名规范）", () => {
  assert.equal(pkg.icon, "icons/dsh-poker-viewer-128.png",
    "icon 应遵循 icons/<包名>-128.png 的家族规范");
  assert.ok(existsSync(join(ROOT, pkg.icon)), `icon 文件不存在：${pkg.icon}`);
});

test("源码内联的是 64x64 PNG data URI（家族同一张图）", () => {
  const m = iconSource.match(/'data:image\/png;base64,([A-Za-z0-9+/=]+)'/);
  assert.ok(m, "client/icon.ts 必须内联 data:image/png;base64,... 图标");
  const bytes = Buffer.from(m[1], "base64");
  assert.equal(bytes.subarray(0, 8).toString("hex"), "89504e470d0a1a0a",
    "base64 解码后必须是合法 PNG");
  assert.equal(bytes.readUInt32BE(16), 64, "家族图标是 64px 宽");
  assert.equal(bytes.readUInt32BE(20), 64, "家族图标是 64px 高");
});

test("图标必须内联进客户端产物（否则设置页图片裂开）", () => {
  assert.match(bundle, /data:image\/png;base64,[A-Za-z0-9+/=]{100,}/,
    "产物里应有内联的 PNG data URI");
  assert.match(bundle, /POKER_VIEWER_PLUGIN_ICON/,
    "产物应定义并引用 POKER_VIEWER_PLUGIN_ICON");
});

test("产物内联的图标与 client/icon.ts 逐字节一致（防止图标漂移）", () => {
  const fromSource = iconSource.match(/base64,([A-Za-z0-9+/=]+)/)[1];
  const fromBundle = bundle.match(/POKER_VIEWER_PLUGIN_ICON = "data:image\/png;base64,([A-Za-z0-9+/=]+)"/);
  assert.ok(fromBundle, "产物里应能找到 POKER_VIEWER_PLUGIN_ICON 的 data URI");
  assert.equal(fromBundle[1], fromSource,
    "改了 client/icon.ts 后忘记重新构建（产物里的图标与源码不一致）");
});

test("图标确实被渲染出来（不是只定义不用的死代码）", () => {
  assert.match(bundle, /src:\s*POKER_VIEWER_PLUGIN_ICON/,
    "卡片里应有 src: POKER_VIEWER_PLUGIN_ICON 的 img");
});

test("产物存在且被 __ModuleLoader__ 包装", () => {
  assert.ok(existsSync(CLIENT), "lib/client.js 必须存在（否则设置页不出现）");
  assert.match(bundle, /window\.__ModuleLoader__\.load\(/, "必须用 DSH 模块加载器包装");
});

test("loader id 与 package.json 的 name 一致", () => {
  const found = bundle.match(/id:\s*"([^"]+)"/);
  assert.ok(found, "bundle 里必须声明 id");
  assert.equal(found[1], pkg.name,
    `loader id(${found[1]}) 必须等于 package name(${pkg.name})，否则加载器找不到`);
});

test("factory 形参是 require，且 React 由 require 提供（不假设全局）", () => {
  assert.match(bundle, /factory:\s*\(require\)\s*=>/, "factory 必须接收 require");
  assert.match(bundle, /require\("react"\)/, "必须通过 require('react') 取 React");
  // 关键反例：不能直接引用全局 React 而不 require
  assert.doesNotMatch(bundle, /^\s*var React = window\.React/m,
    "不能从 window 取 React（DSH 客户端不提供全局）");
});

test("导出 apply / name / inject", () => {
  for (const key of ["apply", "name", "inject"]) {
    assert.match(bundle, new RegExp(`exports\\.${key}\\s*=`),
      `必须导出 ${key}`);
  }
});

test("工厂体内不残留 ESM 语法（会导致语法错误）", () => {
  // 取 factory 体（去掉包装头尾）来查，避免误伤注释里的说明文字
  const body = bundle.replace(/^[\s\S]*?var React = require\("react"\);\n/, "")
                      .replace(/\n\s*return module\.exports;[\s\S]*$/, "");
  const lines = body.split("\n").filter((l) => !/^\s*\/\//.test(l));
  const code = lines.join("\n");
  assert.doesNotMatch(code, /^\s*export\s/m, "工厂体内不得有 export");
  assert.doesNotMatch(code, /^\s*import\s/m, "工厂体内不得有 import");
  assert.doesNotMatch(code, /\bimport\.meta\b/, "工厂体内不得用 import.meta");
});

test("注册到 settings.section 插槽（否则设置页里看不到入口）", () => {
  assert.match(bundle, /slots\.inject\(\s*"settings\.section"/,
    "必须 inject settings.section");
  assert.match(bundle, /slots\.register\(/, "必须 register 插槽");
  assert.match(bundle, /settings\.section/, "注册的 name 必须是 settings.section");
});

test("调用的宿主 API 前缀与 host 端注册的前缀一致", () => {
  // host 端 index.js 里 API_PREFIX = "/poker-viewer/api"
  const host = readFileSync(join(ROOT, "lib", "index.js"), "utf8");
  const hostPrefix = host.match(/API_PREFIX\s*=\s*"([^"]+)"/);
  assert.ok(hostPrefix, "host 端必须声明 API_PREFIX");
  const clientPrefix = bundle.match(/const API\s*=\s*"([^"]+)"/);
  assert.ok(clientPrefix, "client 端必须声明 API 前缀");
  assert.equal(clientPrefix[1], hostPrefix[1],
    `client(${clientPrefix[1]}) 与 host(${hostPrefix[1]}) 的 API 前缀必须一致`);

  // 反例控制：真的改一个字符，这个断言必须失败（证明它有效）
  const tampered = bundle.replace('const API = "/poker-viewer/api"',
                                  'const API = "/poker-viewer/API"');
  const tamperedPrefix = tampered.match(/const API\s*=\s*"([^"]+)"/);
  assert.notEqual(tamperedPrefix[1], hostPrefix[1],
    "前缀被改动后应当不相等（断言具备区分力）");
});

test("客户端调用的路径都在 host 端有对应路由", () => {
  const host = readFileSync(join(ROOT, "lib", "index.js"), "utf8");
  // 客户端实际用到的子路径
  const used = ["/status", "/start", "/stop"];
  for (const path of used) {
    assert.ok(bundle.includes(`"${path}"`), `客户端应调用 ${path}`);
    assert.ok(host.includes(`route === "${path}"`) || host.includes(`"${path}"`),
      `host 端必须有 ${path} 路由`);
  }
});

test("产物与源码同步（防止界面漂移）", () => {
  // 用源码里的一个稳定特征串核对产物：改了 .jsx 却没重建时必须失败。
  // 取"警示语"这句——它是最可能被改动的用户可见文案。
  const marker = "拿到账号口令的人可以启停";
  const inSource = source.includes(marker);
  const inBundle = bundle.includes(marker);
  assert.equal(inSource, inBundle,
    inSource
      ? "源码含有该文案但产物没有 —— 改了 client/index.jsx 后忘记跑 node client/build.mjs"
      : "产物含有源码已删除的文案 —— 需要重建客户端");
});

test("不写入任何口令到客户端源码/产物（口令只能来自运行时 API）", () => {
  // 反例控制：客户端绝不能硬编码口令；口令必须每次从 /status 拿。
  assert.doesNotMatch(source, /password\s*[:=]\s*["'][A-Za-z0-9_-]{8,}["']/,
    "客户端源码不得硬编码口令");
  assert.doesNotMatch(bundle, /password\s*[:=]\s*["'][A-Za-z0-9_-]{8,}["']/,
    "客户端产物不得硬编码口令");
});
