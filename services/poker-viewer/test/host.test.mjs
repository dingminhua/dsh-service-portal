// dsh-poker-viewer 控制检验（宿主端核心逻辑，不起 Web 服务、不开公网入口）。
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
import { mkdtempSync, mkdirSync, writeFileSync, rmSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createServer } from "node:net";

import { _internals, Config, name, apply } from "../lib/index.js";

const { configOf, pythonFor, readStatus, portListening } = _internals;

/** 造一个假的**基础设施**仓库骨架（含 tools/start_public_gui.py 与 runs/）。
 *
 * 2026-10-15 迁移后路径分成两个：
 *   · infraPath —— 隧道/代理脚本与凭据（本函数造的就是它）
 *   · repoPath  —— 被对外开放的服务所在（本插件不读它的文件，只把它传给启动器）
 * 所以这里只造基础设施那一半，repoPath 用任意占位路径即可。
 */
function fakeRepo({ withScript = true, cred = null, state = null } = {}) {
  const root = mkdtempSync(join(tmpdir(), "poker-viewer-test-"));
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
      resolvePort({ server, port: server.address().port });
    });
  });
}

function cleanup(...roots) {
  for (const root of roots) {
    try { rmSync(root, { recursive: true, force: true }); } catch { /* ignore */ }
  }
}

test("name 与 Config 契约", () => {
  assert.equal(name, "dsh-poker-viewer");
  assert.ok(Config, "必须导出 Config（设置页靠它投影表单）");
  // schemastery 的 dict 里必须有这三个字段，否则设置页看不到
  const dict = Config.dict ?? {};
  for (const field of ["repoPath", "pythonPath", "webEnabled"]) {
    assert.ok(field in dict, `Config 缺少字段 ${field}`);
  }
});

test("configOf：认 volatile 引用，也认普通值（宿主两代兼容）", () => {
  // 普通值
  const plain = configOf({ repoPath: "X:\\repo", pythonPath: "Y:\\py.exe", webEnabled: false });
  assert.equal(plain.repoPath, "X:\\repo");
  assert.equal(plain.pythonPath, "Y:\\py.exe");
  assert.equal(plain.webEnabled, false);

  // volatile 引用（只有 get()）
  const vol = configOf({
    repoPath: { get: () => "V:\\vol-repo" },
    pythonPath: { get: () => "V:\\vol-py.exe" },
    webEnabled: { get: () => false },
  });
  assert.equal(vol.repoPath, "V:\\vol-repo", "volatile 引用必须被解包");
  assert.equal(vol.pythonPath, "V:\\vol-py.exe");
  assert.equal(vol.webEnabled, false);

  // 缺失 / undefined -> 回落默认，绝不给 undefined
  const empty = configOf({});
  assert.ok(empty.repoPath && empty.repoPath.length > 0, "repoPath 必须有默认值");
  assert.equal(empty.pythonPath, "");
  assert.equal(empty.webEnabled, true);

  // 反例控制：volatile 返回 undefined 时不能把 undefined 当路径
  const undef = configOf({ repoPath: { get: () => undefined } });
  assert.notEqual(undef.repoPath, undefined);
  assert.ok(String(undef.repoPath).length > 0);
});

test("portListening：正例（真监听）与反例（没监听）必须可区分", async () => {
  const { server, port } = await listenOnFreePort();
  try {
    const yes = await portListening(port);
    assert.equal(yes, true, `端口 ${port} 正在监听，必须判定为 true`);
    // 反例：关掉之后必须变 false（否则"永远运行中"）
    await new Promise((r) => server.close(r));
    const no = await portListening(port);
    assert.equal(no, false, `端口 ${port} 已关闭，必须判定为 false`);
    // 反例：一个几乎不可能被占用的高位端口
    const never = await portListening(65533);
    assert.equal(never, false);
  } finally {
    try { server.close(); } catch { /* ignore */ }
  }
});

