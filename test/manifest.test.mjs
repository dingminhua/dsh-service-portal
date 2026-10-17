// dsh-service-portal 清单契约检验（package.json ↔ 宿主运行时）。
//
// 拦的是这类 bug：**不报错，只是静默失去保护**。
//
//   1. 忘记声明 engines.dsh → 任何 DSH 版本都放行。装到不兼容的宿主上会在
//      启动期炸（或被 Loader 拒绝），而发版时一点提示都没有。
//   2. engines.dsh 写法错（区间写反、漏 prerelease）→ `0.2.1-rc.1` 这种
//      **预发布版不命中**，插件在最新版 DSH 上恰好被自己的门禁挡住。
//   3. 退回去只写 peerDependencies → 新版宿主里「engines.dsh 存在就只看它」，
//      两条路径的判定结果会分叉，测出来的和跑起来的不一样。
//   4. 图标越界（超 256 KiB / 绝对路径 / 跑到包目录外 / 非四种格式）→
//      宿主 readPluginMeta 会挂上 meta.error，插件页显示异常标记。
//
// 控制检验原则（正着打/反着打必须不同）：
//   只断言"能通过"没有意义 —— 一个把 requirements 写死的空实现也能通过。
//   所以这里同时打**反例**：把版本区间篡改成不相容的值，判定必须翻转。
//
// 真相来源是宿主自己的 `evaluatePluginCompatibility()`，不是我们对文档的复述。
// 拿不到宿主实现时明确 skip（并在输出里说明），**不假装通过**。
//
// 运行：node --test test/manifest.test.mjs

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, statSync } from "node:fs";
import { dirname, extname, isAbsolute, join, relative, resolve, sep } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const manifest = JSON.parse(readFileSync(join(ROOT, "package.json"), "utf8"));

/**
 * 宿主 app-boot 的候选入口。
 *
 * 优先级：显式 DSH_APP_BOOT（`<dsh根>/node_modules/@deepseek-ai/dsh-app-boot` 或
 * 该包目录本身）→ DSH_RUNTIME_ROOT / DSH_DSH_ROOT 推出的同一路径 → 普通包解析。
 * 桌面应用把运行时放在 app.asar 解包后的 `dsh/` 下，所以不写死任何绝对路径。
 *
 * 注意：这里必须解析到**模块入口**，不能 import 包的 package.json
 * （JSON 模块需要 `with { type: "json" }`，会抛 ERR_IMPORT_ATTRIBUTE_MISSING）。
 * @returns {string[]} 可直接 import 的模块 URL
 */
function candidateAppBoots() {
  /** 把一个可能的 app-boot 目录换成它的 ESM 入口；目录里没有 exports 时退回 lib/index.js。 */
  const entryOf = (dir) => {
    try {
      const pkg = JSON.parse(readFileSync(join(dir, "package.json"), "utf8"));
      const exported = pkg.exports?.["."];
      const rel = typeof exported === "string"
        ? exported
        : exported?.import?.default ?? exported?.import ?? exported?.default;
      if (typeof rel === "string") return pathToFileURL(resolve(dir, rel)).href;
    } catch { /* 下面走默认入口 */ }
    return pathToFileURL(join(dir, "lib", "index.js")).href;
  };

  const bases = [];
  if (process.env.DSH_APP_BOOT) bases.push(entryOf(resolve(process.env.DSH_APP_BOOT)));
  for (const root of [process.env.DSH_RUNTIME_ROOT, process.env.DSH_DSH_ROOT]) {
    if (!root) continue;
    bases.push(entryOf(join(root, "node_modules", "@deepseek-ai", "dsh-app-boot")));
  }
  return bases;
}

/**
 * 载入宿主真实的兼容性判定。
 * @returns {Promise<{evaluatePluginCompatibility: Function, getDshRuntimeVersion: Function}|undefined>}
 *   找不到宿主时 undefined（调用方据此 skip，而不是假装通过）
 */
async function loadHostCompatibility() {
  for (const base of candidateAppBoots()) {
    try {
      const mod = await import(base);
      if (typeof mod.evaluatePluginCompatibility === "function") return mod;
    } catch { /* 换下一个候选 */ }
  }

  // 普通包解析：在 DSH 自带 Node 下跑 `node --test` 时命中。
  try {
    const mod = await import("@deepseek-ai/dsh-app-boot");
    if (typeof mod.evaluatePluginCompatibility === "function") return mod;
  } catch { /* 宿主不在解析路径上 */ }

  return undefined;
}

const host = await loadHostCompatibility();
const skipReason = host === undefined
  ? "找不到宿主 @deepseek-ai/dsh-app-boot；用 DSH_APP_BOOT=<dsh根> 指定后重跑"
  : false;

test("清单：声明了 engines.dsh（新宿主的版本门禁只看它）", () => {
  assert.equal(typeof manifest.engines?.dsh, "string",
    "必须在 engines.dsh 声明兼容的 DSH 区间：没声明则任何 DSH 版本都放行");
  assert.ok(manifest.engines.dsh.trim() !== "", "engines.dsh 不能是空串（空串在宿主判定里等于不相容）");
});

test("清单：engines.dsh 不以 workspace: 开头（宿主明确视为不相容）", () => {
  assert.ok(!manifest.engines.dsh.startsWith("workspace:"),
    "engines.dsh 里出现 workspace: 会被宿主判为不相容（那是 peerDependencies 才认的写法）");
});

test("清单：声明了 dsh.manifestVersion = 1", () => {
  assert.equal(manifest.dsh?.manifestVersion, 1,
    "dsh.manifestVersion 应声明为 1（清单格式标识；不声明等于放弃声明格式版本）");
});

