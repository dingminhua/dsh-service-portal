// dsh-service-portal 控制检验（宿主端核心逻辑，不起 Web 服务、不开公网入口）。
//
// 拦的是这类 bug（每一个都能"不崩、只给错误答案"）：
//   1. 状态判定只看凭据文件存在 → 脚本被杀后仍显示"运行中"（用户以为能访问，其实打不开）；
//   2. 端口探测恒真/恒假 → 状态永远"运行中"或永远"已停止"；
//   3. 仓库路径配错 → 静默用默认值调起别的目录的脚本；
//   4. python 选择逻辑退化 → 拿系统 python 去跑需要 .venv313 的 GUI；
//   5. 超时不生效 → 启动脚本卡住时把 DSH 主进程一起拖住；
//   6. Config 读取不认 volatile 引用 → 设置页改了参数但插件读不到新值。
//
// 控制检验原则（正着打/反着打必须不同）：不能用"跑通就算过"，必须让
// 正例与反例产生**可区分**的结果。
//
// 运行：node --test test/host.test.mjs   或   node test/host.test.mjs

import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, readdirSync, rmSync, existsSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { createServer } from "node:net";
import { createServer as createHttpServer } from "node:http";

import { _internals, Config, name, apply } from "../lib/index.js";

const { configOf, pythonFor, readStatus, portListening, passwordArgs } = _internals;

/** 仓库根（用于按源码做启动方式回归）。 */
const ROOT = resolve(import.meta.dirname, "..");

/** 造一个假的**基础设施**仓库骨架（含 tools/start_public_gui.py 与 runs/）。 */
function fakeRepo({ withScript = true, cred = null, state = null } = {}) {
  const root = mkdtempSync(join(tmpdir(), "service-portal-test-"));
  mkdirSync(join(root, "runs"), { recursive: true });
  if (withScript) {
    mkdirSync(join(root, "tools"), { recursive: true });
    writeFileSync(join(root, "tools", "start_public_gui.py"), "# stub\n", "utf8");
  }
  if (cred) {
    writeFileSync(join(root, "runs", "public_gui_credentials.json"),
      JSON.stringify(cred), "utf8");
  }
  if (state) {
    writeFileSync(join(root, "runs", "public_gui_state.json"),
      JSON.stringify(state), "utf8");
  }
  return root;
}

/** 组装 readStatus/apply 需要的配置对象（两个路径 + 可选 python）。 */
function repoOf(infraPath, hostPath = "D:\\host-repo") {
  return { infraPath, repoPath: hostPath, pythonPath: "", webEnabled: true };
}

/** 起一个真实监听端口，用于端口探测的正例控制。 */
function listenOnFreePort() {
  return new Promise((resolvePort) => {
    const server = createServer();
    server.listen(0, "127.0.0.1", () => {
      const port = server.address().port;
      resolvePort({ server, port });
    });
  });
}

test("插件身份：name 是 dsh-service-portal", () => {
  assert.equal(name, "dsh-service-portal");
});

test("Config 有四个可热改字段", () => {
  const schema = Config;
  assert.ok(schema);
  // Config 是 schemastery object；字段存在性通过 configOf 默认值体现
  const cfg = configOf({});
  assert.equal(typeof cfg.infraPath, "string");
  assert.equal(typeof cfg.repoPath, "string");
  assert.equal(typeof cfg.pythonPath, "string");
  assert.equal(typeof cfg.webEnabled, "boolean");
});

test("configOf：volatile 引用（{get()}）能读到值", () => {
  const cfg = configOf({
    infraPath: { get: () => "C:\\infra" },
    repoPath: { get: () => "D:\\repo" },
    pythonPath: { get: () => "D:\\py.exe" },
    webEnabled: { get: () => false },
  });
  assert.equal(cfg.infraPath, "C:\\infra");
  assert.equal(cfg.repoPath, "D:\\repo");
  assert.equal(cfg.pythonPath, "D:\\py.exe");
  assert.equal(cfg.webEnabled, false);
});

test("configOf：空值回退到默认", () => {
  const cfg = configOf({});
  assert.equal(cfg.infraPath, resolve(import.meta.dirname, ".."));
  assert.equal(cfg.webEnabled, true);
});

