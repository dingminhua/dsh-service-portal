import { createServer } from "node:http";
import { apply } from "../lib/index.js";

// 模拟宿主 webServer：捕获插件注册的路由，用真实 HTTP 驱动它
const routes = [];
const ctx = {
  logger: { info: () => {} },
  inject: (deps, fn) => fn({
    webServer: { register: (route) => { routes.push(route); return () => {}; } },
  }),
};
apply(ctx, { repoPath: "D:\\DshProject\\ld-rl-poker", pythonPath: "", webEnabled: true });
if (routes.length !== 1) { console.log("FAIL: 期望 1 个路由，得到 " + routes.length); process.exit(1); }

const route = routes[0];
const server = createServer((req, res) => {
  const path = new URL(req.url, "http://127.0.0.1").pathname;
  if (path.startsWith(route.path)) return route.handler(req, res);
  res.writeHead(404).end("no route");
});

await new Promise((r) => server.listen(0, "127.0.0.1", r));
const port = server.address().port;
const base = `http://127.0.0.1:${port}${route.path}`;

async function probe(label, path, method = "GET") {
  const res = await fetch(base + path, { method });
  let body = await res.text();
  let short = body.replace(/\s+/g, " ").slice(0, 110);
  console.log(`  ${String(res.status).padEnd(4)} ${method.padEnd(5)} ${path.padEnd(22)} ${short}`);
  return { status: res.status, body };
}

console.log("路由 =", route.kind, route.path);
console.log("\n=== 真实 HTTP 探测 ===");
const a = await probe("status", "/status");
const b = await probe("bare", "");
const c = await probe("unknown", "/nonexistent");
const d = await probe("GET start", "/start", "GET");

// 断言：正反例必须可区分
const json = JSON.parse(a.body);
const checks = [
  ["status 返回 200", a.status === 200],
  ["status 带 ok 字段", typeof json.ok === "boolean"],
  ["status 能读到仓库（真实仓库存在）", json.ok === true],
  ["status 带 running 布尔", typeof json.running === "boolean"],
  ["裸 api 等同 status", b.status === 200],
  ["未知子路径 404", c.status === 404],
  ["GET /start 不被当启动", d.status === 404],
];
console.log("\n=== 断言 ===");
let bad = 0;
for (const [name, ok] of checks) { console.log(`  ${ok ? "PASS" : "FAIL"} ${name}`); if (!ok) bad++; }
console.log(`\n仓库识别: repoPath=${json.repoPath}`);
console.log(`当前状态: running=${json.running} mode=${json.mode ?? "(未启动)"} password=${json.password ? "(已设置)" : "(无)"}`);
server.close();
process.exit(bad ? 1 : 0);
