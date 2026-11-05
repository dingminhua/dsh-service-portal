#!/usr/bin/env node
/* 用宿主自己的运行时跑「需要 DSH 运行时」的那几个检验套件。
 *
 * 为什么需要它：宿主桌面版装在 `app.asar` 里，**普通 node 的 fs 读不到这种虚拟路径**，
 * 于是 test/manifest.test.mjs 与 test/host-contract.test.mjs 里所有依赖宿主的断言
 * 都会 skip —— 输出仍然是绿的（skipped 不算 fail），但门禁其实一项没跑。
 * 本仓库把「跳过」和「通过」分得很清：找不到宿主时这里返回 **2（跳过）**，绝不返回 0。
 *
 * 用法：
 *   npm run test:host                 # 四个套件全跑（含 23 项宿主契约）
 *   npm run test:host -- test/manifest.test.mjs
 *   DSH_APP_BOOT=<app.asar 里的 dsh-app-boot 目录> DSH_APP_EXE=<宿主可执行文件> npm run test:host
 *
 * 认三种宿主形态：
 *   1. 桌面版 app.asar（默认）：用宿主自带 Electron 当 node 跑（ELECTRON_RUN_AS_NODE=1）；
 *   2. 解包后的 dsh 目录：DSH_APP_BOOT 指向**可读目录**时，直接用当前 node；
 *   3. 找不到：打印原因并返回 2。
 *
 * 为什么不用硬编码路径：本仓库同时跑 macOS / Windows / Linux（见 .github/workflows），
 * 写死一处安装位置，换台机器或换一种安装包就"看起来通过"。所以路径全部按平台推导，
 * 并且允许用环境变量覆盖。
 */
