// dsh-service-portal — 对外服务门户（DSH host-plane 插件）。
//
// 定位：**启动器，不是第二份实现**。
//
//   「随机域名 + 随机口令」的隧道与认证代理由**本仓库自己**承担
//   （tools/start_public_gui.py + tools/tunnel_auth.py，35 项控制检验通过）。
//   本插件只做三件事：
//       1. 以子进程方式调起/停止那个脚本（--single-domain / --stop）；
//       2. 读它的凭据 JSON（<infraPath>/runs/public_gui_credentials.json）拿 URL 与口令；
//       3. 通过宿主 webServer 暴露 /service-portal/api 给设置页消费。
//
// **两个路径要分清**：
//   · infraPath —— 基础设施仓库（本仓库 dsh-service-portal），放着隧道/代理脚本与凭据；
//   · repoPath  —— **宿主仓库**（如 ld-rl-poker），放着被对外开放的服务本体。
//   基础设施用「宿主仓库 + 相对脚本」启动服务，所以两个都要给对。
//
// 为什么不在插件里重写一遍隧道逻辑：那会产生第二份实现，日后修 bug 要改两处，
// 且要重建一整套控制检验。复用已验证实现是本仓库的明确倾向（同族插件的共同纪律）。
//
// 安全边界（必须如实呈现，不粉饰）：
//   · 口令来自 <infraPath>/runs/public_gui_credentials.json，是**明文**；插件按用户选择
//     明文显示在设置页。
//   · 拿到该口令 == 能启停被开放服务（对 ld-rl-poker 而言 = 能启停 5090 上的训练）。
//   · 插件**不会**动 dsh-pocket 自己的隧道（目标 3081），只碰本仓库脚本记录的子进程。

