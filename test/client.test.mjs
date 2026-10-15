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

test("家族一致性：图标与同族 poker-viewer 相同", () => {
  const sibling = resolve(ROOT, "services", "poker-viewer", "client", "icon.ts");
  if (!existsSync(sibling)) return; // 不在本仓库（独立发布）时跳过，不算失败
  const theirs = readFileSync(sibling, "utf8");
  const a = iconSource.match(/'data:image\/png;base64,([A-Za-z0-9+/=]+)'/);
  const b = theirs.match(/'data:image\/png;base64,([A-Za-z0-9+/=]+)'/);
  assert.ok(a && b, "同族插件缺 data URI");
  assert.equal(a[1], b[1], "家族图标漂移：与 poker-viewer 的图标不一致");
});

function statMs(path) {
  return statSync(path).mtimeMs;
}
