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
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { createServer } from "node:net";

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
