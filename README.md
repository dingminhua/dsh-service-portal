# dsh-service-portal · 对外服务门户

一个随机域名 + 一个随机口令，把**本机的服务**按需对外开放。

- 仓库：`D:\DshProject\dsh-service-portal`
- 包名：`dsh-service-portal`（DSH 插件，见 [services/poker-viewer](services/poker-viewer)）
- 定位：**基础设施仓库**。放隧道、认证代理、机器状态采集与它们的控制检验；
  被对外开放的**服务本体**留在各自的宿主仓库里。

## 为什么独立成仓库

这些能力最初长在 `ld-rl-poker` 里（为了把它的训练配置台/模型查看台放到外网）。
但它们本身与德州扑克无关——任何本地服务都能用同一套「一个域名 + 一个口令 + 按需挂载」。
拆出来之后：

| | 放什么 |
| :--- | :--- |
| **本仓库**（dsh-service-portal） | 隧道、认证代理、机器状态采集、服务清单、控制检验、DSH 插件 |
| **宿主仓库**（如 ld-rl-poker） | 被对外开放的服务本体（那里有自己的训练/模型代码） |

两侧通过**服务清单**（`services.json`）解耦：本仓库不 `import` 任何宿主代码。

## 快速开始

```powershell
# 一个域名 + 路径（/train/、/viewer/）
python -X utf8 tools/start_public_gui.py --single-domain

# 两个独立随机域名
python -X utf8 tools/start_public_gui.py

# 查状态 / 关闭
python -X utf8 tools/start_public_gui.py --status
python -X utf8 tools/start_public_gui.py --stop
```

启动后打印外网 URL 与口令，凭据落在 `runs/public_gui_credentials.json`
（**含明文口令，已 gitignore，勿外发**）。

## 服务清单（核心抽象）

不填任何配置时用内置清单（= ld-rl-poker 的两个 GUI，保持向后兼容）。
要开放别的服务就写 `services.json`：

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

- `hostRepo`：服务脚本所在的宿主仓库根（脚本路径相对它解析）。
- `script` / `guiPort`：被拉起的服务与其端口。
- `proxyPort`：非单域名模式下每个服务各自的认证代理端口。
- `mount`：单域名模式下的路径前缀（`/train/`）。

## 工具

| 文件 | 作用 |
| :--- | :--- |
| `tools/tunnel_auth.py` | Basic Auth + 多挂载点路径分流反向代理（认证在转发之前） |
| `tools/start_public_gui.py` | 一键启动：读清单 → 拉服务 → 起代理 → 建 cloudflared 隧道 |
| `tools/host_metrics.py` | 机器状态采集（CPU / 内存 / 显存 / GPU 利用率） |

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
页面接线检查依赖宿主仓库的页面文件；不在就跳过（返回 2），不算通过。

## 安全边界（必须如实理解）

- 口令是**明文**存在 `runs/public_gui_credentials.json` 并明文显示在插件设置页。
- **拿到口令 == 服务就能被外网启停**。对 ld-rl-poker 而言 = 能启停 5090 上的训练。
- 有些本地服务**自身没有认证**（两个 GUI、Ollama 等），挂出去就等于公开——
  门户这层口令是它们唯一的关卡。
- 本仓库**不会**碰 dsh-pocket 自己的隧道（目标 3081）；`--stop` 只停自己记录的进程。

## 未做

- **固定自有域名**：需要 named tunnel + ingress。现在每次启动都是随机 trycloudflare 域名。
- **运行时热改挂载表**：当前改服务清单要重启启动器（会换域名）。
  若要做到「门户页点一下就开关服务且不换域名」，需要把挂载表从启动期常量改成可热改状态。
- **门户页交互 UI**：现在根路径只有一张静态列表，不是可点击开关的面板。
