# Changelog

## 1.0.5 (2026-10-24)

**跟随宿主升级：DSH 0.2.1-rc.3（正式版 `DeepSeek Harness.app`）。**

宿主从 `DSH NEXT.app`（夜间构建）换成正式版 **0.2.1-rc.3**。结论先说：
**插件代码一行不用改**，但宿主重建 profile 清单时把这条 bundle 从
`dsh.profile.bundles` 里漏掉了 —— 于是插件**整体没加载**，而且**不报任何错**。

### 这次的实际故障：插件静默消失（不是代码坏了）

宿主升级后本插件在运行时里**根本不存在**：

- 宿主的插件清单里查不到 `dsh-service-portal`（`Config` 无条目、`plugin list` 无行）；
- 客户端两个槽位（`plugins.bundle.config` / `plugins.row.config`）里没有本插件的注册；
- `GET /service-portal/api/status` 连路由都不存在。

根因不在插件里，在宿主的 profile 组装规则：宿主**只加载 `dsh.profile.bundles`
名单里的 bundle**（`~/.dsh/profiles/desktop/package.json`）。
`dependencies` 里装着 ≠ 会加载。而 `dsh plugin add` 只是 pnpm 的包装，
**只写 dependencies，不碰 bundles** —— 所以"装过"和"被加载"是两件事。

处理：用宿主自己的插件管理器把这条 bundle 重新打开（`set_bundle`），
它会写回 `dsh.profile.bundles` 并立刻生效。修复后实测：

| 检查项 | 结果 |
| :--- | :--- |
| 宿主 `Config` 条目 | `include:dsh-service-portal`（status: schema） |
| 客户端槽位 | `plugins.bundle.config` / `plugins.row.config` 各两条（裸名 + `include:` 前缀两种拼写） |
| `GET /service-portal/api/status` | 200，返回真实状态（门户在跑、pid、内网地址、口令形态、前置条件检测） |
| `GET /service-portal/api/qr?url=<内网地址>` | 200，返回二维码 data URI |
| `npm test` | 134 通过 / 0 失败 |
| `test/manifest.test.mjs`（对着 rc.3 真实运行时） | 10/10 通过 |

### 宿主 rc.3 的改动与本插件的关系

rc.2 → rc.3 的改动集中在：导航/面板入口自定义（新增 `ui-entry-customization`
客户端包与 `conversation.session.header.views.actions`、`sidebar.panellist.actions`、
`sidebar.right.tab.guide.actions` 三个新槽位）、导航/预设埋点、DeepSeek API Key 的
`/models` 列表路由、UI 基础组件的 Menu/Tooltip 调整。

本插件用到的接口**一个都没变**：

| 插件用到的 | rc.3 现状 |
| :--- | :--- |
| `plugins.bundle.config` / `plugins.row.config` 槽位注册契约 | 未变（catalog 只新增了会话/侧栏侧的槽位） |
| `webServer.register({kind:'prefix', path, handler})` | 未变（`dsh-host-webserver` 的路由契约一致） |
| `Config`（schemastery `z.object` + `volatile()`） | 未变 |
| `dsh.client` 清单字段（`platform: web` + `exports["./client"]`） | 未变 |
| `engines.dsh` 版本门禁 | 未变（rc.3 判定本插件相容） |

所以本版本**没有代码改动**，只有安装/启用流程的说明与防呆。

### 修复：口令形态在摘要行说反了（状态里恒为 null）

门户的状态文件（`runs/portal_state.json`）**根本不写** `password_mode`（写它的只有
旧启动器），于是 `/status` 里的 `passwordMode` 恒为 `null`。而口令形态的权威在
**插件自己的 Config**（`POST /settings` 改的是它，门户只管局域网那三项）——
`/settings` 接口一直返回正确的形态，`/status` 却不返回。

后果：用户把形态改成「固定口令」，插件页的摘要行仍显示「随机口令」，
**一句和真实状态相反的话**。

修法：`/status` 在门户形态那条路径上兜底到配置
（`portal.passwordMode ?? repo.passwordMode ?? "random"`），并补了 2 条检验
（正例：配置 fixed → 状态 fixed；反例：配置缺失 → 兜底 random 而不是 null）。

> 注意：这一改在**宿主端**，需要插件重新加载后生效（重启 DSH，或在「插件」面板
> 里把它关一次再开）；宿主端代码的热替换不在插件这一侧的控制范围内。

### 对齐宿主的插件显示元数据契约（locale 词典）

宿主读插件的标题/简介**只认两个来源**：`<包名>/locale/en.json` 起的词典，
以及清单里的 `name` / `description` / `icon` —— 它**不读** `displayName`。
本插件此前没有 locale 词典，于是插件页的标题会退化成包名 `dsh-service-portal`，
简介永远是中文那一段（英文界面下也是中文）。

按同族插件（workbuddy / qoder / trae）的做法补上：

- 新增 `locale/en.json`（英文标题与简介）与 `locale/zh.json`（中文）；
- `package.json` 的 `exports` 增加 `"./locale/*.json": "./locale/*.json"`
  （宿主就是按这个子路径解析词典的，缺了就解析不到、locale 整体失效）；
- `files` 增加 `locale`（否则 npm 包里没有这两个文件，发布出去等于没加）。

并补了 3 条清单检验把这件事钉住（正例 + 反例）：词典存在且字段非空、
按包名能被解析器解析出来、不存在的词典必须解析失败。

### 文档：把"装完还要启用"这件事写清楚

README 新增「⚠ 装完还要『启用』这一步」小节，并写清：

- `dsh plugin add` 只是 pnpm 包装，只写 `dependencies`；
- 真正决定加载的是 `dsh.profile.bundles`，**只在 dependencies 里不会加载**，
  且**不报错**（症状：插件页空白 + 接口 404）；
- 处理方式：应用内「插件」面板打开开关（立即生效、无需重启），或手改 profile 清单后重启。

同时在「已知限制」里补了「宿主升级后插件被静默跳过」条目：给出判据
（`curl .../service-portal/api/status` 连不上 = 没加载，不是"门户没启动"）与处理步骤。

### 已验证的宿主版本

DSH **0.2.1-rc.3**。门禁检验可直接对着宿主的真实运行时跑（宿主装在 `app.asar` 里，
普通 node 读不到，要用宿主自带的 Electron 当 node 用）：

```bash
APP="/Applications/DeepSeek Harness.app/Contents/Resources"
DSH_APP_BOOT="$APP/app.asar/dsh/node_modules/@deepseek-ai/dsh-app-boot" \
ELECTRON_RUN_AS_NODE=1 "$APP/../MacOS/DeepSeek Harness" --test test/manifest.test.mjs
```

## 1.0.4 (2026-10-21)

**修复市场反馈的核心问题：缺 Python / cloudflared 时，插件此前一句话都不说。**

市场 PR（awesome-dsh-plugin#7566）的维护者指出条目描述里没写运行前置，并在合并时补上了。
但描述写清只是第一步 —— 更根本的问题是**插件本身不检测**：

- 门户本体由 Python 脚本拉起（`lib/index.js` 的 `startPublic`），装好插件但本机没有
  Python 3 时，用户点「启动」只会看到一句拉不起进程的报错；
- 外网通道**只复用**本机已装的 `cloudflared`，不会自己下载（`tools/portal_run.py`
  的 `_resolve_cloudflared()`），没有它的用户在点「开启公网访问」时才会失败。

两次失败都发生在用户**已经期待成功**的那一刻，而此时界面此前没有任何预警。

### 新增：前置条件检测（`/status` 与设置页）

`lib/index.js` 新增 `checkPrereqs(repo)`，结果随 `GET /status` 的 `prereqs` 字段返回：

```js
{ ok, python: { ok, path, configured, detail }, cloudflared: { ok, path, detail }, missing: [] }
```

- **只做文件系统探测，不执行任何东西**。这条是硬约束：设置页每 5 秒轮询一次 `/status`，
  如果每次去 spawn 一个 Python，插件会变成持续烧 CPU 的进程。判断「在不在」用 stat 就够；
  「能不能用」仍由启动时真正的 `usablePython` 探测负责，两者职责分开。
- `ok` 的语义是**「开内网够用」**（只看 python），不是「全部齐备」——
  内网访问是核心功能，不该因为没装隧道工具就被判成不可用。是否要公网看 `missing`。
- cloudflared 候选顺序与 `portal_run.py` 的 `_resolve_cloudflared()` **保持一致**
  （两处跑在不同语言里无法共用，但顺序必须一样，否则会出现「插件说没找到、门户却能起」
  的自相矛盾提示）。macOS/Linux 文件名无 `.exe` 后缀，只有 Windows 优先 `.exe`。

### 新增：`cloudflaredPath` 配置项

README「已知限制」早就写着「若你的安装位置不在候选内，需通过配置项显式指定」，
但 `Config` 里**根本没有这个字段** —— 承诺落空。本次补上：

- 留空 = 自动探测（默认）；
- 填了但文件不存在：**明确报「填错」而不是「没装」**。这是两种不同的错，
  混成一句会让用户照着「安装 cloudflared」去装，而真正的问题是他填错了路径。
- 该路径同时经 `POST /start` 与 `POST /tunnel/start` 透传给门户。

### 新增：门户运行时接受 cloudflared 路径覆写

`tools/portal_run.py` 的 `start_tunnel_now()` 增加 `override` 参数，优先级
`本次请求 > --cloudflared 启动参数 > 自动探测`；`/_api/tunnel/start` 从请求体读取
`cloudflared` 字段。原因：门户是常驻进程，启动时就把路径定死了。没有这条，
用户在设置页刚填的路径要等门户**重启**才生效，而重启会换掉隧道域名。

### 修复：pythonPath 填错时被静默回落

`checkPrereqs` 里显式填了不存在的 `pythonPath` 时仍会回落（可用比不可用好），
但此前完全不提示 —— 用户以为自己指定了某个带依赖的特定解释器，实际跑的是另一个，
症状表现为「启动失败但看不出原因」。现在会在 `python.detail` 里写明回落到哪了。

### 设置页：动手之前就说，并按严重程度分级

- 缺 Python 3 → 警示块（`dsp-warn`），且**两个启动按钮都禁用**（点了必然失败，
  亮着的按钮等于邀请用户去撞墙），禁用时用 `title` 说明原因；
- 缺 cloudflared → 行内提示（`dsp-inlineWarn`），**只有「启动并开公网」禁用**，
  「启动（只内网）」必须保持可点 —— 没装隧道工具不影响本机/局域网使用；
- 拿不到 `prereqs`（老宿主 / 字段拼写变化）时一律认作可用：
  把「不知道」当成「不行」比不检测更糟。

### 测试

新增 6 项客户端检验 + 12 项服务端检验（含反证）：

- 缺 Python 时两个按钮都禁用；缺 cloudflared 时**只有**公网按钮禁用（内网按钮的
  断言里不允许出现 `cfReady`）；无 `prereqs` 时不锁死按钮；
- `checkPrereqs` 返回结构固定、`missing` 与各段 `ok` 不自相矛盾；
- 填了不存在的 cloudflared / python 路径分别给出不同的说明；
- 预览工具的 mock 必须与 `checkPrereqs` 返回**同构**（1.0.1 的教训：预览里的假数据
  走形 → 预览正常、真机报错）。

反证验证：把按钮禁用改回旧行为 → 2 条转红；去掉 `!prereqs ||` 兜底 → 2 条转红；
删掉新函数 → 12 条转红。恢复后全绿。

### 预览工具

`tools/render_panel_preview.mjs` 新增三个状态（`misscf` / `misspy` / `pyfallback`），
并在 `off` 状态补上「前置条件齐备」的真形态，供人工核对两种主题下的分级呈现。

## 1.0.3 (2026-10-20)

**修复 1.0.2 的打包卫生回归：`__pycache__` 混进了 npm 包。**

### 症状

`npm install dsh-service-portal@1.0.2` 后，包里多出三个文件：

```
tools/__pycache__/portal_login.cpython-312.pyc
tools/__pycache__/start_public_gui.cpython-312.pyc
tools/__pycache__/tunnel_auth.cpython-312.pyc
```

这些 `.pyc` 内嵌了打包机器上的**绝对路径**
（`/Users/dmh2002/DshProject/dsh-service-portal/tools/...`），
违反本项目「发货代码里不得出现作者本机目录名」的发布纪律。
1.0.0 与 1.0.1 的包内都没有这个问题，属于 1.0.2 引入的回归。

### 根因：files 白名单匹配整个目录，而 npm 不看 .gitignore

- `package.json` 的 `files` 里写的是 `"tools"`，它匹配的是**整个目录**。
- `.gitignore` 里**有** `__pycache__/` 与 `*.pyc`，git 也确实没跟踪它们，
  所以提交历史是干净的 —— 但 **npm 打包时根本不读 `.gitignore`**，
  它只看 `files` 与 `.npmignore`。
- 发布前跑 `check_*.py` 系列检验时，Python 生成了 `tools/__pycache__/`，
  于是被原样打进包里。

### 修复

新增 `tools/.npmignore`：

```
__pycache__/
*.pyc
```

> 注意位置很重要：**根目录**的 `.npmignore` 对已被 `files` 列出的目录
> **无效**（实测仍会打包 3 个 `.pyc`）；只有 `files` 白名单目录**内部**的
> `.npmignore` 才生效。这一点已写进 `.npmignore` 与测试的注释里。

包内文件数由 51 降为 **48**，35 个 Python 脚本与两个运行期入口
（`portal_run.py`、`start_public_gui.py`）全部保留 —— 已逐一核对。

### 测试

新增「打包卫生：npm 包内不得出现 `__pycache__` / `*.pyc` / 编辑器杂项」：

- 用 `npm pack --dry-run --json` 的**真实文件清单**判定，不靠推断。
- 附两个方向的把关：既禁止缓存文件进包，也断言两个运行期入口**仍在包里**
  （防止为了"干净"把 `tools` 整个排除——那正是 v0.8.6 踩过的坑）。
- 带反证：删掉 `tools/.npmignore` 后运行，该检验会精确报出那 3 个 `.pyc`。
- 全量 119 项通过（含 4 项宿主门禁，0 跳过）。

## 1.0.2 (2026-10-20)

**修复深色主题下按钮变成白色方块。** 纯样式修复，无行为契约变更
（1.0.0 冻结的 13 条承诺原样保留）。

### 症状

深色主题下，「访问」「内网访问」「添加节点」等主按钮只剩一个纯白矩形，
文字完全看不见；两个开关的圆形滑钮同样变白。浅色主题一切正常。

### 根因：写死的文字色压在会随主题翻转的背景令牌上

```css
.dsp-btn-primary{background:var(--dsw-alias-brand-primary,#111318);
  color:#fff}
```

宿主的 `--dsw-alias-brand-primary` 语义是"**最高对比度的前景色**"，
它两套主题取值**相反**：

| 主题 | 该令牌 | 解析值 |
| --- | --- | --- |
| 浅色 | `--dsw-static-neutral-bluish-1000` | `#0f1115`（近黑） |
| 深色 | `--dsw-static-neutral-bluish-50` | `#f9fafb`（近白） |

于是深色下是 `#f9fafb` 底 + `#fff` 字，对比度约 **1.02:1** —— 文字并没有
消失，是白压白，视觉上只剩一个白色方块。危险按钮「删除」保持红字可见，
所以现象看起来像是"只有部分按钮坏了"。

### 修复：与宿主一样成对取令牌

宿主自己的 `.button.primary` 就是成对使用的（`button-primary-fill` +
`label-primary-foreground`），换主题时底色和字色一起翻转，永不失配。
本插件此前只抄了底色、字色写死。

| 位置 | 改前 | 改后 |
| --- | --- | --- |
| 主按钮字色 | `#fff` 写死 | `--dsw-alias-label-primary-foreground`（浅 `#fff` / 深 `#0f1115`） |
| 主按钮底色 | `--dsw-alias-brand-primary` | `--dsw-alias-button-primary-fill`（同值，语义更准） |
| 主按钮 hover | `filter:brightness(1.08)` | `--dsw-alias-button-primary-hover`（浅 `#43454a` / 深 `#ebeef2`） |
| 开关圆钮 | `#fff` 写死 | `--dsw-alias-switch-thumb`（浅 `#fff` / 深 `#adb2b8`） |
| 开关轨道 | `--dsw-alias-border-l2` | `--dsw-alias-border-l3`（宿主 Switch 用的就是它） |

> 开关圆钮不能借用主按钮的字色令牌：关态轨道是半透明白叠在深色底上，
> 换成深色钮会与轨道糊在一起。宿主为此专门定义了 `switch-thumb`。

### 同时修正：注释与实现相矛盾的内嵌底色

`--dsp-inset` 的注释早已写明"不要用 `bg-layer-2`，浅色主题里
`bg-layer-1/2/3` 都是同一个白"，但**下一行代码仍指向 `bg-layer-2`**，
这条教训一直没生效。

| 变量 | 改前 | 改后 | 浅色 | 深色 |
| --- | --- | --- | --- | --- |
| `--dsp-inset` | `bg-layer-2` | `interactive-bg-hover` | `#2631480f` | `#ffffff14` |
| `--dsp-inset-solid` / `--dsp-chip` | `bg-layer-2` | `interactive-bg-hover-solid` | `#f1f3f5` | `#353638` |
| `--dsp-surface` | `bg-layer-2` | `bg-layer-1` | `#fff` | `#232324` |

