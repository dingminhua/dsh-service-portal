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

import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, openSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import http from "node:http";
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
/** 门户默认端口（内网地址 http://<内网IP>:<port>）。 */
const DEFAULT_PORTAL_PORT = 8899;

/**
 * 代码指纹：随 package.json 的版本号走，`/status` 会带出去。
 *
 * 用途：宿主进程在 DSH 启动时把 lib/index.js 读进内存，此后**不会**热加载。
 * 改完代码没重启 DSH 时，端到端检验测的是旧代码 —— 那时报出来的"失败"是
 * 测试自己过期，不是插件坏了。检验据此跳过（返回 2）而不是假报失败。
 */
const CODE_STAMP = "0.7.6";

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
  /** 口令形态：random = 每次开启自动随机生成；fixed = 用下面的固定口令。 */
  passwordMode: volatileField(z.union([
    z.const("random"), z.const("fixed"),
  ]).default("random")),
  /** 固定口令（仅 passwordMode = fixed 时使用，至少 12 字符）。 */
  fixedPassword: volatileField(z.string().default("")),
  /** 门户端口（内网地址 http://<内网IP>:<port>，默认 8899）。 */
  portalPort: volatileField(z.number().default(DEFAULT_PORTAL_PORT)),
  /** 插件加载后是否自动启动门户（只开内网，不建隧道）。默认开，对齐 dsh-pocket 的「装好即用」。 */
  autoStart: volatileField(z.boolean().default(true)),
  /** 内网访问是否要口令（默认 false = 内网免密）。 */
  lanAuthEnabled: volatileField(z.boolean().default(false)),
  /** 是否挂载 /service-portal/api 路由。 */
  webEnabled: volatileField(z.boolean().default(true)),
});

/** 固定口令的长度门槛（与 tools/portal_login.py 的 MIN_PASSWORD_LEN 一致）。 */
const MIN_PASSWORD_LEN = 12;

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
  const requested = String(readSwitch(config?.passwordMode, "random") || "random");
  // 只认 "fixed"，其余（含将来新增的未知值）一律按 random —— 默认必须是安全侧。
  const passwordMode = requested === "fixed" ? "fixed" : "random";
  const fixedPassword = String(readSwitch(config?.fixedPassword, "") || "").trim();
  // 端口必须是 1-65535 的整数；非法值（0/负/超界/非数字）一律回落默认，
  // 否则会把端口搞成 -1 之类的值，之后所有端口探测都失败、界面永远显示「未运行」。
  const rawPort = Number(readSwitch(config?.portalPort, DEFAULT_PORTAL_PORT));
  const portalPort = Number.isInteger(rawPort) && rawPort >= 1 && rawPort <= 65535
    ? rawPort : DEFAULT_PORTAL_PORT;
  const autoStart = Boolean(readSwitch(config?.autoStart, true));
  const lanAuthEnabled = Boolean(readSwitch(config?.lanAuthEnabled, false));
  const webEnabled = Boolean(readSwitch(config?.webEnabled, true));
  return { infraPath, repoPath, pythonPath, passwordMode, fixedPassword,
    portalPort, autoStart, lanAuthEnabled, webEnabled };
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

/**
 * 挑一个**真的能写门户 runs/ 目录**的 python 来解释门户。
 *
 * 为什么不能只看文件是否存在（实测踩出来的真 bug）：
 * 本机 `ld-rl-poker\.venv313` 与 `.runtime` 里的 python 带着沙箱访问控制标记，
 * 它们**能写宿主仓库自己的 runs/**，但写 `dsh-service-portal/runs/` 会被拒
 * （`PermissionError [Errno 13]`，因为该目录的 ACL 里没有对应 ACE）。
 * 而 `pythonFor` 恰好优先选它们，于是：
 *   门户进程起来了、端口在听，但**状态/口令文件一个都写不出去** ——
 *   设置页读不到状态就永远显示「未运行」，用户看到的是「启动了但访问失败」。
 *
 * 所以：**必须探测目标目录本身**（不是 TEMP、也不是宿主仓库的 runs），
 * 逐个试「在 portal runs/ 里建一个临时文件」，第一个能写的才用。
 */
