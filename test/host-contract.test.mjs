// 宿主契约检验：本插件依赖的**宿主接口**是否还在、形状有没有变。
//
// 为什么单独一个套件：`test/manifest.test.mjs` 只回答「宿主认不认这个清单」
// （engines.dsh 门禁、图标、locale 词典）。它答不了另一半问题 ——
// 「插件注册的槽位、挂的路由、依赖的运行时版本，宿主这版还给不给」。
//
// 这一半是**静默失败**的重灾区，本仓库栽过两次：
//   · 注册到已不存在的槽位 → 插件页整片空白，控制台一条错都不报；
//   · 宿主升级重建 profile → bundle 不在名单里，插件根本没加载，接口 404。
// 两者都"不崩，只给错误答案"，所以必须用宿主**自己的声明**来对账，
// 而不是我们对文档的复述。
//
// 三条硬纪律：
//   1. 期望值来自宿主（读宿主随包分发的槽位目录 / 依赖清单），不是手抄；
//   2. 每条断言都配**反例**，证明它不是恒真（否则"槽位没了"也会绿）；
//   3. 拿不到宿主时明确 skip 并说明原因，**不假装通过**。
//
// 运行：node --test test/host-contract.test.mjs
// 宿主在 app.asar 里时要用宿主自带的 Electron 当 node（普通 node 读不到 asar）：
//   APP="/Applications/DeepSeek Harness.app/Contents/Resources"
//   DSH_APP_BOOT="$APP/app.asar/dsh/node_modules/@deepseek-ai/dsh-app-boot" \
//   ELECTRON_RUN_AS_NODE=1 "$APP/../MacOS/DeepSeek Harness" --test test/host-contract.test.mjs

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { loadHost, hostRequire } from "./lib/host-runtime.mjs";
import { satisfies as semverSatisfies } from "./lib/semver-range.mjs";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const pkg = JSON.parse(readFileSync(join(ROOT, "package.json"), "utf8"));

const loaded = await loadHost();
const host = loaded?.mod;
const skipReason = host === undefined
  ? "找不到宿主 @deepseek-ai/dsh-app-boot；用 DSH_APP_BOOT=<dsh根> 指定后重跑"
  : false;

/**
 * 槽位目录条目的形状。
 *
 * 宿主把 `CLIENT_SLOT_API` 当成**源码**打包进产物，所以引号样式随打包器的
 * 输出格式漂移，而**目录内容不变**：
 *   · 0.2.2-rc.1 及更早：源码缩进原样保留，双引号
 *     `key: "settings.section",\n\t\t\t\tkind: "list",\n\t\t\t\tscope: "root"`
 *   · 0.2.2-rc.2 起：产物重新压平，末尾换成模板字面量
 *     ``key:`settings.section`,kind:`list`,scope:`root` ``
 * 所以这里**只认字段名与顺序，不认引号种类** —— 把三种引号都放进字符类，
 * 并用反向引用要求开闭一致（避免把 `key:`a"` 这种残片当条目）。
 */