test("readStatus：仓库不存在 -> ok:false 且说明原因（不假装能用）", async () => {
  const missing = join(tmpdir(), "definitely-not-a-repo-" + Date.now());
  const status = await readStatus(repoOf(missing));
  assert.equal(status.ok, false, "仓库不存在必须报 ok:false");
  assert.equal(status.running, false);
  assert.match(status.problem, /不存在/, "必须说明是目录不存在");
});

test("readStatus：仓库存在但缺 tools/start_public_gui.py -> 指出脚本缺失", async () => {
  const root = fakeRepo({ withScript: false });
  try {
    const status = await readStatus(repoOf(root));
    assert.equal(status.ok, false);
    assert.equal(status.running, false);
    assert.match(status.problem, /start_public_gui\.py/, "必须点名缺哪个脚本");
  } finally { cleanup(root); }
});

test("readStatus：没启动过 -> running:false 且有 note（不是 error）", async () => {
  const root = fakeRepo({});
  try {
    const status = await readStatus(repoOf(root));
    assert.equal(status.ok, true, "仓库可用就算 ok");
    assert.equal(status.running, false);
    assert.equal(status.password, null);
    assert.match(status.note ?? "", /尚未启动/, "应提示尚未启动过");
  } finally { cleanup(root); }
});

test("readStatus 关键控制：凭据文件在但端口没监听 -> running 必须为 false", async () => {
  // 造一个"脚本被打死但 JSON 还在"的场景：代理端口用一个确定没人听的端口。
  const { server, port } = await listenOnFreePort();
  await new Promise((r) => server.close(r));  // 立刻释放，确保没人在听
  const root = fakeRepo({
    cred: {
      mode: "single-domain",
      base_url: "https://example.trycloudflare.com",
      username: "poker",
      password: "SECRET-abcdefgh1234",
      started_at: "2026-10-15 00:00:00",
      endpoints: {
        train: { name: "训练配置台", url: "https://example.trycloudflare.com/train/",
                 path: "/train/", proxy_port: port, gui_port: 8810 },
      },
    },
    state: { processes: [{ role: "proxy_single", pid: 12345 }] },
  });
  try {
    const status = await readStatus(repoOf(root));
    assert.equal(status.running, false,
      "端口没在监听时绝不能说 running（这正是『不崩但给错误答案』那类 bug）");
    assert.match(status.problem ?? "", /没在监听|已停止/, "必须说明为什么判定为已停止");
    // 但凭据本身仍要能读出来（用户可能只是要看上次的地址）
    assert.equal(status.username, "poker");
    assert.equal(status.password, "SECRET-abcdefgh1234");
    assert.equal(status.mode, "single-domain");
    assert.equal(status.endpoints.length, 1);
    assert.equal(status.endpoints[0].path, "/train/");
  } finally { cleanup(root); }
});

test("readStatus 关键控制：端口真在监听 -> running 必须为 true", async () => {
  const { server, port } = await listenOnFreePort();
  const root = fakeRepo({
    cred: {
      mode: "single-domain",
      base_url: "https://live.trycloudflare.com",
      username: "poker",
      password: "SECRET-live",
      endpoints: {
        viewer: { name: "模型查看台", url: "https://live.trycloudflare.com/viewer/",
                  path: "/viewer/", proxy_port: port, gui_port: 8811 },
      },
    },
  });
  try {
    const status = await readStatus(repoOf(root));
    assert.equal(status.running, true, "端口在监听时必须判定 running:true");
    assert.equal(status.problem, null, "正常运行时不该有 problem");
  } finally {
    await new Promise((r) => server.close(r));
    cleanup(root);
  }
});

