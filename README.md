<p align="center">
  <img src="icons/dsh-service-portal-64.png" width="64" alt="dsh-service-portal" />
</p>

<h1 align="center">dsh-service-portal</h1>

<p align="center"><b>一个随机域名 + 一个随机口令，把本机的服务按需对外开放。</b></p>

<p align="center">
  <a href="README.en.md">English</a> ·
  <a href="#安装">安装</a> ·
  <a href="#工作原理">工作原理</a> ·
  <a href="#服务清单">服务清单</a> ·
  <a href="CHANGELOG.md">更新日志</a> ·
  <a href="https://github.com/dingminhua/dsh-service-portal/issues">问题反馈</a>
</p>

<p align="center">
  <a href="https://www.npmjs.com/package/dsh-service-portal"><img src="https://img.shields.io/npm/v/dsh-service-portal?style=flat-square&label=npm&color=cb3837" alt="npm version"></a>
  <a href="https://www.npmjs.com/package/dsh-service-portal"><img src="https://img.shields.io/npm/d18m/dsh-service-portal?style=flat-square&label=downloads&color=cb3837" alt="npm downloads"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/dingminhua/dsh-service-portal?style=flat-square" alt="MIT license"></a>
  <a href="https://github.com/dingminhua/dsh-service-portal/stargazers"><img src="https://img.shields.io/github/stars/dingminhua/dsh-service-portal?style=flat-square" alt="GitHub stars"></a>
</p>

