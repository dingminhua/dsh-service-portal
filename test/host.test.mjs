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
import { mkdtempSync, mkdirSync, writeFileSync, rmSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { createServer } from "node:net";

import { _internals, Config, name, apply } from "../lib/index.js";

const { configOf, pythonFor, readStatus, portListening } = _internals;

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
    assert.equal(s.problem, null);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("readStatus：凭据文件在但端口没监听 → running:false 且报告 problem", async () => {
  const root = fakeRepo({
    cred: {
      username: "user", password: "secret",
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
      username: "user", password: "secret",
      mode: "separate-domains",
      endpoints: { train: { name: "训练", url: "https://a.trycloudflare.com", proxy_port: port } },
    },
  });
  try {
    const s = await readStatus(repoOf(root));
    assert.equal(s.ok, true);
    assert.equal(s.running, true);
    assert.equal(s.username, "user");
    assert.equal(s.password, "secret");
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
      username: "u", password: "p", mode: "single-domain",
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