function usablePython(repoPath, configured, probeDir) {
  const candidates = [];
  if (configured && existsSync(configured)) candidates.push(configured);
  const preferred = pythonFor(repoPath, null);
  if (!candidates.includes(preferred)) candidates.push(preferred);
  for (const name of ["python", "python3", "py"]) {
    if (!candidates.includes(name)) candidates.push(name);
  }
  // 探测目录必须是**门户实际要写的那个**：换一个目录测会得出错误结论
  const dir = probeDir || join(repoPath || process.cwd(), "runs");
  try {
    mkdirSync(dir, { recursive: true });
  } catch { /* 建不了就让探测自己失败 */ }
  const failures = [];
  for (const candidate of candidates) {
    const probeFile = join(dir,
      `.portal_pyprobe_${process.pid}_${Math.random().toString(36).slice(2, 8)}.tmp`);
    const result = spawnSync(candidate, ["-X", "utf8", "-c",
      "import io,sys;io.open(sys.argv[1],'w',encoding='utf-8').write('ok')",
      probeFile], {
      cwd: repoPath || process.cwd(), timeout: 20000, windowsHide: true,
    });
    let wrote = false;
    try { wrote = existsSync(probeFile); } catch { wrote = false; }
    try { rmSync(probeFile, { force: true }); } catch { /* ignore */ }
    if (!result.error && result.status === 0 && wrote) {
      return { python: candidate, reason: null, tried: failures };
    }
    const detail = result.error ? String(result.error)
      : (result.status !== 0 ? `退出码 ${result.status}` : "进程成功但文件没出现（目录被限制写）");
    failures.push(`${candidate}：${detail}`);
  }
  return {
    python: "python",
    reason: `候选 python 都无法写入门户目录 ${dir}，已回落到 PATH 里的 python。`
      + "门户可能能起来，但状态与口令保存会失败（设置页会显示未运行）。试过的：\n  - "
      + failures.join("\n  - "),
    tried: failures,
  };
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

/** 新门户（控制台形态）的状态与端口。 */
function portalStatePath(infraPath) {
  return join(infraPath, "runs", "portal_state.json");
}

function portalScript(infraPath) {
  return join(infraPath, "tools", "portal_run.py");
}

function readJson(path) {
  try {
    return JSON.parse(readFileSync(path, "utf8"));
  } catch {
    return null;
  }
}

/**
 * 问**活着的门户**要一份真实状态（`GET /_api/state`，只走本机回环）。
 *
 * 状态文件可能写不进去（实测 Errno 13：宿主派生的子进程在 runs/ 下新建文件被拒），
 * 那时状态文件里只有上一轮留下的偏好，没有地址/口令。设置页就会显示"运行中，
 * 但没有地址也没有二维码" —— 用户看到的就是「二维码丢了」。
 * 门户自己算的这份里这些字段是齐的，问它最可靠。失败就返回 null（不抛）。
 */
async function fetchPortalState(port, timeoutMs = 4000) {
  return new Promise((resolve) => {
    let done = false;
    const finish = (value) => { if (!done) { done = true; resolve(value); } };
    let req;
    try {
      req = http.request({
        host: "127.0.0.1", port, path: "/_api/state", method: "GET",
      }, (res) => {
        if (res.statusCode !== 200) { res.resume(); finish(null); return; }
        let body = "";
        res.setEncoding("utf8");
        res.on("data", (chunk) => { body += chunk; });
        res.on("end", () => {
          try {
            const parsed = JSON.parse(body);
            finish(parsed && typeof parsed === "object" ? parsed : null);
          } catch { finish(null); }
        });
      });
    } catch { finish(null); return; }
    req.setTimeout(timeoutMs, () => { req.destroy(); finish(null); });
    req.on("error", () => finish(null));
    req.end();
  });
}

/**
 * 读取**新门户**（控制台形态）的状态。
 *
 * 与旧启动器的区别：门户自己就是控制台，服务列表在门户里管理，所以插件只需要
 * 知道「门户在不在跑、内网地址、外网地址、口令」。返回 null 表示没跑过。
 *
 * `running` 同样**不只看状态文件**：还要确认门户端口真的在监听，否则
 * 「进程被杀但 JSON 还在」会显示成"运行中"。
 */
async function readPortalStatus(infraPath, repoPath, configuredPort) {
  let state = readJson(portalStatePath(infraPath));
  if (!state) return null;
  // 端口取哪个：**在跑**时以状态文件为准（那才是真在监听的那个）；**没跑**时以
  // 当前配置为准 —— 状态文件里的端口是上次运行留下的，配置可能已经改过。
  // （实测残留过 8991，而配置是 8899，界面会显示一个根本不存在的地址。）
  const statePort = Number(state.portal_port) || 0;
  const configured = Number(configuredPort) || DEFAULT_PORTAL_PORT;
  const listening = await portListening(statePort || configured);
  const port = listening ? (statePort || configured) : configured;

  // 在跑、但状态文件缺地址/口令时，直接问**活着的门户**要。
  //
  // 为什么需要这一步（实测）：门户进程起来了却写不进 runs/portal_state.json
  // （Errno 13），状态文件里只有上一轮留下的偏好。设置页于是显示"运行中、
  // 但没有内网地址、没有口令" —— 二维码和地址整块都不见了，用户看到的就是
  // 「二维码怎么没了」。门户自己的 /_api/state 里这些是齐的（它自己算的）。
  let live = null;
  if (listening) {
    const needLive = !Array.isArray(state.lan_urls) || state.lan_urls.length === 0
      || !state.password;
    if (needLive) live = await fetchPortalState(port);
    if (live) state = { ...state, ...live };
  }

  // 地址同理：没跑时不能直接回上次的 lan_urls（端口可能已变），要用
  // 「上次探测到的网卡地址 + 当前端口」拼出**将要使用**的地址；手动选定的
  // 地址优先（内网判定也认它，见 portal_proxy.resolve_request_kind）。
  const candidates = Array.isArray(state.lan_candidates)
    ? state.lan_candidates.filter((ip) => typeof ip === "string" && ip) : [];
  const override = String(state.lan_ip_override ?? "");
  const planned = override
    ? [override, ...candidates.filter((ip) => ip !== override)]
    : candidates;
  const lanUrls = (() => {
    if (!listening) return planned.map((ip) => `http://${ip}:${port}`);
    const fromState = Array.isArray(state.lan_urls) ? state.lan_urls : [];
    if (fromState.length) return fromState;
    // 在跑、但状态文件里没有地址 —— 实测会发现这种情况（门户起来了却写不进
    // runs/portal_state.json，配置里又留着上次的候选地址）。之前这里直接回
    // 空数组，设置页于是"运行中但既没地址也没二维码"，看起来就像二维码丢了。
    // 这时用候选地址 + 当前端口兜出来（门户确实在这台机器的这些地址上听着）。
    return planned.map((ip) => `http://${ip}:${port}`);
  })();
  return {
    kind: "portal",
    ok: true,
    infraPath,
    repoPath,
    running: listening,
    mode: "portal",
    baseUrl: state.public_url ?? (lanUrls[0] ?? `http://127.0.0.1:${port}`),
    portalUrl: `http://127.0.0.1:${port}`,
    // 当前生效端口（未启动时=配置端口）。设置页用它显示「端口」并算出未启动时
    // 将要使用的地址 —— 之前这个字段没透出去，客户端只能兜底写死 8899。
    portalPort: port,
    lanUrls,
    // true = 门户没在跑，lanUrls 是「将要使用」的地址（不是此刻可用的）
    lanPlanned: !listening,
    publicUrl: state.public_url ?? null,
    password: state.password ?? null,
    passwordMode: state.password_mode ?? null,
    // 内网是否要口令（默认 false = 内网免密）。这是设置页「局域网访问密码」开关的状态。
    lanAuthEnabled: Boolean(state.lan_auth_enabled),
    // **局域网口令**（与公网 password 分开）：内网短数字好输、公网长随机串抗爆破。
    // 内网免密时后端返回空串（那时显示密码反而误导用户以为要输）。
    lanPassword: state.lan_password ?? "",
    // 是否是用户自定义的（自定义后开启公网不再自动轮换，界面要提示）
    lanPinCustom: Boolean(state.lan_pin_custom),
    // 局域网访问总开关（默认 true）。关掉后同一 WiFi 也进不来（公网不受影响）。
    lanEnabled: state.lan_enabled !== false,
    // 手动选定的网卡地址（空 = 自动按网卡评分选）
    lanIpOverride: state.lan_ip_override ?? "",
    // 候选地址（设置页「高级·手动选地址」的下拉框）
    lanCandidates: Array.isArray(state.lan_candidates) ? state.lan_candidates : [],
    // 地址提示（比如"选定的地址不在当前网卡上"）—— 不能静默吞掉
    lanNote: state.lan_note ?? null,
    startedAt: state.started_at ?? null,
    endpoints: [
      ...lanUrls.map((url, index) => ({
        key: `lan-${index}`, name: index === 0 ? "内网访问" : `内网访问 ${index + 1}`,
        url, path: "/", proxy_port: port, gui_port: null,
      })),
      ...(state.public_url
        ? [{ key: "public", name: "外网访问", url: state.public_url,
             path: "/", proxy_port: port, gui_port: null }]
        : []),
    ],
    // 「没在跑」是**正常状态**（用户自己停的也算），所以这里只陈述事实，
    // 不再写成「已停止或异常退出」那种报警口气 —— 设置页现在把它当普通说明显示。
    // 真正异常（找不到仓库、Python 不可用）走 ok:false 那条路，那里才是红色。
    // 用户点了「停止门户」时 portal_run.py 会写下 stopped_clean，那种情况
    // 连这句话都不用出：状态行已经写着「已停止」，再说一遍是噪音。
    problem: listening || state.stopped_clean
      ? null
      : `门户未在运行（端口 ${port} 没在监听）`,
    // 上一次是**主动停止**（而不是崩溃/被杀），设置页据此不再报红字
    stoppedClean: Boolean(state.stopped_clean),
    // 代码指纹：宿主进程只在 DSH 启动时读一次 lib/index.js，改完不重启 DSH
    // 它还是旧的。端到端检验（test_host_buttons.py）用它判断"我测的是当前这份
    // 代码吗"—— 不是就按纪律跳过并返回 2，而不是把一个过期的失败报成产品 bug。
    codeStamp: CODE_STAMP,
  };
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
  // 新门户优先：有 portal_state.json 就按门户形态报告
  const portal = await readPortalStatus(infraPath, repoPath, repo.portalPort);
  if (portal) return portal;

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
      password: null, passwordMode: null, endpoints: [], problem: null,
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
    // 只出口令，没有账号（登录页也只要口令）。
    password: cred.password ?? null,
    passwordMode: cred.password_mode ?? "random",
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

/**
 * 读出当前配置要用的口令形态，返回传给启动器的参数。
 *
 * 固定口令**绝不进命令行**（本机任何进程都能通过 Win32_Process 读到别人的
 * CommandLine）——写进基础设施仓库 runs/ 下一个临时文件，用 --password-file
 * 传路径；启动器读完即删。random 模式什么都不传，启动器自己生成。
 */
function passwordArgs(repo) {
  if (repo.passwordMode !== "fixed") return { argv: [], tempFile: null };
  const password = String(repo.fixedPassword || "").trim();
  if (!password) {
    return { argv: [], tempFile: null, error: "口令形态选了「固定口令」，但固定口令是空的" };
  }
  if (password.length < MIN_PASSWORD_LEN) {
    return {
      argv: [], tempFile: null,
      error: `固定口令至少 ${MIN_PASSWORD_LEN} 个字符（当前 ${password.length} 个）`,
    };
  }
  const dir = join(repo.infraPath, "runs");
  try {
    mkdirSync(dir, { recursive: true });
    const tempFile = join(dir, `.portal_password_${process.pid}.txt`);
    writeFileSync(tempFile, password + "\n", { encoding: "utf8", mode: 0o600 });
    return { argv: ["--password-mode", "fixed", "--password-file", tempFile], tempFile };
  } catch (error) {
    return { argv: [], tempFile: null, error: `无法写入固定口令临时文件：${error}` };
  }
}

/**
 * 只建隧道（门户进程已经在跑，不重启它）。
 *
 * 走门户自己的 `/_api/tunnel/start`：隧道的启动逻辑必须在**门户进程内**执行 ——
 * 那里才有 cloudflared 子进程的句柄与日志偏移量；插件另起一个 cloudflared
 * 会得到第二个域名，且门户不知道自己有隧道，状态永远显示「未开启」。
 */
async function startTunnelOnly(repo) {
  const port = Number(repo.portalPort) || DEFAULT_PORTAL_PORT;
  const endpoint = `http://127.0.0.1:${port}/_api/tunnel/start`;
  try {
    // 隧道握手最多等 75 秒（门户内部超时），这里给足余量
    const res = await fetch(endpoint, { method: "POST", signal: AbortSignal.timeout(110000) });
    const text = await res.text();
    let json = null;
    try { json = JSON.parse(text); } catch { /* 非 JSON */ }
    if (!json) return { ok: false, detail: `门户返回非 JSON（HTTP ${res.status}）：${text.slice(0, 200)}` };
    return {
      ok: json.ok === true && Boolean(json.public_url),
      detail: json.public_url || json.detail || json.error || "隧道未返回地址",
    };
  } catch (error) {
    return { ok: false, detail: `连不上门户进程（${endpoint}）：${error}` };
  }
}

/**
 * 关掉隧道（门户进程继续对内提供内网访问）。
 */
async function stopTunnelOnly(repo) {
  const port = Number(repo.portalPort) || DEFAULT_PORTAL_PORT;
  try {
    const res = await fetch(`http://127.0.0.1:${port}/_api/tunnel/stop`,
      { method: "POST", signal: AbortSignal.timeout(20000) });
    const text = await res.text();
    let json = null;
    try { json = JSON.parse(text); } catch { /* 非 JSON */ }
    return { ok: Boolean(json && json.ok), detail: json?.error ?? null };
  } catch (error) {
    return { ok: false, detail: String(error) };
  }
}

/**
 * 往门户进程的 `/_api/*` POST 一段 JSON，返回解析后的对象。
 *
 * 为什么要经过门户进程而不是插件直接改：局域网口令存在门户进程的 runtime 里
 * （认证层每个请求都从那里读，改完**立即生效**）。插件另起一份就变成了两处真相，
 * 而门户仍按旧口令校验 —— 表现为「设置页显示新口令，但手机上输它进不去」。
 */
async function postPortalJson(repo, path, payload) {
  const port = Number(repo.portalPort) || DEFAULT_PORTAL_PORT;
  const endpoint = `http://127.0.0.1:${port}${path}`;
  try {
    const res = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload ?? {}),
      signal: AbortSignal.timeout(30000),
    });
    const text = await res.text();
    let json = null;
    try { json = JSON.parse(text); } catch { /* 非 JSON */ }
    if (!json) {
      return { ok: false, error: `门户返回非 JSON（HTTP ${res.status}）：${text.slice(0, 200)}` };
    }
    return json;
  } catch (error) {
    return { ok: false, error: `连不上门户进程（${endpoint}）：${error}` };
  }
}

