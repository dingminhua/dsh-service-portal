// 用 Chrome DevTools Protocol 真正点一次门户页上的「测试」按钮，看它是不是真的工作。
//
// 为什么非要做这件事：这一版新增的核心能力是**前端 JS 探活**（fetch -> 读状态码 ->
// 就地写结论）。只断言"页面里有 data-probe 属性"是假检验 —— 属性在、JS 报错，
// 照样绿。这个脚本用真实 Chrome 打开真实门户页，真实点一下按钮，然后把结果框里
// 的**最终文本**读回来，逐字核对。
//
// 只依赖 Node 内置能力（node:http / WebSocket / fetch），不装任何第三方包。
//
// 用法：
//   node tools/probe_button_e2e.mjs --url http://127.0.0.1:PORT/ --port PORT

const args = process.argv.slice(2);
const getArg = (name, dflt) => {
  const i = args.indexOf(name);
  return i >= 0 && args[i + 1] ? args[i + 1] : dflt;
};
const URL_ = getArg("--url", "http://127.0.0.1:8899/");
const CDP_PORT = Number(getArg("--cdp-port", "9333"));

// 浏览器可执行文件：--chrome 优先，其次 $CHROME，再次按平台找常见安装位置。
// 这里原本写死 "C:\Program Files\Google\Chrome\Application\chrome.exe" ——
// 只有作者的 Windows 机器成立，与本仓库 tools/shoot_portal.py 是同一类问题，
// 两处现在都按平台探测（优先级一致）。本文件是 ESM，用 dynamic import。
async function findChrome() {
  const fs = await import("node:fs");
  const path = await import("node:path");
  const env = process.env.CHROME;
  if (env && fs.existsSync(env)) return env;
  const candidates = process.platform === "darwin"
    ? [
      "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
      "/Applications/Chromium.app/Contents/MacOS/Chromium",
      "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ]
    : process.platform === "win32"
      ? [
        path.join(process.env.ProgramFiles || "C:\\Program Files",
          "Google\\Chrome\\Application\\chrome.exe"),
        path.join(process.env["ProgramFiles(x86)"] || "C:\\Program Files (x86)",
          "Google\\Chrome\\Application\\chrome.exe"),
        path.join(process.env.LOCALAPPDATA || "",
          "Google\\Chrome\\Application\\chrome.exe"),
      ]
      : ["/usr/bin/google-chrome", "/usr/bin/chromium",
        "/usr/bin/chromium-browser", "/snap/bin/chromium"];
  return candidates.find((p) => p && fs.existsSync(p)) || null;
}

const CHROME = getArg("--chrome", await findChrome());
if (!CHROME) {
  console.error("找不到无头浏览器。用 --chrome 指定可执行文件，或设环境变量 CHROME。");
  process.exit(2);
}

const { spawn } = await import("node:child_process");
const os = await import("node:os");
const fs = await import("node:fs");
const path = await import("node:path");

const failures = [];
const check = (name, ok, detail = "") => {
  if (!ok) failures.push(name);
  console.log((ok ? "PASS  " : "FAIL  ") + name + (detail ? " —— " + detail : ""));
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const profile = fs.mkdtempSync(path.join(os.tmpdir(), "cdp-"));
const chrome = spawn(
  CHROME,
  [
    "--headless=new",
    "--disable-gpu",
    "--no-sandbox",
    `--remote-debugging-port=${CDP_PORT}`,
    `--user-data-dir=${profile}`,
    "about:blank",
  ],
  { stdio: "ignore" },
);

let ws;
let nextId = 1;
const pending = new Map();
const send = (method, params = {}) =>
  new Promise((resolve, reject) => {
    const id = nextId++;
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params }));
  });

const consoleErrors = [];

