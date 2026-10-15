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

- **自带控制台网页** —— 门户本身就是一张网页：在页面上增删要开放的服务、设置路由路径、
  逐个开关，开启后点链接直接访问。**不用改配置文件、不用重启**。
- **内网 + 外网两种访问** —— 同一张页面，两条入口：
  - 内网（`http://192.168.x.x:8899`）**免密**，同一 WiFi 下手机/平板直接打开；
  - 外网（`https://<随机>.trycloudflare.com`）**必须口令**，人在外面也能用。
- **手机扫码即用** —— 控制台显示二维码，手机扫一下就到（页面按窄屏自适应）。
- **只需口令，不要账号** —— 自定义登录页（只有口令输入框），不弹浏览器原生
  「账号 + 密码」框；口令可**每次随机**或**你自己设固定值**。
- **登录限速** —— 单 IP 连续失败 5 次锁 60 秒，另有全局阈值防分布式撞码。
- **服务状态一目了然** —— 每个服务显示 已启用/未启用/存活探测失败，未启用的不可点。
- **控制检验**（本仓库硬纪律）—— 注册表 88 + 控制台 + 代理 + 认证 35 + 路由 35 项、
  域名 10 项；**依赖缺失必须「跳过并返回 2」，不得静默通过**。

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
| `webEnabled` | `true` | 是否挂载 `/service-portal/api` 路由 |

所有字段都是 `.volatile()`：改设置即时生效，不需要重挂插件。
**口令形态是安全相关设置**：口令模式与固定口令在门户**运行中**不可改（先「关闭」再改），
避免出现「界面显示的口令」与「实际生效的口令」不一致。

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
| `tools/check_portal_registry.py` | 88 | 路由重复/非法、key 冲突、**改完不落盘**（重启就丢）、坏文件崩溃 |
| `tools/check_portal_console.py` | — | 未启用服务可点、服务名里塞 `<script>`（存储型 XSS）、二维码不确定 |
| `tools/check_portal_proxy.py` | — | **自建域名被误判成内网**、认证未前置、限速失效、`cf-connecting-ip` 被伪造 |
| `tools/check_portal_auth.py` | 35 | 未登录被放行、会话可伪造/篡改/过期不失效、cookie 装了口令本身 |
| `tools/check_tunnel_auth.py` | 35 | 认证被绕过、前缀没剥离、多挂载走错上游、未知前缀兜底成 200 |
| `tools/check_tunnel_domain.py` | 10 | 追加日志取到**上一次的旧域名**（外网打开 530 而本地一切正常） |
| `tools/check_plugin.py` | 41 | DSH 插件 exports 契约、报告 running 却服务已死、口令形态配错 |

```powershell
python -X utf8 tools\check_portal_registry.py
python -X utf8 tools\check_portal_console.py
python -X utf8 tools\check_portal_proxy.py
python -X utf8 tools\check_portal_auth.py
python -X utf8 tools\check_tunnel_auth.py
python -X utf8 tools\check_tunnel_domain.py
python -X utf8 tools\check_plugin.py
```
```

**依赖缺失必须「跳过并返回 2」，不得静默通过**——这是本项目的硬纪律。

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