`inset` 改后的值正好等于注释里手算的期望值 `rgba(38,49,72,.06)` /
`rgba(255,255,255,.08)` —— 作者算对了，只是令牌名写错。

另将弹窗肯定语气的标题色由 `brand-primary` 改为 `--dsp-ok`：前者在深色下
会变成近白，语义随之丢失，且与相邻的 `--dsp-warn`（真正的语义色）不成对。

### 为什么开发阶段一直没发现：预览工具本身在骗人

`tools/render_panel_preview.mjs` 里是**手写**的假主题变量，
`--dsw-alias-brand-primary` 被填成 `#4f6ef7`（蓝），而宿主深色下实际是
`#f9fafb`。所以预览里主按钮永远是蓝底白字、始终正常。

现已换成从宿主 `dsh-client-ui-theme`（`body{...}` 与
`body[data-ds-dark-theme]{...}`）逐条提取的 **18 个真实令牌**。换完之后
立刻复现了用户截图里的白块，修复后再验证。

### 测试

- 新增「主题成对：会翻转的背景令牌不得配写死的文字色」：凡 `background`
  使用了会翻转的令牌（`brand-primary` / `button-primary-fill` /
  `bg-layer-*`），`color` 就必须同样取自配套前景令牌。
- 该检验带**反证**：回到 1.0.1 的代码上运行会精确报出
  `.dsp-btn-primary → background 用 var(--dsw-alias-brand-primary,#111318) 但 color=#fff`，
  证明它不是永远通过的空转。
- 全量 118 项通过（含 4 项宿主门禁检验，0 跳过）。

## 1.0.1 (2026-10-17)

**跟进 DSH 0.2.1-rc.1 的清单规范。** 没有任何行为契约变更（1.0.0 冻结的
13 条承诺原样保留），只补上插件与宿主之间的**版本声明**，并把这件事变成
可被测试抓住的契约。

### 背景：新版 DSH 多了两道声明

DSH 0.2.1-rc.1 引入插件↔运行时的版本门禁，判定顺序是：清单里有
`engines.dsh` 就**只看它**；没有才逐个检查 `@deepseek-ai/dsh` /
`@deepseek-ai/dsh-*` 的 `peerDependencies`。两条都没写 = **任何 DSH 版本都放行**。

1.0.0 恰好属于"两条都没写"：只声明了 `cordis` / `schemastery` 的 peer 区间，
这对 DSH 自身版本没有任何约束。实测 1.0.0 在 0.2.1-rc.1 上判定为相容
（不会崩），但这是**运气**——同一个包装在更老的宿主上同样会被放行，然后在
启动期失败，而发版时毫无提示。

### 清单

- 新增 `engines.dsh: ">=0.2.1-rc.1 <0.3.0-0"`：把"本插件适配哪个 DSH 大版本"
  从口头约定变成宿主可执行的声明。
- 新增 `dsh.manifestVersion: 1`：清单格式标识（前瞻声明；当前宿主不强制它，
  已核实源码中无引用）。
- `engines.node` 由 `>=22` 提到 `>=24`：对齐 DSH 0.2.1-rc.1 自带运行时
  （Node 24.21.0）与官方清单示例。

### 测试

- 新增 `test/manifest.test.mjs`（10 项），已并入 `npm test`：
  - **6 项静态契约**：`engines.dsh` 存在且非空、不以 `workspace:` 开头、
    `manifestVersion = 1`、`dsh.bundle.patch` 指向真实文件、
    `dsh.client.platform = web` 且导出了 `./client`、图标是包内相对路径
    且格式/体积合规（宿主 `readPluginMeta` 会校验这些）。
  - **4 项门禁检验**：调用**宿主自己的** `evaluatePluginCompatibility()`
    判定本插件，并用**反例**确认判定逻辑真的生效（篡改成不相容区间后必须翻转；
    `engines.dsh` 存在时必须忽略敌意 `@deepseek-ai/dsh` peer）。
- 验证过测试本身有效：把 `engines.dsh` 删掉、或改成 `>=0.3.0 <0.4.0-0`，
  相应用例立即转红；改回即全绿。
- **找不到宿主运行时则明确 skip，不假装通过**；`DSH_APP_BOOT=<dsh 根目录>`
  或 `DSH_RUNTIME_ROOT` 可显式指定。新增 `npm run test:manifest` 单独跑这一组。

### 一个被实测纠正的假设

原以为"漏写 `-rc` 预发布边界"会把最新 rc 挡在门外。实测宿主用
`semver.satisfies(..., { includePrerelease: true })`，所以 `0.2.1-rc.1` 在
`>=0.2.0 <0.2.1` 与 `>=0.2.1-rc.1 <0.3.0-0` 下**都命中**。真正的风险是上界
卡错（如 `>=0.3.0 <0.4.0-0`），由正例与反例共同兜住。测试注释已写明，
避免后人重蹈这个误判。

### 文档

- README 新增「兼容的 DSH 版本」小节：三个字段的值与作用、为什么必须写
  `engines.dsh`、升级 DSH 大版本时先跑 `npm run test:manifest`。
- 顺带核实（未改动，结论记录在此）：宿主端的
  `plugins.bundle.config` / `plugins.row.config` 两个 keyed slot 在 0.2.1-rc.1
  中仍存在且语义未变；客户端 bundle 只 `require("react")`，属宿主基线模块表；
  `ctx.inject(["webServer"])` 软挂载与 `webServer.register({ kind: "prefix" })`
  的路由契约未变。升级没有带来需要改代码的破坏性变更。

## 1.0.0 (2026-10-17)

**第一个稳定版。** 从 0.1 到 1.0 的所有行为契约自此冻结：下面这份清单里的
每一条都有控制检验守着，改动它会当场报错，而不是等到用户手上才发现。

### 1.0 的承诺（这些是契约，不是实现细节）

- **两条通道，各自独立判断**：内网与公网是两个开关、两个入口、两套凭据。
  关掉其中一条不影响另一条。
- **确认强度与代价对齐**：内网关掉用轻量确认框（可一键重开）；开公网必须勾选
  须知，且**服务端二次校验**（`disclaimer: true`），绕过界面也开不了。
- **fail-closed**：认不出的 Host 一律按公网处理（要口令）。这条来自
  dsh-pocket 用血换来的结论（它曾因反着写被绕过），我们照着守。
- **局域网关掉就是拒绝服务**：返回 403 + 明确的"局域网访问已关闭"页面，
  **不降级**成口令页 —— 否则用户会以为是自己口令输错了。
- **门户页只读**：它是测试页 + 入口页，没有任何设置功能。设置只在插件设置页。
- **屏蔽是路由闸门，不是启停上游**：屏蔽只表示门户不再转发这条路由，
  不会停止上游程序，也动不了上游进程。

### 稳定性

- **测试不再污染用户数据**：8 个会起真门户的检验改用 `PORTAL_RUNS_DIR` 临时
  目录。此前它们直接读写用户真实的 `portal_state.json` —— 实际发生过一次：
  跑完测试后用户的门户被记录成"已停止"，打开设置页看到的是「门户未启动」。
- **修掉一条伪装成"偶发"的失败**：`host.test.mjs` 的一条断言把端口写死成 8899，
  而 8899 正是真实门户的默认端口。用户的门户在跑时这条必红，此前一直被
  "重跑一遍就好"糊过去。
- **跨平台**：`NODE` / `curl` 的 Windows 写死路径改为跨平台解析；
  `test_public_link.py` 的公网链路允许跳过而不是恒失败。

### 界面

- **门户页整体重新设计**：插件真 logo、页首成组、说明降级为脚注、空状态设计、
  窄屏不横向溢出、按钮尺寸与行距按视觉节奏重排。
- **设置页**：节点卡片两个访问入口、确认框按钮可区分、占位符对比度修复。

### 文档

- README 结构对齐同族插件（workbuddy）：补齐「市场收录与展示 / 已知限制 /
  免责声明 / 第三方开源依赖」，致谢拆成四个子章节；中英文同步。
- README 加入设置页与门户页截图（演示数据，已脱敏）。
- 修掉导航里的死锚点。

### 为什么是 1.0

不是"功能加满了"，而是**行为契约稳定了**：上面六条承诺现在都有控制检验守着，
这条线上没有再悬着的重构。0.8.x 期间反复变的是**外观与措辞**，不是这些行为。

## 0.8.12 (2026-10-17)

本轮包含两块：**局域网/公网一致性**（下面长文）与**门户页整体重新设计**，
后者记在「Features（门户页：整体重新设计）」及其下面几节。此外还修掉了一条长期被误判为
"偶发"的测试失败（见「测试：一条长期"偶发失败"的根因」）。

用户看着设置页问：

> 「为什么局域网和外网的体验设计成不一样的呢？应该都是开启和关闭呀，你只读分析」

只读分析后发现，真正的毛病不在"控件长得不一样"，而在**确认强度反了**：
局域网关掉有弹框、开公网却一点就开。随后对照读了本地 `dsh-pocket` 的实现，
把它的做法搬过来 —— 但只搬对得上的那部分。

### Fixes

- **局域网关闭从「降级成要口令」改成真 403（`lan_blocked`）**：
  原先前端写「手机扫码 / 链接均不可用」，后端却只是把内网请求按公网对待、
  弹一个登录页。用户关它的意图是"不想让同一 WiFi 的人看到我的控制台"，
  降级并没有满足这个意图，反而让手机端以为自己口令输错了。
  现在 HTTP 与 WebSocket 用**同一判定**直接 403，返回一张说明页
  （`lan_disabled_html`，明确写「请到电脑上开」，因为手机端不是决策者）。
  loopback / 公网不受影响。
- **公网开启必须在服务端校验免责声明**（`disclaimer: true`）：
  前端那个勾选框只解决"用户看见了"，防不住绕过前端直接打接口。
  只内网启动（`lanOnly`）不要求 —— 它不暴露公网。
- **确认框正文改用 `lines` 数组**：数组直接当 children 是嵌套数组，
  预览 harness 的 `render()` 不处理它，导致截图里弹框正文是空的。

### Features

- **局域网开关加双向确认**（对齐 dsh-pocket 的 `lanToggle`）：
  开/关各一套文案与配色（开=品牌色，关=警告色）。关掉会让同一 WiFi 下
  **已经打开的手机**立刻被 403 挡住，而那一端的人看不到这个开关。
- **公网开启改为勾选式免责声明**：必须真勾选才能点「开启」，未勾选时按钮
  显示「请先勾选」并禁用。两处确认强度**刻意不同**：局域网读两行字点确定，
  公网必须主动勾选 —— 确认强度随代价增长，而不是所有开关都弹一遍。
- **关闭态整块替换内容**：不再保留空的二维码占位框 + 一堆灰掉的控件，
  只留「说清现状 / 说清影响范围 / 给回开关入口」三件事。
- 预览 harness 支持 `?click=<selector>`，可以截图确认框等局部状态。

### Fixes（确认框按钮）

用户截图反馈：「两个按钮看不清」。查下来是确认键落到了**透明底的默认档**，
和「取消」并排时看不出哪个是主操作。

- **两个按钮做主次分离**：取消键带一圈描边当安全出口，确认键一律实心；
  两个按钮等宽等高（宽度也是信息："取消"不是附属链接）。
  收窄方向（关局域网）用 danger（红字 + 描边），放开方向用 primary（实心）。
- **确认键颜色与标题颜色解耦**（新增 `confirmTone`）：标题的 tone 说的是
  "这件事的性质"（warn = 有风险），按钮说的却是"按下它会发生什么"。
  两者混用必然拧巴 —— 开公网那个框标题是 warn，未勾选时按钮也被涂成红色，
  读起来像"点它很危险"，而实际是"现在根本点不了"。现在未勾选走中性的
  `muted` 档（inset 底 + 次级字色）并且真的 `disabled`。

### Fixes（placeholder 看不清 = 假令牌又回来了）

用户截图：「输入框内的字看不清」。根因和 0.8.x 里修过的那次**是同一类问题**，
只是换了个令牌名重新出现：

- `.dsp-input::placeholder` 用的是 `--dsw-alias-label-dimmed` —— **不在宿主
  令牌清单里**（真实只有 14 个 alias 令牌，`cordis inspect Theme.listTokens`
  可查），永远命不中；兜底指向 `--dsp-t3`，而它又是
  `--dsw-alias-label-tertiary`（**也不存在**）兜写死的 `#8b95a5`。
  于是浅色输入框（白底）上的对比度只有约 **2.9:1**。
  现在改用 `--dsw-alias-label-secondary`（真实令牌，#5a6473，约 7:1），
  并显式 `opacity:1`（部分浏览器会再给 placeholder 打折）。
- **`--dsp-t3` 整个删掉**：删掉使用方之后它就只剩定义，留着只会让人再引用
  它。真实令牌只有 primary / secondary 两档文字色，"更次要"不该靠"更浅"表达。
- **把这次审计挖出来的一批假令牌全部换成真令牌**（16 个）：
  `border-l3/l4` → `border-l2`；`button-primary-fill/-hover`、`label-primary-foreground`
  → `brand-primary` + 白字；`interactive-bg-hover/-solid/-active` → `bg-layer-2`；
  `settings-card-fill/-stroke` → `bg-layer-2` / `border-l2`；
  `state-business-primary` → `brand-primary`；`state-warn-label` → `state-warn-primary`；
  `markdown-inline-code` → `bg-layer-2`；`switch-thumb` / `toast-bg` / `toast-label`
  本来就是固定值（白色圆钮、深底浅字），直接写死。
  这些**都不会崩**（都有兜底），但兜底是按浅色写的 —— 深色模式下会露出浅色。

### Fixes（门户页：「鼓励一下」加下划线）

用户：「这个要带下划线」。

它是页面上**唯一的外链**，样式却是一个圆角胶囊 + 淡灰文字 —— 只靠颜色区分，
会被读成"标签"而不是"能点的链接"（WCAG 1.4.1 也要求链接不能只靠颜色表达）。
现在加 `text-decoration:underline` + `text-underline-offset:3px`
（中文离字底太近会糊在一起），hover 时下划线跟着变深。

### Fixes（测试：一条长期"偶发失败"的根因）

`test/host.test.mjs` 的「退出收尾：门户已不在运行 → 幂等跳过」长期被当作
"端口竞争偶发"，跑第二遍就过。这次查清：它把端口**写死成 8899**，而 8899
正是开发机上真实门户的默认端口 —— 本插件默认 `autoStart: true`，所以用户的
门户通常正跑在那里，这条断言必然失败。

它不是时序竞争，是**断言依赖了本机外部状态**。现在先借一个空闲端口再释放，
得到"确定没人监听"的端口。连跑三次全绿，且是在门户正跑着（8899 被占用）的
条件下验证的。

### Fixes（门户页：卡片行间距）

用户：「行间距现在太小了」。

**真实原因不是"看起来小"，是量出来为 0**：宽屏卡片用了 `align-items:center`
并且**没有 `row-gap`**，"状态胶囊底边"与"路由/按钮行顶边"实测间距是 **0px**，
两个元素直接贴在一起，读起来像一行里挤了两行内容。

- **宽屏**：`.card` 加 `row-gap:12px`，内边距 15→17px。同时把 `.route` /
  `.meta` / `.warn` / `.result` 各自的 `margin-top` 删掉 —— 交给 `row-gap`
  统一管，否则两者叠加会变成"东一块西一块"的隐式间距。
- **窄屏**：`display:block` 下 `row-gap` **根本不生效**（CSS Grid 专有），
  所以每一段的间距必须显式给。补上 `.card>.top` / `.route` / `.meta` /
  `.warn` / `.result` 的 `margin-bottom`，取 12–14px 与宽屏同一节奏。
  这里差点漏掉：只改宽屏的话，手机上会安静地保持"全部贴在一起"。

实测：宽屏 标题→路由 16px、路由→提示 17px；窄屏三处 12/12/14px。

### Fixes（门户页：卡片内按钮尺寸）

用户：「这里的按钮大小，你再调整一下」。

**问题**：卡片里「访问 / 测试」两个按钮是 40px 高、17px 横向内边距，而它右侧
紧挨的「上游未响应」状态胶囊只有 24px —— 同一条视平线上差近一倍，加上按钮
落在卡片右端，整张卡看着头重脚轻。

- **卡片内按钮单独降到 32px 高**（`.actions .btn`），横向内边距 17→13px，
  字号 13→12.5px，图标 13→12px。32px 仍高于 WCAG 2.5.8 的 24px 触控下限。
- **窄屏（<521px）放大回 40px 并铺满整行**：那时候按钮是主要操作，手指点的
  地方必须够大，而且窄屏下按钮换到独立一行，不存在"和胶囊比对"的视觉问题。
- 实测比例：胶囊 88×24、按钮组 152×32，两者右边缘都落在 693px。

### Fixes（门户页：去掉「节点 N」区块标题）

用户：「节点1这个不要，只保留分割线」。

- **删掉区块标题行**（「节点」+ 计数药丸 + 一条线）。这页**本来就只有这一个
  区块**，标题"节点"不区分任何东西；上面那句引导语已经把范围说清了。
  现在只留一条 `<hr class="sechead">` 把页首说明与卡片流分开。
- 计数一并删掉：节点少时它是噪音，多起来时列表本身就一眼看得完。
- 有节点 / 空列表两条分支都改成同一形态，避免"空态有标题、有数据没标题"的漂移。

### Features（门户页：整体重新设计）

