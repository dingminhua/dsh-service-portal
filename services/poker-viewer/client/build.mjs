// 客户端构建：client/index.jsx（手写 CJS 风格）+ client/icon.ts → lib/client.js
//
// 输出到 **lib/**（不是 client/）：这是 package.json 的 exports 契约。
// DSH 客户端加载器按 `exports["./client"]` 解析插件的前端入口；产物放在
// lib/client.js 与同族插件（dsh-connect-workbuddy / dsh-ldvh）一致。
//
// 踩过的坑（2026-10-15，导致 DSH 启动失败被 WorkBuddy 自动禁用）：
// package.json 声明了 dsh.client.platform=web，但 exports 里**没有** "./client"，
// 加载器解析该子路径时抛 ERR_PACKAGE_PATH_NOT_EXPORTED —— 这是启动期致命错误，
// 整个 host 起不来。产物目录选错不会立刻报错，只会在下次启动时炸。
// 现在 check_poker_viewer_plugin.py 用真实 Node 解析器钉住这条契约。
//
// 运行：node client/build.mjs

import { readFile, writeFile, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const sourceDir = dirname(fileURLToPath(import.meta.url));
const packageRoot = resolve(sourceDir, "..");
const sourcePath = resolve(sourceDir, "index.jsx");
const iconPath = resolve(sourceDir, "icon.ts");
const outputPath = resolve(packageRoot, "lib", "client.js");
const loaderId = "dsh-poker-viewer";

const source = await readFile(sourcePath, "utf8");

// 源文件是 CommonJS 风格但用了 ESM 的 export 语法（便于人读）。这里把它
// 翻成 __ModuleLoader__ 工厂体：export 变成 factory 内的赋值。
// 刻意不做正则替换的"聪明"处理——只处理本文件确实用到的两种形式，
// 出现其它 export 形式必须显式报错，而不是静默产出坏 bundle。
const exportNames = [];
let body = source;

// 1) export function apply(ctx) { ... }  ->  function apply(ctx) { ... }
body = body.replace(/^export function (\w+)\(/gm, (m, fnName) => {
  exportNames.push(fnName);
  return `function ${fnName}(`;
});

// 2) export { name, inject }; / export { name, inject, x };
body = body.replace(/^export \{([^}]+)\};?\s*$/gm, (m, names) => {
  for (const raw of names.split(",")) {
    const n = raw.trim();
    if (!n) continue;
    if (!exportNames.includes(n)) exportNames.push(n);
  }
  return "";
});

if (/^\s*export\s/m.test(body)) {
  throw new Error(
    "client/index.jsx 里仍有未处理的 export 语法；" +
    "build.mjs 只支持 'export function name(' 与 'export { a, b };' 两种形式"
  );
}

const assignments = exportNames
  .map((n) => `    exports.${n} = ${n};`)
  .join("\n");

// 图标：内联家族 64px 品牌图（client/icon.ts 里唯一的内容就是那个 data URI）。
// 内联而不是让浏览器去取 icons/*.png，是为了与家族其它插件（dsm-plugin-card-icon）
// 一致，也避免插件前端再多一个静态资源路由。构建时校验它确实是 PNG data URI，
// 否则报错而不是产出坏图标。
const iconSource = await readFile(iconPath, "utf8");
const iconMatch = iconSource.match(/'data:image\/png;base64,([A-Za-z0-9+/=]+)'/);
if (!iconMatch) {
  throw new Error(
    "client/icon.ts 里找不到 PNG data URI；家族图标必须内联为 " +
    "'data:image/png;base64,...'（见同族 dsh-connect-workbuddy/client/icon.ts）"
  );
}
const iconDataUri = "data:image/png;base64," + iconMatch[1];

const wrapped = `window.__ModuleLoader__.load({
  id: ${JSON.stringify(loaderId)},
  factory: (require) => {
    var module = { exports: {} };
    var exports = module.exports;
    // React 由 DSH 客户端模块系统提供，绝不假设全局 React。
    var React = require("react");
    // 家族 64px 品牌图标（构建期从 client/icon.ts 内联，见 build.mjs 注释）。
    var POKER_VIEWER_PLUGIN_ICON = ${JSON.stringify(iconDataUri)};
${body}
${assignments}
    return module.exports;
  }
});
`;

await mkdir(dirname(outputPath), { recursive: true });
await writeFile(outputPath, wrapped, "utf8");
console.log(`Wrote ${outputPath}（导出：${exportNames.join(", ") || "无"}；`
  + `图标 ${iconDataUri.length} 字符）`);