/** 读一小段 JSON 请求体（设置页发来的）。读失败返回 null，由调用方决定。 */
function readJsonBody(req, limit = 64 * 1024) {
  return new Promise((resolveBody) => {
    let size = 0;
    const chunks = [];
    req.on("data", (chunk) => {
      size += chunk.length;
      if (size > limit) { resolveBody(null); req.destroy(); return; }
      chunks.push(chunk);
    });
    req.on("end", () => {
      const text = Buffer.concat(chunks).toString("utf8").trim();
      if (!text) { resolveBody({}); return; }
      try { resolveBody(JSON.parse(text)); } catch { resolveBody(null); }
    });
    req.on("error", () => resolveBody(null));
  });
}

async function startPublic(repo, { singleDomain = true, lanOnly = false } = {}) {
  // python 取**宿主仓库**的（服务脚本与依赖都在那边），启动器在**基础设施仓库**。
  //
  // 用 usablePython 而不是 pythonFor：验证解释器**真的能写门户的 runs/**。
  // 本机 .venv313 / .runtime 的 python 带沙箱标记，能写宿主仓库的 runs，
  // 但写 dsh-service-portal/runs 会被拒 —— 用它起门户会「进程活着、端口在听、
  // 状态却一个都存不下」，设置页永远显示「未运行」。
  // 探测必须指向门户自己的 runs 目录，否则测出来的结论是错的。
  const picked = usablePython(repo.repoPath, repo.pythonPath,
    join(repo.infraPath, "runs"));
  const python = picked.python;
  // 新门户启动器（控制台形态）优先；没有它才回退到旧的 start_public_gui.py。
  const portal = portalScript(repo.infraPath);
  const usePortal = existsSync(portal);
  const script = usePortal ? portal : startScript(repo.infraPath);
  const argv = [python, "-X", "utf8", script];
  if (usePortal) {
    argv.push("--port", String(repo.portalPort || DEFAULT_PORTAL_PORT));
    if (repo.repoPath) argv.push("--host-repo", repo.repoPath);
    if (lanOnly) argv.push("--lan-only");
  } else {
    if (singleDomain) argv.push("--single-domain");
    // 若基础设施仓库提供了服务清单，显式传给启动器（否则它用内置默认清单）。
    const manifest = join(repo.infraPath, "services.json");
    if (existsSync(manifest)) argv.push("--services", manifest);
  }

  const pass = passwordArgs(repo);
  if (pass.error) {
    return {
      ok: false, exitCode: -3, stdout: "", stderr: pass.error,
      status: await readStatus(repo),
    };
  }
  argv.push(...pass.argv);

  const port = Number(repo.portalPort) || DEFAULT_PORTAL_PORT;
  const logFile = join(repo.infraPath, "runs", "portal_launch.log");

  // 门户已在跑时**不能一律提前返回** —— 这是实测踩到的坑：
  //   设置页「开启公网访问」走的就是这个 startPublic（lanOnly=false）。
  //   内网门户被 autoStart 起好之后，这里若直接 return already:true，
  //   调用方拿到 ok=true 却**永远等不到公网地址** —— 用户看到的是
  //   「点开启公网访问没反应」。
  // 正确做法分两种情况：
  //   · lanOnly（内网已开）-> 确实没事可做，直接返回；
  //   · 需要公网 -> 去把**隧道**建起来（门户进程本身不重启）。
  if (await portListening(port)) {
    if (lanOnly) {
      return {
        ok: true, exitCode: 0, already: true, stdout: "",
        stderr: "", status: await readStatus(repo),
      };
    }
    const tunnel = await startTunnelOnly(repo);
    return {
      ok: tunnel.ok, exitCode: tunnel.ok ? 0 : -4, already: true,
      stdout: tunnel.detail ? String(tunnel.detail) : "",
      stderr: tunnel.ok ? "" : String(tunnel.detail ?? "建立公网隧道失败"),
      status: await readStatus(repo),
    };
  }

  let result;
  try {
    // ⚠ 门户是**常驻进程**（前台 serve_forever），不会自己退出。
    //    早先这里 await runProcess(...) 等它结束 —— 结果是干等 240 秒，
    //    然后超时把它 kill 掉。现象就是「点了开启，等很久，然后什么都没有」。
    //    旧启动器（start_public_gui.py）起完就退，所以那时看不出这个问题。
    //
    // 正确做法：**分离启动**（detached），然后轮询端口是否真的在听 ——
    // 用「端口在听」而不是「进程退出码」判断成功，后者对常驻进程没有意义。
    result = await spawnDetached(argv, { cwd: repo.infraPath, logFile });
    if (!result.ok) {
      return {
        ok: false, exitCode: result.code ?? -1, stdout: "", stderr: result.error,
        status: await readStatus(repo),
      };
    }
    const up = await waitForPort(port, 45000);
    const status = await readStatus(repo);
    let tail = "";
    try { tail = readFileSync(logFile, "utf8").slice(-8000); } catch { /* 没日志 */ }
    // 解释器是坏的时候，即使端口起来了也不该报成功 —— 状态存不下就没法用
    const pythonWarning = picked.reason
      ? `\n\n[解释器警告] ${picked.reason}` : "";
    return {
      ok: up && status.running,
      exitCode: up ? 0 : -2,
      stdout: tail,
      stderr: (up ? "" : `门户进程已启动，但 ${port} 端口在 45 秒内没有开始监听。`
        + `日志见 ${logFile}`) + pythonWarning,
      status,
    };
  } finally {
    // 口令临时文件用完即删（无论成败），不留残余。
    if (pass.tempFile) {
      try { rmSync(pass.tempFile, { force: true }); } catch { /* ignore */ }
    }
  }
}