import { spawnSync } from "node:child_process";
import { existsSync, readdirSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const DEFAULT_FILES = [
  "test/host.test.mjs",
  "test/client.test.mjs",
  "test/manifest.test.mjs",
  "test/host-contract.test.mjs",
];

const args = process.argv.slice(2).filter((arg) => arg !== "--");
const files = args.length > 0 ? args : DEFAULT_FILES;

const isFile = (path) => {
  try { return statSync(path).isFile(); } catch { return false; }
};
const isDir = (path) => {
  try { return statSync(path).isDirectory(); } catch { return false; }
};

/** app.asar 里 dsh-app-boot 的位置（宿主包的 ESM 入口在它下面）。 */
const bootFromResources = (resources) =>
  join(resources, "app.asar", "dsh", "node_modules", "@deepseek-ai", "dsh-app-boot");

/** Squirrel 布局会把应用放进 `app-<版本>` 子目录：基目录与它的每个子目录都算候选。 */
function withSquirrelBases(base) {
  const bases = [base];
  try {
    for (const name of readdirSync(base).filter((n) => n.startsWith("app-")).sort().reverse()) {
      bases.push(join(base, name));
    }
  } catch { /* 目录不存在就算了，交给下面的存在性检查 */ }
  return bases;
}

/** 各平台默认的「可执行文件 + resources 目录」候选。只做发现，不假设一定存在。 */
function hostCandidates() {
  const out = [];
  if (process.platform === "darwin") {
    const contents = "/Applications/DeepSeek Harness.app/Contents";
    out.push({ exe: join(contents, "MacOS", "DeepSeek Harness"), resources: join(contents, "Resources") });
  } else if (process.platform === "win32") {
    const bases = [
      process.env.LOCALAPPDATA && join(process.env.LOCALAPPDATA, "Programs", "DeepSeek Harness"),
      process.env.ProgramFiles && join(process.env.ProgramFiles, "DeepSeek Harness"),
      process.env["ProgramFiles(x86)"] && join(process.env["ProgramFiles(x86)"], "DeepSeek Harness"),
    ].filter(Boolean);
    for (const base of bases) {
      for (const dir of withSquirrelBases(base)) {
        out.push({ exe: join(dir, "DeepSeek Harness.exe"), resources: join(dir, "resources") });
      }
    }
  } else {
    for (const exe of [
      "/opt/DeepSeek Harness/deepseek-harness",
      "/opt/deepseek-harness/deepseek-harness",
      "/usr/lib/deepseek-harness/deepseek-harness",
    ]) {
      out.push({ exe, resources: join(dirname(exe), "resources") });
      out.push({ exe, resources: join(dirname(exe), "..", "resources") });
    }
  }
  return out;
}

/** 选一个能真正跑起来的宿主；找不到返回 undefined（调用方据此返回跳过码 2）。 */
function resolveRuntime() {
  const explicitBoot = process.env.DSH_APP_BOOT;
  const explicitExe = process.env.DSH_APP_EXE || process.env.DSH_ELECTRON;

  if (explicitBoot) {
    // 可读目录 = 解包后的 dsh-app-boot，普通 node 就能 import。
    if (isDir(explicitBoot)) return { mode: "node", boot: explicitBoot };
    // asar 内路径：普通 node 读不到，必须借宿主的 Electron 当 node。
    if (explicitExe && isFile(explicitExe)) {
      return { mode: "electron", exe: explicitExe, boot: explicitBoot };
    }
    const fallback = hostCandidates().find((candidate) => isFile(candidate.exe));
    if (fallback) return { mode: "electron", exe: fallback.exe, boot: explicitBoot };
    return undefined;
  }

  const explicitResources = process.env.DSH_RESOURCES;
  if (explicitResources && isFile(join(explicitResources, "app.asar"))) {
    const exe = explicitExe && isFile(explicitExe)
      ? explicitExe
      : hostCandidates().find((candidate) => isFile(candidate.exe))?.exe;
    if (exe) return { mode: "electron", exe, boot: bootFromResources(explicitResources) };
  }

  for (const candidate of hostCandidates()) {
    if (!isFile(candidate.exe)) continue;
    if (!isFile(join(candidate.resources, "app.asar"))) continue;
    return { mode: "electron", exe: candidate.exe, boot: bootFromResources(candidate.resources) };
  }
  return undefined;
}

const runtime = resolveRuntime();
if (!runtime) {
  console.error("[test:host] 找不到 DSH 宿主运行时 —— 这是**跳过**（退出码 2），不是通过。");
  console.error("  · 桌面版默认只探测 /Applications 与 %LOCALAPPDATA%\\Programs 下的安装位置；");
  console.error("  · 装在别处时显式指定后重跑：");
  console.error("      DSH_APP_BOOT=<app.asar/dsh/node_modules/@deepseek-ai/dsh-app-boot> \\");
  console.error("      DSH_APP_EXE=<宿主可执行文件> npm run test:host");
  console.error("  · 也可以把解包后的 dsh-app-boot 目录传给 DSH_APP_BOOT（可读目录 = 用普通 node 跑）。");
  process.exit(2);
}

const missing = files.filter((file) => !isFile(resolve(ROOT, file)));
if (missing.length > 0) {
  console.error(`[test:host] 这些套件文件不存在：\n  ${missing.join("\n  ")}`);
  process.exit(1);
}

// ELECTRON_RUN_AS_NODE 对真正的 node 是无关变量；对 Electron 可执行文件是必须的
// （否则会去开窗口而不是跑测试）。两种形态都设，省掉"重入时忘了设"的坑。
const env = { ...process.env, DSH_APP_BOOT: runtime.boot, ELECTRON_RUN_AS_NODE: "1" };
const command = runtime.mode === "electron" ? runtime.exe : process.execPath;

console.log(`[test:host] 宿主运行时：${runtime.mode === "electron" ? "app.asar（宿主 Electron）" : "解包目录"}`);
console.log(`[test:host] DSH_APP_BOOT=${runtime.boot}`);
console.log(`[test:host] 套件：${files.join(" ")}`);

const result = spawnSync(command, ["--test", ...files], {
  cwd: ROOT,
  env,
  stdio: "inherit",
});
if (result.error) {
  console.error(`[test:host] 启动失败：${result.error.message}`);
  process.exit(1);
}
process.exit(result.status ?? 1);
