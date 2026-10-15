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