import { spawn } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { join, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import z from "@deepseek-ai/schemastery";

const PACKAGE_ROOT = dirname(dirname(fileURLToPath(import.meta.url)));

export const name = "dsh-service-portal";
// webServer 是软依赖（headless 组合没有它）：放进 inject 会让无 Web 组合起不来，
// 所以用 inject 拿 connection（可选）并在 apply 里用 ctx.inject(["webServer"]) 软挂载。
export const inject = [];

/** 基础设施仓库（隧道/代理/凭据）：默认 = 本插件所在的仓库（就是本仓库）。 */
const DEFAULT_INFRA = PACKAGE_ROOT;
/** 宿主仓库（被开放的服务本体所在）。 */
const DEFAULT_REPO = "D:\\DshProject\\ld-rl-poker";
const API_PREFIX = "/service-portal/api";

/** 可热改字段：宿主把 .volatile() 字段投影成设置表单。 */
function volatileField(schema) {
  return typeof schema?.volatile === "function" ? schema.volatile() : schema;
}

export const Config = z.object({
  /** 基础设施仓库根（dsh-service-portal）：含 tools/ 与 runs/。 */
  infraPath: volatileField(z.string().default(DEFAULT_INFRA)),
  /** 宿主仓库根：被对外开放的服务在这里。 */
  repoPath: volatileField(z.string().default(DEFAULT_REPO)),
  /** 拉服务用的 python；留空则用宿主仓库 .venv313，再退到 PATH 的 python。 */
  pythonPath: volatileField(z.string().default("")),
  /** 是否挂载 /service-portal/api 路由。 */
  webEnabled: volatileField(z.boolean().default(true)),
});

function readSwitch(value, fallback) {
  if (value && typeof value === "object" && typeof value.get === "function") {
    const got = value.get();
    return got === undefined || got === null ? fallback : got;
  }
  return value === undefined || value === null ? fallback : value;
}

function configOf(config) {
  const infraPath = String(readSwitch(config?.infraPath, DEFAULT_INFRA) || DEFAULT_INFRA);
  const repoPath = String(readSwitch(config?.repoPath, DEFAULT_REPO) || DEFAULT_REPO);
  const pythonPath = String(readSwitch(config?.pythonPath, "") || "");
  const webEnabled = Boolean(readSwitch(config?.webEnabled, true));
  return { infraPath, repoPath, pythonPath, webEnabled };
}

// ---------------------------------------------------------------- 路径与调用

function pythonFor(repoPath, configured) {
  if (configured && existsSync(configured)) return configured;
  const venv = join(repoPath, ".venv313", "Scripts", "python.exe");
  if (existsSync(venv)) return venv;
  const runtime = join(repoPath, ".runtime", "python",
    "cpython-3.13-windows-x86_64-none", "python.exe");
  if (existsSync(runtime)) return runtime;
  return "python";
}

/** 基础设施脚本（隧道/代理启动器）在 infraPath/tools 里。 */
function startScript(infraPath) {
  return join(infraPath, "tools", "start_public_gui.py");
}

/** 凭据与状态落在基础设施仓库的 runs/ 下。 */
function credPath(infraPath) {
  return join(infraPath, "runs", "public_gui_credentials.json");
}

function statePath(infraPath) {
  return join(infraPath, "runs", "public_gui_state.json");
}

function readJson(path) {
  try {
    return JSON.parse(readFileSync(path, "utf8"));
  } catch {
    return null;
  }
}

/**
 * 读取当前公开入口状态。
 *
 * 返回结构（settings 页直接消费）：
 *   { ok, repoPath, running, mode, baseUrl, username, password, endpoints[], logsDir, problem }
 *
 * `running` 的判定**不只看凭据文件存在**：还要确认记录里的代理端口真的在监听，
 * 否则「脚本被杀但 JSON 还在」会显示成"运行中"（本项目最忌讳的"不崩但给错误答案"）。
 */
async function readStatus(repo) {
  const infraPath = repo.infraPath;
  const repoPath = repo.repoPath;
  const problem = [];
  if (!existsSync(infraPath)) {
    return { ok: false, infraPath, repoPath, running: false,
      problem: `基础设施仓库目录不存在：${infraPath}` };
  }
  const script = startScript(infraPath);
  if (!existsSync(script)) {
    return {
      ok: false, infraPath, repoPath, running: false,
      problem: `找不到 ${script}（外网启动器不在该仓库，或 infraPath 配错）`,
    };
  }
  const cred = readJson(credPath(infraPath));
  if (!cred) {
    return {
      ok: true, infraPath, repoPath, running: false, mode: null, baseUrl: null,
      username: null, password: null, endpoints: [], problem: null,
      note: "尚未启动过外网入口（没有凭据文件）",
    };
  }
  const state = readJson(statePath(infraPath));
  const ports = [];
  for (const info of Object.values(cred.endpoints ?? {})) {
    if (info?.proxy_port) ports.push(info.proxy_port);
  }
  const alive = ports.length ? await Promise.all(ports.map(portListening)) : [];
  const running = alive.some(Boolean);
  if (ports.length && !running) {
    problem.push("凭据文件还在，但记录的代理端口都没在监听：服务已停止或异常退出");
  }
  const endpoints = Object.entries(cred.endpoints ?? {}).map(([key, info]) => ({
    key,
    name: info?.name ?? key,
    url: info?.url ?? null,
    path: info?.path ?? null,
    proxy_port: info?.proxy_port ?? null,
    gui_port: info?.gui_port ?? null,
  }));
  return {
    ok: true,
    infraPath,
    repoPath,
    running,
    mode: cred.mode ?? "separate-domains",
    baseUrl: cred.base_url ?? (endpoints[0]?.url ?? null),
    username: cred.username ?? null,
    password: cred.password ?? null,
    startedAt: cred.started_at ?? null,
    endpoints,
    statePids: (state?.processes ?? []).length,
    problem: problem.length ? problem.join("；") : null,
  };
}

function portListening(port) {
  return new Promise((resolvePort) => {
    import("node:net").then(({ Socket }) => {
      const sock = new Socket();
      const done = (result) => { try { sock.destroy(); } catch { /* ignore */ } resolvePort(result); };
      sock.setTimeout(700);
      sock.once("connect", () => done(true));
      sock.once("timeout", () => done(false));
      sock.once("error", () => done(false));
      sock.connect(Number(port), "127.0.0.1");
    }).catch(() => resolvePort(false));
  });
}

/** 起一个子进程并收集输出；带超时兜底，绝不无限挂住 DSH 主进程。 */
function runProcess(argv, { cwd, timeoutMs = 180000 }) {
  return new Promise((resolveRun) => {
    let child;
    try {
      child = spawn(argv[0], argv.slice(1), {
        cwd, windowsHide: true,
        stdio: ["ignore", "pipe", "pipe"],
      });
    } catch (error) {
      resolveRun({ code: -1, stdout: "", stderr: String(error), spawnError: true });
      return;
    }
    let stdout = "";
    let stderr = "";
    let settled = false;
    const finish = (payload) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolveRun(payload);
    };
    const timer = setTimeout(() => {
      try { child.kill(); } catch { /* ignore */ }
      finish({ code: -2, stdout, stderr: stderr + "\n[超时] 启动脚本超过 "
        + Math.round(timeoutMs / 1000) + " 秒未返回，已终止" });
    }, timeoutMs);
    child.stdout?.on("data", (chunk) => { stdout += chunk.toString("utf8"); });
    child.stderr?.on("data", (chunk) => { stderr += chunk.toString("utf8"); });
    child.once("error", (error) => finish({ code: -1, stdout, stderr: String(error) }));
    child.once("close", (code) => finish({ code, stdout, stderr }));
  });
}