test("readStatus：两个端点只活一个也算 running（只要有一个能访问）", async () => {
  const { server, port } = await listenOnFreePort();
  const deadPort = 65533;
  const root = fakeRepo({
    cred: {
      mode: "separate-domains",
      username: "poker", password: "SECRET-x",
      endpoints: {
        train: { name: "训练配置台", url: "https://a.example", proxy_port: port, gui_port: 8810 },
        viewer: { name: "模型查看台", url: "https://b.example", proxy_port: deadPort, gui_port: 8811 },
      },
    },
  });
  try {
    const status = await readStatus(repoOf(root));
    assert.equal(status.running, true, "有一个端口活着就应算运行中");
    assert.equal(status.endpoints.length, 2, "两个端点都要列出来（不能只显示活的）");
  } finally {
    await new Promise((r) => server.close(r));
    cleanup(root);
  }
});

test("readStatus：坏 JSON（半截文件）不能抛异常，要当没启动", async () => {
  const root = fakeRepo({});
  try {
    writeFileSync(join(root, "runs", "public_gui_credentials.json"),
      '{"username": "poker", "passw', "utf8");  // 故意截断
    const status = await readStatus(repoOf(root));
    assert.equal(status.ok, true, "坏 JSON 不应让整个状态查询失败");
    assert.equal(status.running, false);
    assert.equal(status.password, null);
  } finally { cleanup(root); }
});

test("pythonFor：优先配置值 -> .venv313 -> .runtime -> PATH，且都必须真实存在", () => {
  const root = fakeRepo({});
  try {
    // 1) 什么都没配：不能返回一个不存在的路径（要回落到可执行的 'python'）
    const bare = pythonFor(root, "");
    assert.ok(typeof bare === "string" && bare.length > 0);
    assert.ok(!bare.includes(".venv313"),
      "没有 .venv313 时不应返回该路径（否则启动必失败）");

    // 2) 仓库里有 .venv313 时必须选它（正例）
    const venvDir = join(root, ".venv313", "Scripts");
    mkdirSync(venvDir, { recursive: true });
    const venvPy = join(venvDir, "python.exe");
    writeFileSync(venvPy, "", "utf8");
    assert.equal(pythonFor(root, ""), venvPy, "存在 .venv313 时必须优先用它");

    // 3) 显式配置值优先于 .venv313（正例）
    const custom = join(root, "custom-python.exe");
    writeFileSync(custom, "", "utf8");
    assert.equal(pythonFor(root, custom), custom, "显式配置必须最优先");

    // 4) 反例：配置了不存在的路径 -> 必须忽略它，而不是照用
    const ghost = join(root, "no-such-python.exe");
    assert.notEqual(pythonFor(root, ghost), ghost,
      "配置了不存在的解释器时必须回落，不能照用");
  } finally { cleanup(root); }
});

test("apply：无 webServer 时 fail-closed（不抛异常、不宣称 Web 就绪）", () => {
  const logs = [];
  const ctx = {
    logger: { info: (m) => logs.push(m) },
    // 模拟宿主：inject 一个不存在的 webServer（headless 组合）
    inject: (deps, fn) => { fn({ webServer: undefined }); },
  };
  let threw = null;
  try {
    apply(ctx, { infraPath: "D:\\nonexistent-repo", repoPath: "D:\\nonexistent-repo", pythonPath: "", webEnabled: true });
  } catch (error) { threw = error; }
  assert.equal(threw, null, "headless 组合下 apply 不能抛异常（会让插件起不来）");
  assert.ok(logs.some((m) => /poker-viewer/.test(m)), "至少要有启动日志");
});

test("apply：webEnabled=false 时不注册路由（设置能真正关掉 Web 面）", () => {
  let registered = 0;
  const ctx = {
    logger: { info: () => {} },
    inject: (deps, fn) => { fn({ webServer: { register: () => { registered += 1; return () => {}; } } }); },
  };
  apply(ctx, { infraPath: "D:\\nonexistent-repo", repoPath: "D:\\nonexistent-repo", pythonPath: "", webEnabled: false });
  assert.equal(registered, 0, "webEnabled=false 时不应注册任何路由");
});