test("pythonFor：配置的路径存在则优先", () => {
  const root = fakeRepo({});
  try {
    const py = join(root, "my-python.exe");
    writeFileSync(py, "# stub\n", "utf8");
    assert.equal(pythonFor("D:\\repo", py), py);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("pythonFor：宿主 .venv313 存在则用它（Windows 布局）", () => {
  const root = fakeRepo({});
  try {
    const venv = join(root, ".venv313", "Scripts");
    mkdirSync(venv, { recursive: true });
    const py = join(venv, "python.exe");
    writeFileSync(py, "# stub\n", "utf8");
    // 传入一个不存在的 configured，验证回退到 .venv313
    assert.equal(pythonFor(root, ""), py);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

// ---------------------------------------------------------------------------
// 默认宿主仓库必须是**空的**，不得预置作者本机路径。
//
// 起因（2026-10-16 发布前复核查出）：DEFAULT_REPO 曾写死 `D:\DshProject\ld-rl-poker`
// —— 那是「第一用户」的机器路径，对任何别人都不成立。别人装完看到的是一个
// 不存在的目录，却因为界面不报错而**以为配好了**，实际拉服务时用的是错的解释器。
//
// 空默认值的两个必须成立的性质（都做成可证伪的断言）：
//   1. 包里/源码里不得再出现作者的本机绝对路径；
//   2. repoPath 为空时，pythonFor **不得**去拼相对路径 ——
//      join("", ".venv313", ...) 会得到 ".venv313/Scripts/python.exe" 这样的
//      相对路径，existsSync 按 cwd 解析，cwd 下恰好有同名目录就会误命中。
// ---------------------------------------------------------------------------

test("默认值：repoPath 默认是空字符串（不预置作者本机路径）", () => {
  const cfg = configOf({});
  assert.equal(cfg.repoPath, "", "repoPath 默认必须是空 —— 不得猜用户的服务放在哪");
  assert.equal(typeof cfg.repoPath, "string");
});

test("默认值：运行期代码里不得把作者本机路径当**取值来源**", () => {
  // 覆盖面见下面 walk()：由 package.json 的 files 推导，另加 client/（客户端面
  // 的来源）。**不查 .md** —— THIRD_PARTY_NOTICES / CHANGELOG 里出现来源仓库名与
  // 历史路径是正当的溯源（RELEASING.md 还专门断言那个名字必须留在溯源声明里）。
  //
  // 断言的是「不得作为取值来源」，不是「不得出现这几个字」—— 以下三类出现是正当的，
  // 一刀切会把它们一起误伤（第一版就是这么写的，跑出来 5 条里 5 条都不该报）：
  //   · 注释/文档字符串里的举例（讲清「以前写死过什么、为什么改」）
  //   · Windows 系统路径兜底（os.environ.get("SystemRoot", r"C:\Windows")）
  //   · 文档字符串里的清单格式示例（"D:\\\\path\\\\to\\\\host"）
  // 所以判据是：这一行属于注释/文档字符串，或是环境变量缺省值里的系统路径。
  const offenders = [];
  const scanned = new Set();          // 记录扫过的文件，供下面的覆盖面反向自检
  const scanFile = (rel) => {
    scanned.add(rel);
    const lines = readFileSync(join(ROOT, rel), "utf8").split("\n");
    let inDoc = false;
    lines.forEach((line, i) => {
      const trimmed = line.trim();
      const quotes = (line.match(/"""/g) || []).length;
      const isDocLine = inDoc || quotes > 0 || trimmed.startsWith("#")
        || trimmed.startsWith("//") || trimmed.startsWith("*")
        || trimmed.startsWith("/*");
      if (quotes % 2 === 1) inDoc = !inDoc;

      const m = /["'`]([A-Za-z]:[\\/][^"'`]*|[\\/](?:Users|home)\/[^"'`]*)["'`]/
        .exec(line);
      if (!m) return;
      if (isDocLine) return;                      // 注释/举例：正当
      // 环境变量缺省值里的系统路径：正当。两种写法都要放行 ——
      //   Python: os.environ.get("SystemRoot", r"C:\Windows")
      //   Node:   process.env.ProgramFiles || "C:\\Program Files"
      // 都是「取系统目录，取不到才用平台缺省」，不是把某个人的仓库路径写死。
      const envFetch = /os\.environ\.get\(|process\.env[\[.]/.test(line)
        || /os\.environ\.get\(|process\.env[\[.]/.test(
          lines.slice(Math.max(0, i - 3), i).join("\n"));
      if (envFetch) {
        const before = line.slice(0, m.index);
        // 紧跟在 `|| ` 之后（Node 兜底），或所在调用的括号还没闭合（Python 跨行）
        if (/\|\|\s*$/.test(before)) return;
        const near = lines.slice(Math.max(0, i - 3), i + 1).join("\n");
        if ((near.match(/\(/g) || []).length > (near.match(/\)/g) || []).length) {
          return;
        }
      }
      offenders.push(`${rel}:${i + 1} -> ${m[1]}`);
    });
  };
  // 覆盖面必须是**全部随包分发的代码**，不只 lib/index.js 与 tools/*.py。
  // 第一版只扫了这两处，实测漏了两类真问题：
  //   · lib/client.js —— 客户端面同样发货（由 client/index.jsx 构建而来），
  //     在它里面写死路径一样会泄；
  //   · tools 里的 .mjs —— probe_button_e2e.mjs 就硬编码过 Chrome 的 Windows 路径。
  // 所以扫描集**从 package.json 的 files 白名单推导**（而不是硬编码目录名）：
  // files 里每个「目录」都递归扫，另加 client/（它是发货的客户端面的**来源**，
  // 只扫构建产物会在源码阶段漏掉）。
  const CODE_EXT = /\.(js|mjs|cjs|jsx|py)$/;
  const { files: shipped } = JSON.parse(
    readFileSync(join(ROOT, "package.json"), "utf8"));
  const walk = (relDir) => {
    for (const ent of readdirSync(join(ROOT, relDir), { withFileTypes: true })) {
      const rel = `${relDir}/${ent.name}`;
      if (ent.isDirectory()) walk(rel);
      else if (CODE_EXT.test(ent.name)) scanFile(rel);
    }
  };
  for (const entry of shipped) {
    let isDir = false;
    try { isDir = statSync(join(ROOT, entry)).isDirectory(); } catch { isDir = false; }
    if (!isDir) continue;                    // 单个文件（README/LICENSE…）不是代码
    walk(entry);
  }
  // client/ 永远扫：它是 files 里 lib/client.js 的来源。
  if (existsSync(join(ROOT, "client"))) walk("client");

  // 反向自检：扫描集必须真的覆盖到这些关键文件。
  // 为什么需要这条：覆盖面是从 files 推导的，所以「新增了目录却没扫到」那种
  // 情况**永远不会**被下面的 uncovered 断言抓到（推导即覆盖，是条恒真断言）。
  // 真正会发生的退化是反过来 —— 有人把扫描收窄成硬编码的几个文件，于是
  // lib/client.js / *.mjs 重新变成盲区。用一份显式的关键文件清单钉住覆盖面，
  // 收窄扫描就会在这里失败（已实测：把 walk 换成只扫 lib/index.js，本条即红）。
  const REQUIRED_SCANNED = [
    "lib/index.js", "lib/client.js", "client/index.jsx",
    "tools/portal_run.py", "tools/start_public_gui.py",
    "tools/probe_button_e2e.mjs",
  ];
  const missing = REQUIRED_SCANNED.filter((f) => !scanned.has(f));
  assert.deepEqual(missing, [],
    "扫描器没有覆盖这些发货/来源代码文件，覆盖面被收窄了：\n  "
    + missing.join("\n  "));

  // 更强的兜底：作者的宿主仓库目录名**整棵代码树里一次都不许出现**（含注释）。
  // 上面那条只拦「非注释行里的绝对路径字面量」，注释里写全路径它不管；
  // 而 0.8.7 之后注释里也已经不再需要提那个路径（历史细节放 CHANGELOG）。
  // 这条把标准钉死，防止日后又有人图省事在注释里贴本机路径。
  for (const rel of scanned) {
    const text = readFileSync(join(ROOT, rel), "utf8");
    assert.ok(!text.includes("DshProject"),
      `发货代码 ${rel} 里出现了作者的本机目录名 DshProject（应改为中性描述，`
      + "历史细节写进 CHANGELOG）");
  }
  assert.deepEqual(offenders, [],
    "运行期代码把绝对路径当取值来源了（会泄路径 / 换台机器就废）：\n  "
    + offenders.join("\n  "));
});

test("默认值：配置 schema 的 repoPath 默认值不得是作者本机路径", () => {
  // 上一条按行扫，可能被续行/缩进绕过；这条直接问默认值本身。
  const cfg = configOf({});
  assert.ok(!/^[A-Za-z]:[\\/]/.test(cfg.repoPath),
    `repoPath 默认值仍是绝对路径：${cfg.repoPath}`);
  assert.ok(!cfg.repoPath.includes("DshProject"),
    `repoPath 默认值仍含作者本机目录名：${cfg.repoPath}`);
});

test("pythonFor：repoPath 为空时不拼相对路径（否则可能按 cwd 误命中）", () => {
  const root = fakeRepo({});
  try {
    // 在当前 cwd 下造一个 .venv313 —— 若实现写了 join("", ...) 且 cwd 恰好
    // 是 root，就会误命中；正确实现应该无视它，回落到 PATH 的 python。
    const cwdVenv = join(root, ".venv313", "Scripts");
    mkdirSync(cwdVenv, { recursive: true });
    const decoy = join(cwdVenv, "python.exe");
    writeFileSync(decoy, "# decoy\n", "utf8");

    const prev = process.cwd();
    process.chdir(root);
    try {
      const picked = pythonFor("", "");
      assert.equal(picked, "python",
        "repoPath 为空时必须跳过宿主仓库探测、回落到 PATH 的 python；"
        + `实际选到 ${picked}（说明拼出了相对路径并按 cwd 命中了诱饵）`);
    } finally {
      process.chdir(prev);
    }
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("pythonFor：repoPath 非空时仍然照旧优先 .venv313", () => {
  // 反向控制：修「空值」不能把「有值」的路径一起改坏
  const root = fakeRepo({});
  try {
    const venv = join(root, ".venv313", "Scripts");
    mkdirSync(venv, { recursive: true });
    const py = join(venv, "python.exe");
    writeFileSync(py, "# stub\n", "utf8");
    assert.equal(pythonFor(root, ""), py);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("pythonFor：全都不存在则回退到 PATH 的 python", () => {
  const root = fakeRepo({});
  try {
    assert.equal(pythonFor(root, ""), "python");
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("readStatus：infraPath 不存在 → ok:false 且给具体原因", async () => {
  const missing = join(tmpdir(), "service-portal-missing-" + Date.now());
  const s = await readStatus(repoOf(missing));
  assert.equal(s.ok, false);
  assert.equal(s.running, false);
  assert.match(s.problem, /基础设施仓库目录不存在/);
});

test("readStatus：启动器脚本缺失 → ok:false 且给具体原因", async () => {
  const root = fakeRepo({ withScript: false });
  try {
    const s = await readStatus(repoOf(root));
    assert.equal(s.ok, false);
    assert.match(s.problem, /找不到/);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("readStatus：无凭据文件 → 未启动过，running:false，不报 problem", async () => {
  const root = fakeRepo({});
  try {
    const s = await readStatus(repoOf(root));
    assert.equal(s.ok, true);
    assert.equal(s.running, false);
    assert.equal(s.password, null);
    assert.equal(s.passwordMode, null);
    assert.equal(s.problem, null);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("readStatus：凭据文件在但端口没监听 → running:false 且报告 problem", async () => {
  const root = fakeRepo({
    cred: {
      password: "secret",
      mode: "separate-domains",
      endpoints: { train: { name: "训练", url: "https://a.trycloudflare.com", proxy_port: 48901 } },
    },
  });
  try {
    const s = await readStatus(repoOf(root));
    assert.equal(s.running, false);
    assert.match(s.problem, /端口都没在监听/);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("readStatus：凭据文件在且代理端口在听 → running:true", async () => {
  const { server, port } = await listenOnFreePort();
  const root = fakeRepo({
    cred: {
      password: "secret",
      mode: "separate-domains",
      endpoints: { train: { name: "训练", url: "https://a.trycloudflare.com", proxy_port: port } },
    },
  });
  try {
    const s = await readStatus(repoOf(root));
    assert.equal(s.ok, true);
    assert.equal(s.running, true);
    assert.equal(s.password, "secret");
    assert.equal(s.passwordMode, "random");
    assert.equal(s.endpoints.length, 1);
  } finally {
    server.close();
    rmSync(root, { recursive: true, force: true });
  }
});

test("readStatus：single-domain 模式透传 baseUrl 与 path", async () => {
  const { server, port } = await listenOnFreePort();
  const root = fakeRepo({
    cred: {
      password: "p", mode: "single-domain",
      base_url: "https://x.trycloudflare.com",
      endpoints: { train: { name: "训练", url: "https://x.trycloudflare.com/train/", path: "/train/", proxy_port: port } },
    },
  });
  try {
    const s = await readStatus(repoOf(root));
    assert.equal(s.running, true);
    assert.equal(s.mode, "single-domain");
    assert.equal(s.baseUrl, "https://x.trycloudflare.com");
    assert.equal(s.endpoints[0].path, "/train/");
  } finally {
    server.close();
    rmSync(root, { recursive: true, force: true });
  }
});

// ---------------------------------------------------------------------------
// 口令形态（本次新增的核心需求）：每次随机 / 固定口令。
//
// 拦的是这类 bug：
//   · 配了 fixed 但口令为空 -> 启动时才炸（应当**保存时就拒绝**）；
//   · 口令短于门槛也照存 -> 启动器 validate_password 才退出码 2；
//   · 未知/拼错的模式值被当成 fixed -> 安全侧应当回落 random；
//   · 固定口令进命令行 -> 本机任意进程都能从 Win32_Process 读到。
// ---------------------------------------------------------------------------

test("configOf：默认口令形态是 random（安全侧默认）", () => {
  const cfg = configOf({});
  assert.equal(cfg.passwordMode, "random");
  assert.equal(cfg.fixedPassword, "");
});

test("configOf：只有显式 fixed 才算固定口令", () => {
  const fixed = configOf({ passwordMode: { get: () => "fixed" },
    fixedPassword: { get: () => "abcdefghijkl" } });
  assert.equal(fixed.passwordMode, "fixed");
  assert.equal(fixed.fixedPassword, "abcdefghijkl");
  // 拼错/未知值必须落回 random —— 绝不能因为字符串不匹配就放宽
  for (const bogus of ["FIXED", "fixd", "", "random", "true", null]) {
    const cfg = configOf({ passwordMode: { get: () => bogus } });
    assert.equal(cfg.passwordMode, "random", `passwordMode=${bogus} 必须回落 random`);
  }
});

test("configOf：固定口令两端空白被裁掉", () => {
  const cfg = configOf({
    passwordMode: { get: () => "fixed" },
    fixedPassword: { get: () => "  abcdefghijkl  " },
  });
  assert.equal(cfg.fixedPassword, "abcdefghijkl");
});

// ---------------------------------------------------------------------------
// 「装好即用」相关配置（对齐 dsh-pocket 的体验）
//
// 拦的是这类 bug：
//   · autoStart 默认值被写成 false → 设置页打开是空的，「默认主页没打开」；
//   · lanAuthEnabled 默认值被写成 true → 用户以为内网免密，实际每次都要口令；
//   · portalPort 读不回来 → 状态查询打错端口，永远显示「未运行」。
// ---------------------------------------------------------------------------

test("configOf：autoStart 默认开启（装好即用）", () => {
  assert.equal(configOf({}).autoStart, true);
  // 显式关掉要生效
  assert.equal(configOf({ autoStart: { get: () => false } }).autoStart, false);
});

test("configOf：lanAuthEnabled 默认关闭（内网免密）", () => {
  assert.equal(configOf({}).lanAuthEnabled, false);
  assert.equal(configOf({ lanAuthEnabled: { get: () => true } }).lanAuthEnabled, true);
});

test("configOf：portalPort 默认 8899，可被配置覆盖", () => {
  assert.equal(configOf({}).portalPort, 8899);
  assert.equal(configOf({ portalPort: { get: () => 9123 } }).portalPort, 9123);
  // 非法值（0 / 负 / 非数字）回落到默认，不能把端口搞成 0
  for (const bogus of [0, -1, "abc", null]) {
    assert.equal(configOf({ portalPort: { get: () => bogus } }).portalPort, 8899,
      `portalPort=${bogus} 必须回落 8899`);
  }
});

test("passwordArgs：random 模式不传任何口令参数", () => {
  const r = passwordArgs({ infraPath: tmpdir(), passwordMode: "random",
    fixedPassword: "whatever" });
  assert.deepEqual(r.argv, []);
  assert.equal(r.tempFile, null);
});

test("passwordArgs：fixed 模式走临时文件，口令不进命令行", () => {
  const root = mkdtempSync(join(tmpdir(), "sp-pw-"));
  try {
    const r = passwordArgs({ infraPath: root, passwordMode: "fixed",
      fixedPassword: "abcdefghijkl" });
    assert.equal(r.tempFile !== null, true);
    assert.deepEqual(r.argv.slice(0, 2), ["--password-mode", "fixed"]);
    assert.equal(r.argv[2], "--password-file");
    assert.equal(r.argv[3], r.tempFile);
    // 关键：命令行里绝不能出现口令本身
    assert.equal(r.argv.some((a) => a.includes("abcdefghijkl")), false,
      "固定口令泄漏进命令行（本机任意进程可读）");
    // 临时文件内容就是口令
    assert.equal(readFileSync(r.tempFile, "utf8").trim(), "abcdefghijkl");
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("passwordArgs：fixed 但口令为空/过短 -> 明确报错（不等到启动才炸）", () => {
  const empty = passwordArgs({ infraPath: tmpdir(), passwordMode: "fixed",
    fixedPassword: "" });
  assert.match(empty.error, /固定口令是空的/);
  assert.deepEqual(empty.argv, []);
  const short = passwordArgs({ infraPath: tmpdir(), passwordMode: "fixed",
    fixedPassword: "short" });
  assert.match(short.error, /至少 12 个字符/);
  assert.deepEqual(short.argv, []);
  assert.equal(short.tempFile, null);
});

test("portListening：真实监听端口返回 true", async () => {
  const { server, port } = await listenOnFreePort();
  try {
    assert.equal(await portListening(port), true);
  } finally {
    server.close();
  }
});

test("portListening：未监听端口返回 false", async () => {
  // 找一个大概率空闲的端口（起一个再关掉，让系统让出）
  const { server, port } = await listenOnFreePort();
  server.close();
  await new Promise((r) => setTimeout(r, 50));
  assert.equal(await portListening(port), false);
});

test("apply：webEnabled=false 时不挂载路由（fail-closed）", () => {
  let registered = 0;
  const ctx = {
    logger: { info: () => {} },
    inject: () => { registered++; throw new Error("不应调用 inject"); },
  };
  apply(ctx, { infraPath: "D:\\nonexistent", repoPath: "D:\\nonexistent", pythonPath: "", webEnabled: false });
  assert.equal(registered, 0);
});

test("apply：webEnabled=true 且 webServer 存在时注册 1 个 prefix 路由", () => {
  const routes = [];
  const ctx = {
    logger: { info: () => {} },
    inject: (deps, fn) => fn({ webServer: { register: (route) => { routes.push(route); return () => {}; } } }),
  };
  apply(ctx, { infraPath: "D:\\nonexistent", repoPath: "D:\\nonexistent", pythonPath: "", webEnabled: true });
  assert.equal(routes.length, 1);
  assert.equal(routes[0].kind, "prefix");
  assert.equal(routes[0].path, "/service-portal/api");
});

test("apply：webServer 不存在时不注册（headless fail-closed）", () => {
  let registered = 0;
  const ctx = {
    logger: { info: () => {} },
    inject: (deps, fn) => fn({ webServer: undefined }),
  };
  apply(ctx, { infraPath: "D:\\nonexistent", repoPath: "D:\\nonexistent", pythonPath: "", webEnabled: true });
  assert.equal(registered, 0);
});

// ---------------------------------------------------------------------------
// 启动方式回归（真 bug 固化）
//
// 拦的 bug：startPublic 曾经 await runProcess(...) 等门户进程**结束**。
// 但门户是常驻进程（前台 serve_forever）永不退出 —— 于是：
//   点「开启门户」→ 干等 240 秒 → 超时把它 kill 掉 → 用户看到「启动访问失败」。
// 旧启动器（start_public_gui.py）起完就退，所以这个 bug 一直没暴露。
//
// 正确行为：分离启动 + 轮询端口。这里不起真进程（那是 acceptance 的活），
// 只钉住「不能等它退出」这件事在源码里成立。
// ---------------------------------------------------------------------------

test("startPublic：门户是常驻进程，必须分离启动而不是等它退出", () => {
  const src = readFileSync(join(ROOT, "lib", "index.js"), "utf8");
  const start = src.indexOf("async function startPublic");
  assert.ok(start > 0, "找不到 startPublic");
  const rest = src.slice(start);
  const end = rest.indexOf("\nasync function stopPublic");
  const body = end > 0 ? rest.slice(0, end) : rest;

  assert.ok(body.includes("spawnDetached"),
    "startPublic 必须用 spawnDetached（分离启动）");
  assert.ok(!/await runProcess\(argv/.test(body),
    "startPublic 不能 await runProcess(argv…) —— 那会等常驻进程退出并超时 kill 它");
  assert.ok(body.includes("waitForPort"),
    "startPublic 必须轮询端口判断启动成功（常驻进程没有退出码可用）");
});

test("startPublic：已在运行时直接返回，不重复起第二个", () => {
  const src = readFileSync(join(ROOT, "lib", "index.js"), "utf8");
  const start = src.indexOf("async function startPublic");
  const rest = src.slice(start);
  const body = rest.slice(0, rest.indexOf("\nasync function stopPublic"));
  assert.ok(body.includes("portListening(port)"),
    "startPublic 必须先检查端口是否已在监听（幂等，避免撞端口/口令错位）");
});

test("portal_run：绑定端口失败必须明确退出，不能打印「门户已启动」", () => {
  const src = readFileSync(join(ROOT, "tools", "portal_run.py"), "utf8");
  assert.ok(src.includes("except OSError as exc"),
    "portal_run.py 必须捕获绑定失败");
  assert.ok(src.includes("10013"),
    "必须对 WinError 10013（Windows 保留端口）给出可操作提示");
  const bindTry = src.indexOf("server = portal_proxy.make_portal_server");
  const successPrint = src.indexOf('print("门户已启动")');
  assert.ok(bindTry > 0 && successPrint > bindTry,
    "「门户已启动」必须在绑定成功之后才可能打印（否则就是「不崩、只给错误答案」）");
});

test("stop_all：状态文件丢了也要能按端口清理孤儿进程", () => {
  const src = readFileSync(join(ROOT, "tools", "portal_run.py"), "utf8");
  assert.ok(src.includes("_pids_listening_on"),
    "stop_all 必须按端口兜底扫进程（否则状态文件丢了就停不掉）");
});

// ---------------------------------------------------------------------------
// 解释器可写性（本机实测的真 bug，导致「启动后访问失败」）
//
// 拦的 bug：pythonFor 只检查文件**是否存在**，于是选中了
// ld-rl-poker\.venv313 的 python —— 它带沙箱访问控制标记，能写宿主仓库自己的
// runs/，但写 dsh-service-portal/runs 会被拒（PermissionError 13）。
// 后果：门户进程活着、端口在听，但**状态/口令一个都存不下**，
// 设置页读不到状态 → 永远显示「未运行」/ 点开启报 502。
// ---------------------------------------------------------------------------

test("usablePython：必须真的试写，而不是只看文件存在", () => {
  const src = readFileSync(join(ROOT, "lib", "index.js"), "utf8");
  const start = src.indexOf("function usablePython");
  assert.ok(start > 0, "找不到 usablePython");
  const rest = src.slice(start);
  const nextFn = rest.indexOf("\nfunction ", 10);
  const body = nextFn > 0 ? rest.slice(0, nextFn) : rest;
  assert.ok(body.includes("spawnSync"),
    "必须实际运行解释器去试写（文件存在 ≠ 能写）");
  assert.ok(body.includes("existsSync(probeFile)"),
    "要确认文件真的出现了，而不是只看退出码");
});

test("usablePython：探测目录是门户自己的 runs/", () => {
  const src = readFileSync(join(ROOT, "lib", "index.js"), "utf8");
  assert.ok(src.includes("usablePython(repo.repoPath, repo.pythonPath,"),
    "startPublic 必须把探测目录传进去");
  assert.ok(src.includes('join(repo.infraPath, "runs")'),
    "探测目录必须是门户自己的 runs/（换成 TEMP 或宿主 runs 会得出错误结论）");
});

test("usablePython：探测文件用完必删（不留垃圾）", () => {
  const src = readFileSync(join(ROOT, "lib", "index.js"), "utf8");
  const start = src.indexOf("function usablePython");
  const rest = src.slice(start);
  const body = rest.slice(0, rest.indexOf("\nfunction ", 10));
  assert.ok(body.includes("rmSync(probeFile"),
    "探测用的临时文件必须删掉，否则每次启动都在 runs/ 留垃圾");
});

test("save_state：临时文件名唯一（并发启动不再 PermissionError）", () => {
  const src = readFileSync(join(ROOT, "tools", "portal_run.py"), "utf8");
  const start = src.indexOf("def save_state");
  const body = src.slice(start, src.indexOf("\ndef clear_state"));
  assert.ok(body.includes("os.getpid()"),
    "临时名必须含 pid —— 固定名并发写会 PermissionError（实测踩过）");
  assert.ok(!/tmp = STATE_FILE \+ "\.tmp"/.test(body),
    "不能再用固定的 STATE_FILE + '.tmp'");
  assert.ok(body.includes("os.replace"),
    "仍要原子替换（避免写一半留下坏文件）");
});

test("write_password：写失败不阻断启动（它只是给人看的副本）", () => {
  const src = readFileSync(join(ROOT, "tools", "portal_run.py"), "utf8");
  // 公网口令与局域网口令共用 _write_secret_file
  const start = src.indexOf("def _write_secret_file");
  assert.ok(start > 0, "找不到 _write_secret_file");
  const body = src.slice(start, src.indexOf("\ndef write_password", start));
  assert.ok(body.includes("for _attempt in range"),
    "瞬时占用（杀毒扫描）要靠重试穿过");
  assert.ok(body.includes("os.replace"),
    "必须原子替换（避免写一半留下坏文件）");
  assert.ok(body.includes("return False"),
    "写不进去要 return False 而不是抛异常 —— 真凭据在 state 里，不该因此起不来");
  // 两个入口都要在：公网口令 / 局域网口令（两套凭据分开）
  assert.ok(src.includes("def write_password") && src.includes("def write_lan_password"),
    "公网口令与局域网口令各有各的副本写入函数");
  const lan = src.slice(src.indexOf("def write_lan_password"),
    src.indexOf("def write_lan_password") + 200);
  assert.ok(lan.includes("LAN_PASSWORD_FILE"),
    "write_lan_password 写 LAN_PASSWORD_FILE（不能和公网写同一个文件）");
});

// ---------------------------------------------------------------------------
// 未启动状态：地址必须是「将要使用的」，不能回上次运行的残留
// ---------------------------------------------------------------------------

/** 造一个带 portal_state.json 的假仓库（门户形态）。 */
function portalRepo(state) {
  const root = mkdtempSync(join(tmpdir(), "service-portal-state-"));
  mkdirSync(join(root, "runs"), { recursive: true });
  if (state) {
    writeFileSync(join(root, "runs", "portal_state.json"),
      JSON.stringify(state), "utf8");
  }
  return root;
}

/**
 * 拿一个「确定没人监听」的端口。
 *
 * 必须这样拿，不能写死 8899 —— 用户自己的门户可能正跑在那个端口上，
 * 写死会让「未启动」用例在别人机器上偶发失败（本检验第一版就踩了：
 * 本机 8899 正被用户的真实门户占着，listening 意外为真）。
 */
async function closedPort() {
  const { server, port } = await listenOnFreePort();
  await new Promise((done) => server.close(done));
  return port;
}

test("readPortalStatus：没有状态文件时返回 null（从没启动过）", async () => {
  const root = portalRepo(null);
  try {
    assert.equal(await _internals.readPortalStatus(root, "D:\\x", 8899), null);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("readPortalStatus：未启动时地址用**当前配置端口**，不是上次残留的", async () => {
  // 实测踩过：状态文件残留 8991（上次运行），配置已经改成别的端口，
  // 界面就会显示一个根本不存在的地址 —— 用户点它打不开，且无从判断为什么。
  const configured = await closedPort();
  const root = portalRepo({
    portal_port: 8991,
    lan_urls: ["http://192.168.71.10:8991", "http://10.198.75.60:8991"],
    lan_candidates: ["192.168.71.10", "10.198.75.60"],
    lan_ip_override: "",
    password: "oldpw",
  });
  try {
    const s = await _internals.readPortalStatus(root, "D:\\x", configured);
    assert.equal(s.running, false, "端口没监听就该是未运行");
    assert.equal(s.portalPort, configured,
      "未启动时要回配置端口，不是状态文件里的 8991");
    assert.deepEqual(s.lanUrls, [
      `http://192.168.71.10:${configured}`,
      `http://10.198.75.60:${configured}`,
    ], "地址要按当前端口重算，不能直接沿用上次的 8991");
    assert.equal(s.lanPlanned, true, "未启动时地址是「将要使用」，要标出来");
    assert.ok(!String(s.problem).includes("异常退出"),
      "未启动是正常状态，problem 不该是报警口气");
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("readPortalStatus：未启动时手动选定的地址排在第一个", async () => {
  // 手动选定的地址是用户明确指定要用的（认证层也认它），未启动预览必须也认，
  // 否则用户看到的地址和启动后真正拿到的不一致。
  const configured = await closedPort();
  const root = portalRepo({
    portal_port: configured,
    lan_urls: [],
    lan_candidates: ["192.168.71.10", "10.198.75.60"],
    lan_ip_override: "26.31.152.7",
  });
  try {
    const s = await _internals.readPortalStatus(root, "D:\\x", configured);
    assert.equal(s.running, false);
    assert.equal(s.lanUrls[0], `http://26.31.152.7:${configured}`,
      "手动选的地址必须排第一");
    assert.equal(s.lanUrls.length, 3, "其余候选跟在后面，不能丢");
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("readPortalStatus：透出服务清单（设置页据此管理服务，不必开控制台）", async () => {
  // 用户要求：控制台的功能搬进插件设置 —— 刷新服务、增删启停、自动发现。
  // 前提是宿主 /status 得把门户上报的服务清单带出去，否则面板拿不到数据。
  const { server, port } = await listenOnFreePort();
  const root = portalRepo({
    portal_port: port,
    lan_urls: [`http://192.168.71.10:${port}`],
    services: [
      { key: "a", name: "A", mount: "/a", target: "127.0.0.1:1", enabled: true, alive: true },
      { key: "b", name: "B", mount: "/b", target: "127.0.0.1:2", enabled: true, alive: false },
      { key: "c", name: "C", mount: "/c", target: "127.0.0.1:3", enabled: false, alive: false },
    ],
  });
  try {
    const s = await _internals.readPortalStatus(root, "D:\\x", port);
    assert.equal(s.services.length, 3, "三条服务都要透出去");
    assert.equal(s.servicesAlive, true, "拿到过服务清单要标出来");
    // 「开着但上游没响应」= 需要用户处理的那一类。只算 enabled && alive===false：
    // 未启用的 C 不算（它本来就不该在跑）。
    assert.equal(s.servicesDegraded, 1, "只数已启用但上游没响应的");
  } finally {
    server.close();
    rmSync(root, { recursive: true, force: true });
  }
});

test("readPortalStatus：门户没跑时服务清单是空数组（不是 undefined）", async () => {
  // 反例控制：没在跑就没有"正在开放的服务"。面板拿到 undefined 会崩在
  // .map() 上，拿到 [] 才能安全渲染"暂无服务"。
  const configured = await closedPort();
  const root = portalRepo({ portal_port: configured, lan_urls: [] });
  try {
    const s = await _internals.readPortalStatus(root, "D:\\x", configured);
    assert.deepEqual(s.services, []);
    assert.equal(s.servicesAlive, false);
    assert.equal(s.servicesDegraded, 0);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("readPortalStatus：透出 publicPinCustom（设置页据此显示「自定义/随机」）", async () => {
  // 公网密码也能自定义（与局域网对称）。设置页要靠这个标记决定显示
  // 「自定义」还是「本次随机」，以及要不要给「换回随机」出口。
  const { server, port } = await listenOnFreePort();
  const root = portalRepo({
    portal_port: port,
    lan_urls: [`http://192.168.71.10:${port}`],
    public_url: `https://demo-${port}.trycloudflare.com`,
    password: "custom-public-9x",
    lan_password: "12345678",
    public_pin_custom: true,
    lan_pin_custom: false,
  });
  try {
    const s = await _internals.readPortalStatus(root, "D:\\x", port);
    assert.equal(s.publicPinCustom, true, "自定义标记必须透出去");
    assert.equal(s.lanPinCustom, false, "两个标记各自独立，不能串");
  } finally {
    server.close();
    rmSync(root, { recursive: true, force: true });
  }
});

test("readPortalStatus：状态里没写 publicPinCustom 时按 false（不是 undefined）", async () => {
  // 反例控制：老状态文件没有这个字段。界面拿到 undefined 会把「本次随机」
  // 渲染成空白 —— 兜底成 false 才有一致的默认（随机模式）。
  const configured = await closedPort();
  const root = portalRepo({ portal_port: configured, lan_urls: [] });
  try {
    const s = await _internals.readPortalStatus(root, "D:\\x", configured);
    assert.equal(s.publicPinCustom, false);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("readPortalStatus：真在监听时用状态文件里的地址（不做重算）", async () => {
  // 反例控制：运行中必须相信门户报出来的地址 —— 那时端口可能和配置不同
  // （门户支持 --port 覆盖），重算会得到一个错的地址。
  const { server, port } = await listenOnFreePort();
  const root = portalRepo({
    portal_port: port,
    lan_urls: [`http://192.168.71.10:${port}`],
    lan_candidates: ["192.168.71.10", "10.198.75.60"],
    lan_ip_override: "",
  });
  try {
    const s = await _internals.readPortalStatus(root, "D:\\x", 12345);
    assert.equal(s.running, true);
    assert.equal(s.portalPort, port, "运行中要用真实监听端口");
    assert.deepEqual(s.lanUrls, [`http://192.168.71.10:${port}`],
      "运行中要用门户报的地址，不能拿配置端口重算");
    assert.equal(s.lanPlanned, false);
    assert.equal(s.problem, null, "正常运行时没有 problem");
  } finally {
    server.close();
    rmSync(root, { recursive: true, force: true });
  }
});

test("readPortalStatus：用户主动停止过就不再报 problem（不是异常退出）", async () => {
  // portal_run.py --stop 会写下 stopped_clean。那种情况下状态行已经写着
  // 「已停止」，再挂一句红字（"端口没在监听…"）就是噪音 —— 用户截图里的
  // 红字有一部分就是它。
  const configured = await closedPort();
  const root = portalRepo({
    stopped_clean: true,
    stopped_at: "2026-10-16 02:10:35",
    lan_password: "57457404",
    lan_candidates: ["192.168.71.10"],
  });
  try {
    const s = await _internals.readPortalStatus(root, "D:\\x", configured);
    assert.equal(s.running, false);
    assert.equal(s.stoppedClean, true, "要能把「干净停止」透给设置页");
    assert.equal(s.problem, null, "主动停止不是 problem");
    assert.deepEqual(s.lanUrls, [`http://192.168.71.10:${configured}`],
      "停止后仍然要知道下次会用哪个地址");
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("readPortalStatus：反例 —— 没写 stopped_clean 时要报出来（崩溃/被杀）", async () => {
  const configured = await closedPort();
  const root = portalRepo({
    lan_password: "57457404",
    lan_candidates: ["192.168.71.10"],
  });
  try {
    const s = await _internals.readPortalStatus(root, "D:\\x", configured);
    assert.equal(s.stoppedClean, false);
    assert.ok(String(s.problem || "").includes("没在监听"),
      "不是主动停止就要给出「没在监听」这个事实，problem=%r" % s.problem);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

// ---------------------------------------------------------------------------
// 停止门户：请门户「自己退」（沙箱里从外面杀 pid 根本看不见那个进程）
// ---------------------------------------------------------------------------

/** 起一个假的"门户"：只处理 POST /_api/shutdown，按 status 回。 */
function fakePortal({ status = 200, hang = false } = {}) {
  return new Promise((resolvePort) => {
    const server = createHttpServer((req, res) => {
      if (hang) return;                       // 故意不回，用来测超时兜底
      res.writeHead(status, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ ok: status === 200 }));
    });
    server.listen(0, "127.0.0.1", () => {
      resolvePort({ server, port: server.address().port });
    });
  });
}

test("askPortalShutdown：门户回 200 → 认成功", async () => {
  const { server, port } = await fakePortal({ status: 200 });
  try {
    assert.equal(await _internals.askPortalShutdown(port, 2000), true);
  } finally {
    server.close();
  }
});

test("askPortalShutdown：门户回 403 → 认失败（不能当停好了）", async () => {
  // 反例控制：只有 2xx 才算"请它退成功了"。把 403 也当成功的话，
  // 设置页会显示"已停止"，而门户其实还在跑。
  const { server, port } = await fakePortal({ status: 403 });
  try {
    assert.equal(await _internals.askPortalShutdown(port, 2000), false);
  } finally {
    server.close();
  }
});

test("askPortalShutdown：端口上没人 → 快速失败，不拖住设置页", async () => {
  const port = await closedPort();
  const t0 = Date.now();
  assert.equal(await _internals.askPortalShutdown(port, 1500), false);
  assert.ok(Date.now() - t0 < 4000, "失败不能拖太久，否则点停止像卡死");
});

test("askPortalShutdown：门户不回话（卡住）→ 超时失败，仍给兜底机会", async () => {
  const { server, port } = await fakePortal({ hang: true });
  try {
    const t0 = Date.now();
    assert.equal(await _internals.askPortalShutdown(port, 800), false);
    assert.ok(Date.now() - t0 < 5000, "超时后必须返回，不能永远挂着");
  } finally {
    server.close();
  }
});

// ---------------------------------------------------------------------------
// 「下次打开 DSH 要不要自动起」跟随用户的启停动作
//
// 用户的原话：「我觉得默认就应该是启动的，用户关闭下次打开就还是关闭，
// 用户启动下次打开就还是启动，默认是内网启动，外网关闭」。
//
// 这里要拦的是两类"不崩、只给错误答案"：
//   · 动作没记住 → 用户明明停过，下次开机它又自己起来（用户会以为插件自作主张）；
//   · 记住的时机不对 → 停**失败**（门户僵死、端口还占着）也记成"下次别起"，
//     界面说已停止、真实进程还在跑，偏好却被改掉了。
// ---------------------------------------------------------------------------

/**
 * 把宿主路由处理器挂到**真 HTTP server** 上打一次，返回 {status, json}。
 *
 * 为什么不直接调用 handler(req,res)：路由层本身就是被检验的对象（路径、方法、
 * 状态码、JSON 形状都在这一层），用假 req/res 只能证明"函数能跑"，证明不了
 * 真实请求打进去会怎样 —— 这与本文件开头那条"不能用跑通就算过"一致。
 */
async function callHandler(handler, method, route, body) {
  const server = createHttpServer((req, res) => { handler(req, res); });
  await new Promise((done) => server.listen(0, "127.0.0.1", done));
  const port = server.address().port;
  try {
    const res = await fetch(`http://127.0.0.1:${port}/service-portal/api${route}`, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const text = await res.text();
    let json = null;
    try { json = JSON.parse(text); } catch { /* 非 JSON 也算结果 */ }
    return { status: res.status, json };
  } finally {
    await new Promise((done) => server.close(done));
  }
}

/** 造一个"正在监听"的假门户：端口真的在听，/_api/shutdown 回 200 并松开端口。 */
function fakeRunningPortal() {
  return new Promise((resolvePortal) => {
    const server = createHttpServer((req, res) => {
      if (req.url && req.url.startsWith("/_api/shutdown")) {
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ ok: true }));
        // 真门户收到 shutdown 会自己退出、端口随后松掉；这里照做，
        // 否则 stopPublic 会走「兜底 --stop」那条路去 spawn 真进程。
        setTimeout(() => server.close(), 10);
        return;
      }
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ ok: true, kind: "portal", lan_urls: [], services: [] }));
    });
    server.listen(0, "127.0.0.1", () => {
      resolvePortal({ server, port: server.address().port });
    });
  });
}

/** 造一个假的 configEditor，记录 editor.edit 收到的补丁。 */
function fakeConfigEditor({ rows, throwOnEdit = false } = {}) {
  const calls = [];
  const entries = rows ?? [{ options: { name }, value: { repoPath: "", portalPort: 8899 } }];
  return {
    calls,
    entries: () => entries,
    async edit(entry, mutate) {
      if (throwOnEdit) throw new Error("editor 炸了");
      const next = mutate(structuredClone(entry.value ?? {}));
      entry.value = next;
      calls.push(next);
      return next;
    },
  };
}

test("rememberAutoStart：只写本插件自己的条目，其余字段原样保留", async () => {
  const editor = fakeConfigEditor();
  const ctx = { get: () => editor, logger: { warn() {} } };
  assert.equal(await _internals.rememberAutoStart(ctx, false), false);
  assert.equal(editor.calls.length, 1);
  assert.equal(editor.calls[0].autoStart, false);
  assert.equal(editor.calls[0].repoPath, "", "不能顺手抹掉别的字段");
  // 反着打：true 也要能写进去（不是只有 false 生效）
  assert.equal(await _internals.rememberAutoStart(ctx, true), true);
  assert.equal(editor.calls[1].autoStart, true);
});

test("rememberAutoStart：没有 configEditor 时不报错、返回 undefined", async () => {
  // 老宿主/无配置环境的兜底：偏好记不住可以接受，但**绝不能**因此让启停失败。
  const ctx = { get: () => undefined, logger: { warn() {} } };
  assert.equal(await _internals.rememberAutoStart(ctx, false), undefined);
});

test("rememberAutoStart：editor 抛错时吞掉（best-effort），不冒泡", async () => {
  const editor = fakeConfigEditor({ throwOnEdit: true });
  const ctx = { get: () => editor, logger: { warn() {} } };
  assert.equal(await _internals.rememberAutoStart(ctx, true), undefined,
    "写偏好失败必须返回 undefined，而不是把异常抛给调用方");
});

test("rememberAutoStart：找不到本插件条目时不动别的插件", async () => {
  const editor = fakeConfigEditor({
    rows: [{ options: { name: "别的插件" }, value: { autoStart: true } }],
  });
  const ctx = { get: () => editor, logger: { warn() {} } };
  assert.equal(await _internals.rememberAutoStart(ctx, false), undefined);
  assert.equal(editor.calls.length, 0, "不能改到别的插件的条目");
  assert.equal(editor.entries()[0].value.autoStart, true);
});

test("路由 POST /stop：门户自退成功 → 记下「下次不再自动启动」", async () => {
  const { server, port } = await fakeRunningPortal();
  const root = portalRepo({ portal_port: port, password: "pw", lan_urls: [], services: [] });
  const editor = fakeConfigEditor();
  const ctx = { get: () => editor, logger: { warn() {} } };
  try {
    const handler = _internals.createHandler(
      () => ({ infraPath: root, repoPath: root, pythonPath: "", portalPort: port }), ctx);
    const res = await callHandler(handler, "POST", "/stop");
    assert.equal(res.status, 200, "门户已自退就该回 200");
    assert.equal(editor.calls.length, 1, "停成功必须写一次偏好");
    assert.equal(editor.calls[0].autoStart, false);
  } finally {
    try { server.close(); } catch { /* 已关 */ }
    rmSync(root, { recursive: true, force: true });
  }
});

test("路由 POST /stop：没停掉（端口上没人/失败）→ 偏好一动不动", async () => {
  // 反例控制（必须与上一条产生**可区分**的结果）：停失败还写偏好，就会出现
  // 「界面说已停止、下次开机它又自己起来」这种最难查的错位。
  const port = await closedPort();
  const root = portalRepo({ portal_port: port, password: "pw", lan_urls: [], services: [] });
  const editor = fakeConfigEditor();
  const ctx = { get: () => editor, logger: { warn() {} } };
  try {
    const handler = _internals.createHandler(
      () => ({ infraPath: root, repoPath: root, pythonPath: "", portalPort: port }), ctx);
    const res = await callHandler(handler, "POST", "/stop");
    assert.notEqual(res.status, 200, "没停掉就不能回 200");
    assert.equal(editor.calls.length, 0, "失败路径绝不能改偏好");
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("路由 POST /start：启动成功（已在跑，幂等）→ 记下「下次自动启动」", async () => {
  const { server, port } = await fakeRunningPortal();
  const root = portalRepo({ portal_port: port, password: "pw", lan_urls: [], services: [] });
  const editor = fakeConfigEditor();
  const ctx = { get: () => editor, logger: { warn() {} } };
  try {
    const handler = _internals.createHandler(
      () => ({ infraPath: root, repoPath: root, pythonPath: "", portalPort: port }), ctx);
    // lanOnly=true：端口已在听 → startPublic 幂等返回 ok，不需要真起进程
    const res = await callHandler(handler, "POST", "/start", { lanOnly: true });
    assert.equal(res.status, 200);
    assert.equal(editor.calls.length, 1);
    assert.equal(editor.calls[0].autoStart, true);
  } finally {
    try { server.close(); } catch { /* 已关 */ }
    rmSync(root, { recursive: true, force: true });
  }
});

// 开公网的免责声明必须在**服务端**校验，不能只靠前端那个勾选框。
// 为什么（对齐 dsh-pocket 的 issue #31）：前端勾选只解决"用户看见了"，
// 防不住绕过前端直接打接口（脚本 / 旧缓存的前端 / 改过的客户端）。
// 开公网 = 把一台能执行代码的机器暴露到互联网，这一道必须再挡一次。
test("路由 POST /start：开公网未带 disclaimer → 400 拒绝，且不真的去启动", async () => {
  const root = portalRepo({ portal_port: 8899, password: "pw", lan_urls: [], services: [] });
  const editor = fakeConfigEditor();
  const ctx = { get: () => editor, logger: { warn() {} } };
  try {
    const handler = _internals.createHandler(
      () => ({ infraPath: root, repoPath: root, pythonPath: "", portalPort: 8899 }), ctx);
    const res = await callHandler(handler, "POST", "/start", {});
    assert.equal(res.status, 400, "没勾免责声明就开公网必须被拒");
    assert.equal(res.json?.code, "disclaimer-required");
    assert.equal(editor.calls.length, 0,
      "被拒的请求绝不能改「下次自动启动」偏好");
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("路由 POST /start：只内网启动不要求 disclaimer（不暴露公网，别为难它）", async () => {
  const src = readFileSync(join(ROOT, "lib", "index.js"), "utf8");
  const at = src.indexOf('route === "/start"');
  assert.ok(at > 0, "找不到 /start 路由");
  const block = src.slice(at, at + 1200);
  assert.match(block, /body\.lanOnly !== true && body\.disclaimer !== true/,
    "免责声明的校验必须排除 lanOnly 这条路径");
});

test("只认启停动作：自动启动与建/收隧道都不碰该偏好", () => {
  // 「这次是用户点的」与「这是我们自己顺手起的」必须分开 —— 否则自动启动会把
  // 用户"停掉"的决定又改回来，形成"永远关不掉"的循环。
  const src = readFileSync(join(ROOT, "lib", "index.js"), "utf8");
  const ensure = src.slice(src.indexOf("async function ensurePortal"));
  const body = ensure.slice(0, ensure.indexOf("export function apply"));
  assert.ok(!body.includes("rememberAutoStart"),
    "ensurePortal（自动启动）不得改写用户的启停偏好");
  for (const route of ["/tunnel/start", "/tunnel/stop"]) {
    const at = src.indexOf(`route === "${route}"`);
    assert.ok(at > 0, `找不到 ${route} 路由`);
    const chunk = src.slice(at, at + 400);
    assert.ok(!chunk.includes("rememberAutoStart"),
      `${route} 只动隧道，不该改「下次是否自动启动」`);
  }
});

test("readStatus：把「下次是否自动启动」透出给设置页", async () => {
  // 设置页要靠它说清"你停过它，下次不会自己回来"，字段缺了那句话就没法显示。
  const root = portalRepo({
    portal_port: 8899, lan_urls: [], services: [], password: "pw",
  });
  try {
    const on = await _internals.readStatus({ ...repoOf(root), autoStart: true });
    assert.equal(on.autoStart, true);
    const off = await _internals.readStatus({ ...repoOf(root), autoStart: false });
    assert.equal(off.autoStart, false, "停过之后必须如实报 false");
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("cloudflared 探测：跨平台（回归 0.8.10 的 `开启公网访问失败`）", async () => {
  // 真 bug：DEFAULT_CLOUDFLARED 写死 `.../bin/cloudflared.exe`。
  // Windows 上对；macOS/Linux 上同目录里其实叫 `cloudflared`（无后缀），
  // 于是 POST /_api/tunnel/start 恒回 502、公网功能整体哑掉 ——
  // 而路径打印出来"看着是对的"（目录里确实有个 cloudflared），极难发现。
  //
  // 所以这里对**两个启动器**做源码级回归：解析逻辑必须按平台给文件名，
  // 且必须留 PATH 回落，绝不能出现无条件写死 `.exe` 的那一行。
  for (const rel of ["tools/portal_run.py", "tools/start_public_gui.py"]) {
    const src = readFileSync(join(ROOT, rel), "utf8");
    assert.ok(src.includes("def _resolve_cloudflared"),
      `${rel} 必须用 _resolve_cloudflared() 探测，不能写死路径`);
    assert.ok(src.includes("shutil.which(\"cloudflared\")"),
      `${rel} 的探测必须回落到 PATH —— 用户自己装的 cloudflared 也要能用`);
    assert.ok(src.includes("sys.platform"),
      `${rel} 必须按平台决定可执行文件名`);
    assert.ok(!/DEFAULT_CLOUDFLARED = os\.path\.join\([^)]*cloudflared\.exe/.test(src),
      `${rel} 不得再无条件写死 cloudflared.exe（这正是本次 bug）`);
  }
});

// ---------------------------------------------------------------------------
// 「随 DSH 开关」：宿主退出时必须把门户收掉，且**不能误杀别人的门户**。
//
// 用户要求：「这个服务本身就随 dsh 打开和关闭的，不需要再有设置」。
// 门户是 spawnDetached 起的（故意脱离 DSH 子进程树，否则 DSH 一退手机就断），
// 代价是 DSH 退出时它不会自己走 —— 所以必须由插件在 dispose/信号时接管收尾。
// 这个收尾是「删掉停止门户按钮」的前提：没有它，用户就再没有正规入口去停了。
// ---------------------------------------------------------------------------
test("退出收尾：pid 不是我们起的 → 不代关（不误杀用户手动起的门户）", async () => {
  // 用户在终端手动 `portal_run.py --lan-only` 调试时，那个门户不该被
  // DSH 退出顺手杀掉。判据是状态文件里的 pid 与本插件记住的 pid 是否一致。
  //
  // 注意：必须让门户**看起来在运行**（端口真的在听），否则会先命中
  // "已不在运行"那条更早的分支 —— 那样测的是另一件事，是空转。
  // 直接 listen(0) 拿到一个**正被占用**的端口 —— 不要先探一个再重新绑：
  // 探完就关掉的那个端口可能立刻被系统回收/复用，重新 bind 会失败或挂住。
  // （原来的写法就死在这：listen 的回调签名是 (err)，我按"成功了"当无参回调，
  //   结果那个 Promise 永远不 resolve，整个 test 进程挂到 30 秒超时。）
  const probe = createServer();
  const port = await new Promise((resolvePort, rejectPort) => {
    probe.once("error", rejectPort);
    probe.listen(0, "127.0.0.1", () => resolvePort(probe.address().port));
  });
  const root = portalRepo({
    portal_port: port, portal_pid: 4242, lan_urls: [],
    password: "pw", services: [],
  });
  try {
    const result = await _internals.shutdownPortal(
      { ...repoOf(root), portalPort: port }, 9999);
    assert.equal(result.skipped, true, "pid 不匹配时必须跳过，不能代关");
    assert.match(result.reason ?? "", /接管|不代关/,
      "应当命中 pid 不匹配分支（若报「不在运行」，说明本检验空转了）");
  } finally {
    // close() 的回调会等**所有已建连接**结束。readPortalStatus 会朝这个端口
    // 发一个 /_api/state 探测（就绪判据之一），而我们的 probe 只是个裸 TCP
    // server、永不回包 —— 那条连接会一直挂着，close 的回调于是**永远不来**，
    // 整个 test 进程挂到超时（我就在这上面挂了两轮）。
    // 先手动掐掉所有活连接，再关；两个回调都加超时兜底。
    try { probe.closeAllConnections?.(); } catch { /* 老版本 node */ }
    await Promise.race([
      new Promise((done) => probe.close(done)),
      new Promise((done) => setTimeout(done, 3000)),
    ]);
    rmSync(root, { recursive: true, force: true });
  }
});

test("退出收尾：没有本插件启动记录 → 不动（不猜着去杀）", async () => {
  const root = portalRepo({
    portal_port: 8899, portal_pid: 4242, lan_urls: [],
    password: "pw", services: [],
  });
  try {
    const result = await _internals.shutdownPortal(
      { ...repoOf(root), portalPort: 8899 }, null);
    assert.equal(result.skipped, true);
    assert.equal(result.ok, true, "跳过不算失败，不能拖垮 DSH 退出流程");
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("退出收尾：门户已不在运行 → 幂等跳过（退出时不会报错）", async () => {
  // 关键是"端口上没人"。原来写死 8899 —— 而 8899 正是**开发机上真实门户的
  // 默认端口**：只要用户的门户在跑（本插件默认 autoStart 就会让它跑着），
  // 这条必定失败。它看起来像"偶发抖动"，其实是断言依赖了本机外部状态。
  // 现在先借一个空闲端口再释放，得到一个"确定没人监听"的端口。
  const { server, port } = await listenOnFreePort();
  await new Promise((resolveClose) => server.close(resolveClose));

  const root = portalRepo({
    portal_port: port, portal_pid: 4242, lan_urls: [],
    password: "pw", services: [],
  });
  try {
    // 端口上没人 = 已停。此时收尾应当安静跳过，而不是抛异常。
    const result = await _internals.shutdownPortal(
      { ...repoOf(root), portalPort: port }, 4242);
    assert.equal(result.skipped, true);
    assert.match(result.reason ?? "", /不在运行/);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("退出收尾：pid 匹配且端口在听 → 真的把门户停掉", async () => {
  // 端到端：起一个真的门户进程（模拟本插件起的那个），记下它的 pid，
  // 然后走 shutdownPortal —— 必须真的停掉，而不是"报成功但进程还在"。
  const { spawn } = await import("node:child_process");
  const port = await new Promise((resolvePort) => {
    const s = createServer();
    s.listen(0, "127.0.0.1", () => {
      const p = s.address().port;
      s.close(() => resolvePort(p));
    });
  });
  const root = portalRepo(null);
  const script = join(ROOT, "tools", "portal_run.py");
  if (!existsSync(script)) { rmSync(root, { recursive: true, force: true }); return; }
  // 解释器要按平台挑，不能写死 "python3"。
  //
  // 踩到的真问题（在 Windows 上跑 npm test 必红）：写死 "python3" 时，
  // Windows 只有 `python` / `py`，spawn 会**抛 ENOENT 异常**而不是返回一个
  // 起不来的进程 —— 于是下面那句「环境没 python：跳过（不假装通过）」根本
  // 执行不到，整个测试文件直接算失败。生产代码（lib/index.js 的 pythonFor）
  // 本来就做了 PATH 回退，测试反而没有。
  const PY = process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");
  const child = spawn(PY, ["-X", "utf8", script,
    "--port", String(port), "--password", "teardown-check-pw-1", "--lan-only"],
    { cwd: root, detached: true, stdio: "ignore",
      env: { ...process.env, PORTAL_RUNS_DIR: join(root, "runs") } });
  // spawn 失败是异步 emit 的 error 事件；不接住会变成 uncaughtException。
  let spawnError = null;
  child.on("error", (err) => { spawnError = err; });
  try {
    // 等门户真的起来（端口在听）
    let up = false;
    for (let i = 0; i < 60; i += 1) {
      // 解释器根本不存在时不要空等 30 秒：立刻走"环境不具备"的跳过路径
      if (spawnError) break;
      up = await _internals.portListening(port);
      if (up) break;
      await new Promise((r) => setTimeout(r, 500));
    }
    if (!up) {
      // 环境没 python / 起不来：跳过，不假装通过。但如果是我们自己把
      // 解释器名字写错（ENOENT），那要报出来 —— 静默跳过等于让这条
      // 端到端检验永远不跑，反而更糟。
      if (spawnError && spawnError.code !== "ENOENT") {
        throw new Error(`spawn ${PY} 失败：${spawnError.message}`);
      }
      rmSync(root, { recursive: true, force: true });
      return;
    }

    const repo = { ...repoOf(root), portalPort: port };
    const status = await _internals.readPortalStatus(root, "", port);
    assert.equal(status.running, true);
    assert.ok(status.portalPid, "状态里必须透出 portalPid（收尾靠它判归属）");

    const result = await _internals.shutdownPortal(repo, status.portalPid);
    assert.equal(result.ok, true, "pid 一致时必须真的停掉");
    // 关键：进程要真的没了，不能只是"接口返回成功"
    let still = true;
    for (let i = 0; i < 40; i += 1) {
      still = await _internals.portListening(port);
      if (!still) break;
      await new Promise((r) => setTimeout(r, 250));
    }
    assert.equal(still, false, "收尾后端口仍在监听 —— 门户没真停掉");
  } finally {
    try { process.kill(-child.pid, "SIGKILL"); } catch { /* 已退 */ }
    try { child.kill("SIGKILL"); } catch { /* 已退 */ }
    rmSync(root, { recursive: true, force: true });
  }
});

test("随 DSH 开关：apply() 把收尾挂到 dispose 与信号上（不是只定义没接）", () => {
  // registerPortalTeardown 定义了收尾，但**定义了不等于接上了**。
  // 这条检验盯的是接线本身：apply() 必须真的注册 ctx.on("dispose")，
  // 并在进程信号上兜底（DSH 被 Ctrl+C 时 cordis 不一定来得及跑 dispose）。
  const src = readFileSync(join(ROOT, "lib", "index.js"), "utf8");
  assert.ok(src.includes('ctx.on?.("dispose"'),
    "apply 必须把收尾挂到 ctx.on(\"dispose\")，否则卸载时门户不会被收掉");
  assert.ok(src.includes("registerPortalTeardown"),
    "apply 必须使用 registerPortalTeardown（收尾逻辑只有一份）");
  for (const sig of ["SIGINT", "SIGTERM"]) {
    assert.ok(src.includes(`"${sig}"`), `缺少 ${sig} 兜底：DSH 被中断时门户会变残留进程`);
  }
  // 收尾必须幂等：dispose 与信号可能都触发，不能收两遍/抛错
  assert.ok(/let closed = false/.test(src) && /if \(closed\) return/.test(src),
    "收尾必须幂等（closed 标志），否则重复退出会互相打架");
  // 收尾要只针对"自己起的"门户，不能误杀用户手动起的调试进程
  assert.ok(src.includes("Number(status.portalPid) !== Number(ownedPid)"),
    "必须按 pid 判归属，否则会误杀用户手动起的门户");
});