用户：「这个页面你好好设计一下，一共就这么点内容」，并指定 logo 用插件那个 LD。

**设计取向**：这页只有「标题 + 节点列表 + 一段说明」，内容极少，所以设计上
要**克制**——层级靠留白与字重建立，不靠框和底色堆叠。按 `design_recommend`
取的 Minimalism / Swiss 方向（variance 3、motion 2、density 4）。

- **logo 换成插件真图**：原来是我手绘的一个 "LD" SVG 方块（占位）。现在直接读
  `client/icon.ts` 里那个 data URI —— 与设置页卡片、插件列表**同一张图**。
  品牌标记必须是同一张图，否则用户会以为是两个东西。读不到时退回占位方块，
  不让整页渲染失败（门户是用来救急的页面）。
- **页首三件成组**：logo + 标题组 + 「鼓励一下」，一行内对齐。原来 logo 在最右、
  鼓励一下也最右，两个不相关的元素挤在一头。
- **副标题与引导句拆开**：`h1` 下面一行短副标题（"已发布的节点，点开即用"），
  再下面才是带端口的完整引导句。原来两句话挤在一处，读起来是"标题 + 长句"。
- **说明区降级为脚注**：原来「怎么管理」是一张和节点列表**同等重量**的白卡，
  读起来像"另一半内容"。它其实是一次性说明，所以去掉卡片、缩字号、加分隔线，
  放到节点之后。
- **节点卡信息层级重排**：名称（最强）> 状态药丸 > 等宽路由/上游 > 提示 > 动作。
  卡片只要 1px 描边 + 极轻投影 —— 这页没有第二层卡片，不需要堆视觉重量。
- **空状态**：从一句灰字改成虚线框 + 明确指路（"去 设置 → 插件 → … 点添加节点"）。
- **窄屏不再横向溢出**：`.head` 原来 `nowrap` 且子元素都 `flex:0 0 auto`，
  窄屏整行超宽把**正文和卡片一起裁掉**。改成允许换行，「鼓励一下」掉到第二行靠右；
  窄屏按钮拉成全宽堆叠。
- **行宽单位从 `ch` 改成 `px`**：中文一个字约等于 2ch，`52ch` 只有约 26 个汉字，
  会把一句完整的话劈成两行。
- 包名 `dsh-service-portal` 用 `.nobr` 包住，避免在连字符处断成两行。

**验证方式**：headless Chrome 的 `--window-size` 有最小宽度限制（实测要塞 390px
得到的是 500–741px），所以窄屏改用 **CDP `Emulation.setDeviceMetricsOverride`**
精确模拟 390px 移动视口截图 —— 桌面 / 移动 / 空状态三种形态都肉眼核对过。

### Features（门户页：删掉分类徽标、两者靠右）

用户：「蓝色的删掉，鼓励一下放到右上角」。

- **删掉页首的「内网(免密)/外网(需口令)」徽标**。这个信息**页脚本来就有**
  （"当前分类：内网(免密)"），页首再顶一个同色胶囊是同一件事讲两遍 ——
  而它是这页最不需要强调的内容：用户扫码进来就已经知道自己从哪条路进来的。
  删的是**页首那一个**，不是这条信息本身。
- **LD logo 与「鼓励一下 ★」都靠右**：`justify-content` 从 `space-between`
  改成 `flex-end`。只剩两个元素时 space-between 会把它们撑到两端、中间留一大片
  空白；flex-end 让它们贴右边缘排成一组（logo 在前、"鼓励一下"在最右）。
- 顺手删掉已无使用者的 `.badge` 样式与 `hide_lan` / `lan_urls` 两个局部变量
  （地址卡删掉后它们就不再被读取了；留着会让人以为还有地方在用）。

### Features（门户页：删掉地址卡、换页首）

用户要求：「左上角换成 鼓励一下，右上角要有 LD 的 logo，图2整个都不需要显示」。

- **删掉整个「访问地址」区块**（用户截图里那张列着三个地址 + 二维码的大卡）。
  为什么删得掉而不是藏起来：进门户本来就是**扫码 / 点链接**来的，地址此刻就
  在浏览器地址栏里 —— 在页面上再复述一遍是纯冗余，而且那张卡把这页顶到一屏
  之外，把真正要看的「已发布的节点」挤了下去。需要复制地址或看二维码时，
  插件设置页里有完整的一套（那是发给别人用的场景）。
- **页首重排**：左上「鼓励一下 ★」（原来在页脚），右上 LD logo。
  标题 `h1` 从 `.top` 里挪出来单独一行 —— 左边现在属于「鼓励一下」，
  标题再挤在同一行就会和它抢位置。
- **LD logo 是内联 SVG**（`_BRAND_MARK`）：这一页要在断网、无外链时也完整
  显示（它本身就是给人扫进来用的），用 `<img src=...>` 会留一个破图。
  用 `currentColor`，深浅主题自动跟随。

### Features（节点卡片：两个访问入口）

用户要求：「这里要有内网访问、公网访问 2 个访问按钮，各自判断当前是否开启，
开启才能点击」。

- **一个「访问」拆成「内网访问」+「公网访问」**：两条通道的开关是**互相独立**
  的 —— 关掉局域网后公网仍可用，没开公网时公网按钮就没有意义。合成一个按钮
  只能要么给死链、要么给一条不一定是用户想走的路（在手机上点，可能只有公网
  能到；在电脑上点，内网最快）。
- **各自判断自己的开关**：内网看 `lanEnabled`，公网看 `publicUrl`。
  可达的那个实心/描边（内网是默认路径，所以实心留给它），不可达的灰掉。
- **不可达时不给 `href`**：`<a>` 没有 `:disabled`，只加个灰样式是**假的禁用**
  —— 浏览器照样能点开、能中键新标签、能复制链接。所以 href 置 `undefined`
  且 `onClick` 里 `preventDefault`，`aria-disabled="true"` 让读屏也读对。
- **灰掉时说明去哪开**：`title` 写「局域网访问已关闭 —— 先在「局域网访问」里
  打开开关」/「公网访问未开启 —— 先点「开启公网访问」」。只灰不解释，用户
  会以为是这个节点的问题。
- 新增 `.is-disabled`（复刻 `:disabled` 的外观与光标）与 `.dsp-btn-outline`
  （描边档，给公网按钮）。
- 预览 harness 新增 `svcboth` / `svclanoff` 两个状态，用来并排核这两个按钮的
  启用/禁用，以及"关局域网不影响公网按钮"。

### Docs（清理 27 条过期断言）

`check_portal_parity.py` 长期停留在 **141/168**。查下来不是产品有问题，是
**断言在守已经不存在的东西** —— 它们钉的是某次重构之前的类名、内联样式对象
（`styles.warnBox` / `actionRow` / `COLOR.*`）和已被删除的功能（「停止门户」、
「访问地址」预告、「局域网免密」底部警示）。全是本会话之前那次未完成的重构
留下的尾巴。现在 **169/169**。

**没有一条是"删掉就绿"的**，分四种处理：

1. **改锚点，保意图**（类名/写法变了，行为没变）：
   `styles.warnBox` → `.dsp-warn`；`actionRow` → `.dsp-row`；
   `styles.svc` → `.dsp-node`；`.dsp-primary:hover` → `.dsp-btn-primary:hover`；
   `outline:2px solid` → `--dsp-focus`（令牌化）；`COLOR.*` → `--dsp-*` 别名层；
   `copyText("lan", lanPrimary)` → `copyText(copyKey, url)`（收敛成通用 addrRow）。
2. **改判据，不钉数值**（调参不算契约）：
   卡片上限 880→960、窄屏断点 720→760、窄屏二维码 132→148 都只断言
   "有上限 / 有单栏兜底 / 窄屏档存在"，而不是钉死那个像素值。
3. **反转断言**（功能按用户要求删了，要守的是"别再回来"）：
   「停止门户」「停止门户的后果说明」「还没探测过网卡地址」「底部局域网免密警示」
   「未启动时预告地址」—— 改成断言它们**不出现**。
4. **改断结构**（原来数次数，但两处其实在互斥分支里）：
   公网风险文案在「未开启 → 开启前须知」与「已开启 → 风险条」各出现一次，
   同一时刻只渲染一个，不是重复。改成断言两处分别挂在 `pub-none-steps` 与
   `pub-risk` 上。

**顺带修好的一个方法论问题**：很多断言是"某东西不再出现"，而那些东西的名字
恰恰该留在注释里（记录踩过的坑）。按裸文本判 = 注释越诚实、检验越失败。
现在统一用模块级 `_strip_comments()`，只判可执行内容。（`doStop` 那条还踩了
`doStopTunnel` 含子串的坑，改用词边界。）

**反向验证过**：故意注入 4 处回归（删 hover 规则、改回假令牌、去掉
`preventDefault`、让 `doStop` 复活），6 条断言全部报红；恢复后回到 169/169。
不然"全绿"可能只是断言被削弱了。

### Docs

- `check_portal_parity.py` 的令牌守卫改成只校验 **alias 命名空间**，并把判据
  从"整份源码里出现过"改成"**剥掉注释后**仍被引用"。原实现会把 radius /
  shadow / focus-ring 这些真实存在的别套命名空间判成"可疑"（噪音 26 条），
  又禁止注释里提假令牌的名字（而注释里恰恰该记录踩过的坑）。新增 20 条钉死
  本轮修掉的假令牌，并加了一条 placeholder 专项守卫。

- 修了 `check_portal_parity.py` 里两条**过期**断言（钉着 `key: "head"` 和
  `primary: {}` 这类已被重构删掉的东西，前者会让整份检验在 ① 就中断）；
  `check_portal_lan_pin.py` 的就绪轮询加了 `URLError` 容忍（门户没起来时
  原来会抛一坨堆栈，看起来像产品挂了）。

## 0.8.11 (2026-10-17)

> **关于 0.8.9 / 0.8.10 / 0.8.11 的 tag。** 这三个版本有 CHANGELOG 记录，
> 但**没有对应的 git tag**：那段时间的改动没有各自落到独立提交上，最后并进了
> `v0.8.12` 那一次提交（`5165587`）。给它们补打 tag 会让 tag 指向**包含更多改动**
> 的代码，比没有 tag 更误导，所以选择不补、在这里如实说明。
> 0.8.6 / 0.8.7 / 0.8.8 / 0.8.12 / 1.0.0 的 tag 都是准确的。

用户发来一张截图（「门户进程 / 停止门户 / 刷新」），说：

> 「修复吧，顺带吧这些去掉，这个服务本身就随dsh打开和关闭的，不需要再有设置，太啰嗦。」

这句话里其实藏着**两件事**，第二件才是重点：

1. 显性要求：把「门户进程」那块 UI 删掉；
2. 隐含前提：门户要**真的随 DSH 开关**。

而当时远不是这样：门户是 `spawnDetached` 起的**脱离进程**（故意脱离 DSH 的
子进程树，否则 DSH 一退、手机上的二维码就断了），代价是 DSH 退出时门户
**不会自己走**。正因为如此才需要在设置页给一个「停止门户」按钮让用户手动收。
所以不能只删 UI —— 删了之后用户就再也没有正规入口去停它了。
正确顺序是**先补上生命周期收尾，再删按钮**。

### Features

- **门户随 DSH 开关**（新增 `registerPortalTeardown` / `shutdownPortal`）：
  插件在 `ctx.on("dispose")` 与 `SIGINT/SIGTERM/SIGHUP` 上挂收尾，DSH 退出
  或被 Ctrl+C 时把门户一起停掉。收尾**幂等**（`closed` 标志），dispose 与信号
  都触发也只收一遍。
- **只收自己起的那个**：用户在终端手动 `portal_run.py --lan-only` 调试的门户
  **不会**被 DSH 退出顺手杀掉 —— 按状态文件里的 `portal_pid` 与插件记住的 pid
  比对，不一致就跳过（宁可留一个进程，也不误杀用户正在用的会话）。
- `readPortalStatus` 透出 `portalPid`（收尾判归属要用；原来只在状态文件里，
  插件侧拿不到）。

### Removals（按用户要求"太啰嗦"）

- 删掉设置页底部整块「门户进程」：`停止门户` + `刷新` + 那句后果说明。
  前两个按钮的前提（门户脱离 DSH 常驻、只能手动收）已被上面的收尾消除。
- 顺带删掉 `doStop`（其唯一调用方就是这块 UI），避免留死代码。
- **没有**动「关闭公网访问」：它在公网栏里，语义是"收起对外暴露"（只收隧道、
  不碰门户），与"停掉本机门户进程"是两件事。
- **没有**动「门户未启动」那一屏的「启动（只内网）/ 启动并开公网」两个按钮 ——
  这是用户明确要求保留的（我提出来问过：既然要自动起，是否连这两个也删，
  用户选了"两个都留"）。

### Fix（用户上一条问的「服务二是哪里来的」）

查清了：**不是用户设置的，是 `test/acceptance_portal.py` 漏出来的测试残留。**

- 脚本会往**用户真实的** `runs/portal_registry.json` 里加一条测试服务
  `s2 / 服务二 / 127.0.0.1:<随机端口>`（那个 57441 就是当时临时起的测试服务
  随机分到的端口），但**从不删它**。
- 它本该被收尾还原/删除，却漏了，因为：

      backup = None
      for path in (state_file, reg_file):
          if os.path.exists(path):
              backup = backup or tempfile.mkdtemp(...)   # 只在第一个存在的文件上建
              ...

  用户真实目录里往往**只有 portal_state.json、还没有 portal_registry.json**
  （他还没添加过任何服务）→ `backup` 因 state 而建、注册表从未进备份 →
  收尾 `if backup:` 成立、走还原分支 → **注册表既不还原也不删除** →
  s2 永久留在真实配置里。
- 根因不是"忘了删"，而是**测试直接改真实配置、只靠收尾兜底**。现在改为
  根本不写那个目录：整个跑在 `PORTAL_RUNS_DIR` 指向的临时目录里，跑完
  `rmtree`。已实测：跑完 30/30，真实注册表 md5 不变。
- 已用正规路径（`registry.remove`）清掉用户注册表里的 `s2`，现在是空表。

### 回归（105 项全绿）

- `退出收尾：pid 不是我们起的 → 不代关`（反例控制：必须命中 pid 分支，
  否则说明喂的状态不对、检验空转）
- `退出收尾：没有本插件启动记录 → 不动`
- `退出收尾：门户已不在运行 → 幂等跳过`
- `退出收尾：pid 匹配且端口在听 → 真的把门户停掉`（**端到端**：真起门户进程、
  走收尾、断言端口真的松掉 —— 不是只看接口返回 ok）
- `随 DSH 开关：apply() 把收尾挂到 dispose 与信号上`（防"定义了没接上"）
- `渲染：运行中状态下面板不再出现「门户进程 / 停止门户」`（**真渲染**断言）

最后一条是踩了坑才这么写的：我第一版用 `grep 源码` 断言删干净了，结果那是
**假通过** —— 那块只在 `running` 分支渲染，喂一个"未启动"的 status 就永远
渲染不到它，断言恒真。改成喂**运行中**的 status 真渲染，并人工拿旧产物对比
确认过它会报 FAIL（非空转）。

### 真机验证

- `POST /_api/tunnel/start` → 200，公网根路径 200、`/_auth/health` ok:true。
- 端到端：起门户 → 走收尾 → 端口松掉（`PASS 门户已随收尾停掉`）。
- `check_portal_tunnel` 11/11、`check_public_pin` 18/18、
  `test/acceptance_portal.py` 30/30 且真实注册表 md5 不变。

## 0.8.10 (2026-10-17)

用户：「开启公网访问失败」。复现出来了，是**一行写死的 Windows 路径**：

    DEFAULT_CLOUDFLARED = os.path.join(
        os.path.expanduser("~"), ".dsh", "dsh-pocket", "bin", "cloudflared.exe")

`~/.dsh/dsh-pocket/bin/` 里在 macOS/Linux 上确实有一个 cloudflared，但**叫
`cloudflared`，没有 `.exe`**。于是 `start_tunnel_now()` 的 `os.path.isfile`
恒为假，`POST /_api/tunnel/start` 恒回 **502**：

    {"ok": false, "public_url": null,
     "detail": "找不到 cloudflared：/Users/.../dsh-pocket/bin/cloudflared.exe"}

这个 bug 特别难自己看出来，因为**报错路径肉眼是对的** —— 目录里真有个
cloudflared。只有盯住结尾的 `.exe` 才会发现。而界面上只留下一句"失败"。

### Fix

- `tools/portal_run.py` / `tools/start_public_gui.py`：新增
  `_resolve_cloudflared()` —— 按平台决定候选文件名（Windows `cloudflared.exe`，
  其余 `cloudflared`），依次在 `~/.dsh/dsh-pocket/bin`、`~/.dsh/bin`、
  `~/.local/bin`、`/usr/local/bin`、`/opt/homebrew/bin` 里找，最后回落到
  `shutil.which("cloudflared")`（用户自己装的那份也能用）。
- 失败信息补上**下一步怎么修**（装什么、用哪个参数指定），不再只丢一句"找不到"。

### 同类问题一并收口（检验脚本也写死了平台）

排查时发现检验脚本自己也踩同一个坑，导致"看着像功能坏了"，其实是脚本量不出来：