**dsh-service-portal（对外服务门户）** 是一个 [DeepSeek Harness (DSH)](https://github.com/deepseek-ai/deepseek-harness) 插件。
它把**任意本机服务**按需暴露到外网：`cloudflared` 建一个**随机域名**，一道**口令登录**
（只需口令，没有账号）守住入口，设置页一键开关并显示连接与口令。

它最初长在 `ld-rl-poker` 里（为了把训练配置台/模型查看台放到外网），但门户本身与德州扑克无关——
**任何本地服务**都能用同一套「一个域名 + 一个口令 + 按需挂载」。

## 功能特性

- **装好即用，不用先点开关** —— 插件加载后门户自动起来（**只开内网**，不会自动把本机
  服务挂到公网）。打开设置页就能看到内网地址和二维码，扫一下就进。
  外网暴露必须由你显式点「开启公网访问」。
- **设置页就是 dsh-pocket 那个形态** —— 局域网、公网两个区块，各自带开关 + 二维码 +
  地址 + 访问密码行 + 高级（手动选地址）。
- **自带控制台网页** —— 扫码打开的就是门户控制台：在页面上增删要开放的服务、设置路由
  路径、逐个开关，开启后点链接直接访问。**不用改配置文件、不用重启**。
- **内网 + 外网两种访问** —— 同一张页面，两条入口：
  - 内网（`http://192.168.x.x:8899`）默认**免密**，同一 WiFi 下手机/平板直接打开。
    可开「局域网访问密码」，也可以直接关掉整个局域网访问；
  - 外网（`https://<随机>.trycloudflare.com`）**必须口令**，人在外面也能用。
  - 两个开关**改完立即生效**，不用重启门户（重启会换掉隧道域名，代价太大）。
  - **本机访问永远免密** —— 否则你在电脑上连自己的门户都进不去。
- **手机扫码即用** —— 设置页与控制台都显示二维码（内联 SVG，不依赖外部请求），
  手机扫一下就到；页面按窄屏自适应。
- **只需口令，不要账号** —— 自定义登录页（只有口令输入框），不弹浏览器原生
  「账号 + 密码」框；口令可**每次随机**或**你自己设固定值**。
- **登录限速** —— 单 IP 连续失败 5 次锁 60 秒，另有全局阈值防分布式撞码。
- **服务状态一目了然** —— 每个服务显示 已启用/未启用/存活探测失败，未启用的不可点；
  健康检查是**真探测**（TCP 连上游端口），不是标记位。
- **控制检验**（本仓库硬纪律）—— 8 项 Python 控制检验 + 5 个端到端脚本 + 44 项 Node
  检验；**依赖缺失必须「跳过并返回 2」，不得静默通过**。

## 工作原理

```
                    ┌─────────── 门户进程（一个端口，默认 8899）───────────┐
 内网 http://192.168.x.x:8899 ──┤                                        │
                                ├──▶ 按 Host 分类：loopback / lan / public │
 外网 https://<随机>.trycloudflare.com ─┘    │                            │
                                            ├─ /            → 控制台页（管理服务）
                                            ├─ /_auth/login → 口令登录（外网）
                                            ├─ /_api/*      → 控制台 API
                                            └─ /<路由路径>/… → 转发到对应服务
```

**认证强度按来源区分**（照搬 dsh-pocket 的模型，见[致谢](#致谢)）：

| Host 分类 | 判定 | 控制台 / 服务 |
| :--- | :--- | :--- |
| `loopback` | `localhost`、`127.x`、`::1` | 免密 |
| `lan` | RFC1918 私网、CGNAT(100.64/10)、`.local`、单标签名 | 免密 |
| `public` | **其余一切**（含你自建域名） | **必须口令** |

> 兜底方向是**安全的一侧**：认不出的 Host 一律当公网。反着写（只把 `*.trycloudflare.com`
> 当外网、其余当内网）会让人挂个自己的域名就绕过认证——dsh-pocket 踩过这个坑
> （它的 issue #66），本项目直接按 fail-closed 实现。

## 安装

### 方式一：npm（发布后）

```powershell
$dsh = "$env:LOCALAPPDATA\Programs\DeepSeek Harness\resources\runtime\cli\bin\dsh.cmd"
& $dsh plugin --profile desktop add dsh-service-portal
```

### 方式二：link 本地插件（开发中）

```powershell
$dsh = "$env:LOCALAPPDATA\Programs\DeepSeek Harness\resources\runtime\cli\bin\dsh.cmd"
& $dsh plugin --profile desktop add "link:D:/DshProject/dsh-service-portal"
```

装完**需要重启 DSH**（插件在宿主进程里加载）。

> 若旧 profile 仍装有已删除的子插件 `dsh-poker-viewer`，先移除再装根插件：
> `& $dsh plugin --profile desktop remove dsh-poker-viewer`。

## 配置（DSH 设置页）

| 字段 | 默认 | 说明 |
| :--- | :--- | :--- |
| `infraPath` | 本仓库根 | 基础设施仓库：含 `tools/` 与 `runs/`（隧道/代理/凭据） |
| `repoPath` | `D:\DshProject\ld-rl-poker` | 宿主仓库根：被开放的服务本体在这里 |
| `pythonPath` | 空 | 拉服务用的解释器；留空则自动选 `.venv313` → `.runtime` → PATH |
| `passwordMode` | `random` | 口令形态：`random` 每次开启自动生成 / `fixed` 用固定口令 |
| `fixedPassword` | 空 | `passwordMode = fixed` 时使用，至少 12 字符（保存时即校验） |
| `portalPort` | `8899` | 门户端口。只接受 1–65535 的整数，非法值回落默认 |
| `autoStart` | `true` | 插件加载后自动启动门户（**只开内网**，不建隧道） |
| `lanAuthEnabled` | `false` | 内网访问是否要口令（`false` = 免密） |
| `webEnabled` | `true` | 是否挂载 `/service-portal/api` 路由 |

所有字段都是 `.volatile()`：改设置即时生效，不需要重挂插件。
「局域网访问密码」「局域网访问」两个开关走门户的 `/_api/settings`，
**改完立即生效且立即落盘**，不受「运行中不可改」限制。
**口令形态是安全相关设置**：口令模式与固定口令在门户**运行中**不可改（先「关闭」再改），
避免出现「界面显示的口令」与「实际生效的口令」不一致。

### 为什么 `autoStart` 默认开、但只开内网

对齐 dsh-pocket 的「装好即用」：装了插件打开设置页就该看到内网地址和二维码，
而不是一片空白等着你点按钮。但**外网暴露是另一回事** —— 那是把本机服务放到公网上，
必须由你显式决定（点「开启公网访问」），不能因为装了插件就自动发生。

### 口令的两种形态

| | `random`（默认） | `fixed` |
| :--- | :--- | :--- |
| 谁生成 | 门户每次开启自动生成 16 字符随机口令 | 你自己设定（≥12 字符） |
| 何时变 | 每次点「开启」都换 | 只有你改它才变 |
| 泄漏后果 | 只在本次开启期间有效，重启即作废 | **长期有效**，直到你改口令 |
| 适用 | 分享给临时协作者、不想记口令 | 常用设备，省去每次复制口令 |
| 安全代价 | 需重新分发口令 | 口令一旦外泄就是长期敞口 |

> 固定口令**不会**进入进程命令行（那会让本机任意进程通过 `Win32_Process` 读到它）：
> 插件把它写进 `runs/` 下的临时文件并以 `--password-file` 传路径，启动器读完即删。

## HTTP 接口

挂在宿主 webServer 上（`prefix` 路由，路径 `/service-portal/api`）：

| 方法 | 路径 | 作用 |
| :--- | :--- | :--- |
| GET | `/service-portal/api/status` | 当前状态：是否运行、模式、地址、口令、口令形态、端点列表 |
| GET | `/service-portal/api` | 等同 `/status` |
| GET | `/service-portal/api/settings` | 口令形态设置（模式 + 固定口令 + 最小长度） |
| POST | `/service-portal/api/settings` | 保存口令形态（body：`{"passwordMode":"fixed","fixedPassword":"..."}`） |
| POST | `/service-portal/api/start` | 启动（body 可选 `{"singleDomain": true}`，默认单域名+路径） |
| POST | `/service-portal/api/stop` | 停止 |

未知子路径返回 **404**（不拿 status 兜底——拼错的路径不许「看起来能用」）。

## 在控制台上管理服务

打开门户地址就是控制台。每个服务一条卡片：

| 操作 | 说明 |
| :--- | :--- |
| **添加服务** | 填 名称 / 路由路径（如 `/ollama`）/ 上游地址（如 `127.0.0.1:11434`）/ 备注 |
| **开启 · 关闭** | 逐服务切换。开启时会尝试拉起它的脚本（若配了 `script`），关闭后该路由**立即 404** |
| **访问** | 已启用的服务显示可点链接，直达 `/<路由路径>/`；未启用的**置灰不可点** |
| **编辑 / 删除** | 改路径、上游、备注；删除会先停掉它拉起的进程 |
| **状态** | 绿=已启用且存活，灰=未启用，红=存活探测失败（不是 0 值假象） |

改动**立即落盘**（`runs/portal_registry.json`）并生效，不用重启门户、不用重建隧道。

服务条目字段：

| 字段 | 必填 | 说明 |
| :--- | :--- | :--- |
| `key` | ✓ | 唯一标识，`[a-zA-Z0-9_-]{1,32}`，不能与保留字冲突 |
| `name` | ✓ | 显示名（≤64 字符，页面会 HTML 转义） |
| `mount` | ✓ | 路由路径，以 `/` 开头；不能与其他启用项重复、不能占用 `/_auth` `/_api` |
| `target` | ✓ | 上游 `host:port` |
| `script` | | 拉起用的脚本（相对 `hostRepo`）；不填则要求服务已自行运行 |
| `enabled` | | 是否对外开放（页面开关） |
| `autoStart` | | 门户启动时是否自动拉起 |

> 命令行也能直接改（等同页面操作）：
> `POST /_api/services`、`POST /_api/services/<key>/enable|disable|restart|delete|update`。

## 工具（也可脱离插件直接用）

| 文件 | 作用 |
| :--- | :--- |
| `tools/portal_run.py` | **门户启动器**：起控制台 + 内网/外网双入口 + 服务进程托管 |
| `tools/portal_proxy.py` | 按 Host 分类认证的反向代理（内网免密 / 外网口令） |
| `tools/portal_console.py` | 控制台页面渲染 + 二维码（纯 Python，无依赖） |
| `tools/portal_registry.py` | 服务注册表（运行时增删改查 + 原子落盘） |
| `tools/portal_login.py` | 口令登录 + 签名会话 cookie |
| `tools/start_public_gui.py` | 旧版启动器（静态清单 + 单/多域名两种形态，仍可用） |
| `tools/tunnel_auth.py` | 旧版认证代理（口令登录 + 多挂载点路径分流） |

```powershell
python -X utf8 tools/portal_run.py                 # 起门户（内网 + 外网隧道）
python -X utf8 tools/portal_run.py --lan-only      # 只开内网
python -X utf8 tools/portal_run.py --port 8899     # 指定端口
python -X utf8 tools/portal_run.py --status / --stop
```

## 控制检验

| 检查 | 项数 | 拦的 bug |
| :--- | ---: | :--- |
| `tools/check_portal_parity.py` | 101 | 设置页三处对标：缺右上角求 Star 区块、局域网口令与公网共用、**「自动选地址」只是显示不生效**；未启动状态逻辑；排版（字号刻度、只引用真实主题令牌、动作与说明分层、警示块去重）；公网密码自定义与警告提示 |
| `tools/check_portal_stop_scope.py` | 13 | **`--stop` 顺手杀掉同端口上别人的进程**（用户正在跑的门户被检验脚本干掉）；停止后口令/候选被整份删掉 |
| `tools/check_portal_shutdown.py` | 6 | 门户自退接口：局域网/公网来源必须被拒（不能从手机把门户关掉）、GET 不生效、**端口松了进程没退** |
| `tools/check_plugin_stop.py` | 6 | 设置页「停止门户」真能停：**宿主派生进程杀不掉门户却报成功**（沙箱/作业隔离），改走"请门户自己退" |
| `tools/check_portal_settings_forward.py` | 7 | 设置页局域网三项（总开关 / 口令开关 / 手动选地址）被宿主**静默忽略**：返回 ok:true、toast 说改了，门户其实一点没变 |
| `tools/check_public_pin.py` | 18 | 公网密码自定义：**新密码真能登录、旧密码真的作废**（拿会话 cookie 当判据）、重启后仍在；安全负例：不能用局域网口令当公网密码、太短/空白被拒 |
| `tools/check_portal_lan_pin.py` | 23 | 局域网口令刷新/自定义；**公网拿局域网口令能进来**（安全边界）、候选列表没落盘 |
| `tools/check_portal_form.py` | 8 | **控制台表单提交被当成坏 JSON**（页面上点「添加服务」永远失败）、表单没有 key 字段导致必然失败 |
| `tools/check_portal_tunnel.py` | 11 | **门户已在跑时「开启公网访问」什么都不做**（幂等检查把建隧道也跳过了）、「关闭公网」把整个门户停掉 |
| `tools/check_portal_bind.py` | 7 | **只绑 127.0.0.1**（手机永远连不上）、Windows `SO_REUSEADDR` 重复绑定（流量随机分流）、端口被占不换端口 |
| `tools/check_portal_websocket.py` | 8 | 升级头被过滤（握手失败）、101 响应没原样回传、握手后没有双向管道（实时数据不刷新） |
| `tools/check_portal_integration.py` | — | **畸形 Host 被判成内网**（`garbage value` 竟免密）、控制台链接双斜杠、局域网总开关只改界面不改认证 |
| `tools/check_portal_registry.py` | 88 | 路由重复/非法、key 冲突、**改完不落盘**（重启就丢）、坏文件崩溃 |
| `tools/check_portal_console.py` | — | 未启用服务可点、服务名里塞 `<script>`（存储型 XSS）、二维码不确定 |
| `tools/check_portal_proxy.py` | — | **自建域名被误判成内网**、认证未前置、限速失效、`cf-connecting-ip` 被伪造 |
| `tools/check_portal_auth.py` | 35 | 未登录可访问、会话被伪造/篡改/过期、口令进 cookie |
| `tools/check_tunnel_auth.py` | 35 | 认证绕过、前缀没剥、上游错、未知前缀 200 兜底 |
| `tools/check_tunnel_domain.py` | 10 | 复用**上一次**的域名（追加日志里读到旧行） |
| `tools/check_plugin.py` | 41 | 插件导出契约、服务已死却报「运行中」、口令形态非法 |

### 端到端（真起门户进程，不是单元级）

| 脚本 | 项数 | 覆盖 |
| :--- | ---: | :--- |
| `test/acceptance_portal.py` | 29 | 页面增删改开关服务、路由改动生效、内网免密/外网口令、二维码/手机端/限速/健康检查真实性、三分类 fail-closed、依赖缺失返回 2 |
| `test/test_autostart.py` | 4 | **插件加载后门户自动跑起来**（「装好即用」）、只开内网、内网地址可用 |
| `test/test_lan_address.py` | 16 | **网卡评分选地址**（物理网卡优先、198.18.x 降权）、手动选地址立即生效、非法地址被拒、覆盖值落盘 |
| `test/test_lan_toggle.py` | 10 | 内网口令开关**立即生效**（不重启门户）、本机永远免密、公网不受影响 |
| `test/test_lan_switch.py` | 6 | 局域网访问总开关：关掉后内网要求口令、本机不受影响、重开恢复 |
| `test/test_public_link.py` | 12 | **真实公网链路**：域名可达、公网首页是登录页、未登录拿不到 API 数据、内网免密、畸形 Host fail-closed |
| `test/test_settings_data.py` | 10 | 设置页数据链：状态字段、二维码生成、二维码只给本门户地址（防图床） |
| `test/test_host_buttons.py` | 10 | **走插件宿主 API**（设置页按钮真正调用的路径）：开启→状态→重复开启→停止；停止走的是"门户自退"；**收尾恢复用户原本在跑的门户** |

**依赖缺失必须「跳过并返回 2」，不得静默通过** —— 这是本仓库的硬纪律。

**检验不许动用户正在跑的门户**：脚本一律用临时端口 + 临时 `PORTAL_RUNS_DIR`，
不碰用户真实的 `runs/`（那里面存着局域网口令和用户在控制台注册的服务）。
这条是踩出来的：一句裸的 `portal_run.py --stop` 曾把用户的门户干掉，
用户看到的是「二维码和访问地址一起消失」。

```powershell
$node = "$env:LOCALAPPDATA\Programs\DeepSeek Harness\resources\runtime\primary-runtime\dependencies\node\bin\node.exe"
& $node --test test/host.test.mjs      # 46 项宿主端控制检验
& $node --test test/client.test.mjs    # 17 项客户端分发契约检验

# Python 控制检验
python -X utf8 tools\check_portal_bind.py
python -X utf8 tools\check_portal_websocket.py
python -X utf8 tools\check_portal_integration.py
python -X utf8 tools\check_portal_registry.py
python -X utf8 tools\check_portal_console.py
python -X utf8 tools\check_portal_proxy.py
python -X utf8 tools\check_portal_auth.py
python -X utf8 tools\check_portal_stop_scope.py
python -X utf8 tools\check_portal_shutdown.py
python -X utf8 tools\check_plugin_stop.py
python -X utf8 tools\check_tunnel_auth.py
python -X utf8 tools\check_tunnel_domain.py
python -X utf8 tools\check_plugin.py

# 端到端（会真起门户进程，几十秒）
python -X utf8 test\acceptance_portal.py
python -X utf8 test\test_autostart.py
python -X utf8 test\test_lan_address.py
python -X utf8 test\test_lan_toggle.py
python -X utf8 test\test_lan_switch.py
python -X utf8 test\test_settings_data.py
python -X utf8 test\test_host_buttons.py   # 需要 DSH 在跑；宿主代码过期会跳过并返回 2
```

### 改样式时怎么看效果（人工看图，不是自动检验）

`tools/render_panel_preview.mjs` 把设置面板**真渲染**出来（直接 require
`lib/client.js`，最小 React 替身 + 假 fetch），用无头 Chrome 截图肉眼核对：

```powershell
node tools\render_panel_preview.mjs          # 打印地址
# 然后访问 /?s=running|public|off[&dark=1] 截图
```

它是**人工工具**，不进控制检验（要人看图，没法自动判过），而且有已知局限：
替身 React 的文本排版不真实（截图里标题与副标题会"看起来压在一起"），
只适合看结构顺序、颜色、胶囊形状、层级差别。局限写在文件头。

## 安全边界（必须如实理解）

- 口令是**明文**存在 `runs/public_gui_credentials.json` 并明文显示在插件设置页。
- **拿到口令 == 服务就能被外网启停**。对 ld-rl-poker 而言 = 能启停 5090 上的训练。
- 有些本地服务**自身没有认证**（两个 GUI、Ollama 等），挂出去就等于公开——
  门户这层口令是它们唯一的关卡。
- 本插件**不会**碰 dsh-pocket 自己的隧道（目标 3081）；`--stop` 只停自己记录的进程。
- **登录后的会话是签名 cookie**（HttpOnly，默认 12 小时到期）：不必每次请求都带口令，
  但这也意味着**在这段时间内，那个浏览器就等于已授权**。会话密钥随门户进程随机生成，
  关掉门户即全体登出。
- **选固定口令就要接受它的代价**：门户重启后口令不变，一次外泄就是长期敞口。
  只想临时分享就保持默认的 `random`。
- 门户跑在本机 `127.0.0.1` 上，口令校验也发生在这一层；**不要把入口端口直接暴露到公网**，
  否则认证层会被绕过（cloudflared 隧道才是唯一的对外通道）。

## 测试

```powershell
$node = "$env:LOCALAPPDATA\Programs\DeepSeek Harness\resources\runtime\primary-runtime\dependencies\node\bin\node.exe"
& $node --test test/host.test.mjs      # 24 项宿主端控制检验
& $node --test test/client.test.mjs    # 17 项客户端分发契约检验

# 端到端验收：真起门户进程，逐条验证「内网免密/外网口令/页面管理服务/限速/健康检查」
python -X utf8 test\acceptance_portal.py    # 29 项

# 认证层与路由层的控制检验（纯标准库）
python -X utf8 tools\check_portal_auth.py    # 35 项：登录页/会话/认证前置
python -X utf8 tools\check_tunnel_auth.py    # 35 项：路由/前缀剥离/多挂载/502
```

## 与同族插件的关系

`dsh-service-portal` 是 LaoDing 插件家族的一员（家族品牌图标与 `dsh-connect-workbuddy` /
`dsh-connect-trae` 等一致）。家族成员共享：

- 设置卡片外观与 `row.*` 文案约定；
- 手写 CommonJS 客户端分发格式（`window.__ModuleLoader__.load`），零构建依赖；
- 「启动器，不是第二份实现」的复用纪律：隧道/认证等已完成并验收的实现不在插件里重写。

> 历史上门户功能曾是专用子插件 `dsh-poker-viewer`（ld-rl-poker 外网开关）；2026-10-15
> 已将其功能**吸收进根插件**成为通用门户能力（服务清单驱动，不绑定任何具体服务），
> 子插件目录已删除。

## 未做

- **固定自有域名**：需要 named tunnel + ingress。现在每次启动都是随机 trycloudflare 域名。
- **cloudflared 自动下载**：本项目复用本机已有的那份（dsh-pocket 会多镜像源下载）。
- **服务健康检查定时刷新**：现在是页面刷新时探测存活，没有后台定时器。

## 致谢

本项目的**门户形态**（控制台网页、内网+外网双入口、按 Host 分类的认证强度）明确参照了：

### [shaobeichen/dsh-pocket](https://github.com/shaobeichen/dsh-pocket)

> 「把 DeepSeek Harness 装进你的口袋：一个包、一个设置页，手机扫码即同步访问电脑上的
> DSH（局域网 + 公网，实时同屏）。」 —— GPL-2.0

**我们从它学到的设计**（逐条对应到本项目的实现）：

| 它的做法 | 我们的实现 |
| :--- | :--- |
| `classifyHost()` 把 Host 分成 `loopback` / `lan` / `public`，按类别决定认证强度 | `tools/portal_proxy.py::classify_host()`，同一套三分类 |
| **fail-closed**：认不出的 Host 一律当公网（它曾因反着写被绕过，issue #66） | 同样 fail-closed，并有 20 项分类控制检验（含「自建域名必须判为公网」） |
| 公网始终要密码；局域网可开关；loopback 免密 | 内网免密、外网必须口令（用户选定） |
| 登录限速：单 IP 5 次失败锁 60s + 全局阈值 | `RateLimiter`，同样的阈值策略 |
| `cf-connecting-ip` 只在源地址是 loopback 时信任 | `client_ip()`，同一条判定（防伪造绕过限速） |
| 自定义登录页（不弹浏览器原生认证框） | `tools/portal_login.py` |
| 手机扫码即用（二维码 + 移动端适配） | `tools/portal_console.py`（纯 Python 生成 SVG 二维码，不引入依赖） |

**同时说明清楚**：本项目**没有复制 dsh-pocket 的任何代码**。

- 它是 JavaScript（`lib/proxy.mjs` / `lib/tunnel.mjs` / `client/`），本项目的门户是独立的
  Python 实现（`tools/portal_*.py`），两侧语言、结构与命名均不同；
- 双方暴露的 HTTP 接口、口令存储格式、配置文件格式都不兼容；
- 我们借用的是**设计判断**（尤其是 fail-closed 的兜底方向、限速阈值、IP 信任边界这类
  「用血换来的结论」），实现是从零写的。

因此本项目的 MIT 许可不受其 GPL-2.0 **传染**：GPL 约束的是衍生作品的代码分发，而
「参考设计思路、独立实现」不构成衍生作品。我们仍在此**明确致谢并标注其许可**，
一是尊重原作者，二是让读者能自己判断。

> 如果将来要在本项目里**直接搬运它的代码**，那就必须整体转为 GPL-2.0 ——
> 请勿在未确认的情况下混入其源码片段。

### 其他

- [cloudflared](https://github.com/cloudflare/cloudflared)（Apache-2.0）—— 公网隧道。
- [mexiaosqwq/dsh-web-mobile](https://github.com/mexiaosqwq/dsh-web-mobile)（MIT）——
  dsh-pocket 的移动端适配移植自它，本项目未直接使用，但移动端设计的源头在此。
- 插件家族的卡片样式与品牌图标来自 `dingminhua/dsh-connect-workbuddy` 等同族插件。

完整的第三方清单与许可要求见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 许可证

MIT，Copyright (c) 2026 LaoDing。第三方致谢见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。