test("apply：有 webServer 时注册 prefix 路由，路径必须是 /poker-viewer/api", () => {
  const routes = [];
  const disposers = [];
  const ctx = {
    logger: { info: () => {} },
    inject: (deps, fn) => {
      fn({ webServer: {
        register: (route) => { routes.push(route); const d = () => {}; disposers.push(d); return d; },
      } });
    },
  };
  apply(ctx, { infraPath: "D:\\nonexistent-repo", repoPath: "D:\\nonexistent-repo", pythonPath: "", webEnabled: true });
  assert.equal(routes.length, 1, "应注册恰好一个路由");
  assert.equal(routes[0].kind, "prefix", "必须是 prefix 路由（要覆盖子路径）");
  assert.equal(routes[0].path, "/poker-viewer/api");
  assert.equal(typeof routes[0].handler, "function");
});

test("路由 handler：未知子路径 -> 404，status -> 200（正反例可区分）", async () => {
  const routes = [];
  const ctx = {
    logger: { info: () => {} },
    inject: (deps, fn) => {
      fn({ webServer: { register: (route) => { routes.push(route); return () => {}; } } });
    },
  };
  apply(ctx, { infraPath: "D:\\nonexistent-repo", repoPath: "D:\\nonexistent-repo", pythonPath: "", webEnabled: true });
  const handler = routes[0].handler;

  // 极简的 req/res 模拟
  function mockRes() {
    return {
      statusCode: null, headers: null, body: null,
      writeHead(code, headers) { this.statusCode = code; this.headers = headers; },
      end(buf) { this.body = buf; },
    };
  }
  const makeReq = (url, method = "GET") => {
    const req = {
      url, method,
      async *[Symbol.asyncIterator]() { /* 无 body */ },
    };
    return req;
  };

  // 正例：/poker-viewer/api/status 在仓库不存在时也要返回结构化 JSON（200 + ok:false）
  const resOk = mockRes();
  await handler(makeReq("/poker-viewer/api/status"), resOk);
  assert.equal(resOk.statusCode, 200, "status 路由必须返回 200（即使仓库不可用，也要给出结构化原因）");
  const payload = JSON.parse(resOk.body.toString("utf8"));
  assert.equal(payload.ok, false, "仓库不存在时 ok 必须为 false");
  assert.ok(payload.problem, "必须带 problem 说明");

  // 正例：裸 /poker-viewer/api 也等同 status
  const resBare = mockRes();
  await handler(makeReq("/poker-viewer/api"), resBare);
  assert.equal(resBare.statusCode, 200);

  // 反例：未知子路径必须 404（不能拿 status 兜底——拼错路径不许"看起来能用"）
  const res404 = mockRes();
  await handler(makeReq("/poker-viewer/api/nonexistent"), res404);
  assert.equal(res404.statusCode, 404, "未知子路径必须 404");

  // 反例：GET 打 /start 必须 404（启动只接受 POST）
  const resMethod = mockRes();
  await handler(makeReq("/poker-viewer/api/start", "GET"), resMethod);
  assert.equal(resMethod.statusCode, 404, "GET /start 不应被当成启动");
});

test("模块不残留全局状态：两次 readStatus 互不影响（无缓存串味）", async () => {
  const rootA = fakeRepo({});
  const rootB = fakeRepo({});
  try {
    const a1 = await readStatus(repoOf(rootA));
    const b1 = await readStatus(repoOf(rootB));
    // 迁移后区分两个实例的是 infraPath（凭据/脚本所在），不是 repoPath
    // （repoPath 默认相同，它是被开放的宿主仓库）。
    assert.equal(a1.infraPath, rootA);
    assert.equal(b1.infraPath, rootB, "第二个仓库的状态必须用自己的路径（不能缓存第一个）");
    assert.notEqual(a1.infraPath, b1.infraPath);
  } finally { cleanup(rootA, rootB); }
});