- `check_plugin.py` / `check_portal_tunnel.py` / `check_probe_button_browser.py`：
  找 node 原来只认 `%LOCALAPPDATA%\Programs\DeepSeek Harness\...\node.exe`。
  非 Windows 上 `LOCALAPPDATA` 为空 → 拼出一个**相对路径**，必然找不到，
  脚本一起手就 FileNotFoundError。现在统一走 `check_plugin.find_node()`
  （加 macOS/Linux 候选 + PATH 回落）。
- `check_portal_bind.py`：`SO_EXCLUSIVEADDRUSE` 只有 Windows 有，三处直接引用
  → 非 Windows 上 AttributeError 把检验崩掉。改为 `_make_exclusive()` 兜住。
- `check_portal_bind.py`：`listening_addrs()` 只解析 Windows `netstat -ano`
  的 `LISTENING` 行；macOS/Linux 用 `LISTEN` 且没有 `-p TCP`，于是**永远返回空集**，
  那条「监听 0.0.0.0」断言必然 FAIL（同一条检验里「从内网 IP 能访问」却通过 ——
  真只绑 127.0.0.1 的话它不可能通过）。现在按平台改用
  `lsof -nP -iTCP:<port> -sTCP:LISTEN`。

### 回归

- 真机验证：修复前 `POST /_api/tunnel/start` → 502；修复后 → 200
  并拿到 `https://<随机>.trycloudflare.com`，公网根路径 200、`/_auth/health` ok:true。
- 新增源码级回归测试（`test/host.test.mjs`）：两个启动器都必须用
  `_resolve_cloudflared()`、必须按 `sys.platform` 选文件名、必须留 PATH 回落，
  且不得再出现无条件写死 `cloudflared.exe` 的那一行。
- `test/host.test.mjs` 93 项全绿；`check_portal_tunnel` 11/11、
  `check_portal_bind` 7/7、`check_public_pin` 18/18、`check_portal_shutdown` 6/6。

### 关于「不要自动添加服务」

已确认：**没有任何自动添加服务的行为**。用户明确要求过「取消自动发现服务的功能」，
该功能早已删除（`client/index.jsx` 有明确记录）。注册表
`runs/portal_registry.json` 只有两处写入，都在用户点击时才走：

- `POST /_api/services`（控制台表单「添加」）→ `registry.add(data)`；
- `POST /_api/services/<key>/delete`（点删除）→ `registry.remove(key)`。

启动路径不写注册表；`enable/disable/open/block` 只改 `enabled` 字段，
**不 spawn/kill 任何进程**（上游程序归用户自己的启动脚本管）。
当前注册表里那条 `s2 / 服务二 / 127.0.0.1:57441` 是用户自己填的，本次未改动分毫。

## 0.8.9 (2026-10-17)

用户：「你要把这个页面（插件设置页）美化一下，我才能截图发布」。中途又提了三件小事
（「鼓励一下要有下划线」/「端口号这里不要显示」/「没启动时那两个地址不要显示」），
以及一条**行为**要求（见 Features 第一条：自动启动跟随用户的启停动作）。

主体是**外观与信息层级** —— 服务、路由、口令、隧道的逻辑一行没改（改版前后的处理器
区域逐字节比对：removed lines = 0）。唯一的行为改动是那条自动启动偏好，它有自己的
控制检验；本版共 92 项全绿。改的是"为什么它看起来不像宿主的一部分"。

### 根因（不是审美偏好，是三条具体事实）

1. **浅色主题里没有层级可用**：宿主 `--dsw-alias-bg-layer-1/2/3` 在浅色下是
   **同一个白**（都是 `neutral-bluish-00`）。原来面板的层级全靠 1px 描边硬撑，
   于是"卡片里套盒子、盒子里再套盒子"，看着平。现在内嵌块改用
   `--dsw-alias-interactive-bg-hover`（浅色 `rgba(38,49,72,.06)`、深色
   `rgba(255,255,255,.08)`）—— 它自带透明，明暗两套主题里都成立。
2. **几何不在宿主的尺度里**：面板用了 10px 圆角、999px 胶囊按钮、44×26 的绿色
   开关；宿主是 4/8/12/16/20/28 六档圆角、Button H36/R12（紧凑 H28/R8）、
   Input H32/R12、Switch 36×20（开=品牌色）。逐项对齐后，面板与旁边的宿主控件
   像同一套东西了。
3. **未启动时是两块空盒子**：原来未启动也照常画"局域网访问 / 公网访问"两栏，
   而那时栏里只有一句"门户未启动"—— 两块并排的空盒子比一句话更占地方，也更像
   没做完。现在未启动只画一件事：一句说明 + 将要使用的地址 + 「启动后你会得到」
   三条清单。

### Features

- **「下次打开 DSH 要不要自动起」跟随用户的启停动作**（用户要求：「默认就应该是启动的，
  用户关闭下次打开就还是关闭，用户启动下次打开就还是启动，默认是内网启动，外网关闭」）。

  默认本来就是开的（`autoStart` 默认 `true`，只开内网），缺的是**记住用户的动作**：
  原来用户停掉门户，下次开 DSH 又会被自动拉起来 —— 用户会以为插件在自作主张。
  现在 `POST /start` 成功 → 写 `autoStart=true`；`POST /stop` 成功 → 写 `autoStart=false`。

  为什么写回 `autoStart` 配置本身，而不是另建一个偏好文件：`autoStart` 就是这件事的
  权威字段。另存一份等于两个真相源 —— 用户在插件配置里手改 `autoStart` 之后，界面行为
  会和配置不一致，那种错最难查。写回同一个字段后，"点按钮"与"改配置"完全等效。
  落盘走宿主 `configEditor.edit`（原子写 + 文件锁，见 README 里那段说明）。

  两条纪律（都有控制检验盯着）：
  - **只在动作真的成功时写**：停不掉（门户僵死 / 端口还占着）时不改偏好，
    否则会出现"界面说已停止、下次开机它又自己起来"的错位；启动失败同理。
  - **只认启停动作**：自动启动本身、开/关公网、崩溃退出都不碰它 —— 否则自动启动
    会把用户"停掉"的决定又改回来，形成"永远关不掉"的循环。

  设置页在未启动态多一句实话：`autoStart=true` → "下次打开 DSH 会自动启动（只开内网，
  公网仍要手动开）"；`false` → "你上次停掉了它：下次打开 DSH 不会自动启动"。
  宿主没透出该字段（老版本）时整句不显示 —— 不猜、不编。

- **面板重排**（`client/index.jsx`，外观全部改由注入的 CSS 承担）：
  - 顶部：44px 图标 + 标题 + 副标题；右侧是状态胶囊（运行中=绿点 / 已停止=灰点）、
    端口胶囊（等宽）、启动时间胶囊、「鼓励一下 ★」。
  - 未启动：软底 CTA 块 + 计划使用的地址（可复制）+ 启动两档按钮 + 启动后清单。
  - 运行中：局域网 / 公网两栏并排，栏头是淡底标题条 + 各自的开关或「关闭公网 /
    开启公网访问」；栏内二维码放进白底方块（扫码**必须**白底，两种主题都固定为白），
    地址块统一为"等宽地址 + 访问 + 复制"。
  - 节点列表：每条一张卡（名称 + 路由标记 + 开放/屏蔽状态 + 上游地址 + 操作行），
    上游地址用等宽；"上游没响应"仍是**提示**，不改变路由本身的开放/屏蔽语义。
  - 表单行学宿主的设置表单：标签 + 说明，行与行之间 0.5px 发丝线。
  - Toast 照宿主 Toast：顶部居中、R16、深底浅字（两种主题都是深底）。
- **公网暴露风险改为通栏**，放在两栏下面。原来塞在公网那一栏里，会把那栏撑高、
  左边留一大片空白，读起来还像"公网栏的一部分"。文案保留 0.8.2 的口径：拿到口令
  的人能改**路由**，动不了上游程序。
- **「上次没有正常退出」改为警示块**。`status.problem` 有两种性质：还在跑时是提醒
  （一行提示就够），已经停了则说明上次没正常退出（宿主的判定：只有没写
  `stoppedClean` 才带 problem，用户主动停掉的不算）。后者是异常，不该混在一堆
  灰字里。

### Fixes

- **插件列表摘要的「口令形态」永远是「固定口令」**：`status.passwordMode` 是宿主给的
  字符串 `"random"` / `"fixed"`，原判定写成了真值判断（`status.passwordMode ? …`），
  两种形态都会落到"固定口令"这一支。改为 `=== "fixed"`。
- **地址块在长地址下按钮错行**：公网地址是 `https://xxx.trycloudflare.com`，原来整块
  `flex-wrap:wrap`，于是「复制」被顶到第二行、与左栏形态不一致。现在**地址负责收缩
  换行、按钮组不换行**。
- **「局域网访问已关闭」时二维码的关闭态丢了**（本版改造中自己引入，复核查出）：
  局域网关掉后原来那块会显示"已关闭"并淡化，重排时 `qrTile()` 只剩下"码 / 生成中"
  两种形态，于是会把**一张扫了必然打不开的旧二维码**照常显示（缓存命中时），
  真正"不可用"的信号只剩下面一行小字。现在给 `qrTile` 显式加了 `off` 参数：
  灰底 + 虚线 + "已关闭 / 打开右上角开关后出现二维码"，绝不给可扫的死码。
- **公网未开时右栏被拉成一大块空框**：两栏栅格默认 `stretch`，短的右栏被拉到与左栏
  等高。改为 `align-items:start`。
- **未启动时按钮与脚注贴在一起**（散落的 margin 漏了一处）：CTA 左栏收成一个等距
  的竖列（gap 12px），不再逐元素写 margin。
- **顶部不再显示「端口 8899」胶囊**（用户要求）：端口在下面的地址里已经写着
  （`http://…:8899`），单独再挂一个胶囊是同一件事说两遍；而且它既不是状态、用户
  也改不了（改端口要动插件配置，不在这页）。端口仍在状态数据里：地址、摘要行、
  以及"没探测到局域网地址"时的回环提示都还用它。顺带删掉因此没人用的 `.dsp-mono`。
- **「鼓励一下 ★」改为常驻下划线**（用户要求）：它是一块**链接**，下划线是它唯一的
  非颜色线索 —— 只靠颜色表达"可点"，不符合"颜色不是唯一信息载体"这条规范；原样式
  只在 hover 时才出现下划线，静止状态看着像普通文字。
- **`aria-checked` 显式写成字符串**：CSS 的 `[aria-checked="true"]` 只认字符串。
  同样显式化 `aria-expanded` 与 `role="switch"` 的无障碍名字 —— 开关现在一定
  带 `aria-label`。

### Tests

- **预览 harness 补四个此前覆盖不到的状态**（`tools/render_panel_preview.mjs`）：
  `?s=services`（三个节点：开放且上游在 / 开放但上游死 / 已屏蔽）、
  `?s=problem`（凭据在、端口没进程 —— 此前只能靠真机复现的异常分支）、
  `?s=lanoff`（局域网访问关掉：二维码必须显示"已关闭"而不是死码）、
  `?view=summary`（插件列表行的一行摘要）。四者在改版前都无处可看。
- **`?s=off` 的假 `/start` 响应补一段 `stdout`**，于是「启动器输出」那一块也能在
  预览里看到（原来那块永远渲染不出来）。
- **客户端/宿主控制检验 92 项全绿**（新增 9 项自动启动偏好的控制检验）；`node --check lib/client.js` 通过。

- **新增 9 项自动启动偏好的控制检验**（正反都可证伪，不是"跑通就算过"）：
  `rememberAutoStart` 只写本插件自己的条目且保留其他字段 / 无 `configEditor` 与
  `editor` 抛错时都不冒泡（best-effort）/ 找不到自己条目时**不动别的插件**；
  真实 HTTP 路由 `POST /stop` 门户自退成功 → 记 `false`，而**没停掉**（端口上没人）
  → 偏好一动不动（反例控制）；`POST /start` 成功 → 记 `true`；
  「自动启动 / 开公网 / 关公网都不碰偏好」；`readStatus` 透出 `autoStart`。
  路由层用真 HTTP server 打（`callHandler()`），不走假 req/res —— 路径、方法、状态码
  就是被检验的对象。
- 改版做了一次**行为对等的独立复核**（逐项核对 28 个 state、全部 handler 的引用、
  `Switch()` 改签名后的两个调用点、两个 view 分支），除上面那条局域网关闭态外
  无遗漏 —— 那条已修。

### Docs

- 本页改动全部走注入 CSS（类名 `dsp-` 前缀不变），颜色一律 `var(--dsw-alias-…, 兜底)`；
  圆角只用 `--dsw-radius-*`。评审用的对照实拍（浅/深 × 未启动/运行/已开公网 +
  编辑/添加/高级/摘要）在 `runs/portal-settings-preview/` 下留档。

## 0.8.8 (2026-10-16)

接 0.8.7。0.8.7 自己新加的那条「不得把作者本机路径当取值来源」的检验，**覆盖面有洞**，
发出去之后复核时发现，本版本把它补上并清掉漏网的实例。

### Fixes

- **`tools/probe_button_e2e.mjs` 的 Chrome 路径改为按平台探测**。
  与 0.8.7 修掉的 `shoot_portal.py` 是同一类问题（原本写死
  `C:\Program Files\Google\Chrome\Application\chrome.exe`，只有作者的 Windows 机器成立）。
  新增 `findChrome()`：`--chrome` > `$CHROME` > 按 `process.platform` 找常见安装位置；
  都找不到时**返回退出码 2**（跳过），而不是拿着不存在的路径去 spawn 再报一句看不懂的错。

### Tests

- **扫描覆盖面改由 `package.json` 的 `files` 推导**（递归 + 另扫 `client/`），
  不再硬编码 `lib/index.js` + `tools/*.py`。实测原覆盖面漏了两类真问题：
  - `lib/client.js` —— 客户端面同样发货，在它里面写死路径一样会泄；
  - `tools` 里的 `.mjs` —— `probe_button_e2e.mjs` 的 Chrome 路径正是从这里漏掉的。

  三个方向都证伪过：往 `lib/client.js` 贴路径 → 红；往 `client/index.jsx` 贴路径 → 红；
  把扫描收窄回只扫 `lib/index.js` → 由新增的 `REQUIRED_SCANNED` 覆盖自检拦下 → 红。

- **加一条更狠的兜底**：作者的宿主仓库目录名（`DshProject`）在**整棵被扫代码树里
  一次都不许出现**，含注释。原判定只拦「非注释行里的绝对路径字面量」，注释里写全路径
  它放行 —— 而 0.8.7 起注释里其实已经不需要提那个路径了。已把 `lib/index.js` /
  `tools/portal_run.py` 两处注释改成中性描述（历史细节留在 CHANGELOG）。
  证伪：往注释里贴 `D:\DshProject\...` → 该条即红。

- 修正 0.8.7 一节的一处**说满的话**：那里写「改判据后只揪出 1 条真问题」，
  实际是扫描器当时只扫了 `lib/index.js` + `tools/*.py`，所以只看见 1 条；
  扩面后又揪出 `probe_button_e2e.mjs`（本节修复）。

### Docs

- `RELEASING.md` 增加发货前守卫：`lib/ tools/ client/` 里不得出现 `DshProject`，
  且 `client/` 必须被扫描覆盖。

## 0.8.7 (2026-10-16)

用户：「把默认值改为空值，再发布」。

### Fixes

- **`repoPath` 默认值不再预置作者本机路径**（原 `D:\DshProject\ld-rl-poker`）。

  那是「第一用户」的机器路径，对任何别人都不成立。更糟的是它**看起来像配好了** ——
  界面不报错，用户以为装完即可用，实际 `pythonFor` 会去那台并不存在的机器上探
  `.venv313` / `.runtime`，全落空后静默回落到 PATH 的 python，拉服务时用的是错的解释器。

  改为三处默认值为空：
  - `lib/index.js` 的 `DEFAULT_REPO`
  - `tools/portal_run.py` 的 `DEFAULT_HOST_REPO`
  - `tools/start_public_gui.py` 的 `DEFAULT_HOST_REPO` / `DEFAULT_PYTHON`

  `portal_run.py`（新门户）里 `host_repo` **只写进状态给界面显示**，服务清单走
  `runs/portal_registry.json`，所以留空不影响启动 —— 已实测：空 `repoPath` 下
  `startPublic` 成功、端口在听、`HTTP 200`、返回的是「对外服务门户」。

- **`pythonFor` 在 `repoPath` 为空时不再拼相对路径**。

  `join("", ".venv313", "Scripts", "python.exe")` 会得到 `.venv313/Scripts/python.exe`
  这样一个**相对路径**，`existsSync` 按进程 cwd 解析 —— cwd 下恰好有同名目录就会
  误命中，等于拿一个不是用户意图的解释器去拉服务。现在空值直接跳过宿主仓库那两个
  候选，回落到 PATH 的 python。

- **旧启动器（`start_public_gui.py`）在宿主仓库为空时给出可操作提示**，
  而不是让 `os.path.isdir("")` 打印「宿主仓库不存在：」这种空路径。现在会列出
  三条可行做法（设置页 `repoPath` / `SERVICE_HOST_REPO` / 自写 `services.json`）
  并返回 2。`--python` 缺省值为空时的提示也单独写清楚了，不再出现
  「未找到 ，改用 …」这种带空路径的话。