async function main() {
  // 等 CDP 起来
  let target = null;
  for (let i = 0; i < 100; i += 1) {
    try {
      const res = await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`);
      const list = await res.json();
      target = list.find((t) => t.type === "page");
      if (target && target.webSocketDebuggerUrl) break;
    } catch {
      /* 还没起来 */
    }
    await sleep(200);
  }
  if (!target) throw new Error("连不上 Chrome 的调试端口");

  ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    ws.addEventListener("open", resolve, { once: true });
    ws.addEventListener("error", reject, { once: true });
  });
  ws.addEventListener("message", (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      if (msg.error) reject(new Error(JSON.stringify(msg.error)));
      else resolve(msg.result);
      return;
    }
    if (msg.method === "Runtime.consoleAPICalled" && msg.params.type === "error") {
      consoleErrors.push(
        (msg.params.args || []).map((a) => a.value || a.description).join(" "),
      );
    }
    if (msg.method === "Runtime.exceptionThrown") {
      consoleErrors.push(
        msg.params.exceptionDetails?.exception?.description || "uncaught",
      );
    }
  });

  await send("Page.enable");
  await send("Runtime.enable");
  await send("Page.navigate", { url: URL_ });
  await sleep(2500);

  const evalJs = async (expr) => {
    const r = await send("Runtime.evaluate", {
      expression: expr,
      returnByValue: true,
      awaitPromise: true,
    });
    if (r.exceptionDetails) {
      throw new Error(
        r.exceptionDetails.exception?.description || "页面里抛异常了",
      );
    }
    return r.result.value;
  };

  // ① 按钮真的挂上事件了吗（点之前先看 DOM）
  const nProbe = await evalJs(
    `document.querySelectorAll(".probe").length`,
  );
  check("页面上有测试按钮", nProbe >= 1, `count=${nProbe}`);

  const nBox = await evalJs(`document.querySelectorAll(".result").length`);
  check("每个按钮配一个结果框", nBox === nProbe, `result=${nBox} probe=${nProbe}`);

  // 结果框初始应是隐藏的（无 JS 时不打扰阅读）
  const hiddenBefore = await evalJs(
    `(function(){var b=document.querySelector(".result");`
      + `return b?b.hasAttribute("hidden"):null;})()`,
  );
  check("结果框初始是隐藏的", hiddenBefore === true, `hidden=${hiddenBefore}`);

  // ② **真点一次**第一个可用的测试按钮
  //    注意：被屏蔽节点的按钮是 disabled 的，点了也不该有反应 —— 先按这个区分。
  const clicked = await evalJs(
    `(function(){
       var btns=[].slice.call(document.querySelectorAll(".probe"));
       var live=btns.filter(function(b){return !b.disabled;})[0];
       if(!live) return null;
       var name=live.getAttribute("data-name");
       var card=live.closest(".card");
       live.click();
       return {name:name, path:live.getAttribute("data-probe")};
     })()`,
  );
  check("存在可点的测试按钮（未屏蔽的节点）", !!clicked,
        clicked ? `节点=${clicked.name} 路径=${clicked.path}` : "全是禁用");

  if (clicked) {
    // 等结果落定（按钮文字恢复 = 请求结束）
    let text = "";
    for (let i = 0; i < 60; i += 1) {
      await sleep(250);
      text = await evalJs(
        `(function(){
           var btns=[].slice.call(document.querySelectorAll(".probe"));
           var live=btns.filter(function(b){return !b.disabled;})[0];
           var box=document.querySelector(".result");
           return (box && !box.hasAttribute("hidden")) ? box.textContent : "";
         })()`,
      );
      if (text && !/正在通过门户请求/.test(text)) break;
    }
    check("点「测试」后结果框显示了内容", !!text, JSON.stringify(text).slice(0, 200));
    check("结果里带真实 HTTP 状态码（说明请求真发生了）",
          /HTTP\s*\d{3}/.test(text), text.slice(0, 160));
    check("结果是可执行的结论（通/不通），不是干巴巴的状态码",
          /(通了|不通|上游|拒绝|失败)/.test(text), text.slice(0, 160));
    // 结果框的 class 应当落成 ok / bad
    const klass = await evalJs(
      `(function(){var b=document.querySelector(".result");return b?b.className:"";})()`,
    );
    check("结果框带 ok/bad 语义类（颜色能对上）",
          /\b(ok|bad)\b/.test(klass), klass);
  }

  // ②b **逐个点完每张卡的测试按钮**，把每个节点的结论都收回来。
  //     只点第一个是不够的："上游没起"和"上游自己 502"给的文案必须不同，
  //     而那两张卡在后面。这里按 data-name 逐一记录结论。
  const perNode = {};
  const names = await evalJs(
    `[].slice.call(document.querySelectorAll(".probe"))
       .filter(function(b){return !b.disabled;})
       .map(function(b){return b.getAttribute("data-name");})`,
  );
  for (let i = 0; i < names.length; i += 1) {
    const name = names[i];
    await evalJs(
      `(function(){
         var b=[].slice.call(document.querySelectorAll(".probe"))
           .filter(function(x){return !x.disabled;})[${i}];
         if(b) b.click();
       })()`,
    );
    let txt = "";
    for (let k = 0; k < 60; k += 1) {
      await sleep(250);
      txt = await evalJs(
        `(function(){
           var b=[].slice.call(document.querySelectorAll(".probe"))
             .filter(function(x){return !x.disabled;})[${i}];
           if(!b) return "";
           var box=b.closest(".card").querySelector(".result");
           return (box && !box.hasAttribute("hidden")) ? box.textContent : "";
         })()`,
      );
      if (txt && !/正在通过门户请求/.test(txt)) break;
    }
    perNode[name] = txt;
  }
  console.log("      各节点结论：" + JSON.stringify(perNode, null, 0));
  const liveText = perNode["活的"] || "";
  const deadText = perNode["死的"] || "";
  const boomText = perNode["自崩的"] || "";
  check("「活的」判通（说通了 + 200）",
        /通了/.test(liveText) && /200/.test(liveText), liveText.slice(0, 120));
  check("「死的」判不通，并提示去启动上游（不是只甩状态码）",
        /不通/.test(deadText) && /(启动|上游)/.test(deadText),
        deadText.slice(0, 140));
  check("「死了的」文案与「自崩的」文案**不同**（别把上游自己的错冤枉成没启动）",
        deadText !== boomText && !!boomText, boomText.slice(0, 140));
  check("「自崩的」指向上游自己出的问题，不说成「没启动」",
        /上游/.test(boomText) && !/请用它自己的方式启动/.test(boomText),
        boomText.slice(0, 140));

  // ③ 被屏蔽的节点：按钮禁用，且点了不产生结果
  const offState = await evalJs(
    `(function(){
       var btns=[].slice.call(document.querySelectorAll(".probe"));
       var off=btns.filter(function(b){return b.disabled;})[0];
       if(!off) return {exists:false};
       var card=off.closest(".card");
       var box=card.querySelector(".result");
       return {exists:true, hiddenBefore:box.hasAttribute("hidden")};
     })()`,
  );
  check("被屏蔽节点的测试按钮是禁用的", offState.exists === true,
        JSON.stringify(offState));

  // ④ 页面上不该有 JS 报错（我刚才写的内联脚本必须干净）
  check("页面没有 JS 报错", consoleErrors.length === 0,
        consoleErrors.slice(0, 3).join(" | "));

  // ⑤ 复制按钮也在（不点，避免动用户剪贴板；只确认挂上了）
  const nCopy = await evalJs(`document.querySelectorAll(".copy").length`);
  check("复制按钮都在", nCopy >= 1, `count=${nCopy}`);

  // ⑥ 鼓励一下链接指向仓库
  const credit = await evalJs(
    `(function(){var a=document.querySelector("a.credit");
       return a?{href:a.href,rel:a.rel}:null;})()`,
  );
  check("「鼓励一下」是外链且带 noopener",
        credit && /github\.com\/dingminhua\/dsh-service-portal/.test(credit.href)
          && /noopener/.test(credit.rel),
        JSON.stringify(credit));

  console.log("");
  if (failures.length) {
    console.log(`「测试」按钮真机端到端失败：${failures.length} 项`);
    failures.forEach((f) => console.log("  - " + f));
    return 1;
  }
  console.log("「测试」按钮真机端到端全部通过");
  return 0;
}

let code = 1;
try {
  code = await main();
} catch (err) {
  console.log("异常：" + (err && err.message ? err.message : err));
  code = 1;
} finally {
  try {
    ws?.close();
  } catch {
    /* ignore */
  }
  try {
    chrome.kill();
  } catch {
    /* ignore */
  }
  await sleep(300);
  try {
    fs.rmSync(profile, { recursive: true, force: true });
  } catch {
    /* ignore */
  }
}
process.exit(code);
