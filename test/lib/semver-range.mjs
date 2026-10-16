// 极简 semver 判定器 —— 只认本仓库 peer 范围实际使用的语法。
//
// 为什么不直接 require("semver")：本仓库不引入任何测试依赖（CI 只装 schemastery + 系统 Node），
// 而 npm 自带的那份 semver 在不同 Node 发行版里路径不一致，靠它会让检验结果随环境漂移。
//
// 为什么不用正则「看起来像」就放行：那样写对正则、行为仍然错也能绿。这里真算一遍。
//
// **认不出的语法一律抛错**（`^`、`~`、`x` 通配、不完整版本号如 "4"、前导零如 "01.2.3"）——
// 宁可炸，也不要在一个自己没读懂的范围上假装通过。这正是本仓库
// 「依赖缺失必须跳过并返回 2，不得静默通过」的同一条纪律。
//
// 前导零为什么要单独卡：`01.2.3` / `1.2.3-alpha.01` 在 semver 里是**非法**的，
// node-semver 一律判 false；而正则 `\d+` 会放行、`Number()` 又会把 `"01"` 悄悄吃掉，
// 于是本判定器会给出一个**静默的错答案**。非法输入必须抛，不能假装算出来了。

const FULL = /^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$/;

/** semver 规定：数字标识符不得有前导零（"0" 本身除外）。 */
function hasLeadingZero(id) {
  return id.length > 1 && id[0] === "0";
}

function parse(v, where) {
  const s = String(v).trim();
  const m = FULL.exec(s);
  if (!m) {
    throw new Error(
      `不支持的版本写法：${JSON.stringify(s)}（${where}）—— ` +
      `本判定器只认完整的 x.y.z[-pre]；遇到新语法请在此实现，不要静默放过`);
  }
  // 主版本三段：数字段不得有前导零
  for (const seg of [m[1], m[2], m[3]]) {
    if (hasLeadingZero(seg)) {
      throw new Error(
        `非法的版本写法：${JSON.stringify(s)}（${where}）—— ` +
        `数字标识符不得有前导零（semver 规定；node-semver 会判它无法解析）。` +
        `不要静默当成合法版本算下去`);
    }
  }
  // 预发布段：逐个标识符查，数字型同样不得有前导零
  const pre = m[4] ?? null;
  if (pre !== null) {
    for (const id of pre.split(".")) {
      if (/^\d+$/.test(id) && hasLeadingZero(id)) {
        throw new Error(
          `非法的版本写法：${JSON.stringify(s)}（${where}）—— ` +
          `预发布里的数字标识符 ${JSON.stringify(id)} 有前导零，semver 不允许`);
      }
    }
    if (pre.split(".").some((id) => id === "")) {
      throw new Error(`非法的版本写法：${JSON.stringify(s)}（${where}）—— 预发布段有空标识符`);
    }
  }
  return { nums: [Number(m[1]), Number(m[2]), Number(m[3])], pre, raw: s };
}

function cmpPre(a, b) {
  const A = a.split("."), B = b.split(".");
  for (let i = 0; i < Math.max(A.length, B.length); i++) {
    const x = A[i], y = B[i];
    if (x === undefined) return -1;          // 段数少的更小：1.0.0-alpha < 1.0.0-alpha.1
    if (y === undefined) return 1;
    const xn = /^\d+$/.test(x), yn = /^\d+$/.test(y);
    if (xn && yn) { if (+x !== +y) return +x < +y ? -1 : 1; }
    else if (xn) return -1;                  // 数字段 < 字母段
    else if (yn) return 1;
    else if (x !== y) return x < y ? -1 : 1;
  }
  return 0;
}

export function cmp(a, b) {
  const A = parse(a, "待比较版本"), B = parse(b, "范围里的版本");
  for (let i = 0; i < 3; i++) if (A.nums[i] !== B.nums[i]) return A.nums[i] < B.nums[i] ? -1 : 1;
  if (A.pre === B.pre) return 0;
  if (A.pre === null) return 1;              // 正式版 > 同元组的预发布版
  if (B.pre === null) return -1;
  return cmpPre(A.pre, B.pre);
}

const sameTuple = (a, b) => {
  const A = parse(a, "版本"), B = parse(b, "范围");
  return A.nums.join(".") === B.nums.join(".");
};

const COMPARATOR = /^(>=|<=|>|<|=)?(\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)$/;

function parseComparatorSet(set) {
  const comps = set.trim().split(/\s+/).filter(Boolean);
  if (comps.length === 0) throw new Error("peer 范围里有空的 || 分支");
  return comps.map((c) => {
    const m = COMPARATOR.exec(c);
    if (!m) {
      throw new Error(
        `不支持的比较符写法：${JSON.stringify(c)} —— ` +
        `本项目只用 ">=A <B" 形式的 || 分支（contributing.md 的预发布分支写法）`);
    }
    return { op: m[1] || "=", ver: m[2] };
  });
}

export function satisfies(version, range) {
  const vp = parse(version, "被测版本");
  for (const set of String(range).split("||")) {
    const comps = parseComparatorSet(set);
    const inRange = comps.every(({ op, ver }) => {
      const d = cmp(version, ver);
      if (op === ">=") return d >= 0;
      if (op === "<=") return d <= 0;
      if (op === ">") return d > 0;
      if (op === "<") return d < 0;
      return d === 0;
    });
    if (!inRange) continue;

    // node-semver 的预发布规则：带预发布标签的版本，只有当前分支里存在一个
    // 「同 major.minor.patch 元组、且自身带预发布标签」的比较符时才放行。
    if (vp.pre !== null) {
      const anchored = comps.some(({ ver }) => {
        const rp = parse(ver, "范围");
        return sameTuple(version, ver) && rp.pre !== null;
      });
      if (!anchored) continue;
    }
    return true;
  }
  return false;
}