- **`tools/shoot_portal.py` 的 Chrome 路径改为按平台探测**（原本写死
  `C:\Program Files\Google\Chrome\Application\chrome.exe`，只有作者的 Windows 机器成立）。
  新增 `find_chrome()`：`$CHROME` 环境变量优先，其次 macOS / Windows / Linux 的常见
  安装位置。

### Tests

- 新增 5 条控制检验（`test/host.test.mjs`，50 → 55 项；全仓 78 → 83 项）：
  - `repoPath` 默认为空字符串
  - 运行期代码（`lib/` + `tools/*.py`）不得把绝对路径当**取值来源**
  - 配置 schema 的 `repoPath` 默认值不得是作者本机路径
  - `pythonFor` 在 `repoPath` 为空时不拼相对路径（用 cwd 下的诱饵目录反向验证）
  - `pythonFor` 在 `repoPath` 非空时仍照旧优先 `.venv313`（防修过头）

  每条都用**退回旧写法**验过会失败。

  > 第二条的判据是「不得作为取值来源」，不是「不得出现这几个字」——
  > 第一版按「出现盘符路径就报」写，跑出来 5 条里 5 条都不该报（注释里的举例、
  > `os.environ.get("SystemRoot", r"C:\Windows")` 这类系统路径兜底）。
  > 改判据后只揪出 1 条真问题（`shoot_portal.py` 的 Chrome 路径），已修。

### Docs

- README / README.en.md 的配置表：`repoPath` 默认值改为「**空**」并标注必须自己填。
- `services.example.json` 的 `hostRepo` 改为占位路径并补说明（该文件不随 npm 包分发）。

## 0.8.6 (2026-10-16)

发布前核查 awesome-dsh-plugin 收录要求时，查出**发布通道上一个致命缺陷**，
以及两处不合规声明。都不影响本地 `link:` 开发形态 —— 这正是它们一直没被发现的原因。

### Fixes

- **npm 包缺少 `tools/`，装到用户机器上根本起不来（发布通道致命）**。
  `package.json` 的 `files` 白名单里没有 `tools`，于是 `npm pack` / `npm publish`
  打出来的包里**一个 Python 脚本都没有**（11 个文件、286 kB，全是 lib/ 与文档）。
  而 `lib/index.js` 是靠 `infraPath/tools/portal_run.py` 启动门户的。

  实测（装 tarball 后读状态）：

  ```
  找不到 .../node_modules/dsh-service-portal/tools/start_public_gui.py
  （外网启动器不在该仓库，或 infraPath 配错）
  ```

  即：用户 `dsh plugin add dsh-service-portal` 装完，点「开启」必然失败。

  **为什么此前没暴露**：唯一验证过的安装方式是 `link:` 本地链接 ——
  符号链接指向真实仓库，`tools/` 一直在。开发形态恰好是唯一不暴露问题的形态。
  修法：`files` 加 `"tools"`，并补打包契约断言（见下）。

- **`@deepseek-ai/cordis` 的 peer 范围是 `>=4`，会静默排除所有预发布版**。
  node-semver 只在范围里**某个比较符**与该版本的 `major.minor.patch` 元组完全一致、
  且自身带预发布标签时才放行预发布版，所以 `>=4` 匹配不到 `4.0.5-alpha.1` /
  `4.0.5-alpha.2`，用户在预发布版 harness 上装会撞 `ERESOLVE`。改成
  contributing.md 给出的显式 `||` 分支写法：

  ```jsonc
  "@deepseek-ai/cordis": ">=4.0.1-rc.1 <4.0.5-0 || >=4.0.5-alpha.1 <5.0.0-0"
  ```

  用**两段式**而不是逐个枚举预发布版：`4.0.5-alpha.3`、`4.0.5-rc.1` 这类将来发布
  的新预发布版会被自动吸收，不必再改 package.json（逐个枚举的写法在上游发新预发布版
  时会重新变成「静默排除」）。已验证放行 cordis 全部 9 个已发布版本、拒绝 `5.x`。

- **`@deepseek-ai/schemastery` 改为「peer 声明 + dependencies 兜底」**。

  原来只在 `dependencies` 里 pin 死了 `3.18.4`，不合规（contributing.md 要求官方包
  声明为 `peerDependencies`，否则可能与宿主装出两份实例）。

  ⚠️ **但只改成 peer 是错的 —— 这一步差点把插件改坏，必须记下来。**
  本仓库把 schemastery 标成 `optional` peer，而 pnpm 会**直接跳过** optional peer，
  一个都不装。于是：

  ```
  profile vp-a：仅 peer 声明，无 dependencies 兜底
    node_modules/ 下只有 dsh-service-portal
    -> import "@deepseek-ai/schemastery" ERR_MODULE_NOT_FOUND，插件整个加载不了
  profile vp-b：peer 声明 + dependencies 兜底
    node_modules/ 下出现 @deepseek-ai/schemastery -> 加载成功
  ```

  **是 `dsh plugin add` 实装进一次性 profile 才查出来的**：76 项单测当时全绿，
  因为单测跑在开发检出上，本地 node_modules 里那份一直在 —— 与上面 Defect A
  同一种「开发形态恰好看不见」的陷阱，同一个发布日里踩了两次。

  最终形态为两者并存（peer 让宿主已有的那份可被复用，dependencies 保证宿主没提供时
  也能跑），与已收录的 `DDDMUC/dsh-free-search` 同形：

  ```jsonc
  "peerDependencies": { "@deepseek-ai/schemastery": ">=3.18.1-rc.1 <3.18.5-0 || >=3.18.5-alpha.1 <4.0.0-0" },
  "dependencies":     { "@deepseek-ai/schemastery": ">=3.18.4 <3.18.5-0 || >=3.18.5-alpha.1 <4.0.0-0" }
  ```

### Features

- 新增 9 条**打包契约**控制检验（`test/client.test.mjs`，19 → 28 项）：
  - `tools/` 必须在 `files` 白名单里
  - 两个运行期入口脚本必须存在
  - `portal_run.py` 的本地 import 闭包 8 个文件必须齐全
  - `files` 白名单每一项都必须真实存在（写错名字会被 npm 静默忽略）
  - 官方 `@deepseek-ai/*` 必须声明为 `peerDependencies`
  - `schemastery` 必须在 `dependencies` 里有兜底（上面那次事故的正面断言）
  - `cordis` peer 范围必须放行全部已发布版本、且拒绝 `5.x`
  - `schemastery` peer 范围必须放行全部已发布版本、且拒绝 `4.x`
  - **产物里每个 bare import 都必须有对应声明** —— 这条是那次事故的通用化收口：
    静态解析 `lib/` 下**全部** `.js` 的 import（`import x from` / `import "p"` /
    `import("p")` / `require("p")` / 模板字面量，且不限行首），逐个要求能在
    `dependencies`/`peerDependencies` 里找到归属（宿主注入的 `react` 走显式白名单），
    相对导入必须真实存在。今后「加了 import 却忘了声明依赖」会当场失败。

    > 初版这条只扫 `lib/index.js` + `lib/client.js`，且正则漏掉 `await import("p")`
    > 这类不在行首的动态导入 —— 被发布前的对抗性复核当场指出并补齐。
    > 记在这里是因为它说明一件事：**「我已加了兜底检验」本身也需要被验**。

  每条都用**退回旧写法**验过会失败（可证伪，不是装饰）。

- 新增 `test/lib/semver-range.mjs`：极简 semver 判定器，用于 peer 范围断言。
  不引第三方测试依赖（CI 只装 schemastery），且**认不出的语法一律抛错**，
  而不是「看着像就放行」——`>=4`、`^3.18.4`、`4.x` 都会直接抛错；
  非法版本（前导零如 `1.2.3-alpha.01`，node-semver 判 false）同样抛错，
  不会静默给出一个错的布尔值。已与真 `semver` 对比
  **2808 组用例（含 alpha/beta/rc × 数字标识符的预发布组合）、0 处差异**。

### Docs

- 修正测试数字漂移：README 两处「24 / 17 项」与「46 项」→ 实测 **50 / 28 项**；
  README.en.md 同步；RELEASING.md 的「18 / 14 项」→ **50 / 28 项**；
  `test/acceptance_portal.py` 的「29 项」→ 实跑 **30/30**（README.md 两处 + README.en.md）。
- README / README.en.md 的控制检验概述改为与仓库实际一致
  （26 个 Python 控制检验脚本 + 8 个端到端脚本 + 78 项 Node 检验）。
- 新增「界面」章节与截图：`docs/assets/` 三张（窄屏浅色 / 窄屏深色 / 宽屏）
  由 `tools/shoot_portal.py` 用**真门户进程 + 无头浏览器**实拍；根目录
  `screenshots.json` 按注册表约定声明（awesome-dsh-plugin 推荐项）。
  README 里用**绝对 URL** 引用这三张图：`docs/` 不在 npm 包的 `files` 白名单里，
  相对路径在 npmjs.com 上会裂图。
- RELEASING.md 第 7 步补上 `tools/` 的发布前断言（`npm pack --dry-run` 必须看到
  两个入口脚本），否则 v0.8.6 修掉的「包里没有运行期脚本」可以无声复现。

## 0.8.5 (2026-10-16)

用户：「访问页我看也没有符合要求变成一个只读的测试页，并且这个页面也需要美化，
并需要增加一个 鼓励一下的连接」。

### 先核事实：页面**早就是只读的**了
我把线上 8899 的 HTML 抓下来，把**每一个可交互元素**列出来核对：

```
<button class="copy" data-copy="...">×4      ← 复制
<a class="btn primary" href="/realapp/">×4   ← 访问
```

零 `<form>`、零删除/编辑、零开启/关闭、零 `/_api/services/`。0.8.2 就已经改成
只读了。**但用户的感觉是对的**：那个页面**只给链接、不能测** —— 它读起来是
「入口页」，不是「测试页」。所以这一版补的是**测试能力**，不是删管理入口。

### 让它真的成为一个「测试页」
每个节点两张动作：「访问」（跳走）和「测试」（**就地**探一次，结论写进卡片）。
为什么不是把「访问」当测试：访问是跳走，上游没起来时门户回的是 502 纯文本，
用户看到一片空白，分不清"是门户坏了还是我的程序没起"。测试就地给结论。

三种结论必须**分开**（真机用 Chrome 逐个点过，三种都对且各不相同）：

| 上游状态 | 页面结论 |
| :--- | :--- |
| 活着 | 通了：HTTP 200 |
| 没启动 | 不通：HTTP 502 —— **请用它自己的方式启动那个程序** |
| 在线但自己 502 | 上游有响应，但它自己返回了 HTTP 502 —— 在线，看它自己的日志 |

最后两条状态码**都是 502**，只能靠正文区分（门户自己发的那条固定含
`Bad Gateway` + `上游`）。分开说是必须的：把上游自己的错报成「没启动」，
用户会去启动一个本来就在跑的程序。这个契约由 `check_portal_probe.py` 钉住。

### 我自己写错、被检验抓到的两个 bug
1. **`data-probe` 变成 `%2Falpha%2F`**：探测路径用了 `urllib_quote(safe="")`，
   把分隔用的 `/` 也编码了。于是点「测试」请求的是一个"名字里带斜杠的段"，
   门户按 mount 匹配不上，**永远 404** —— 而页面看起来完全正常。
   修法：新增 `path_quote(safe="/")` 专用于整条路径，与单段的 `urllib_quote`
   严格分开（两个函数混用就是 bug，已各钉一条断言）。
   反例已验：改回 `urllib_quote` -> 3 项转红、18/21；还原 21/21。
2. **`redirect:"manual"`**：按 Fetch 规范那返回 opaque-redirect，`status` 恒为 0。
   而"上游把 / 重定向到 /login"极其常见，会把一个正常服务报成"状态 0"。
   改为默认跟随，拿真实状态码。

### 美化
- 颜色全部改成语义令牌（`--brand/--ink/--line/--ok/--warn/--bad`），深浅色各一套
  令牌，不再在结构里写裸 hex；
- 触控目标 44px（手机拇指）、键盘 `:focus-visible` 焦点环、
  `prefers-reduced-motion` 关掉过渡；
- 状态从「圆点+文字」改成**胶囊徽标**（开放中/上游未响应/已屏蔽），
  一眼能扫；
- 窄屏（≤420px）收窄内边距、二维码 172→140；
- 复制按钮点完给"已复制"反馈（原来点了毫无反应，用户无法确认）。

### 页脚「鼓励一下 ★」
与插件设置页那个链接指向同一处（`tools/portal_console.py` 的 `REPO_URL`
必须和 `client/index.jsx` 的 `REPO_URL` 一致），新窗口打开 + `noopener`
（防 tabnabbing）。

### 诚实说明：**你的门户需要重启**才会看到新页面
`portal_console.py` 是 Python 模块，一 import 就固定了。我验过：你线上 8899
现在返回的仍是旧页（无测试按钮、无鼓励链接）。重启门户才会加载新代码 ——
代价是 cloudflared 隧道域名会变（你如果已经把地址发出去过，那个链接会失效）。
**我没有擅自重启你的门户**，这个决定交给你。
（另外 `tools/shoot_portal.py` 可以在临时端口用新代码起一个真门户来看效果，
不用碰你正在跑的那个。）

### 检验
- 新增 `tools/check_portal_probe.py`（21 项）：页面结构 + 服务端契约 +
  真上游/真门户端到端（200 / 402 / 上游自己的 502 / 302 四种情况）。
- 新增 `tools/check_probe_button_browser.py` + `tools/probe_button_e2e.mjs`：
  **CDP 驱动真 Chrome 真点按钮**（不装任何第三方包，只用 Node 内置
  `WebSocket`/`fetch`），逐节点核对三种结论文案。
- `check_portal_console.py` 41 项：补测试页、页脚、美化的断言。
- 全量：26 项控制检验 + 50 host + 19 client + 8 e2e 全通过。

## 0.8.4 (2026-10-16)

用户：「页面你还是要看下，需要调整一下，因为宽度变了，此外设计，美观的细节
调用插件再美化完善一下」。

### 宽度：注册位置换了之后没跟着改
`maxWidth: 560` 是在"宿主设置的一整页"时代定的。0.8.3 把注册位置挪到插件页
的配置区后，可用宽度从约 560 变成约 900–1000 —— 结果卡片在宽栏里缩成一条窄柱：
二维码挤在中间、右侧大片留白、标题与「鼓励一下」挤在一起（用户截图就是这个）。
- 卡片改为用满可用宽度 + 上限 880（再宽行长过长）；
- **局域网与公网两栏并排**（`grid` + `auto-fit`）：它们是同一张页面的两条入口，
  本来就该并排看；原来竖着叠，两个二维码加两块开关要滚很久；
- 窄屏（≤720px）自动塌成单栏，二维码 176→132（手机上 176 会占掉半屏）。

### 美化：把外观从内联 style 迁到一份注入的 CSS
之前的按钮**点了毫无反应**、也没有键盘焦点环 —— 因为外观全用内联 `style`
写死，而**内联压不过 `:hover`/`:focus-visible`/`@media`**（这是硬约束，不是我
偷懒）。照 workbuddy 的做法（`WorkBuddyCard` 模块加载时注入一个 `<style>`）：
- 新增 `.dsp-*` 类体系（`dsp-card/duo/pane/btn/primary/danger/access/switch/
  knob/input/select/svc/link/qr`），类名统一 `dsp-` 前缀避免与宿主撞车；
- 注入是**幂等**的（按 `data-plugin-css` 查重，重挂载不会越堆越多），
  失败只 `console.error`、不让面板挂掉；
- 补上规范要求的交互态：**hover**、**focus-visible 焦点环**、
  **disabled 弱化**、**prefers-reduced-motion**；
- 四个按钮原语的 style 对象清空（`primary/btn/danger/accessLink: {}`）——
  留一行注释说明"为什么不能再内联"，免得以后有人又把底色写回去。

### 顺手修掉三处「预览骗人」与文案失真
- **预览 harness 把 `className` 当字面量属性**（设成 `className="..."` 而不是
  `class="..."`），改成类体系后预览会画出一个**和真实渲染完全不同**的页面
  （栅格不并排、hover 没有）。这种"预览骗人"比没有预览更糟，已修。
- 公网风险提示还写着「拿到口令的人可以**启停**你开放的服务」—— 启停能力在
  0.8.2 已按用户要求取消，照抄旧文案会**夸大风险**、也让人以为插件能操作进程。
  改为「可以增删、开放或屏蔽你发布的节点，但动不了上游程序」。
  （写检查时踩到：旧说法还留在注释里解释"为什么不能这么写"，
  所以断言必须判**字符串字面量**而不是裸文本。）
- 公网区块底部重复了一遍"域名每次都会变"，与上面那块同义，删掉。

### 顺带抓到一个真 bug：**第二次点「停止」失败**
用户重启 DSH 后，`test/test_host_buttons.py` 从 SKIP 变成 FAIL（真机验证通道
打开了），暴露出：
- `serve_forever` 先起（端口开始监听），而 `shutdown_holder["fn"]` 晚得多才装 ——
  中间夹着隧道建立 + 一次可能重试约 2 秒的 `save_state`（沙箱里写 `runs/` 是
  Errno 13）；
- 那个窗口里 POST `/_api/shutdown` 命中 `fn is None` → **503「门户还没就绪」**；
- 宿主判 `asked=false` → 退到 `portal_run.py --stop` 兜底；而兜底子进程在沙箱里
  taskkill 看不见门户、读不到状态文件，回一句"门户未在运行" ——
  于是**报错、门户还活着**。`stoppedBy=stop-command` 就是这条路。
