import { createServer } from "node:http";
import { apply, _internals } from "../lib/index.js";

const routes = [];
const ctx = {
  logger: { info: () => {} },
  inject: (deps, fn) => fn({ webServer: { register: (r) => { routes.push(r); return () => {}; } } }),
};
const repo = { repoPath: "D:\\DshProject\\ld-rl-poker", pythonPath: "", webEnabled: true };
apply(ctx, repo);
const route = routes[0];

const server = createServer((req, res) => {
  const path = new URL(req.url, "http://127.0.0.1").pathname;
  if (path.startsWith(route.path)) return route.handler(req, res);
  res.writeHead(404).end("no route");
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const base = `http://127.0.0.1:${server.address().port}${route.path}`;

async function call(path, method = "GET") {
  const res = await fetch(base + path, { method });
  const text = await res.text();
  let json = null;
  try { json = JSON.parse(text); } catch {}
  return { status: res.status, json };
}

console.log("=== 步骤1：停掉现有入口 ===");
let r = await call("/stop", "POST");
console.log(`  HTTP ${r.status}  ok=${r.json?.ok}  running=${r.json?.status?.running}`);
await new Promise((s) => setTimeout(s, 1500));

let st = await call("/status");
console.log(`  停止后 status.running = ${st.json?.running}  (期望 false)`);
const stopOk = st.json?.running === false;

console.log("\n=== 步骤2：通过插件 API 启动（真实调起脚本+隧道）===");
r = await call("/start", "POST");
console.log(`  HTTP ${r.status}  ok=${r.json?.ok}  exitCode=${r.json?.exitCode}`);
const status = r.json?.status;
console.log(`  running=${status?.running}  mode=${status?.mode}`);
console.log(`  baseUrl=${status?.baseUrl}`);
console.log(`  username=${status?.username}`);
console.log(`  口令长度=${status?.password?.length}`);
for (const e of status?.endpoints ?? []) {
  console.log(`    /${String(e.path ?? e.key).replace(/^\/|\/$/g, "")} -> ${e.url}`);
}

console.log("\n=== 步骤3：断言 ===");
const checks = [
  ["停止后 running=false", stopOk],
  ["启动返回 ok", r.json?.ok === true],
  ["启动后 running=true", status?.running === true],
  ["拿到 base_url", typeof status?.baseUrl === "string" && status.baseUrl.startsWith("https://")],
  ["拿到用户名", status?.username === "poker"],
  ["拿到口令(>=16)", (status?.password?.length ?? 0) >= 16],
  ["拿到至少一个端点", (status?.endpoints?.length ?? 0) >= 1],
];
let bad = 0;
for (const [n, ok] of checks) { console.log(`  ${ok ? "PASS" : "FAIL"} ${n}`); if (!ok) bad++; }
if (r.json?.stdout) { console.log("\n--- 脚本输出 ---"); console.log(r.json.stdout.split("\n").slice(-14).join("\n")); }
server.close();
process.exit(bad ? 1 : 0);