test("清单：dsh.bundle.patch 指向真实存在的补丁文件", () => {
  const patch = manifest.dsh?.bundle?.patch;
  const paths = Array.isArray(patch) ? patch : [patch];
  assert.ok(paths.length > 0 && paths.every((p) => typeof p === "string" && p !== ""),
    "dsh.bundle.patch 必须是非空字符串或字符串数组");
  for (const p of paths) {
    assert.ok(statSync(join(ROOT, p)).isFile(), `补丁文件不存在：${p}`);
  }
});

test("清单：dsh.client.platform = web 且导出了 ./client", () => {
  assert.equal(manifest.dsh?.client?.platform, "web",
    "客户端声明平台必须是 web");
  assert.ok(manifest.exports?.["./client"],
    "声明了 dsh.client 就必须在 exports 里导出 \"./client\"，否则加载器解析子路径时抛错、整个 host 起不来");
});

test("清单：图标是包内相对路径、格式合规、体积在 256 KiB 以内", () => {
  const icon = manifest.icon;
  assert.equal(typeof icon, "string", "必须声明 icon（插件页与插件市场都读它）");
  assert.ok(!isAbsolute(icon) && !/^[A-Za-z][A-Za-z\d+.-]*:/u.test(icon),
    "宿主只接受相对文件路径，绝对路径或带协议前缀会被拒");
  const target = resolve(ROOT, icon);
  const local = relative(ROOT, target);
  assert.ok(local !== ".." && !local.startsWith(`..${sep}`) && !isAbsolute(local),
    "图标必须留在清单所在目录内（宿主会拒绝越界路径）");
  assert.ok([".svg", ".png", ".jpg", ".jpeg", ".webp"].includes(extname(target).toLowerCase()),
    "宿主只接受 SVG / PNG / JPEG / WebP");
  const size = statSync(target).size;
  assert.ok(size > 0 && size <= 256 * 1024, `图标必须在 256 KiB 以内，当前 ${size} 字节`);
});

test("门禁：宿主判定本插件与当前运行时相容（正例）", { skip: skipReason }, () => {
  const runtimeVersion = host.getDshRuntimeVersion();
  const issue = host.evaluatePluginCompatibility(manifest, {}, runtimeVersion);
  assert.equal(issue, undefined,
    `本插件与 dsh ${runtimeVersion} 不相容：${JSON.stringify(issue?.requirements)}\n`
    + `请更新 engines.dsh，或修掉 peer 区间。当前 engines.dsh=${JSON.stringify(manifest.engines?.dsh)}`);
});

test("门禁：运行时版本落在 engines.dsh 区间内", { skip: skipReason }, () => {
  const runtimeVersion = host.getDshRuntimeVersion();
  // 这条与上一条的区别：它**只**看 engines.dsh 这一项，出问题时报错信息能直接
  // 指出是区间覆盖问题，而不是笼统的"不相容"。
  //
  // 关于预发布（实测过，别再猜）：宿主用 semver.satisfies(..., { includePrerelease: true })，
  // 所以 `0.2.1-rc.1` 在 `>=0.2.0 <0.2.1` 与 `>=0.2.1-rc.1 <0.3.0-0` 下**都命中** ——
  // "漏写 rc"并不会像直觉那样把最新预发布版挡在门外。真正的风险是上界卡错
  // （例如写成 `>=0.3.0 <0.4.0-0`），那会连装都装不上，由上面那条正例与
  // 下面那条反例共同兜住。
  const issue = host.evaluatePluginCompatibility(manifest, {}, runtimeVersion);
  assert.equal(issue?.requirements?.["engines.dsh"], undefined,
    `engines.dsh=${JSON.stringify(manifest.engines?.dsh)} 未覆盖当前运行时 ${runtimeVersion}`);
});

test("门禁：反例 —— 篡改成不相容区间后判定必须翻转", { skip: skipReason }, () => {
  // 这条是在验"测试本身有效"：如果连篡改过的清单都判相容，
  // 说明上面几条正例根本没有测到判定逻辑（例如被 try/catch 吞掉）。
  const runtimeVersion = host.getDshRuntimeVersion();
  const tampered = {
    ...manifest,
    engines: { ...manifest.engines, dsh: ">=99.0.0 <100.0.0-0" },
  };
  const issue = host.evaluatePluginCompatibility(tampered, {}, runtimeVersion);
  assert.ok(issue !== undefined, "篡改后的清单必须被判为不相容，否则正例没有意义");
  assert.equal(issue?.requirements?.["engines.dsh"], ">=99.0.0 <100.0.0-0",
    "判定结果必须点名是 engines.dsh 未满足");
  assert.equal(issue?.name, manifest.name, "判定结果必须点名本包");
  assert.equal(issue?.version, manifest.version, "判定结果必须带本包版本（豁免按 name@version 精确匹配）");
});

test("门禁：engines.dsh 存在时 peerDependencies 被忽略（宿主契约）", { skip: skipReason }, () => {
  // 宿主文档与源码一致：有 engines.dsh 就只看它。这里用一个必然不相容的
  // dsh peer 做反例 —— 只要 engines.dsh 相容，判定就不能因 peer 而失败。
  const runtimeVersion = host.getDshRuntimeVersion();
  const withHostilePeer = {
    ...manifest,
    peerDependencies: {
      ...manifest.peerDependencies,
      "@deepseek-ai/dsh": ">=99.0.0 <100.0.0-0",
    },
  };
  assert.equal(host.evaluatePluginCompatibility(withHostilePeer, {}, runtimeVersion), undefined,
    "声明了 engines.dsh 后，宿主应忽略 @deepseek-ai/dsh peer；若这条挂了，说明宿主契约变了，需要重新评估本插件的声明策略");
});