- 修法：把 `stopped` / `shutdown` / 信号注册 / `shutdown_holder` **全部提前到
  serve_forever 之前**，让"端口开始监听"与"能接受关闭请求"同时成立。
- 新增 `tools/check_shutdown_self_exit.py`（8 项）：含**源码顺序**断言（钩子必须
  早于 serve_forever）与**实测**（端口一在听就立刻打 shutdown，必须是 2xx 而不是
  503）。**反例已验**：把钩子赋值注释掉，该检验 5 项转红、3/8；还原后 8/8。

### 检验
- parity 新增 12 项（宽度不用满/两栏并排/窄屏塌单栏/焦点环/hover/禁用态/
  reduced-motion/幂等注入/按钮外观不内联/类前缀），共 147 项。
- `test/test_public_link.py` 的两条"免密直接见控制台"原来判 `name="mount"`
  （添加服务表单的字段，门户页 0.8.2 已改只读、表单被删）—— 判据换成
  "是门户页且没有口令输入框"，**没有删掉断言**（那会让"本机/内网免密"这条
  安全边界失去守卫）。
- 全量：24 项控制检验 + 50 host + 19 client + 8 e2e **全通过，0 跳过**。

## 0.8.3 (2026-10-16)

用户：「插件设置要放到插件设置里，而不是出现在宿主的设置里，你看看 workbuddy
是怎么做的」。

### 找到了 —— 我注册错槽位了
实测（`cordis_inspect` 查活的 Slot 树）：

| | 我（原样） | workbuddy |
| :--- | :--- | :--- |
| 槽位 | `settings.section` | `plugins.bundle.config` + `plugins.row.config` |
| 出现位置 | **宿主设置的左侧导航**（和「通用 / 模型 / 插件」并列） | **插件页里该插件自己那页** |

`settings.section` 的 occupants 里原先明明白白有
`{ registrant: "dsh-service-portal", id: "service-portal", order: 40 }` ——
所以我做的其实是"宿主设置里的一个独立页面"，而不是"这个插件的设置"。
workbuddy 与本地兄弟 `dsh-subagent-default-model` **完全不用** `settings.section`。

### 改法
- 改注册 `plugins.bundle.config`（bundle 页里的配置区）与
  `plugins.row.config`（行入口的独立配置页，键是 `<包名>#<行 id>`）；
- **两种包名拼写都注册**（裸名 + `include:` 前缀）：插件页按 key 精确匹配库存
  里的包名，而部署可以用任意名字挂载 —— workbuddy 的 issue #55 就是只注册了
  裸名、实际挂在 `include:` 前缀下，结果**整页空白且不报任何错**；
- 每个槽位独立 try/catch（一个失败不带下另一个），失败时 `console.error` 写明
  是哪个槽位哪个 key —— 让"没出现"和"成功了"可区分；
- 处理 `view` 属性：`summary` 只回一行摘要（插件页折叠态），`page` 出完整配置页。

### 一个差点踩中的坑
我一度把 `settingsScope` 加进 `inject`，想让配置卡片能用宿主的保存控件 ——
**这会让整个插件静默失效**：Cordis 的 inject 是硬依赖闸门，列了本运行线不提供
的服务，`apply` 就永远不会执行。而且本线（0.1.7+）已用 `configForms` 取代
`settingsScope`。workbuddy 的注释明确警告了这点。已改回只注入两条线都有的服务。
（要探可能不存在的服务只能用 `ctx.get()`；直接写 `ctx.settingsScope` 会**抛异常**。）

### 检验
- `test/client.test.mjs` 新增**行为断言**（19 项）：真的执行产物里的 factory、
  真的调 `apply(mockCtx)`，然后断言注册收到的 `name`/`key`。
  为什么要这么做：只做源码正则的话，正则只能证明"字符串在文件里"，证明不了
  "注册真的发生了、键的形状对" —— 本轮正是栽在这，正则一路绿灯而位置是错的。
- **反例已验**：把注册临时改回 `settings.section`、重新构建，该测试确实转红
  （`没有注册 plugins.bundle.config；实际=["settings.section"]`），
  还原后转绿 —— 证明它不是"永真"的测试。
- parity 校验新增 8 项（含"不再注册 settings.section"的反向断言），共 134 项。
- 全量：23 项控制检验 + 50 项 host + 19 项 client + 7 项 e2e 全通过。

## 0.8.2 (2026-10-16)

用户一口气定了六条，其中**第 2 条纠正了我上一版的理解**：

> 「我们添加的节点是做在插件设置里的，每个节点都有屏蔽和开放的开关，
>  不是服务开启的开关」「启动服务是服务本身的事情，这里只是负责可以路由」
> 「如果是负责启动和停止，还需要配置对应的启停程序，暂不处理」

这句话把我上一版的语义纠对了：我原来把开关做成"启停服务"（会去
`supervisor.start()` 拉起进程），于是"开放"一个没配 script 的节点会报
「没有配 script，无法拉起」—— 用户以为功能坏了。**正解是"路由闸门"**：
开关只决定门户要不要把请求转过去，上游程序归用户自己的启动方式管。

### 修掉一个真 bug：「添加服务后看不到」（用户报的）
宿主 `readPortalStatus` 只在 `needLive` 为真时才去问活着的门户要实时状态，
而那个条件只看「有没有内网地址/口令」—— 那两样在状态文件里**一般都有**，
于是条件恒为假，**从来不去问活门户**。服务清单只在门户内存里（状态文件
从不写它），所以 `services` 永远是空数组。

实测证据：用户加了一个节点，门户 `/_api/state` 报 4 个服务（含新加的），
宿主 `/status` 的 `services` 却是 0。修法是判据里加上 `!Array.isArray(state.services)`。
新增 `tools/check_portal_status_running_services.py`（6 项）钉住它，
含反例（门户没跑时必须是空数组，不许凭空编造）。

### 开关改为「开放 / 屏蔽」（路由闸门，不启停上游）
- 门户侧 `enable/disable` 与新增的 `open/block` **只改注册表的 enabled**，
  `supervisor.start()/stop()` 全部移除；
- `ServiceSupervisor` 整块删掉（按 script 拉起/停止子进程那套）；
- 启动时不再按 `autoStart` 拉起服务；删除节点不再顺手停上游进程；
- `restart` 动作取消（那是启停语义），调用会明确回
  「不认识的动作 restart（本插件只管路由开关：open/block；不再启停上游程序）」——
  比只回一句"未知接口"更让人明白这是有意的。
- 新增 `tools/check_gate_does_not_stop_upstream.py`（17 项）：起一个**真上游
  进程**（探针 HTTP 服务），验证「屏蔽 → 上游 PID 仍活着 + 绕过门户直连仍通
  + 门户不再转发（404）」「删除节点 → 上游仍活着」。

### 每个节点加「访问」；地址旁「复制」边也加「访问」
- 节点卡上「访问」是主线（品牌色实心），点了直接在新标签打开该路由；
  屏蔽时不给链接（确实不转发），显示为不可点的灰按钮并说明原因。
- 局域网地址与公网地址那一行，`复制` 旁边各加一个「访问」（品牌色描边，
  与灰色「复制」区分开）——共 2 处，parity 校验按 `accessLink` 出现次数钉住。
- 「访问」地址用**门户地址 + 路由路径**拼（不是上游地址）：对外可用的入口
  是门户的路由，上游 `127.0.0.1:2460` 只有本机能开。

### 取消自动发现、取消「刷新」
- 删掉 `tools/portal_discover.py` 与 `tools/check_portal_discover.py`、
  门户 `/_api/discover`、宿主 `/discover`、面板的发现界面与勾选逻辑。
- 删掉面板「刷新」按钮（节点清单本来就随 5 秒轮询自动更新）。
- 只保留**手动添加**：「添加节点」表单填名称/对外路径/本机端口/备注。

### 门户页面改为只读（测试页 + 引导页）
- 删掉页面上的添加表单、开启/关闭、编辑、删除（`_service_form` 整块移除，
  `/edit` 那个本来就 404 的死链接也随之消失）。
- 保留「访问」——那正是"测试这个节点通不通"的动作，也就是测试页的用处。
- 新增「怎么管理」区块：说明本页只读、要管理请到
  **设置 → 对外服务门户**，并讲清「屏蔽」只表示门户不再转发、
  **不会**停止上游程序。
- 状态文案区分**两件事**：这条路是否开放（已屏蔽 / 开放中）、
  上游是否响应（上游未响应 + "请用它自己的方式启动该程序"）。

### 检验
- 全量：23 项控制检验 + 50 项 host 测试 + 17 项 client 测试 + 7 项 e2e 全通过
  （`test_host_buttons` 因宿主未重启按纪律跳过返回 2）。
- parity 校验重写第 ⑥ 节（33 项钉住新语义），共 126 项；
  其中"不再启停上游"用**可执行代码**判据（无 `class ServiceSupervisor`、
  无 `supervisor.` 调用），不当成"注释里提了这个词"就算失败。

## 0.8.1 (2026-10-16)

用户问：「手动添加的内容，会保存在哪里呢？你测试成功过吗」。

### 保存在哪里
`<仓库>/runs/portal_registry.json`（可用 `PORTAL_RUNS_DIR` 覆盖，测试就靠它
隔离）。UTF-8、原子写（同目录临时文件 + `os.replace`），所以断电/崩溃不会
留下半截文件。每条包含 key（从 mount 派生，用户不必填）/ name / mount /
target / enabled / autoStart / script / cwd / note。

顺带澄清一个**假象**：在 PowerShell 里 `Get-Content` 这个文件会显示成
`鐪熷疄搴旂敤` 这样的乱码 —— 那是控制台用 GBK 解码 UTF-8 的显示问题，
**文件本身是对的**（用 Python 按 UTF-8 读就是「真实应用」）。差点被这个
假象误判成"中文没存对"。

### 测试成功过吗 —— 分三层，逐层都测了
之前只验到中间层，这次补齐，而且**判据是磁盘内容**（不是接口返回）：
  1. **转发函数层**：`postPortalJson` 把请求送到门户 → 注册表被创建、
     中文/上游/备注无损落盘、**重启门户后仍在**（证明是持久化而非内存）。
  2. **宿主 HTTP 路由层**（新增 `tools/check_portal_add_route.py`，10 项）：
     把真实 `createHandler` 挂到真 HTTP server 上，用**与面板完全相同的请求**
     打 `POST /service-portal/api/services/add`。为什么要多这一层：路由的
     匹配与参数解析是另一段代码，它错了同样会让"手动添加"失败，而只测
     转发函数发现不了 —— 本项目有前科（局域网开关就是"函数层没问题、
     路由层把字段漏了"）。顺带验了启停/删除/发现与**反例**
     （target 非法时 HTTP 400 + 明确 error，不许假成功）。
  3. **真机**：用户自己的门户（8899）在跑，但宿主进程仍是旧代码
     （`/status` 里没有 `services` 字段），所以**面板上的实际点击效果还没在
     真机验证过** —— 需要重启 DSH 才能验。这一点如实记录，不假装测过。

### 检验
- 新增 `tools/check_portal_add_route.py`（10 项）：宿主路由层端到端。
- `test/host.test.mjs` 现有 50 项 + `check_portal_*` 21 项全通过。

## 0.8.0 (2026-10-16)

用户：「在插件设置里，能把控制台的功能做了吗？这样就不需要独立控制台了，
在插件设置里提供刷新当前系统服务、自动发现、手动添加某个服务这种功能」。

### 服务管理搬进设置页（控制台的核心功能）
设置页新增「开放中的服务」区块，原来只有一句「打开控制台」的入口：
  · **服务清单**：每个服务一张卡（状态点 / 名称 / 路由 / 上游 / 备注 + 启停编辑删除）；
  · **刷新**：立刻取一次最新清单（清单本来也随 5 秒轮询自动更新，这个按钮给的是
    "我就要现在这份"的确定动作）；
  · **自动发现**：扫描本机在听的端口，列出像 Web 服务的候选；
  · **手动添加**：名称 / 路由 / 上游 / 备注，就地填。
数据来自宿主 `/status`（转发门户的服务清单），所以面板不必再开控制台。

### 自动发现：做了**安全分级**（这是本功能最容易出事的地方）
实测本机扫出 16-18 个"像 Web 服务"的端口，其中一批**绝不能一键发布**：
  · `19387` / `2462-2465` = **DSH 自己的界面** —— 发布等于把整个开发环境挂公网；
  · `20241` = **本项目自己的 cloudflared 隧道** —— 发布会让请求成环；
  · `8738` / `7897` = clash 代理 —— 发布等于开放翻墙入口；
  · `443` / `1042` / `9013` / `9014` = VPN / 厂商常驻服务；
  · `35600` / `37600` = ToDesk 远程控制 —— 发布等于把远程桌面入口开放。
所以发现结果**不是**"可添加的服务"，而是**带风险档的候选**：
  · `ok` 可推荐 / `caution` 谨慎 / `danger` 绝不推荐（附原因）；
  · 界面上**只默认勾选 `ok`**，`caution`/`danger` 必须用户显式勾选；
  · 判定按**进程名**而不只是端口号（隧道端口每次都会变，写死端口会漏），
    这正是"cloudflared 一开始被判成 ok"那个坑的修法。
发现是**只读**操作：不改注册表、不添加任何服务。

### 顺带修掉控制台里发现的两个真 bug（同一套逻辑）
  · **上游死了却显示绿色「已启用」**：判定顺序把 `enabled` 放在 `alive` 之前，
    实测 realapp（上游 2460 无进程）显绿。现在 `alive` 优先，显示琥珀
    「上游未响应」，并直接告诉用户"请先把那个程序启动起来"。
  · **「访问」点了 502**：现在只在"开着且上游活着"时才给访问链接 ——
    能点却打不开比不给链接更让人困惑。

### 检验
- 新增 `tools/check_portal_discover.py`（25 项）：分级函数对 11 种真实进程名
  的判定（含本机实测到的 DSH / cloudflared / clash / ToDesk / Armoury）、
  门户端口与 exclude 排除、系统端口表、真起一个 HTTP 服务验证能被发现且判 ok、
  本机危险项确实标 danger、发现过程不改注册表。
- 新增 `tools/check_portal_service_api.py`（9 项）：门户侧增删启停发现全通，
  外加**反例**（门户没跑时 `getPortalJson` 必须返回 ok:false，不许假成功）——
  上一轮局域网开关就是栽在"宿主静默忽略、界面还弹成功"上。
- `check_portal_parity.py` 增加 15 项钉住"控制台功能在设置页里"与安全边界
  （危险项默认不勾、删除二次确认、访问链接的条件、宿主转发路由），共 115 项。
- `test/host.test.mjs` 增加 2 项（`services` 透出与 `servicesDegraded` 口径；
  门户没跑时是空数组而不是 undefined），共 50 项。
- 全量回归 0 失败（`test_host_buttons` 因宿主未重启按纪律跳过返回 2）。

### 尚未做（等确认）
手机扫码后到达的那个控制台页面**仍在**（它还有"看服务、点进去"的用途）。
是否把它降级成只读目录、去掉里面的管理表单，等确认后再动。

## 0.7.9 (2026-10-16)

用户指着「服务控制台 / 停止门户 / 刷新 / 那条黄字」说：「这里设计的好看点」。
那是设置页的最后三块，问题不在配色而在**结构**。

### 按钮右边挤着说明 → 动作与说明分层
原来「打开控制台」按钮右边紧跟一句"在控制台里添加服务…"，窄面板下被按钮
挤断，读起来像按钮标签的一部分；「停止门户 / 刷新」那一行还在一行里同时
塞了"能做什么"和"会有什么后果"，主次不分。
现在：新增 `actionRow`（按钮行只放按钮），说明文字一律**另起一行**当副文本。

### 三个动作区看不出边界 → 各自有小标题
「服务控制台」下面直接跟按钮和说明，再往下「停止门户」那行没有标题 ——
视觉上像同一段里的两拨按钮。
现在拆成两块，各有小标题：「服务控制台」（打开）与「门户进程」（停止 / 刷新）。

### 一条长黄字讲了三件事 → 一块只讲一件，且放在**能做那件事的地方**
原来页尾是一条琥珀色长句，把"公网风险 / 局域网免密 / 去点关闭公网"三件事
挤在一起，既像报错又像注脚；更矛盾的是**未开公网时它在教用户点「关闭公网」**，
而那个按钮那时根本不在。
现在：
  · 公网风险**合并进「公网访问」区块**（用户管理公网的地方），与"临时地址、
    勿收藏"合成一块 —— 同主题不再分置页面首尾；
  · 页尾只留「局域网免密」这一条 —— 它是**跨区块**的全局安全姿态，不属于
    任何单一区块；
  · "局域网也要口令"删掉：上面「局域网访问密码」已经写着状态了，复述是冗余。

### 不再用 emoji 当结构标记
`⚠️` 从警示块标题里去掉。"这是警告"改由**结构**承担：左侧色条 + 加粗警示色
标题（设计规范：结构图标用矢量/结构表达，不用 emoji）。

### 检验
- `check_portal_parity.py` 新增 8 项钉住上面的排版意图（动作与说明分层、
  两块各有标题、公网风险去重、未开公网不出现"点关闭公网"、不用 emoji 当结构）；
  并把两条**绑字面量**的旧断言改成断言**含义** —— 文案被润色两次，
  绑字面量会把"改进文案"变成"检验失败"（共 101 项）。
