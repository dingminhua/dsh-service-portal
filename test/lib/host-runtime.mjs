// 宿主运行时的**唯一**定位入口（供各检验套件共用）。
//
// 为什么要独立成模块：`test/manifest.test.mjs` 与 `test/host-contract.test.mjs`
// 都要回答同一个问题 ——「当前这台机器上的 DSH 运行时在哪、是哪个版本」。
// 两处各写一份候选路径，迟早会分叉：一处认 app.asar、一处认解包目录，
// 于是在同一台机器上一个套件跑 14 项、另一个套件全 skip，而输出都"绿"。
//
// 桌面版把运行时装在 `app.asar` 里（`<Resources>/app.asar/dsh/`），普通 node
// 的 fs 读不到这种虚拟路径 —— 必须用宿主自带的 Electron 当 node 跑
// （`ELECTRON_RUN_AS_NODE=1`）。所以候选路径**不写死**，而是从环境变量与
// 常见的安装位置推导；推不出来就明确返回 undefined，让调用方 skip，
// 而不是假装通过。

import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

/**
 * 把一个可能的 app-boot 目录换成它的 ESM 入口。
 * 目录里没有 exports 时退回 lib/index.js（与宿主的旧包结构一致）。
 * @param {string} dir app-boot 包目录
 * @returns {string} 可直接 import 的模块 URL
 */
export function entryOf(dir) {
  try {
    const pkg = JSON.parse(readFileSync(join(dir, "package.json"), "utf8"));
    const exported = pkg.exports?.["."];
    const rel = typeof exported === "string"
      ? exported
      : exported?.import?.default ?? exported?.import ?? exported?.default;
    if (typeof rel === "string") return pathToFileURL(resolve(dir, rel)).href;
  } catch { /* 下面走默认入口 */ }
  return pathToFileURL(join(dir, "lib", "index.js")).href;
}

/**
 * 宿主 app-boot 的候选入口。
 *
 * 优先级：显式 DSH_APP_BOOT（`<dsh根>/node_modules/@deepseek-ai/dsh-app-boot`
 * 或该包目录本身）→ DSH_RUNTIME_ROOT / DSH_DSH_ROOT 推出的同一路径。
 * 最后一条由调用方补上普通包解析。
 * @returns {string[]} 可直接 import 的模块 URL
 */
export function candidateAppBoots() {
  const bases = [];
  if (process.env.DSH_APP_BOOT) bases.push(entryOf(resolve(process.env.DSH_APP_BOOT)));
  for (const root of [process.env.DSH_RUNTIME_ROOT, process.env.DSH_DSH_ROOT]) {
    if (!root) continue;
    bases.push(entryOf(join(root, "node_modules", "@deepseek-ai", "dsh-app-boot")));
  }
  return bases;
}

/**
 * 载入宿主真实的 app-boot 模块。
 * @returns {Promise<{mod: any, entryUrl: string}|undefined>}
 *   找不到宿主时 undefined（调用方据此 skip，而不是假装通过）；
 *   `entryUrl` 是真正命中的那个模块 URL，供 `hostRequire()` 用它当解析基准。
 */
export async function loadHost() {
  for (const entryUrl of candidateAppBoots()) {
    try {
      const mod = await import(entryUrl);
      if (typeof mod.evaluatePluginCompatibility === "function") return { mod, entryUrl };
    } catch { /* 换下一个候选 */ }
  }

  // 普通包解析：在 DSH 自带 Node 下跑 `node --test` 时命中。
  try {
    const mod = await import("@deepseek-ai/dsh-app-boot");
    if (typeof mod.evaluatePluginCompatibility === "function") {
      return {
        mod,
        entryUrl: pathToFileURL(createRequire(import.meta.url).resolve("@deepseek-ai/dsh-app-boot")).href,
      };
    }
  } catch { /* 宿主不在解析路径上 */ }

  return undefined;
}

/**
 * 从宿主自己的解析基准去解析一个包（而不是从本仓库的 node_modules）。
 *
 * 为什么必须这样：本仓库只依赖 schemastery；宿主那几十个包只存在于宿主的
 * `app.asar/dsh/node_modules` 下。从本仓库解析必然失败（或更糟：命中一份
 * 版本不同的本地副本，于是"检验通过"与"用户实际跑的"不是同一个东西）。
 * @param {string} entryUrl 宿主模块的 URL（loadHost().entryUrl）
 * @returns {NodeRequire} 绑定到宿主解析路径的 require
 */
export function hostRequire(entryUrl) {
  return createRequire(entryUrl);
}