const SLOT_ENTRY = /key:\s*(["'`])([^"'`]+)\1\s*,\s*kind:\s*(["'`])([^"'`]+)\3\s*,\s*scope:\s*(["'`])([^"'`]+)\5/gu;

/**
 * 注册项声明的匹配式，同样不认引号种类。
 * 宿主产物里 `name` / `requirement` 两个字段的引号也跟着打包格式变（见上）。
 *
 * @param {string} field 字段名（`name` 或 `requirement`）
 * @param {string} value 期望值（`id` / `required` …）
 * @returns {RegExp} 该字段等于该值的匹配式
 */
const registrantField = (field, value) =>
  new RegExp(`${field}:\\s*(["'\`])${value}\\1`, "u");


/**
 * 解析宿主槽位目录的产物原文（纯函数，便于用两种引号风格各打一遍）。
 *
 * @param {string} raw 宿主 `dsh-cordis-client-runner/client` 的产物原文
 * @returns {{entries: Map<string, {kind: string, scope: string, body: string}>}}
 *   条目表（key → 该条目的片段，供进一步断言注册参数）
 */
function parseSlotCatalog(raw) {
  // 用「下一处 key:」当条目边界，这样每个条目的体里能查 registerOptions。
  const keys = [...raw.matchAll(SLOT_ENTRY)];
  const entries = new Map();
  keys.forEach((m, index) => {
    const start = m.index ?? 0;
    const next = keys[index + 1]?.index ?? raw.length;
    entries.set(m[2], { kind: m[4], scope: m[6], body: raw.slice(start, next) });
  });
  return { entries };
}

/**
 * 读宿主随包分发的**客户端槽位目录**。
 *
 * 为什么读文件而不是 import：`@deepseek-ai/dsh-cordis-client-runner/client`
 * 是浏览器半（模块加载器包装 + 依赖 window），在 node 里 import 会抛
 * `window is not defined`。而槽位目录（`CLIENT_SLOT_API`）就在它的产物里，
 * 是给第三方插件作者看的**权威清单** —— 读它等于读宿主自己写下的契约。
 *
 * @param {string} entryUrl 宿主 app-boot 的模块 URL（用作解析基准）
 * @returns {{raw: string, entries: Map<string, {kind: string, scope: string, body: string}>}}
 *   原文与解析出的条目（key → 该条目的片段，供进一步断言注册参数）
 */
function readHostSlotCatalog(entryUrl) {
  const req = hostRequire(entryUrl);
  const entry = req.resolve("@deepseek-ai/dsh-cordis-client-runner/client");
  const raw = readFileSync(entry, "utf8");
  return { raw, ...parseSlotCatalog(raw) };
}

// ---------------------------------------------------------------------------
// 〇、解析器自身：宿主的两种引号风格都必须解析出来
//
// 这条检验不依赖宿主，**任何环境都跑**。理由是一次真实的红：
// 宿主 0.2.2-rc.2 把槽位目录重新压平，引号从双引号换成模板字面量，目录内容
// 一个字都没变，但旧正则只认双引号 → 解析出 0 条 → 三条契约检验一起变红。
// 那时候红的**不是插件坏了**，是"我们读宿主的方式坏了"，而失败信息看起来
// 跟"宿主删了槽位"一模一样。所以把两种真实产物形态各钉一份样本。
// ---------------------------------------------------------------------------

/** 0.2.2-rc.1 及更早的产物形态（源码缩进原样保留，双引号）。 */
const SLOT_SAMPLE_QUOTED = [
  "{",
  "\t\t\tkey: \"settings.section\",",
  "\t\t\tkind: \"list\",",
  "\t\t\tscope: \"root\",",
  "\t\t\tsummary: \"One settings page per list entry.\",",
  "\t\t\tregisterOptions: [{",
  "\t\t\t\tname: \"id\",",
  "\t\t\t\trequirement: \"required\",",
  "\t\t\t\ttype: \"string\",",
  "\t\t\t\townerProps: [\"export interface X\"]",
  "\t\t\t}],",
  "\t\t\townerProps: [\"\"]",
  "\t\t}",
  "",
].join("\n");

/** 0.2.2-rc.2 起的产物形态（压平，模板字面量）。 */
const SLOT_SAMPLE_TEMPLATE = [
  "{",
  "key:`settings.section`,kind:`list`,scope:`root`,",
  "summary:`One settings page per list entry.`,",
  "registerOptions:[{",
  "name:`id`,",
  "requirement:`required`,",
  "type:`string`,",
  "ownerProps:[`export interface X`]",
  "}],",
  "ownerProps:[``]",
  "},",
  "",
].join("\n");

test("解析器：宿主的双引号与模板字面量两种产物形态都解析得出来", () => {
  for (const [label, sample] of [
    ["双引号（≤0.2.2-rc.1）", SLOT_SAMPLE_QUOTED],
    ["模板字面量（0.2.2-rc.2 起）", SLOT_SAMPLE_TEMPLATE],
  ]) {
    const { entries } = parseSlotCatalog(sample);
    const entry = entries.get("settings.section");
    assert.ok(entry !== undefined,
      `${label} 形态一个条目都没解析出来 —— 解析正则已失配，契约检验会以`
      + "\"宿主删了槽位\"的样子误报");
    assert.equal(entry.kind, "list", `${label}：kind 没解析对`);
    assert.equal(entry.scope, "root", `${label}：scope 没解析对`);
    assert.match(entry.body, registrantField("name", "id"),
      `${label}：注册项 name=id 没解析出来`);
    assert.match(entry.body, registrantField("requirement", "required"),
      `${label}：注册项 requirement=required 没解析出来`);
  }

  // 反例：形状不符的片段不许被当成条目（否则上面的"解析得到"等于空对空）。
  assert.equal(parseSlotCatalog("key: \"a\", kind: \"list\"({}).length").entries.size, 0,
    "反例失败：缺少 scope 的片段也被当成了槽位条目");
  assert.equal(parseSlotCatalog('key: "a", kind: \'list, scope: "root"').entries.size, 0,
    "反例失败：引号不成对的残片也被当成了槽位条目");
});

test("宿主槽位目录：设置导航的两个槽位仍是 list / root / id 必填", { skip: skipReason }, () => {
  const { entries, raw } = readHostSlotCatalog(loaded.entryUrl);

  // 先证明解析器**真的读到了目录**：条目太少说明产物形状变了，
  // 此时下面的"存在性"断言会以一条看不懂的失败出现，先在这里点名。
  assert.ok(entries.size >= 50,
    `只解析出 ${entries.size} 个槽位 —— 宿主产物形状可能变了（正则失配），`
    + "这条检验已失效，必须先修解析再谈结果");

  for (const slot of ["settings.section", "settings.section.icon"]) {
    const entry = entries.get(slot);
    assert.ok(entry !== undefined,
      `宿主不再声明槽位 "${slot}" —— 本插件的设置页会**静默消失**`
      + "（左侧导航里没有这一行，控制台不报错）。宿主当前的设置相关槽位："
      + JSON.stringify([...entries.keys()].filter((k) => k.startsWith("settings."))));

    assert.equal(entry.kind, "list",
      `槽位 "${slot}" 的 kind 从 list 变了；本插件按 list 语义注册，形状不符即注册失败`);
    assert.equal(entry.scope, "root",
      `槽位 "${slot}" 的 scope 从 root 变了；插件的注册选项按 root 写`);

    // `id` 仍是必填注册项 —— 插件给的就是 id（本插件用包名）。
    // 若宿主把它改成可选或改名，插件的注册对象会被判无效。
    assert.match(entry.body, registrantField("name", "id"),
      `槽位 "${slot}" 的注册项里没有 name=id；本插件的注册参数需要跟着改`);
    assert.match(entry.body, registrantField("requirement", "required"),
      `槽位 "${slot}" 不再要求必填的 "id" 注册项；本插件的注册参数需要跟着改`);
  }

  // 反例：拼错/不存在的槽位必须**不在**目录里。否则上面两句等于空对空
  // （例如正则宽松到匹配任意字符串）。
  assert.equal(entries.get("settings.section.nonexistent"), undefined,
    "反例失败：不存在的槽位也出现在目录里，说明解析器把任意字符串都当条目了");
  assert.ok(!raw.includes("settings.section.nonexistent"),
    "反例失败：宿主产物里根本不存在这个假槽位名，解析器却给出了条目");
});

test("宿主槽位目录：图标的注册 id 必须等于页面的 id（宿主按 only: row.id 派发）", { skip: skipReason }, () => {
  const { entries } = readHostSlotCatalog(loaded.entryUrl);
  const icon = entries.get("settings.section.icon");
  assert.ok(icon !== undefined, "宿主不再声明 settings.section.icon");

  // 宿主文档原话：注册 id 必须等于目标 section 的 id，不匹配的 id 永不渲染，
  // 且回落成默认齿轮 —— **页面上看不出任何错误**。
  assert.match(icon.body, /must equal the target section's id|must equal/u,
    "宿主对 settings.section.icon 的 id 匹配规则描述变了；本插件按包名做 id，需要重新核对");
});

// ---------------------------------------------------------------------------
// 二、插件**实际注册**的每个槽位，宿主都还认（行为断言，不是读源码）
// ---------------------------------------------------------------------------

/** 载入插件自己的客户端产物（真 shape：__ModuleLoader__.load({ id, factory })）。 */
function loadPluginClient() {
  const src = readFileSync(join(ROOT, "lib", "client.js"), "utf8");
  let loaded2 = null;
  const window = { __ModuleLoader__: { load(entry) { loaded2 = entry; return entry; } } };
  let react = null;
  const requireShim = (name) => {
    if (name !== "react") throw new Error(`unexpected require: ${name}`);
    react ??= {
      createElement: () => null,
      useState: () => [null, () => {}],
      useEffect: () => {},
      useRef: () => ({ current: null }),
      useCallback: (fn) => fn,
      Fragment: "F",
    };
    return react;
  };
  // eslint-disable-next-line no-new-func -- 与宿主客户端加载器同样的执行方式
  const run = new Function("window", "require", `${src}\n;return window.__ModuleLoader__.__last;`);
  window.__ModuleLoader__ = {
    load(entry) { loaded2 = entry; return entry; },
    get __last() { return loaded2; },
  };
  const entry = run(window, requireShim);
  assert.ok(entry && typeof entry.factory === "function",
    "lib/client.js 不是 __ModuleLoader__.load({ factory }) 形状");
  return entry.factory(requireShim);
}

test("插件注册的每个槽位都仍在宿主目录里（宿主改名 = 卡片静默消失）", { skip: skipReason }, () => {
  const { entries } = readHostSlotCatalog(loaded.entryUrl);
  const mod = loadPluginClient();
  assert.equal(typeof mod.apply, "function", "客户端产物没有 apply");

  const registered = [];
  const ctx = {
    slots: {
      inject(_name, cb) { cb(); },
      register(options) { registered.push(options.name); return () => {}; },
    },
    effect() {},
    get() { return undefined; },
    logger: { info() {}, warn() {}, error() {} },
  };
  mod.apply(ctx);

  // 反例控制：一条都没注册时，下面的 every() 会**恒真**。
  assert.ok(registered.length > 0,
    "apply() 一条槽位都没注册 —— 下面的对账会退化成空对空");

  const unknown = [...new Set(registered)].filter((name) => !entries.has(name));
  assert.deepEqual(unknown, [],
    "插件注册到了宿主目录里没有的槽位：" + JSON.stringify(unknown)
    + "；这些卡片不会渲染，也**不会报错**（插件页空白）。"
    + "对照宿主当前插件相关槽位：" + JSON.stringify([...entries.keys()].filter((k) => k.startsWith("plugins."))));
});

// ---------------------------------------------------------------------------
// 三、stdout 纪律（宿主 0.2.1-rc.4 把整批诊断从 stdout 挪到 stderr）
//
// ACP 运行线把 **stdout 留给 JSON-RPC 协议**。任何 console.log 都会插进协议流，
// 让宿主与客户端都解析失败 —— 表现是"整条会话无响应"，而不是一条明显的错。
// 宿主自己在 rc.4 里修了三处（DeepSeek 账号目录、MCP 资源列表），把日志改到
// stderr；插件这边必须守住同一条线：运行期代码不写 stdout，子进程不继承 stdio。
// ---------------------------------------------------------------------------

const RUNTIME_FILES = [
  "lib/index.js",     // 宿主半：随宿主进程跑，与 ACP 共用 stdout
  "lib/client.js",    // 客户端半：产物
  "client/index.jsx", // 客户端半的源码（防止只改源码漏了产物）
];

/**
 * 找出「会写 stdout」的写法。
 * @param {string} text 待检源码
 * @returns {string[]} 命中的片段说明（空数组 = 干净）
 */
function stdoutOffenders(text) {
  const offenders = [];
  // console.log / console.info 直接写 stdout；console.error / warn 走 stderr 是允许的
  for (const m of text.matchAll(/console\.(log|info)\s*\(/gu)) {
    offenders.push(`console.${m[1]}()`);
  }
  if (/process\.stdout\.write\s*\(/u.test(text)) offenders.push("process.stdout.write()");
  // spawn 的 stdio 显式写了 inherit 也会把子进程输出接进宿主 stdout
  for (const m of text.matchAll(/stdio:\s*\[([^\]]*)\]/gu)) {
    if (/\binherit\b/u.test(m[1])) offenders.push(`stdio: [${m[1].trim()}]`);
  }
  return offenders;
}

test("stdout 纪律：运行期代码不写 stdout（ACP 把 stdout 留给 JSON-RPC）", () => {
  for (const rel of RUNTIME_FILES) {
    const text = readFileSync(join(ROOT, rel), "utf8");
    const offenders = stdoutOffenders(text);
    assert.deepEqual(offenders, [],
      `${rel} 会写 stdout：${JSON.stringify(offenders)}。`
      + "宿主 0.2.1-rc.4 起把诊断一律改到 stderr（ACP 运行线的 stdout 是协议流），"
      + "插件同理：日志走 ctx.logger / console.error，不要 console.log");
  }
});

test("stdout 纪律：拦得住的写法必须真被拦住（检测器自身有效）", () => {
  // 反例：这段"脏"代码必须被检出；否则上面的"干净"结论毫无意义。
  assert.deepEqual(stdoutOffenders("console.log('hi')"), ["console.log()"]);
  assert.deepEqual(stdoutOffenders("console.info('hi')"), ["console.info()"]);
  assert.deepEqual(stdoutOffenders("process.stdout.write('x')"), ["process.stdout.write()"]);
  assert.deepEqual(stdoutOffenders('spawn(a, b, { stdio: ["inherit", "pipe", "pipe"] })'),
    ['stdio: ["inherit", "pipe", "pipe"]']);
  // 干净的写法不许误报（否则这条检验会被迫放宽到"永远绿"）
  assert.deepEqual(stdoutOffenders("console.error('x')"), []);
  assert.deepEqual(stdoutOffenders('spawn(a, b, { stdio: ["ignore", "pipe", "pipe"] })'), []);
});

test("stdout 纪律：子进程一律重定向到文件或管道（不继承宿主 stdout）", () => {
  const text = readFileSync(join(ROOT, "lib", "index.js"), "utf8");
  const stdios = [...text.matchAll(/stdio:\s*(\[[^\]]*\]|"[^"]*")/gu)].map((m) => m[1]);

  // 覆盖面自检：插件有两处起子进程（启动器走文件日志、探测走管道）。
  // 一处都找不到时下面的循环恒真，等于没测。
  assert.ok(stdios.length >= 2,
    `只找到 ${stdios.length} 处 stdio 配置 —— 解析可能失配，这条检验已失效`);

  for (const spec of stdios) {
    assert.doesNotMatch(spec, /\binherit\b/u,
      `有一处 spawn 继承了父进程 stdio：${spec}。`
      + "门户/云隧道的输出会串进宿主 stdout，ACP 运行线下直接毁掉协议流");
  }
});

// ---------------------------------------------------------------------------
// 四、宿主运行时依赖仍在插件声明的版本区间内
//
// 宿主换 core 版本（cordis / schemastery）时插件**不会**因此被门禁拦住 ——
// engines.dsh 只看 DSH 自己的版本。而 Config 用的是 schemastery 的
// z.object().volatile()：大版本一升，设置页表单可能静默变形（字段读不到默认值、
// 或 volatile 换成别的机制），表现是"设置保存了但插件读的还是旧值"。
// ---------------------------------------------------------------------------

test("宿主依赖：cordis 与 schemastery 仍在插件声明的区间内", { skip: skipReason }, () => {
  const req = hostRequire(loaded.entryUrl);
  const pairs = [
    ["@deepseek-ai/cordis", pkg.peerDependencies?.["@deepseek-ai/cordis"]],
    ["@deepseek-ai/schemastery", pkg.dependencies?.["@deepseek-ai/schemastery"]],
  ];
  for (const [name, range] of pairs) {
    assert.ok(typeof range === "string" && range.trim() !== "",
      `清单里没有声明 ${name} 的区间，无法对账`);
    const manifestPath = req.resolve(`${name}/package.json`);
    const { version } = JSON.parse(readFileSync(manifestPath, "utf8"));
    assert.ok(semverSatisfies(version, range),
      `宿主随包分发的 ${name}@${version} 落在插件声明的区间之外（${range}）。`
      + "engines.dsh 只看 DSH 版本、不管 core 依赖，所以这类漂移不会被门禁拦住："
      + "请确认 Config（schemastery）与插件加载（cordis）的用法是否仍成立，再放宽区间");
  }
});

test("宿主依赖：区间判定不是恒真（反例必须被拒）", { skip: skipReason }, () => {
  // 反例：把版本推到区间之外，同一套判定必须翻转。
  // 没有这条，"区间仍满足"可能来自一个永远返回 true 的比较器。
  const range = pkg.dependencies["@deepseek-ai/schemastery"];
  assert.equal(semverSatisfies("99.0.0", range), false,
    "反例失败：99.0.0 也被判为满足，说明区间判定恒真，上面的对账没有意义");
  const cordisRange = pkg.peerDependencies["@deepseek-ai/cordis"];
  assert.equal(semverSatisfies("99.0.0", cordisRange), false,
    "反例失败：cordis 区间判定恒真");
});

test("宿主资源：插件声明的 locale 词典宿主解析得到（显示元数据的唯一来源）", { skip: skipReason }, () => {
  // 宿主读插件标题/简介只认 `<包名>/locale/<语言>.json`（另有清单里的
  // name/description/icon，它**不读** displayName）。这里反查一次：能解析到 +
  // 内容是宿主能解析的 JSON。
  //
  // 解析基准选谁很有讲究：从本仓库锚点解析走的是"自引用"（同一份 exports 契约），
  // 而宿主实际是从 **profile 的 package.json** 按包名解析的。两边锚点不同，
  // exports 写错时可能一边过一边挂。有 DSH_PROFILE_DIR（宿主自己设的）就用 profile，
  // 没有（CI、临时检出）退回仓库锚点 —— 并在输出里说明只验了 exports。
  const profileDir = process.env.DSH_PROFILE_DIR;
  const anchor = profileDir === undefined ? join(ROOT, "package.json") : join(profileDir, "package.json");
  const resolved = createRequire(anchor).resolve(`${pkg.name}/locale/en.json`);

  assert.ok(existsSync(resolved),
    `解析不到 ${pkg.name}/locale/en.json（锚点 ${anchor}）：${resolved}`);
  const dict = JSON.parse(readFileSync(resolved, "utf8"));
  assert.equal(typeof dict?.meta?.title, "string",
    "解析到的英文词典没有 meta.title —— 插件页标题会退化成包名");
  assert.ok(resolved.includes("locale"), "解析结果必须指向包内的 locale 词典");
});