- 全量回归 0 失败（`test_host_buttons` 因宿主未重启按纪律跳过返回 2）。

## 0.7.8 (2026-10-16)

用户：「公网也要能设置自定义密码，体验和局域网一样，但是公网要有警告提示，
这个你学习一下 dsh-pocket 的体验」。

### 公网密码可以自定义了（与局域网对称）
原先公网密码只能"每次开启自动换新"，想设个记得住的只能去控制台。现在设置页的
公网密码行末尾有「自定义」（dsh-pocket 的 `customBtn` 同位置），点开就地输入、
回车保存；自定义之后状态标成「自定义」，并提示"开启公网不再自动换新"。

体验与局域网一致的地方：
  · 同一个位置、同一套交互（输入框 + 保存/取消 + Enter/Esc）；
  · 自定义后显示提示（局域网是"不再自动换"）；
  · 「刷新/换回随机」出口 —— 自定义不是单向状态，否则永远回不到自动轮换。

与局域网**故意不同**的地方（安全）：
  · 门槛 ≥12 位（局域网 6–12 位数字）。公网面对整个互联网，长度是主要防线；
  · 不限制字符种类（12 位纯数字也接受）—— 用户要的是"体验一样"，
    替用户做绝对化限制反而不让他设自己记得住的密码；
  · **拒绝"公网密码 = 局域网口令"**：局域网口令会传给同一 WiFi 的设备，
    拿它当公网凭据等于把内网口令公开。

关键实现：改口令**立即生效、不重启门户**（`password_provider`，与局域网
`lan_password_provider` 同一套机制）。若要求重启才生效，就会换掉 trycloudflare
域名 —— 而用户的典型场景恰恰是"地址已经发出去了，再改个记得住的密码"。
自定义口令会落盘、且列进 `KEEP_ON_STOP`，重启/停止门户都不丢。

### 公网警告提示（学 dsh-pocket）
按 dsh-pocket 的形态做成**左侧色条 + 浅底的警示块**，不是一行灰字（一行会被略过）：
  · 地址是临时的（每次开启都变、关闭或重启后失效、可能被陌生人复用为别的网站）
    → 因此**请勿收藏**，每次从本页扫"当前"二维码；
  · 拿到口令的人就能访问你开放的服务，不用时请点「关闭公网」；
  · 在"自定义密码"输入态里额外提示：改完立即生效、地址与二维码不变，
    但已登录的设备不会被踢下线（要彻底作废旧密码需「关闭公网」再开）。

### 检验
- 新增 `tools/check_public_pin.py`（18 项）：起真门户，设自定义公网密码后
  **真的用新密码登录**（会话 cookie 是判据）、**旧密码确实登不进**、
  换回随机后旧自定义失效、重启后自定义仍在；含安全负例（= 局域网口令被拒、
  太短被拒、空白被拒）。
- `check_portal_parity.py` 增加 17 项钉住上面这些体验与安全边界（93 → 现在共 110 项）。
- `test/host.test.mjs` 增加 2 项（`publicPinCustom` 透出；老状态文件缺字段时
  兜底 false，不是 undefined）。

## 0.7.7 (2026-10-16)

用户：「这里始终打不开」。查下来是**两个独立问题**，一个是真 bug。

### 真 bug：设置页局域网三项开关被宿主静默忽略
设置页的三个控件 —— 「局域网访问」总开关、「局域网访问密码」开关、
「高级 · 手动选地址」—— 都 POST 到宿主 `/settings`，而宿主那个处理函数
**只认** `passwordMode` / `fixedPassword`。局域网字段被直接无视：
返回 `ok: true`、前端弹「局域网已需要口令」的 toast，**门户那边一点没变**。

用户截图里就摆着这个矛盾：toast 说"已需要口令"，下面那行仍写着
「已关闭：同一 WiFi 扫码直连」，开关自己弹回去。
典型的"不崩、只给错误答案" —— 界面说成功了，真实状态没动。

修法：宿主 `saveSettings` 识别这三个字段并**转发给门户**
`POST /_api/settings`（这三项是门户的运行期配置，权威在门户）；
转发失败就如实返回 `ok:false`，不再假成功。

### 另一个不是插件的问题
控制台里挂的三个服务（`/realapp` 2460、`/rltrain` 8810、`/viewer` 8811）
**全都没有进程在监听** —— 点「访问」当然 502。门户本身正常
（`http://192.168.71.10:8899` 实测 200，二维码有效，隧道也通）。
这类"打不开"要先看上游服务起没起，不是插件坏了。

另外记录一个环境事实：本机两个网卡都是 **Public** 配置且**没有 8899 入站规则**，
所以局域网设备（手机）要访问 8899 需要放行入站；`127.0.0.1` 与隧道不受影响。

### 检验
- 新增 `tools/check_portal_settings_forward.py`（7 项）：起真门户，通过宿主
  `saveSettings` 改这三项，然后**问门户自己**变没变；含反例（门户没在跑时
  必须如实失败，不许回 ok:true）。
- `codeStamp` 改为**取自 lib/index.js 文件本身**（版本+mtime+大小）。
  原来只用版本号：我把 0.7.5 提到 0.7.6、而宿主内存里恰好也是"0.7.6 但缺新修复"
  的旧代码，守卫放行 → 过期代码被当成产品失败报出来。现在文件一改指纹就变。

## 0.7.6 (2026-10-16)

用户：「设置页面的字大大小小，样式难看，能不能梳理一下」。

### 字号：从"混着 4 种"收敛成一套刻度
原来面板里同时存在 11/12/13/14 —— 而且相邻级差只有 1px：**看不出层级，
只觉得忽大忽小**（1px 的差别不会产生层次，只会显得脏）。更糟的是同一个
"正文"概念在不同区块用了不同的号（按钮 13、说明 12、公告 12、标签 11）。

现在全部走 `TYPE` 刻度，只保留 4 级、单调递减：
`title 16 / section 14 / body 13 / caption 12`，12 是下限（再小在 2 倍缩放下会糊）。
字重跟层级走（标题/分区 600，正文 400）；间距收敛成 `SPACE` 的 8px 节奏
（块 16 / 行 8 / 行内 4），行内不再写裸的 `marginTop`。

### 颜色：4 个**不存在**的令牌一直在吃浅色兜底
面板原先引用了 4 个 DSH 主题里根本没有的令牌：
`--dsw-alias-label-tertiary`、`--dsw-alias-state-warning-primary`、
`--dsw-alias-button-primary-fill`、`--dsw-alias-label-primary-foreground`。
不存在的令牌永远不会命中，于是**一直**在用写死的浅色值 —— 深色模式下说明
文字和按钮就是浅色主题的颜色（对比度不够、按钮发白）。
现在统一走 `COLOR`，只用真实令牌（真实清单来自宿主 `cordis inspect Theme`），
并加了一条守卫：出现清单外的 `--dsw-*` 令牌直接判失败。

### 真渲染出图抓到的两个问题
新增 `tools/render_panel_preview.mjs`：直接 require `lib/client.js`，用最小
React 替身在无头 Chrome 里把面板**真渲染**出来（不是手写 HTML mock —— mock 只能
证明"我照着数值画了一遍"）。它抓到两处：
- 未启动时两个地址粘成一行 `...:8899http://...:8899`（`<code>` 是行内元素）；
- 「局域网访问密码」用了和「局域网访问」同级字号，父子关系读成了同级标题。

⚠ 这个工具只用于人工看图，**不是**控制检验：它的 React 是替身，文本排版不真实
（截图里标题/副标题会"看起来压在一起"，真实渲染不会）。适合看结构顺序、颜色、
胶囊形状、层级；不适合看行高与精确间距。局限已写在文件头。

### 检验
`tools/check_portal_parity.py` 66 → 76：新增「只引用真实令牌」「没有裸数字字号」
「刻度是 4 级且单调」「说明文字不小于 12」「用 COLOR 取色」「间距用 SPACE 刻度」。
其中「灰色+下划线」那条原来钉的是那个**假令牌名**，改成看意图（灰、非品牌蓝）。

## 0.7.5 (2026-10-16)

修「未开启状态很乱，感觉没有逻辑」，并修掉一个**让二维码看起来消失**的真凶。

用户第二次说「你还是恢复之前的二维码吧」。查下来代码里二维码从没删过
（0.7.4 已提交，源码和产物都有），**真正的原因是门户被停了**：局域网整块
（二维码 + 地址 + 口令）都在 `if (running)` 里面，门户一停就整块消失。
而门户为什么停 —— 是我自己的检验脚本干的：`test_autostart.py` 里一句不带
`--port` 的 `portal_run.py --stop`，按默认端口兜底扫到了用户正在跑的门户。

### 未启动状态（用户截图指出的三处硬伤）
- **`--stop` 不许乱杀**：端口兜底只在**显式**给了 `--port` 时才做；按端口杀之前
  还要先确认「这端口上是我们的门户」（`/_auth/health` 回 200 + `{"ok": true}`），
  不是就不碰。原来默认扫 8899，等于「停我这一个」变成「杀掉任何监听 8899 的进程」。
- **停止不再删光状态文件**：`mark_stopped()` 只清运行痕迹（pid/端口），保留
  局域网口令、自定义标记、网卡候选、手动选的地址。删整份会让「局域网口令重启后
  不变」失效（用户手机里存过的口令白存），设置页也再算不出"将来会用哪个地址"。
- 「启动于 xx」只在运行中显示（停着时显示它是自相矛盾）。
- 未启动时新增引导块：一句说明 + **将要使用的内网地址** + 启动按钮；
  公网区块不再放那个点不动的「开启公网访问」死按钮。
- 未启动时 `problem` 降级为普通说明（不再红字报警）；主动停止过就完全不报。

### 停止门户：原来根本没停掉（顺带查出来的）
- 宿主（DSH 插件进程）派生出来的子进程，在某些环境里与门户**不在同一个作业/
  沙箱**内：`taskkill` 直接回「找不到进程」(128)，而门户还在 8899 上应答；
  那个子进程连 `runs/portal_state.json` 都写不进去（Errno 13）。
  于是「停止」报成功、实际什么都没停 —— 一类典型的"不崩但给错误答案"。
- 对策：门户新增 **`POST /_api/shutdown`（只允许本机来源）**，改由宿主直接
  HTTP 请门户**自己退**，可靠且不受作业隔离影响；`--stop` 退化成兜底。
- 局域网/公网来源请求自退一律 403（不能让手机把门户关掉）；GET 不生效。
- `_kill_pid` 区分「已退出」和「杀不掉」，不再谎报；`save_state` 原子替换被拒时
  降级为原地写入并如实报出来，不再一个字段都写不进去。
- 设置页「停止门户」把失败原因显给用户（原来点了没反应、像点错了）。

### 检验
- 新增 `tools/check_portal_stop_scope.py`（13 项）：正例/反例控制证明
  `--stop` 的作用域，以及停止后偏好仍在、运行痕迹已清。
- 新增 `tools/check_portal_shutdown.py`（6 项）：真门户上验证自退生效、
  非本机被拒、端口松了进程也必须真的退出。
- 新增 `tools/check_plugin_stop.py`（6 项）：走 `stopPublic` 真路径，
  在临时 `PORTAL_RUNS_DIR` 里验证「请门户自退」链路。
- `tools/check_portal_parity.py` 41 → 66 项：钉住未启动状态的逻辑。
- `test/host.test.mjs` 36 → 46 项；`test/test_host_buttons.py` 改为
  **收尾恢复用户原本在跑的门户**，不再把用户的现场弄乱。
- 纪律写进 README：检验一律用临时端口 + 临时 `PORTAL_RUNS_DIR`，不碰用户
  真实的 `runs/`（那里存着口令和用户注册的服务）。

## 0.7.4 (2026-10-15)

访问地址旁边加**「复制」**按钮（二维码保留）。

用户先要求「不要二维码了，保留访问地址，并且地址可以复制」，随后改口
「还是恢复之前的二维码吧」（改动当时尚未提交，直接回退后只保留复制这一项）。
最终形态 = **二维码 + 地址 + 复制按钮**：扫码适合当面把手机接过去，
复制适合把地址贴进聊天窗发给别人，两条路对应不同场景。

- 局域网 / 公网地址右侧各加一个「复制」按钮，点后按钮显示「已复制」1.5 秒
- 剪贴板有兜底：面板若在非安全上下文（http 内网地址）下打开，`navigator.clipboard`
  会不可用，退回 `execCommand` 复制 —— 否则按钮点了没反应，用户以为坏了
- 新增 `addrRow` 样式：长 URL 可换行、复制按钮不被挤走

tools/check_portal_parity.py 新增一组断言：二维码仍在、两个复制按钮在、
有「已复制」反馈、剪贴板兜底在。

## 0.7.3 (2026-10-15)

**修回标题**：设置页标题恢复为「对外服务门户」。

上一轮「对齐 dsh-pocket」时，我把标题文案也一起照抄了
（「对外服务门户」->「手机访问」），副标题也从「门户控制台，管理要开放的服务」
换成了它的「实时同步」。用户一眼发现不对。

教训记进代码注释与检查：**「对齐能力」不等于「替换身份」** ——
dsh-pocket 叫「手机访问」是因为它整个插件的使命就是手机访问；
我们是「把本机服务对外发布并统一管理」，扫码只是入口之一。

tools/check_portal_parity.py 新增一组断言钉住身份文案：
标题是「对外服务门户」、不是「手机访问」；副标题是「管理要开放的服务」、
不是「实时同步」。防止以后对齐时又照抄。

## 0.7.2 (2026-10-15)

右上角最终形态：**「鼓励一下 ★」**（灰色下划线短链接，用户指定）。

- 文案从「⭐ 顺手留颗 Star，作者能高兴一整天」压到「鼓励一下 ★」
- 颜色从品牌蓝改成 **label-tertiary 灰**（低调，不抢注意力）
- 保留下划线（让人知道能点）+ 	itle 提示（三个字太短，hover 时说明点了做什么）

tools/check_portal_parity.py 的断言同步换成这个最终形态，并加一条
「没有长鼓励文案残留」—— 用户前后提了三次精简（三行 → 一句 → 三个字），
这条断言防止以后谁又加回去。

## 0.7.1 (2026-10-15)

右上角那句求 Star **从三行压成一句**（用户反馈：「这里就简单一句 星星+鼓励一下就好了」）。

- 去掉「开发者：xxx」署名行
- 去掉第三行 CTA「行，给你一颗 Star」（那是 dsh-pocket 的 starAsk + starCta 两行结构）
- 合并成一句：**「⭐ 顺手留颗 Star，作者能高兴一整天」**，整句就是指向仓库的链接
- 清掉不再用的 DEVELOPER 常量与 credit / creditLine 样式（不留死代码）

相应地更新 tools/check_portal_parity.py：断言换成**精简后的形态**
（有一句、带 ⭐、是链接、无署名行、无第三行 CTA、无多行容器样式残留），
这样以后谁再加回多行都会被拦下。

## 0.7.0 (2026-10-15)

用户逐条对照 dsh-pocket 的截图，指出三处没对齐。**这次去 dsh-pocket 源码里读明白
再实现，不自己琢磨**（用户明确要求）。三处里有真 bug。

### ① 右上角「开发者 / 求颗 Star」区块（对齐 dsh-pocket）

dsh-pocket 在标题行右侧放了 `developer` / `starAsk` / `starCta` 三行（见其
`pocket-locales.js`），求 Star 是个指向仓库的可点链接。我们此前完全没有。
现在同位置同结构：开发者 + 求 Star 文案 + 「行，给你一颗 Star」外链
（`target="_blank"` + `rel="noreferrer"`）。
放标题行而不是页脚：这是设置页唯一的「关于」区域，页脚几乎没人滚到。

### ② 局域网口令独立（真 bug）

**此前「局域网访问密码」区块里显示和刷新的其实是公网口令。**
在「局域网访问密码」里点「刷新」，改的是 `passwordMode` / `fixedPassword`
（公网凭据）；而内网与公网**共用同一个 16 位随机串** —— 手机在同一 WiFi 下
要手输那一长串，等于没法用。

按 dsh-pocket 的 `lanToken` / `accessToken` 分离模型重做：
- 后端新增 `gen_lan_password()`（8 位纯数字，手机好输）与
  `validate_lan_pin()`（6–12 位数字；拒绝字母符号，局域网口令设成 "1" 也不行）；
- 认证层按**请求来源**选比对哪个口令：内网用局域网口令、公网用公网口令。
  **公网拿局域网口径进不来**（这是安全边界，已用控制检验钉住）；
- 新增 `/_api/lan-pin/refresh` 与 `/_api/lan-pin/custom`，走**动态 provider**，
  改完立即生效**不重启门户**（重启会换掉隧道域名，代价太大）；
- 自定义后打标记、界面提示「自定义后开启公网不再自动换」
  （对齐 dsh-pocket 的 `publicPinCustom` / `lanPinCustom`）;
- 口令落盘，重启门户延续上次的值（不是每次重启都换）。
- 插件宿主只**转发**给门户进程执行 —— 口令在门户内存里，插件另存一份会变成
  两处真相，表现是「设置页显示新口令，手机上输它进不去」。

### ③ 「自动设置」（手动选地址）没效果（真 bug，两层）

用户报「他的自动设置就是有效的，我们的没有效果」。查出来是两层：