/**
 * 分离启动：进程不随插件走，插件也不等它退出。
 *
 * 输出重定向到日志文件（不用 pipe）—— 因为父进程不等它，pipe 缓冲区满了会让
 * 子进程写阻塞而卡死。
 */
function spawnDetached(argv, { cwd, logFile }) {
  return new Promise((resolveSpawn) => {
    let child;
    try {
      mkdirSync(dirname(logFile), { recursive: true });
      const out = openSync(logFile, "a");
      child = spawn(argv[0], argv.slice(1), {
        cwd, windowsHide: true, detached: true,
        stdio: ["ignore", out, out],
      });
    } catch (error) {
      resolveSpawn({ ok: false, code: -1, error: `无法启动门户进程：${error}` });
      return;
    }
    // 立刻解除父子关系：DSH 退出/重启不该带走门户，门户也不该拖住插件。
    child.once("error", (error) => resolveSpawn({
      ok: false, code: -1, error: `门户进程启动失败：${error}`,
    }));
    // spawn 成功即可（不是等它结束）—— 用 setImmediate 让 'error' 有机会先到。
    setImmediate(() => {
      try { child.unref(); } catch { /* ignore */ }
      resolveSpawn({ ok: true, code: 0, pid: child.pid });
    });
  });
}

/** 轮询端口直到开始监听（或超时）。常驻进程的「启动成功」只能这样判定。 */
function waitForPort(port, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolveWait) => {
    const tick = async () => {
      if (await portListening(port)) { resolveWait(true); return; }
      if (Date.now() >= deadline) { resolveWait(false); return; }
      setTimeout(tick, 400);
    };
    tick();
  });
}