async function startPublic(repo, { singleDomain = true } = {}) {
  // python 取**宿主仓库**的（服务脚本与依赖都在那边），启动器在**基础设施仓库**。
  const python = pythonFor(repo.repoPath, repo.pythonPath);
  const script = startScript(repo.infraPath);
  const argv = [python, "-X", "utf8", script];
  if (singleDomain) argv.push("--single-domain");
  // 若基础设施仓库提供了服务清单，显式传给启动器（否则它用内置默认清单）。
  const manifest = join(repo.infraPath, "services.json");
  if (existsSync(manifest)) argv.push("--services", manifest);
  const result = await runProcess(argv, { cwd: repo.infraPath, timeoutMs: 240000 });
  const status = await readStatus(repo);
  return {
    ok: result.code === 0 && status.running,
    exitCode: result.code,
    // 脚本输出含 URL 与口令；原样回传便于用户在设置页看到失败原因。
    stdout: result.stdout.slice(-8000),
    stderr: result.stderr.slice(-8000),
    status,
  };
}

async function stopPublic(repo) {
  const python = pythonFor(repo.repoPath, repo.pythonPath);
  const script = startScript(repo.infraPath);
  const result = await runProcess([python, "-X", "utf8", script, "--stop"],
    { cwd: repo.infraPath, timeoutMs: 60000 });
  const status = await readStatus(repo);
  return {
    ok: result.code === 0,
    exitCode: result.code,
    stdout: result.stdout.slice(-4000),
    stderr: result.stderr.slice(-4000),
    status,
  };
}

// ---------------------------------------------------------------- Web 路由

function sendJson(res, status, payload) {
  const body = Buffer.from(JSON.stringify(payload, null, 2), "utf8");
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": String(body.length),
    "Cache-Control": "no-store",
  });
  res.end(body);
}

async function readBody(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  if (!chunks.length) return {};
  try {
    return JSON.parse(Buffer.concat(chunks).toString("utf8"));
  } catch {
    return {};
  }
}

function createHandler(getRepo) {
  return async (req, res) => {
    const url = new URL(req.url ?? "/", "http://127.0.0.1");
    const route = url.pathname.slice(API_PREFIX.length) || "/";
    const repo = getRepo();
    try {
      if (req.method === "GET" && (route === "/" || route === "/status")) {
        return sendJson(res, 200, await readStatus(repo));
      }
      if (req.method === "POST" && route === "/start") {
        const body = await readBody(req);
        const payload = await startPublic(repo, {
          singleDomain: body.singleDomain !== false,
        });
        return sendJson(res, payload.ok ? 200 : 502, payload);
      }
      if (req.method === "POST" && route === "/stop") {
        const payload = await stopPublic(repo);
        return sendJson(res, payload.ok ? 200 : 502, payload);
      }
      return sendJson(res, 404, { error: `unknown route ${route}` });
    } catch (error) {
      return sendJson(res, 500, { error: String(error?.stack ?? error) });
    }
  };
}

// ---------------------------------------------------------------- apply

export function apply(ctx, config) {
  const repo = configOf(config);
  ctx.logger?.info?.(
    `[service-portal] 基础设施=${repo.infraPath} 宿主=${repo.repoPath} `
    + `python=${repo.pythonPath || "(自动)"}`);

  if (!repo.webEnabled) return;

  // 软挂载：无 webServer 的组合（headless）保持 fail-closed，不宣称 Web 就绪。
  ctx.inject(["webServer"], (webCtx) => {
    const webServer = webCtx.webServer;
    if (webServer === undefined) return;

    // 每次请求现读 Config —— volatile 字段是 { get() } 引用且无订阅，
    // 这样改设置即时生效，无需重挂插件。
    const getRepo = () => configOf(config);
    const dispose = webServer.register({
      kind: "prefix",
      path: API_PREFIX,
      handler: createHandler(getRepo),
    });
    ctx.logger?.info?.(`[service-portal] 已挂载 ${API_PREFIX}`);
    return dispose;
  });
}

// 供测试直接调用（不经过 HTTP）。
export const _internals = {
  configOf, pythonFor, readStatus, startPublic, stopPublic, portListening,
};