**a) 候选列表根本没写进状态文件。**
`state_snapshot()` 里有 `lan_candidates`，但启动时的 `save_state({...})`
**没把它写进去**。宿主读 `state.lan_candidates` 永远是 `undefined` → 回给设置页
`lanCandidates: []` → 下拉框里只有「自动（推荐）」一项，用户看不到也选不到别的
地址。**看起来像「自动没效果」，实际是候选压根没传过来。**

**b) 就算选了，认证层也不认这个地址。**
有些 overlay 网段（Radmin VPN 的 26.x）**不在 RFC1918 里**，`classify_host()`
会判成 `public`。于是用户从自己刚选的「局域网地址」访问，被要求输**公网**口令，
去输界面显示的局域网口令永远「口令错误」。
这正是 dsh-pocket `isLanOverrideHost()` 处理的坑（其 issue #79），其注释写明：
「避免某 overlay 地址落在公网判定里、导致局域网入口被错判成公网」。

按同样思路新增 `is_lan_override_host()` / `resolve_request_kind()`：
**只要 Host 等于用户手动选的地址，就按局域网裁决，优先级高于按网段判定**
（用户已明确说了「这是我的局域网地址」，那就以他为准）。公网域名不受影响。

### Tests

- 新增 `tools/check_portal_parity.py`（41 项）：钉住三处的实现与数据链，
  含 `resolve_request_kind` 的真实调用（overlay 地址选中后判 lan、未选判 public、
  公网域名不受影响、畸形 Host 仍 fail-closed）。
- 新增 `tools/check_portal_lan_pin.py`（23 项）：真起门户进程验证刷新/自定义、
  非法输入被拒、**内网不接受公网口令**、**公网不接受局域网口令**、
  候选列表确实落盘、覆盖值落盘、从手动选的地址访问按内网裁决。
- 更新 `test/test_lan_toggle.py`：原先断言「内网用公网口令能登录」——那是旧设计。
  改为用局域网口令登录，并加反例「内网不接受公网口令」。
- 更新 `test/host.test.mjs`：`write_password` 重构为 `_write_secret_file`
  （公网/局域网两份副本共用），断言跟着调整。
## 0.6.2 (2026-10-15)

用户报「点击添加服务报错：请求体不是合法 JSON」。这是**两个叠在一起的 bug**，
任何一个都足以让「添加服务」完全不可用：

1. **控制台用原生表单提交，API 只认 JSON。**
   页面是 `<form method="POST">`（浏览器发 `application/x-www-form-urlencoded`），
   而 api_handler 里只有 `json.loads(body)` —— 于是点「添加服务」永远得到
   `请求体不是合法 JSON`。表单是网页最自然的提交方式，不该为了配合后端被迫改写成
   JS fetch；而插件/脚本调 API 走 JSON 更自然。现在 `parse_body()` **两种都收**，
   坏 JSON 仍被明确拒绝（不因为宽容就什么都收）。

2. **表单没有 key 字段，但注册表要求 key。**
   表单只收集「名称 / 路由路径 / 上游 / 备注」——那是用户能理解的东西；key 是内部
   标识符（用于 API 路径与状态）。早先表单传上去没有 key，注册表直接报
   「服务 key 不能为空」——**即使修好 JSON 解析，添加仍然会失败**。
   现在从路由路径自动派生 key：`/rltrain` -> `rltrain`，`/a/b` -> `a_b`；
   全中文路径（`/中文`）用稳定短哈希兜底（`svc_<hash>`），保证仍能添加。

顺带改进错误提示：路由冲突时说「路由路径 /rltrain 已经被占用了，换一个
（例如 /rltrain2）」，而不是「服务 key rltrain 已存在」——后者对用户毫无意义，
因为 key 是派生的，用户根本不知道有这个东西。

### Tests

新增 `tools/check_portal_form.py`（8 项）：真起门户进程，用**表单编码**提交
（就是控制台页面发的东西），验证服务真的进了注册表；覆盖 JSON 调用仍可用、
空表单体的开关操作、坏 JSON 被拒、缺字段给出中文原因。
## 0.6.1 (2026-10-15)

用户报「无法开启公网访问」。查到的**根因是我在 0.5.0 加 autoStart 时引入的**：

- **门户已在运行时，「开启公网访问」什么都不做。**
  设置页按钮 → 宿主 `POST /start` → `startPublic` 里的幂等检查
  `if (await portListening(port)) return { ok: true, already: true }` 直接返回，
  **建隧道那一步被一起跳过了**。调用方拿到 ok=true 却永远等不到公网地址。
  以前不显形的原因：门户以前不会自动起，第一次点按钮时端口没在听，会走完整
  启动流程（含建隧道）；加了 autoStart 之后门户总是已经跑着，于是永远跳过隧道。
  修：幂等分支区分 `lanOnly` —— 只开内网才直接返回；要公网则去拨隧道
  （新增 `startTunnelOnly()`，走门户自己的 `/_api/tunnel/start`，
  因为 cloudflared 子进程句柄与日志偏移量都在门户进程里）。

- **「关闭公网」把整个门户停掉。** 语义错了：用户点它是想收起对外暴露，
  不该顺带把内网二维码也弄失效。新增 `doStopTunnel()` → 宿主 `/tunnel/stop`
  → 只收隧道，内网继续可用（实测：关公网后内网仍 HTTP 200）。

### Tests

- 新增 `tools/check_portal_tunnel.py`（11 项）：用**假门户**端到端验证宿主确实
  会去调 `/_api/tunnel/start`、如实回报地址；含「隧道失败不谎报成功」的反例控制；
  以及「关闭公网走 /tunnel/stop 而不是 /stop」的源码断言。
- 新增 `test/test_public_link.py`（12 项）：**真实公网链路**验证 ——
  自包含起门户 + 拨隧道，用 curl（`--noproxy` 绕过本机代理）验证域名可达、
  公网首页是登录页、未登录访问 API 拿不到数据、未登录访问服务路径被拦、
  本机/内网免密、畸形 Host fail-closed、cloudflared 已注册到边缘。
  关键细节：只看状态码会误判（登录页也是 200），必须看**内容**；
  刚建好的域名要等 DNS 生效，不能直接断言。

### 说明：本机代理会影响公网自测

本机开着 Clash/Mihomo（TUN 模式 + `HTTP_PROXY=127.0.0.1:7897`）时：
cloudflared 日志会出现 `ICMP proxy will use 198.18.0.1 ... zone Mihomo`；
PowerShell 的 `Invoke-WebRequest` 走系统代理去访问自己的公网域名会失败
（`基础连接已经关闭`），而 `curl --noproxy '*'` 正常 200。
**这是本机代理的干扰，不是门户故障。** dsh-pocket 的 README 也记录过同类现象
（`公网 error 1033` → 多半是本机代理/VPN 掐断隧道）。
## 0.6.0 (2026-10-15)

用户反馈「体验距离参考对象还差很多」。这次做了系统性对照（逐段读 dsh-pocket 的
客户端与 service.mjs），补齐能力并修掉查出来的真 bug。

### 修复（都是「扫码打不开 / 启动了却访问失败」的直接原因）

- **门户只绑 127.0.0.1 -> 手机永远连不上**。这是「扫码打不开」的**根本原因**：
  内网设备根本到不了 127.0.0.1。改为默认绑 `0.0.0.0`（认证层按 Host 分类做豁免，
  暴露到局域网是安全的：loopback/lan 免密、public 必须口令）。
- **Windows `SO_REUSEADDR` 允许重复绑定** -> 端口被别的进程占着时也「绑定成功」，
  流量被内核随机分到两个进程，表现为「有时能开、有时打不开」。改用
  `SO_EXCLUSIVEADDRUSE` 独占；同时**端口被占自动往后试 5 个**（对齐 dsh-pocket
  的端口自适应），用户不必为「上个门户没停干净」手动换端口。
- **选错解释器 -> 状态一个都存不下**。`pythonFor` 只看文件是否存在，选中了
  `ld-rl-poker\.venv313` 的 python —— 它带沙箱访问控制标记，**能写宿主仓库自己的
  runs/，但写 dsh-service-portal/runs 被拒**（PermissionError 13）。
  后果：门户进程活着、端口在听，但状态/口令全写不出去，设置页读不到状态就
  永远显示「未运行」、点开启报 502。新增 `usablePython()`：**实际运行解释器去
  试写门户自己的 runs/**，第一个能写的才用；全都不能写时明确报出原因。
- **`save_state` 用固定临时名 -> 并发启动 PermissionError**。DSH 的 autoStart 与
  设置页按钮并发时，两个进程同时写 `portal_state.json.tmp`，后开的直接
  PermissionError 崩掉。改为唯一临时名（pid + 线程 id）+ 重试 + 原子替换。
- **`write_password` 失败会阻断启动**。它只是「给人看的副本」（真凭据在
  portal_state.json），写不进去不该让门户起不来；改为原子写 + 重试 + 不阻断。
- 注册表读取失败时 Windows 上会因 PermissionError 静默按空表处理 —— 现在明确提示。

### 新增

- **WebSocket 透传**（对齐 dsh-pocket）。早先完全不支持：升级头被过滤、101 响应没原样
  回传、握手后没有双向管道。而本机服务里有相当一部分靠 WebSocket ——
  Jupyter 的 kernel 通道、训练看板的实时曲线、日志流式推送。现在握手 + 双向字节
  透传 + 长连接多帧都工作，且认证仍然前置（公网未登录不给 101）。
- **网卡评分选地址**（对齐 dsh-pocket 的 `selectLanIPv4`）。原来「取第一个非回环私网
  地址」在多网卡机器上会拿到 Radmin VPN 的 `198.18.0.1`（手机连不上）。现在评分：
  物理网卡 +20、VPN/虚拟网卡 -50、RFC1918 +100、`198.18.0.0/15` 基准测试段 -200。
  实测本机：`192.168.71.10`(以太网 2) 得 120 分排第一，`198.18.0.1` 得 -190 排最后。
- **高级·手动选地址真正可选**：下拉框列出候选（带网卡名），选定后立即生效并落盘，
  非法地址被拒（400 + 中文原因），选空回到自动。
- **Toast 反馈**（2.6 秒自动消失，与 dsh-pocket 一致）：开关切换、地址变更后给出
  明确确认，用户不必猜「到底保存成功没有」。
- 地址提示不再静默：选定的地址不在当前网卡上时明确告知。

### Tests

- 新增 `tools/check_portal_bind.py`（7 项）：监听地址、独占绑定、端口自适应、
  **从内网 IP 访问（手机可达性）**。
- 新增 `tools/check_portal_websocket.py`（8 项）：手写最小 WebSocket 服务端做
  端到端握手 + 回显 + 长连接多帧，含「不带 Upgrade 走普通 HTTP」与「公网未登录
  不给 101」两个反例控制。不引入第三方库。
- 新增 `test/test_lan_address.py`（16 项）：评分排序、198.18.x 降权、覆盖生效、落盘。
- `test/host.test.mjs` 36 项：新增 6 项钉住「解释器必须试写」「临时名必须唯一」
  「写口令失败不阻断启动」等。
## 0.5.0 (2026-10-15)

### 对齐 dsh-pocket 的「装好即用」体验

- **插件加载即自动启动门户**（只开内网，不建隧道）。修的是「默认主页访问也没打开」：
  之前要先手点「开启门户」才有东西，设置页打开是空的。外网暴露仍必须由用户显式开启
  —— 不能因为装了插件就自动把本机服务挂到公网。
  新增配置 `autoStart`（默认 `true`）。
- **设置页重做为 dsh-pocket 形态**：局域网、公网两个区块，各自带
  iOS 风格开关 + 二维码 + 地址 + 访问密码行 + 高级（手动选地址）。
  扫码打开的是**门户控制台**（在那里管理要开放的服务）—— 这是与 dsh-pocket 的
  本质区别：它的二维码指向一个目标（DSH web），我们的指向一个可管理多服务的控制台。
- **局域网访问密码开关**（默认关 = 免密）：开启后同一 WiFi 也要口令。
  **改完立即生效，不重启门户**（重启会换掉隧道域名，代价太大）。
  通过 `open_classes_provider` 动态读取实现。
- **局域网访问总开关**（默认开）：关掉后同一 WiFi 也进不来（一律要口令）。
  **本机（loopback）永远免密** —— 否则用户在电脑上连自己的门户都进不去。
- 新增 `GET /_api/qr?url=`：为门户自己的地址生成二维码（白名单校验，
  拒绝为外部地址出图，防止被当免费图床）。设置页从这里取二维码，避免两处 QR 逻辑漂移。
- 新增 `GET/POST /_api/settings`：读/改局域网两个开关，立即落盘。

### Fixes

- **`portalPort` 非法值未回落**：`portalPort: -1` 会原样通过，之后所有端口探测
  都失败、界面永远显示「未运行」。现在只接受 1–65535 的整数，其余回落 8899。
- **认证判定重构为纯函数** `needs_auth()`：原实现把判定散在 Handler 方法里，
  且踩到本仓库已知的「类属性回调被当成绑定方法」坑（`self._lan_allowed()` 会
  多传一个 self）。现在 provider 出错统一**收紧**（fail-closed）。

### Tests

- 新增端到端脚本 4 个（见 README「端到端」表）：自动启动 4 项、内网口令开关 10 项、
  局域网总开关 6 项、设置页数据链 10 项。
- `tools/check_portal_integration.py` 增加局域网总开关的 7 项判定（含两种 provider
  异常必须收紧的 fail-closed 控制）。
- `test/host.test.mjs` 27 项（新增 3 项：「装好即用」相关配置默认值）。

## 0.4.0 (2026-10-15)

### Fixes

- **fail-closed 漏洞：畸形 Host 被误判为内网**。原实现「不含点的 Host 就是局域网」，
  导致 `Host: garbage value`、`Host: <script>` 这类畸形值都享受内网免密，等于给出了一条
  「随便编个 Host 就能绕过口令」的路径。现在只认合法的单标签主机名
  （RFC 1123：字母/数字/连字符，不以下划线开头结尾，≤63 字符），其余一律 public。
- **控制台访问链接双斜杠**：生成的是 `href="/acc//"`（mount 已含前导斜杠，模板又补了一个）。

### Tests

- 新增 `tools/check_portal_integration.py`：把上面两个缺陷固化成回归检查
  （含「合法单标签名仍判 lan」的反向控制，防修过头）。
- 新增 `test/acceptance_portal.py`：端到端验收脚本，真起门户进程，29 项逐条验证
  内网免密 / 外网口令 / 页面增删改开关服务 / 路由改动生效 / 限速 / 健康检查真实性 /
  三分类 fail-closed / 依赖缺失返回 2。

## 0.3.0 (2026-10-15)

### Features

- **认证改为「只验口令」**，取消账号。
  - 访问时返回自定义登录页（仅一个口令输入框），不再触发浏览器原生 Basic Auth 弹框。
  - 口令正确后下发**签名会话 cookie**（HttpOnly + SameSite + Secure，默认 12 小时），
    cookie 里是 HMAC 签名而非口令本身；会话密钥每次进程启动随机，重启即全体登出。
  - 认证仍在转发之前：未登录请求绝不触达上游，响应也不泄露上游是否可达。
- **口令两种形态**（设置页可选，运行中不可改）：
  - `random`（默认）：每次开启自动生成新口令；
  - `fixed`：用户设定的固定口令（至少 12 字符），保存时即校验，不等到启动才报错。
  - 固定口令**不进命令行**（避免被 Win32_Process 读到），经临时文件传给启动器，用完即删。

### Tests

- 新增 `tools/check_portal_auth.py`：35 项认证控制检验（登录页、会话签名、伪造/篡改/过期、
  认证先于转发、口令解析与比较、口令门槛）。
- `tools/check_tunnel_auth.py` 从 Basic Auth 时代改造为口令登录时代（保留全部路由/转发/挂载检查）。
- 插件宿主端控制检验 18 → 24 项（新增口令形态与固定口令临时文件检查）。

## 0.2.0 (2026-10-15)

### Features

- **子插件 `dsh-poker-viewer` 已删除，功能吸收进根插件成为通用门户能力**。
  - 原专用子插件（ld-rl-poker 外网开关）取消；门户由服务清单（`services.json`）驱动，
    不绑定任何具体服务——两个 GUI 只是内置默认清单。
  - profile 安装切换：移除 `dsh-poker-viewer`，新增 `dsh-service-portal`（仓库根，link 安装）。
  - `check_plugin.py` 从「检验两个插件」恢复为只检验根插件。

## 0.1.0 (2026-10-15)

### Features

- **初始发布**：对外服务门户插件 `dsh-service-portal`（自 `ld-rl-poker` 迁入基础设施仓库）。
  - 一键对外开放本机服务：`cloudflared` 随机域名 + Basic Auth 随机口令。
  - 两种形态：每服务独立随机域名 / 单域名 + 路径前缀（`--single-domain`）。
  - 服务清单驱动（`services.json`），不填用内置默认（ld-rl-poker 的两个 GUI，向后兼容）。
  - DSH 设置页「对外服务门户」一节：一键开启/关闭、显示连接地址与口令（明文，用户选型）。
  - 宿主端 18 项 + 客户端 14 项控制检验。

### Docs

- 仓库 README 改为插件发布视角（安装 / 工作原理 / 服务清单 / 安全边界 / 控制检验）；
  新增英文版 README.en.md、THIRD_PARTY_NOTICES.md、RELEASING.md、CHANGELOG.md。