/**
 * 请门户**自己退出**（POST /_api/shutdown，只允许本机发起）。
 *
 * 为什么不能只靠 `portal_run.py --stop`：实测在某些环境里，插件（DSH 宿主）
 * 派生出来的子进程与门户不在同一个作业/沙箱内 —— taskkill 直接回「找不到进程」
 * (128)，而门户明明还在 8899 上应答；那个子进程甚至写不进
 * `runs/portal_state.json`（Errno 13，Denied）。于是「停止」报成功、实际什么都没停。
 * 从宿主进程直接发 HTTP 是可靠的：宿主本来就连得上门户（状态探测、/qr 都走它）。
 */
async function askPortalShutdown(port, timeoutMs = 5000) {
  return new Promise((resolve) => {
    let done = false;
    const finish = (value) => {
      if (!done) {
        done = true;
        resolve(value);
      }
    };
    let req;
    try {
      req = http.request({
        host: "127.0.0.1", port, path: "/_api/shutdown", method: "POST",
        headers: { "Content-Length": "0" },
      }, (res) => {
        res.resume();
        finish(res.statusCode >= 200 && res.statusCode < 300);
      });
    } catch {
      finish(false);
      return;
    }
    req.setTimeout(timeoutMs, () => { req.destroy(); finish(false); });
    req.on("error", () => finish(false));
    req.end();
  });
}

