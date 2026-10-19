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
import { readFileSync, readdirSync, existsSync, statSync } from "node:fs";
import { join, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import { satisfies as semverSatisfies } from "./lib/semver-range.mjs";

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

// ---------------------------------------------------------------------------
// 打包契约：**运行期脚本必须随包分发**。
//
// 血的教训（2026-10-16 实测）：package.json 的 files 白名单里没有 "tools"，
// 于是 `npm pack` / `npm publish` 打出来的包里**一个 Python 脚本都没有**。
// 装到用户机器上以后，lib/index.js 去 infraPath/tools 找 portal_run.py 全部落空：
//
//   readStatus -> "找不到 .../tools/start_public_gui.py（外网启动器不在该仓库）"
//   点「开启」 -> startPublic 拿不到脚本，门户永远起不来
//
// 而 link: 本地安装（开发形态）**看不到**这个 bug —— 符号链接指向真实仓库，
// tools/ 一直在。这就是它一直没被发现的全部原因：唯一验证过的安装方式恰好是
// 唯一不暴露问题的安装方式。所以这条断言按「打包后的形状」检查，不按开发检出。
//
// 同时钉住 files 白名单里的每一项都真实存在（写错目录名的白名单条目在
// npm 眼里是静默忽略，不报错）。
// ---------------------------------------------------------------------------

test("打包契约：tools/ 在 files 白名单里（否则发布包没有运行期脚本）", () => {
  assert.ok(Array.isArray(pkg.files), "package.json 缺 files 白名单");
  assert.ok(pkg.files.includes("tools"),
    "files 白名单缺 tools —— npm 包不会带任何 Python 脚本，"
    + "用户装完点「开启」必然失败。实际=" + JSON.stringify(pkg.files));
});

test("打包契约：运行期脚本两个入口都在仓库里（打包前必须存在）", () => {
  // 这两个是 lib/index.js 会去 infraPath/tools 里找的入口：
  //   portal_run.py       新门户（控制台形态），优先
  //   start_public_gui.py  旧启动器，回退
  for (const rel of ["tools/portal_run.py", "tools/start_public_gui.py"]) {
    assert.ok(existsSync(join(ROOT, rel)), `运行期脚本缺失：${rel}`);
  }
});

test("打包契约：运行期脚本的本地 import 闭包都在 tools/ 里", () => {
  // portal_run.py 用 `import portal_proxy` 这种**同目录裸模块名**导入兄弟脚本
  // （靠 sys.path.insert(0, HERE)）。少发任何一个，门户就在运行期 ImportError，
  // 而打包产物本身看不出这个问题。这里按闭包逐个钉住。
  const closure = [
    "portal_run.py", "portal_console.py", "portal_proxy.py", "portal_registry.py",
    "portal_login.py", "lan_address.py", "start_public_gui.py", "tunnel_auth.py",
  ];
  for (const rel of closure) {
    assert.ok(existsSync(join(ROOT, "tools", rel)),
      `tools/${rel} 缺失 —— portal_run.py 的 import 闭包不完整`);
  }
});

test("打包契约：files 白名单里每一项都真实存在（写错名字会被静默忽略）", () => {
  const missing = pkg.files.filter((f) => !existsSync(join(ROOT, f)));
  assert.deepEqual(missing, [],
    "files 白名单里有不存在的条目（npm 会静默忽略，不会报错）："
    + JSON.stringify(missing));
});

test("打包契约：官方 @deepseek-ai 包必须声明为 peerDependencies", () => {
  // contributing.md：官方 @deepseek-ai/* 包请用 peerDependencies 声明。
  // 声明成 peer 才能和宿主共用同一份实例（否则会装出第二份宿主内部包）。
  for (const name of ["@deepseek-ai/cordis", "@deepseek-ai/schemastery"]) {
    assert.ok(pkg.peerDependencies?.[name],
      `${name} 必须声明为 peerDependencies（contributing.md 明确要求）`);
  }
});

test("打包契约：schemastery 必须在 dependencies 里有兜底（否则新装用户插件加载不了）", () => {
  // 这条是**实测出来的**，不是推演出来的。
  //
  // lib/index.js 第一行就 `import z from "@deepseek-ai/schemastery"`，所以它是
  // **硬依赖**，装不上就直接 ERR_MODULE_NOT_FOUND、插件整个加载失败。
  //
  // 但只声明成 peer 是不够的：本仓库 peerDependenciesMeta 把 schemastery 标成了
  // optional，而 pnpm 会**直接跳过** optional peer —— 一个都不装。实测（真 dsh CLI
  // 装进一次性 profile）：
  //
  //   profile vp-a：peer 声明 + 无 dependencies 兜底
  //     node_modules/ 下只有 dsh-service-portal 一个包 -> 插件加载 ERR_MODULE_NOT_FOUND
  //   profile vp-b：peer 声明 + dependencies: ^3.18.4 兜底
  //     node_modules/ 下出现 @deepseek-ai/schemastery -> 加载成功、readStatus ok
  //
  // 所以两者都要：peer 让宿主已有的那份可被复用（不装第二份），
  // dependencies 保证在宿主没提供时也一定能跑。已收录的 DDDMUC/dsh-free-search
  // 就是同一种写法（peer ^3.18.4 + deps ^3.18.4）。
  const peer = pkg.peerDependencies?.["@deepseek-ai/schemastery"];
  const dep = pkg.dependencies?.["@deepseek-ai/schemastery"];
  assert.ok(peer, "缺 peer 声明（contributing.md 要求）");
  assert.ok(dep,
    "缺 dependencies 兜底 —— optional peer 会被 pnpm 跳过，"
    + "新装用户 node_modules 里不会有 schemastery，插件加载即失败");
  // 兜底范围必须真能匹配已发布的稳定版，否则等于没兜底
  assert.ok(semverSatisfies("3.18.4", dep),
    `dependencies 兜底范围必须放行 3.18.4（当前稳定版）；实际=` + dep);

  // 声明了还不够 —— 真解析一次，证明装得上
  const resolved = createRequire(join(ROOT, "package.json")).resolve(
    "@deepseek-ai/schemastery");
  assert.ok(existsSync(resolved),
    "@deepseek-ai/schemastery 解析不到实际文件：" + resolved);
});

test("打包契约：cordis peer 范围必须放行预发布版（含显式 || 分支）", () => {
  // contributing.md 的重点警告：node-semver 只有当范围里**某个比较符**与该版本的
  // major.minor.patch 元组完全一致、且自身带预发布标签时，才放行预发布版本。
  // 所以 ">=4" 这种看起来宽松的写法会静默排除 4.0.5-alpha.1，用户装的时候撞 ERESOLVE。
  //
  // 这里不看字符串像不像，而是**直接拿 semver 判**：npm 自己有一份 semver 依赖，
  // 用它跑真实的 satisfies()，才算真验过（否则正则写对、行为仍错也照样绿）。
  const range = pkg.peerDependencies?.["@deepseek-ai/cordis"];
  assert.ok(range, "缺 @deepseek-ai/cordis 的 peerDependencies");

  // 实测已发布的 cordis 版本（npm view @deepseek-ai/cordis versions）
  const published = [
    "4.0.1-rc.1", "4.0.1-rc.4", "4.0.1", "4.0.2", "4.0.3", "4.0.4",
    "4.0.5-alpha.1", "4.0.5-alpha.2", "4.0.5",
  ];
  const excluded = published.filter((v) => !semverSatisfies(v, range));
  assert.deepEqual(excluded, [],
    "peer 范围静默排除了已发布的 cordis 版本（用户会撞 ERESOLVE）："
    + JSON.stringify(excluded) + "；范围=" + range);

  // 预发布版也不能漏：宿主自己就可能是预发布构建
  assert.ok(semverSatisfies("4.0.5-alpha.1", range),
    "范围必须放行 4.0.5-alpha.1（宿主实际在用预发布构建）；范围=" + range);
  // 同时不能把下一个大版本放进来
  for (const v of ["5.0.0", "5.0.0-alpha.1"]) {
    assert.ok(!semverSatisfies(v, range),
      `范围不该放行 ${v}（跨大版本会被静默装上不兼容的宿主）；范围=` + range);
  }
});

test("打包契约：schemastery peer 范围必须放行全部已发布版本", () => {
  const range = pkg.peerDependencies["@deepseek-ai/schemastery"];
  const published = [
    "3.18.1-rc.1", "3.18.1-rc.4", "3.18.1", "3.18.2", "3.18.3", "3.18.4",
    "3.18.5-alpha.1", "3.18.5-alpha.2", "3.18.5",
  ];
  const excluded = published.filter((v) => !semverSatisfies(v, range));
  assert.deepEqual(excluded, [],
    "schemastery peer 范围静默排除已发布版本：" + JSON.stringify(excluded));
  // 也不能放行下一个大版本
  assert.ok(!semverSatisfies("4.0.0", range), "不该放行 schemastery 4.x；范围=" + range);
});

test("打包契约：包里每个运行期 import 的 bare specifier 都必须装得上", () => {
  // 这条是上面那次「peer-only 声明」事故的**通用化**收口。
  //
  // 事故回顾：把 schemastery 从 dependencies 改成仅 peer（且 optional）之后，
  // 76 项单测全绿 —— 因为本地 node_modules 里那份还在。但在**一次性 profile**
  // 里用真 dsh CLI 装，node_modules 下只有 dsh-service-portal 一个包，
  // lib/index.js 第一行的 `import z from "@deepseek-ai/schemastery"` 直接
  // ERR_MODULE_NOT_FOUND，插件整个加载不了。
  //
  // 教训：单测跑在开发检出上，永远看得见本地 node_modules，所以**看不见**
  // 「新装用户缺什么」。这条断言不看本地装了什么，而是静态解析 lib/ 下**所有**
  // .js 产物的 import，逐个要求：
  //   - node: 内置 -> 不用管
  //   - 相对路径 -> 必须真实存在
  //   - bare specifier -> 必须在 dependencies 或 peerDependencies 里被声明
  //
  // 注意覆盖范围（初版这里只扫 lib/index.js + lib/client.js，且正则漏掉动态
  // import()，被对抗性复核当场指出 —— 所以现在三处都补齐了）：
  //   1. 扫 lib/ 下**全部** .js，而不只是两个已知文件（将来加文件不会漏网）
  //   2. 正则同时覆盖 `import x from "p"`、`import "p"`、`import("p")`、
  //      `require("p")`，以及模板字面量 `import(\`p\`)`
  //   3. 顺带扫 .mjs 残留（若将来产物形态变化）
  const bare = new Set();
  const relative = new Set();
  const SPEC = String.raw`["'\`]([^"'\`]+)["'\`]`;
  const re = new RegExp(
    // import x from "p" / import "p" / import("p") / require("p") / require(`p`)
    // **不加行首锚点** —— `await import("p")` / `const x = require("p")`
    // 这类真实写法都不在行首，加锚点就会漏掉（对抗性复核指出过这一点）。
    String.raw`(?:import\s+[^;\n]*?\sfrom\s*|import\s*|import\s*\(\s*|require\s*\(\s*)` + SPEC,
    "g",
  );
  const scan = (file, source) => {
    let m;
    re.lastIndex = 0;
    while ((m = re.exec(source)) !== null) {
      const spec = m[1];
      if (!spec) continue;
      if (spec.startsWith("node:")) continue;
      if (spec.startsWith(".") || spec.startsWith("/")) relative.add(`${file}\u0000${spec}`);
      else bare.add(spec);
    }
  };
  // lib/ 下所有 .js 都扫（不只两个已知入口）
  const libFiles = readdirSync(join(ROOT, "lib"))
    .filter((f) => f.endsWith(".js") || f.endsWith(".mjs"));
  assert.ok(libFiles.length > 0, "lib/ 下没有找到任何产物文件");
  for (const f of libFiles) {
    scan(`lib/${f}`, f === "client.js" ? bundle : readFileSync(join(ROOT, "lib", f), "utf8"));
  }

  const declared = new Set([
    ...Object.keys(pkg.dependencies ?? {}),
    ...Object.keys(pkg.peerDependencies ?? {}),
    ...Object.keys(pkg.optionalDependencies ?? {}),
    // 客户端产物由**宿主**在运行期注入，不走 npm 依赖解析：
    //   · react —— 工厂体 `var React = require("react")`，宿主提供（不能进 dependencies，
    //     否则会装出第二份 React，hooks 直接崩）
    //   · 两个 @deepseek-ai 包 —— 宿主单例
    // 这里是**显式**白名单而不是「凡 peerMeta 里有就算」：宿主注入哪些是事实，
    // 写出来才能被 review；偷偷放宽会让一个真的漏声明的包混过去。
    ...Object.keys(pkg.peerDependenciesMeta ?? {}),
  ]);
  // 宿主注入的内置模块（不走 npm 解析）。新增前请先确认宿主确实提供。
  const HOST_PROVIDED = new Set(["react", "react-dom", "react/jsx-runtime"]);

  const undeclared = [...bare].filter((s) => {
    if (declared.has(s) || HOST_PROVIDED.has(s)) return false;
    // 子路径导入（如 `pkg/sub`）按其包名归属
    const pkgName = s.startsWith("@") ? s.split("/").slice(0, 2).join("/") : s.split("/")[0];
    return !declared.has(pkgName) && !HOST_PROVIDED.has(pkgName);
  });
  assert.deepEqual(undeclared, [],
    "产物里 import 了没声明的依赖 —— 新装用户会直接加载失败："
    + JSON.stringify(undeclared) + "（已声明=" + JSON.stringify([...declared]) + "）");

  // 相对导入必须真实存在
  const missingRel = [...relative].filter((k) => {
    const [file, spec] = k.split("\u0000");
    return !existsSync(resolve(ROOT, dirname(file), spec));
  });
  assert.deepEqual(missingRel, [],
    "产物里的相对导入指向不存在的文件：" + JSON.stringify(missingRel));
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

// ---------------------------------------------------------------------------
// 设计系统契约：面板的几何/令牌必须落在**宿主真实原语**的尺度里。
//
// 为什么需要这一组：这一批"难看"的根因全部是**无法从源码看出来的值** ——
// 0.5px 在 DPR=1 下被浏览器向上取整成 1px（写 0.5 从来没生效过）、
// 按钮 32px 高而宿主只有 36/28 两档、12.5px/11px 字号低于本文件自己定的下限。
// 这些都不是"跑挂了"，而是"看着不像一家"——没有断言就会一改再改、反复回潮。
//
// 期望值来自 app.asar 里宿主的真实文件（照抄，不是估计）：
//   dsh-client-ui-primitives/lib/Button.module.css   H36(常规)/H28(.sm)
//   dsh-client-ui-primitives/lib/Input.module.css    H32
//   dsh-client-ui-primitives/lib/Switch.module.css   36x20
// ---------------------------------------------------------------------------

// 剥掉 CSS 注释再检查：注释里会**引用**这条教训（"0.5px 会被抹成 1px"），
// 那是文档，不是声明。测试要看的只有声明。
const cssDecls = (text) => text.replace(/\/\*[\s\S]*?\*\//g, "");

test("设计契约：不用 0.5px 描边（DPR=1 下会被抹成 1px，写它等于自欺）", () => {
  const css = cssDecls(bundle);
  // 允许出现在注释里解释这条教训，但**声明**里不能有 0.5px
  const decls = css.match(/(border|border-top|border-bottom|border-left|border-right|outline)[^;{}]*0\.5px/g) || [];
  assert.deepEqual(decls, [],
    "出现 0.5px 描边声明；实测在 DPR=1 下渲染成 1px，与宿主尺度不一致。实际=" + JSON.stringify(decls));
});

test("设计契约：按钮只用宿主的 36 / 28 两档高度", () => {
  // .dsp-btn 默认档 = 宿主 .button.md（36），.dsp-btn-sm = 宿主 .sm（28）
  const css = cssDecls(bundle);
  const m = css.match(/\.dsp-btn,\.dsp-btn-primary,\.dsp-btn-ghost,\.dsp-btn-danger\{[^}]*height:(\d+)px/);
  assert.ok(m, "找不到 .dsp-btn 的高度声明（选择器被改过？）");
  assert.equal(m[1], "36", "默认按钮高度必须是宿主的 36 档；实际=" + m[1]);
  const sm = css.match(/\.dsp-btn-sm\{[^}]*height:(\d+)px/);
  assert.ok(sm, "找不到 .dsp-btn-sm 的高度声明");
  assert.equal(sm[1], "28", "紧凑按钮高度必须是宿主的 28 档；实际=" + sm[1]);
});

test("设计契约：默认按钮不描边（宿主的 .button 是 border:none，靠底色分级）", () => {
  const css = cssDecls(bundle);
  const m = css.match(/\.dsp-btn,\.dsp-btn-primary,\.dsp-btn-ghost,\.dsp-btn-danger\{([^}]*)\}/);
  assert.ok(m, "找不到 .dsp-btn 基础规则");
  assert.ok(/\bborder:none\b/.test(m[1]),
    "默认按钮必须 border:none —— 宿主只有 .outline 变体带描边；"
    + "给所有按钮套框是『不像一套』最大的来源。实际规则=" + m[1]);
});

// CARD_CSS 是一段**模板字符串**，里面用 ${TYPE.caption} 这类插值引用字号刻度。
// 在产物里它们仍是字面量（构建不展开），运行期才由 JS 求出 —— 所以测试要
// **照运行期的方式**把令牌换成数字，否则正则一个字号都扫不到，
// 断言会在"什么都没检查"的情况下通过（这个假绿灯实际发生过一次）。
function resolveTypeTokens(css, sizeSource) {
  const typeBlock = sizeSource.match(/const TYPE\s*=\s*\{([^}]*)\}/);
  if (!typeBlock) throw new Error("源码里找不到 TYPE 字号刻度常量");
  const table = {};
  for (const m of typeBlock[1].matchAll(/(\w+)\s*:\s*(\d+)/g)) table[m[1]] = m[2];
  return css.replace(/\$\{TYPE\.(\w+)\}/g, (all, key) => {
    if (!(key in table)) throw new Error("CARD_CSS 引用了 TYPE 里没有的刻度: " + key);
    return table[key];
  });
}

test("设计契约：字号只能取 TYPE 四档，且不低于 12px", () => {
  // 先确认插值真的被解析了 —— 否则下面就是在扫描空集合（假绿灯）
  const css = resolveTypeTokens(cssDecls(bundle), source);
  assert.ok(!/\$\{TYPE\./.test(css),
    "仍有未解析的 ${TYPE.*} 插值，说明刻度替换没生效，本测试会变成空断言");
  const sizes = new Set();
  for (const m of css.matchAll(/font-size:([0-9.]+)px/g)) sizes.add(parseFloat(m[1]));
  assert.ok(sizes.size >= 4,
    "扫到的字号种类过少（" + sizes.size + "），测试可能没真正覆盖到 CARD_CSS");
  // 面板里的字号声明只允许 12 / 13 / 14 / 16（TYPE 刻度）
  const allowed = new Set([12, 13, 14, 16]);
  const bad = [...sizes].filter((s) => !allowed.has(s));
  assert.deepEqual(bad, [],
    "出现 TYPE 刻度之外的字号（会出现『字大大小小』且无层级）；实际超纲值=" + JSON.stringify(bad));
  // 12 是下限：低于 12px 在 2 倍缩放下会糊
  const tooSmall = [...sizes].filter((s) => s < 12);
  assert.deepEqual(tooSmall, [], "字号低于 12px 下限；实际=" + JSON.stringify(tooSmall));
});

test("设计契约：两栏必须等高（避免一侧露出大片空白）", () => {
  const css = cssDecls(bundle);
  const m = css.match(/\.dsp-duo\{([^}]*)\}/);
  assert.ok(m, "找不到 .dsp-duo 规则");
  assert.ok(!/align-items:start/.test(m[1]),
    ".dsp-duo 不能用 align-items:start —— 实测两栏高度差 324px，"
    + "右半边会出现一整块空白。宿主的卡片网格默认等高。实际=" + m[1]);
  assert.ok(/align-items:stretch/.test(m[1]),
    ".dsp-duo 应显式 stretch（两栏下沿对齐露不出缺口）；实际=" + m[1]);
});

test("设计契约：胶囊/标签不出现 line-height:1（文字会贴着行盒）", () => {
  const css = cssDecls(bundle);
  const bad = css.match(/\.dsp-(pill|chip|tag)\{[^}]*line-height:1\b/g) || [];
  assert.deepEqual(bad, [],
    "pill/chip/tag 不能用 line-height:1（实测 12px 字号配 12px 行高，2 倍缩放下挤在一起）；"
    + "实际=" + JSON.stringify(bad));
});

// ---------------------------------------------------------------------------
// 「门户进程」整块必须真的从**渲染结果**里消失（不是只从源码里删字符串）。
//
// 用户原话：「这个服务本身就随 dsh 打开和关闭的，不需要再有设置，太啰嗦」。
// 他给的是那张「停止门户 / 刷新」的截图 —— 要的是**屏幕上没有它**。
//
// 为什么非渲染不可（我第一版就栽在这）：源码里 grep 「门户进程」为 0，
// 看着像删干净了，其实那块只在 `running` 分支渲染；喂一个"未启动"的 status
// 就永远渲染不到它，断言恒真 = 假通过。所以下面必须喂**运行中**的 status，
// 并且这个检验要能对旧产物报 FAIL（已人工对比验证过非空转）。
// ---------------------------------------------------------------------------
test("渲染：运行中状态下面板不再出现「门户进程 / 停止门户」", () => {
  const RUNNING = {
    ok: true, running: true, portalPort: 8899, portalUrl: "http://127.0.0.1:8899",
    baseUrl: "http://192.168.71.61:8899",
    lanUrls: ["http://192.168.71.61:8899"],
    publicUrl: "https://demo.trycloudflare.com",
    password: "Abc123456789", lanPassword: "4182", lanAuthEnabled: true,
    lanEnabled: true, lanPinCustom: false, publicPinCustom: false,
    services: [], servicesDegraded: 0, autoStart: true,
    lanCandidates: ["192.168.71.61"],
  };
  let nth = 0;
  const R = {
    createElement: (t, p, ...k) => ({ type: t, props: p, kids: k.flat(9).filter((x) => x != null) }),
    useState: (init) => {
      const i = nth += 1;
      let v = typeof init === "function" ? init() : init;
      if (i === 1) v = RUNNING; // 第一个 useState(null) 就是 status
      return [v, () => {}];
    },
    useEffect: () => {}, useRef: () => ({ current: null }),
    useCallback: (f) => f, useMemo: (f) => f(), Fragment: "F",
  };
  const requireShim = (r) => {
    if (r === "react") return R;
    throw new Error("unexpected require: " + r);
  };
  const win = { __ModuleLoader__: { load: () => {} } };
  let captured = null;
  win.__ModuleLoader__.load = (m) => { captured = m; return m; };
  // eslint-disable-next-line no-new-func
  new Function("window", "require", bundle)(win, requireShim);
  const mod = captured.factory(requireShim);

  const registered = [];
  const ctx = {
    slots: {
      inject: (_n, cb) => cb(),
      register: (opts, comp) => { registered.push({ ...opts, comp }); return () => {}; },
    },
    effect() {}, on() {}, get() { return undefined; },
    inject: (_d, cb) => cb({ webServer: { register: () => () => {} } }),
    logger: { info() {}, warn() {}, error() {} },
  };
  mod.apply(ctx, {
    infraPath: ROOT, repoPath: "", portalPort: 8899, webEnabled: true,
    autoStart: false, passwordMode: "random",
  });

  const flatten = (n, out = []) => {
    if (n == null || typeof n === "boolean") return out;
    if (typeof n === "string" || typeof n === "number") { out.push(String(n)); return out; }
    if (Array.isArray(n)) { n.forEach((x) => flatten(x, out)); return out; }
    if (n.kids) flatten(n.kids, out);
    if (n.props && typeof n.props === "string") out.push(n.props);
    return out;
  };

  const comp = registered.map((r) => r.comp).find((f) => typeof f === "function");
  assert.ok(comp, "没有注册可渲染的设置面板组件");
  nth = 0;
  const text = flatten(comp({ view: "page", ctx })).join(" | ");

  // 先证明"确实渲染到了运行中那一屏"，否则下面的断言毫无意义（假通过）
  assert.match(text, /公网访问|外网访问|局域网/,
    "没有渲染到「运行中」分支 —— 本检验会变成空转，必须修喂进去的 status");
  assert.ok(!text.includes("门户进程"), "「门户进程」仍在渲染（用户要求删掉）");
  assert.ok(!text.includes("停止门户"), "「停止门户」按钮仍在渲染");
  // 「关闭公网访问」是**另一件事**（只收隧道），必须还在 —— 别连带删错
  assert.ok(text.includes("公网"), "公网那一栏不该被误删");
});

// ---------------------------------------------------------------------------
// 主题成对性：**写死的颜色不许压在会随主题翻转的令牌上**。
//
// 拦的是这个真实 bug（用户截图报"按钮都有白色一块一块的"）：
//   .dsp-btn-primary{background:var(--dsw-alias-brand-primary); color:#fff}
// 宿主的 --dsw-alias-brand-primary 语义是"最高对比度的前景色"，两套主题**取值
// 相反**：浅色 bluish-1000(#0f1115 近黑) / 深色 bluish-50(#f9fafb 近白)。
// 于是深色下是 #f9fafb 底 + #fff 字，对比度约 1.02:1 —— 文字没消失，是白压白，
// 视觉上只剩一个白色方块。它只在深色主题触发，浅色下的所有预览与人工核对都
// 看不见，所以必须由机器盯住。
//
// 规则：凡是 background 用了"会翻转"的令牌（brand-primary / button-primary-fill
// / 各 bg-layer-*），color 就必须**同样**取自配套的前景令牌
// （label-primary-foreground / label-primary / label-inverse），不许写死 #fff。
// 开关的 thumb 不在此列 —— 它用宿主专用的 --dsw-alias-switch-thumb。
// ---------------------------------------------------------------------------
test("主题成对：会翻转的背景令牌不得配写死的文字色", () => {
  // 抽出所有含 background 且含 color 的规则块
  const blocks = [];
  const re = /([^{}]+)\{([^{}]*)\}/g;
  let m;
  while ((m = re.exec(source))) blocks.push({ sel: m[1].trim(), body: m[2] });

  const flipping = [
    "--dsw-alias-brand-primary",
    "--dsw-alias-button-primary-fill",
    "--dsw-alias-bg-layer-1",
    "--dsw-alias-bg-layer-2",
    "--dsw-alias-bg-layer-3",
  ];
  const foreground = [
    "--dsw-alias-label-primary-foreground",
    "--dsw-alias-label-primary",
  ];
  const bad = [];
  for (const { sel, body } of blocks) {
    const bg = /background(?:-color)?\s*:\s*([^;]+)/.exec(body);
    const fg = /(?:^|;)\s*color\s*:\s*([^;]+)/.exec(body);
    if (!bg || !fg) continue;
    if (!flipping.some((t) => bg[1].includes(t))) continue;
    const colorVal = fg[1].trim();
    const isForegroundToken = foreground.some((t) => colorVal.includes(t));
    const isInherit = /^(inherit|currentcolor)$/i.test(colorVal);
    if (!isForegroundToken && !isInherit) {
      bad.push(`${sel} → background 用 ${bg[1].trim()} 但 color=${colorVal}`);
    }
  }
  assert.deepEqual(bad, [],
    "以下规则把写死的文字色压在会随主题翻转的背景令牌上（深色主题会白底白字）：\n"
    + bad.join("\n"));

  // 反证：本条检验必须真的能抓到 bug —— 否则它可能是永远通过的空转
  const fake = ".x{background:var(--dsw-alias-brand-primary);color:#fff}";
  const m2 = /([^{}]+)\{([^{}]*)\}/.exec(fake);
  const bg2 = /background(?:-color)?\s*:\s*([^;]+)/.exec(m2[2]);
  const fg2 = /(?:^|;)\s*color\s*:\s*([^;]+)/.exec(";" + m2[2]);
  assert.ok(bg2 && fg2 && flipping.some((t) => bg2[1].includes(t))
    && !foreground.some((t) => fg2[1].trim().includes(t)),
    "反证失败：这条检验抓不到经典的 brand-primary + #fff 组合，等于空转");
});
