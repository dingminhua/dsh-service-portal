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
它把**任意本机服务**按需暴露到外网：`cloudflared` 建一个**随机域名**，一个带 **Basic Auth** 的
认证代理守一道**随机口令**，设置页一键开关并显示连接与口令。

它最初长在 `ld-rl-poker` 里（为了把训练配置台/模型查看台放到外网），但门户本身与德州扑克无关——
**任何本地服务**都能用同一套「一个域名 + 一个口令 + 按需挂载」。

## 功能特性

- **一键对外开放本机服务** —— 设置页点「开启」即拉服务 → 起认证代理 → 建 tunnel，全程无手工步骤。
- **随机域名 + 随机口令** —— 每次启动都换；口令只写入本机凭据文件（明文，已 gitignore，勿外发）。
- **两种形态**：每个服务一个独立随机域名，或**单域名 + 路径前缀**（`https://<随机>/train/`）。
- **服务清单驱动** —— 写 `services.json` 就能开放任意服务，无需改代码；不填则用内置默认
  （ld-rl-poker 的两个 GUI，保持向后兼容）。
- **控制检验**（本仓库硬纪律）—— 隧道认证 35 项、域名解析 10 项、机器状态 23+23 项、插件契约
  26 项检验；**依赖缺失必须「跳过并返回 2」，不得静默通过**。
- **机器状态采集** —— CPU / 内存 / 显存 / GPU 利用率，缺读数显示「—」绝不画成 0。

## 工作原理

```
https://<随机>.trycloudflare.com   (cloudflared quick tunnel，域名每次启动都换)
              |
              v
127.0.0.1:<proxyPort>  tools/tunnel_auth.py（Basic Auth，口令每次启动都换）
              |
              v
127.0.0.1:<guiPort>  本机服务（GUI / Ollama / 任何 HTTP 服务）
```

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
| `webEnabled` | `true` | 是否挂载 `/service-portal/api` 路由 |

四个字段都是 `.volatile()`：改设置即时生效，不需要重挂插件。

## HTTP 接口

挂在宿主 webServer 上（`prefix` 路由，路径 `/service-portal/api`）：

| 方法 | 路径 | 作用 |
| :--- | :--- | :--- |
| GET | `/service-portal/api/status` | 当前状态：是否运行、模式、地址、口令、端点列表 |
| GET | `/service-portal/api` | 等同 `/status` |
| POST | `/service-portal/api/start` | 启动（body 可选 `{"singleDomain": true}`，默认单域名+路径） |
| POST | `/service-portal/api/stop` | 停止 |

未知子路径返回 **404**（不拿 status 兜底——拼错的路径不许「看起来能用」）。

## 服务清单

不填任何配置时用内置清单（= ld-rl-poker 的两个 GUI）。要开放别的服务就写 `services.json`：

```json
{
  "hostRepo": "D:\\DshProject\\ld-rl-poker",
  "services": [
    {"key": "train",  "script": "gui/server.py",        "guiPort": 8810,
     "proxyPort": 8890, "name": "训练配置台", "mount": "train"},
    {"key": "ollama", "script": "serve.py",             "guiPort": 11434,
     "proxyPort": 11499, "name": "Ollama",   "mount": "ollama"}
  ]
}
```

优先级：`--services <json>` > `$SERVICE_PORTAL_SERVICES` > `./services.json` > 内置清单。

- `hostRepo`：服务脚本所在的宿主仓库根（脚本路径相对它解析）；
- `script` / `guiPort`：被拉起的服务与其端口；
- `proxyPort`：非单域名模式下每个服务各自的认证代理端口；
- `mount`：单域名模式下的路径前缀（`/train/`）。

## 工具（也可脱离插件直接用）

| 文件 | 作用 |
| :--- | :--- |
| `tools/start_public_gui.py` | 一键启动：读清单 → 拉服务 → 起代理 → 建 cloudflared 隧道 |
| `tools/tunnel_auth.py` | Basic Auth + 多挂载点路径分流反向代理（认证在转发之前） |
| `tools/host_metrics.py` | 机器状态采集（CPU / 内存 / 显存 / GPU 利用率） |

```powershell
python -X utf8 tools/start_public_gui.py --single-domain   # 单域名+路径
python -X utf8 tools/start_public_gui.py                   # 两个独立随机域名
python -X utf8 tools/start_public_gui.py --status / --stop
```

## 控制检验

| 检查 | 项数 | 拦的 bug |
| :--- | ---: | :--- |
| `tools/check_tunnel_auth.py` | 35 | 认证被绕过、前缀没剥离、多挂载走错上游、未知前缀兜底成 200 |
| `tools/check_tunnel_domain.py` | 10 | 追加日志取到**上一次的旧域名**（外网打开 530 而本地一切正常） |
| `tools/check_host_metrics.py` | 23 | 读数缺失被画成 0（远程误以为机器空闲） |
| `tools/check_host_metrics_pages.py` | 23 | 页面没接状态条 / 为接状态条改坏宿主页面契约 |
| `tools/check_plugin.py` | 26 | DSH 插件 exports 契约、报告 running 却服务已死 |

```powershell
python -X utf8 tools\check_tunnel_auth.py
python -X utf8 tools\check_tunnel_domain.py
python -X utf8 tools\check_host_metrics.py
python -X utf8 tools\check_host_metrics_pages.py   # 需宿主页面（SERVICE_PAGES_DIR）
python -X utf8 tools\check_plugin.py
```

**依赖缺失必须「跳过并返回 2」，不得静默通过**——这是本项目的硬纪律。

## 安全边界（必须如实理解）

- 口令是**明文**存在 `runs/public_gui_credentials.json` 并明文显示在插件设置页。
- **拿到口令 == 服务就能被外网启停**。对 ld-rl-poker 而言 = 能启停 5090 上的训练。
- 有些本地服务**自身没有认证**（两个 GUI、Ollama 等），挂出去就等于公开——
  门户这层口令是它们唯一的关卡。
- 本插件**不会**碰 dsh-pocket 自己的隧道（目标 3081）；`--stop` 只停自己记录的进程。

## 测试

```powershell
$node = "$env:LOCALAPPDATA\Programs\DeepSeek Harness\resources\runtime\primary-runtime\dependencies\node\bin\node.exe"
& $node --test test/host.test.mjs      # 18 项宿主端控制检验
& $node --test test/client.test.mjs    # 14 项客户端分发契约检验
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
- **运行时热改挂载表**：当前改服务清单要重启启动器（会换域名）。
- **门户页交互 UI**：现在根路径只有一张静态列表，不是可点击开关的面板。

## 许可证

MIT，Copyright (c) 2026 LaoDing。第三方致谢见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。