async function stopPublic(repo) {
  const python = pythonFor(repo.repoPath, repo.pythonPath);
  const portal = portalScript(repo.infraPath);
  const script = existsSync(portal) ? portal : startScript(repo.infraPath);
  const port = Number(repo.portalPort) || DEFAULT_PORTAL_PORT;

  // ① 先请它自己退（对沙箱/作业隔离免疫）
  const asked = await askPortalShutdown(port);
  if (asked) {
    // 等端口真的松掉，别让用户"点了停止还显示运行中"
    for (let i = 0; i < 40; i += 1) {
      if (!(await portListening(port))) break;
      await new Promise((r) => setTimeout(r, 250));
    }
    if (!(await portListening(port))) {
      const status = await readStatus(repo);
      return {
        ok: true, stoppedBy: "self", exitCode: 0,
        stdout: "门户已自行退出（HTTP /_api/shutdown）", stderr: "", status,
      };
    }
  }

  // ② 兜底：`--stop`（本机直接跑、或门户不响应 HTTP 时清理残留进程）。
  // 显式带上端口：状态文件可能是旧的/写不进去，那时只能靠"这个端口上是不是
  // 我们的门户"来兜底清理。
  const result = await runProcess(
    [python, "-X", "utf8", script, "--stop", "--port", String(port)],
    { cwd: repo.infraPath, timeoutMs: 60000 });

  // ③ 事后核对，而且必须在**宿主这一侧**做。
  // 子进程那侧核对不了：实测它的 HTTP 探测连 127.0.0.1 都会失败、taskkill 还会
  // 回「找不到进程」(128)，于是它报"门户未在运行"、退出码 0 —— 假成功。
  // 宿主看得见端口（状态探测和 /qr 都靠它），所以就地问一句："还在听吗？"
  let still = await portListening(port);
  for (let i = 0; i < 8 && still; i += 1) {
    await new Promise((r) => setTimeout(r, 250));
    still = await portListening(port);
  }
  const status = await readStatus(repo);
  if (still) {
    // 点了停止却还在监听：绝不能回 ok=true —— 用户会以为已经关了
    return {
      ok: false,
      stoppedBy: asked ? "fallback" : "stop-command",
      exitCode: result.code,
      stdout: result.stdout.slice(-4000),
      stderr: [result.stderr.slice(-3600),
               `门户仍在 ${port} 端口上监听 —— 没有真正停掉`].filter(Boolean).join("\n"),
      status,
    };
  }
  return {
    ok: result.code === 0,
    stoppedBy: asked ? "fallback" : "stop-command",
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

function createHandler(getRepo, ctx) {
  return async (req, res) => {
    const url = new URL(req.url ?? "/", "http://127.0.0.1");
    const route = url.pathname.slice(API_PREFIX.length) || "/";
    const repo = getRepo();
    try {
      if (req.method === "GET" && (route === "/" || route === "/status")) {
        return sendJson(res, 200, await readStatus(repo));
      }
      if (req.method === "GET" && route === "/settings") {
        // 口令形态的设置：只回「模式 + 固定口令」，不回其他配置。
        return sendJson(res, 200, {
          ok: true,
          passwordMode: repo.passwordMode,
          fixedPassword: repo.fixedPassword,
          minPasswordLength: MIN_PASSWORD_LEN,
        });
      }
      if (req.method === "POST" && route === "/settings") {
        const body = await readBody(req);
        const payload = await saveSettings(ctx, body);
        return sendJson(res, payload.ok ? 200 : 400, payload);
      }
      if (req.method === "POST" && route === "/start") {
        const body = await readBody(req);
        // lanOnly 默认 false（用户在设置页点「开启」= 内网 + 外网）；
        // 自动启动那条路径传 lanOnly=true（只开内网，安全侧）。
        const payload = await startPublic(repo, {
          singleDomain: body.singleDomain !== false,
          lanOnly: body.lanOnly === true,
        });
        return sendJson(res, payload.ok ? 200 : 502, payload);
      }
      if (req.method === "GET" && route === "/qr") {
        // 设置页要显示二维码。二维码由门户进程生成（同一个实现，不重复造），
        // 插件这边只转发，避免两处 QR 逻辑漂移。
        const target = url.searchParams.get("url") || "";
        const payload = await fetchPortalQr(repo, target);
        return sendJson(res, payload.ok ? 200 : 502, payload);
      }
      if (req.method === "POST" && route === "/stop") {
        const payload = await stopPublic(repo);
        return sendJson(res, payload.ok ? 200 : 502, payload);
      }
      // 公网隧道单独控制：门户（内网）继续跑，只拨/收隧道。
      // 设置页的「关闭公网」走这里 —— 它不该顺带把内网访问也停掉。
      if (req.method === "POST" && route === "/tunnel/start") {
        const payload = await startTunnelOnly(repo);
        return sendJson(res, payload.ok ? 200 : 502, payload);
      }
      if (req.method === "POST" && route === "/tunnel/stop") {
        const payload = await stopTunnelOnly(repo);
        return sendJson(res, payload.ok ? 200 : 502, payload);
      }
      // 局域网口令的刷新 / 自定义：由门户进程执行（口令在它内存里，改完立即生效，
      // 不重启门户 —— 重启会换掉隧道域名，代价太大）。
      if (req.method === "POST" && route === "/lan-pin/refresh") {
        const payload = await postPortalJson(repo, "/_api/lan-pin/refresh", {});
        return sendJson(res, payload.ok ? 200 : 502, payload);
      }
      if (req.method === "POST" && route === "/lan-pin/custom") {
        const body = await readJsonBody(req);
        const payload = await postPortalJson(repo, "/_api/lan-pin/custom",
          { value: body?.value ?? "" });
        return sendJson(res, payload.ok ? 200 : 400, payload);
      }
      return sendJson(res, 404, { error: `unknown route ${route}` });
    } catch (error) {
      return sendJson(res, 500, { error: String(error?.stack ?? error) });
    }
  };
}

/**
 * 向门户进程要一张二维码（设置页显示用）。
 *
 * 门户只为本门户自己的地址出二维码（它内部有白名单校验），插件这边只做转发。
 */
async function fetchPortalQr(repo, target) {
  if (!target) return { ok: false, error: "缺少 url 参数" };
  const port = Number(repo.portalPort) || DEFAULT_PORTAL_PORT;
  const endpoint = `http://127.0.0.1:${port}/_api/qr?url=${encodeURIComponent(target)}`;
  try {
    const res = await fetch(endpoint, { method: "GET" });
    const text = await res.text();
    let json = null;
    try { json = JSON.parse(text); } catch { /* 非 JSON */ }
    if (!json) return { ok: false, error: `门户返回非 JSON（HTTP ${res.status}）` };
    return json;
  } catch (error) {
    return { ok: false, error: `连不上门户进程：${error}` };
  }
}

/**
 * 写入口令形态设置（走 DSH 的 configEditor，持久化到 profile 的 patch 层）。
 *
 * 校验必须在**写之前**做：把 11 字符的口令存进配置，下次点「开启」才报错，
 * 那就是「不崩但给错误答案」——启动会失败，用户却不知道为什么。
 */
async function saveSettings(ctx, body) {
  const requested = body?.passwordMode === "fixed" ? "fixed" : "random";
  const fixedPassword = String(body?.fixedPassword ?? "").trim();
  if (requested === "fixed") {
    if (!fixedPassword) {
      return { ok: false, error: "选了固定口令就必须填口令" };
    }
    if (fixedPassword.length < MIN_PASSWORD_LEN) {
      return {
        ok: false,
        error: `固定口令至少 ${MIN_PASSWORD_LEN} 个字符（当前 ${fixedPassword.length} 个）`,
      };
    }
  }

  const editor = ctx?.get?.("configEditor") ?? ctx?.configEditor;
  if (!editor) {
    return { ok: false, error: "当前环境没有 configEditor，无法保存设置" };
  }
  // 找到本插件自己的 Loader 条目（按名字精确匹配，不碰别的插件）
  const entry = editor.entries().find((row) => row?.options?.name === name
    || row?.name === name);
  if (!entry) {
    return { ok: false, error: `找不到插件 ${name} 的配置条目` };
  }
  await editor.edit(entry, (current) => Object.assign({}, current, {
    passwordMode: requested,
    fixedPassword: requested === "fixed" ? fixedPassword : "",
  }));
  return { ok: true, passwordMode: requested };
}

// ---------------------------------------------------------------- apply

/**
 * 门户进程的「默认自动启动」。
 *
 * 为什么要自动起：参照 dsh-pocket 的「装好即用」——插件加载后设置页一打开就该看到
 * 内网地址与二维码可直接扫。之前要用户先点一次「开启门户」才有东西，体验对不上。
 *
 * 默认**只开内网、不建隧道**（安全侧）：外网暴露是一件应该由用户显式决定的事，
 * 不能因为装了插件就自动把本机服务挂到公网。要外网仍由用户点「开启外网访问」。
 *
 * 幂等：门户已在跑（状态文件 + 端口在听）就什么都不做，不重复起进程。
 */
async function ensurePortal(repo) {
  if (!existsSync(portalScript(repo.infraPath))) {
    return { ok: false, skipped: true, reason: "找不到 tools/portal_run.py" };
  }
  const status = await readPortalStatus(repo.infraPath, repo.repoPath, repo.portalPort);
  if (status && status.running) {
    return { ok: true, already: true, status };
  }
  const payload = await startPublic(repo, { lanOnly: true });
  return { ok: Boolean(payload?.ok), already: false, payload };
}

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
      handler: createHandler(getRepo, ctx),
    });
    ctx.logger?.info?.(`[service-portal] 已挂载 ${API_PREFIX}`);

    // 自动起门户（只开内网）。失败不能拖垮 DSH 启动：只记日志，
    // 用户仍可在设置页点「开启门户」看到具体原因。
    if (repo.autoStart) {
      Promise.resolve()
        .then(() => ensurePortal(getRepo()))
        .then((result) => {
          if (result?.ok && !result.already) {
            ctx.logger?.info?.("[service-portal] 已自动启动门户（内网）");
          } else if (result?.already) {
            ctx.logger?.info?.("[service-portal] 门户已在运行，跳过自动启动");
          } else if (result && !result.ok) {
            ctx.logger?.warn?.(
              `[service-portal] 自动启动门户失败：${result.reason || result.payload?.stderr || "未知原因"}`);
          }
        })
        .catch((error) => {
          ctx.logger?.warn?.(`[service-portal] 自动启动门户异常：${error}`);
        });
    }

    return dispose;
  });
}

// 供测试直接调用（不经过 HTTP）。
export const _internals = {
  configOf, pythonFor, usablePython, readStatus, readPortalStatus, startPublic,
  stopPublic, startTunnelOnly, stopTunnelOnly, portListening, passwordArgs,
  MIN_PASSWORD_LEN, ensurePortal, askPortalShutdown,
};
