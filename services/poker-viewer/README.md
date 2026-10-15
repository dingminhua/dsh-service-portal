# dsh-poker-viewer

ld-rl-poker **训练配置台**与**模型查看台**的外网开关（DSH 插件）。

在 DSH 设置页一键开启/关闭外网访问，并显示连接地址与口令。

## 它是什么 / 不是什么

**是**：一个**启动器**。负责调起/停止 ld-rl-poker 仓库里已经过验收的实现，
把 URL 与口令读出来给设置页显示。

**不是**：第二份隧道实现。隧道与认证代理由 ld-rl-poker 仓库承担：

| 组件 | 位置 | 作用 |
| :--- | :--- | :--- |
| `tools/start_public_gui.py` | ld-rl-poker 仓库 | 一键启动：拉 GUI → 起认证代理 → 建隧道 |
| `tools/tunnel_auth.py` | ld-rl-poker 仓库 | Basic Auth + 路径分流反向代理 |
| `gui/server.py` / `gui/viewer_server.py` | ld-rl-poker 仓库 | 两个 GUI 本体 |

复用的理由：那套实现已有 **35 项控制检验 + 10 项域名解析检验**，并通过了
真实公网三态探测与 headless 浏览器渲染验证。在插件里重写一遍会产生第二份实现，
日后修 bug 要改两处。

## 安装

```powershell
$dsh = "$env:LOCALAPPDATA\Programs\DeepSeek Harness\resources\runtime\cli\bin\dsh.cmd"
& $dsh plugin --profile desktop add "link:D:/DshProject/dsh-poker-viewer/plugin"
```

装完**需要重启 DSH**（插件在宿主进程里加载）。已确认它出现在 profile 的
`bundles` 列表里。

## 配置（DSH 设置页）

| 字段 | 默认 | 说明 |
| :--- | :--- | :--- |
| `repoPath` | `D:\DshProject\ld-rl-poker` | ld-rl-poker 仓库根目录 |
| `pythonPath` | 空 | 拉 GUI 用的解释器；留空则自动选 `.venv313` → `.runtime` → PATH |
| `webEnabled` | `true` | 是否挂载 `/poker-viewer/api` 路由 |

三个字段都是 `.volatile()`：改设置即时生效，不需要重挂插件。

## HTTP 接口

挂在宿主 webServer 上（`prefix` 路由，路径 `/poker-viewer/api`）：

| 方法 | 路径 | 作用 |
| :--- | :--- | :--- |
| GET | `/poker-viewer/api/status` | 当前状态：是否运行、模式、地址、口令、端点列表 |
| GET | `/poker-viewer/api` | 等同 `/status` |
| POST | `/poker-viewer/api/start` | 启动（body 可选 `{"singleDomain": true}`，默认单域名+路径） |
| POST | `/poker-viewer/api/stop` | 停止 |

未知子路径返回 **404**（不拿 status 兜底——拼错的路径不许「看起来能用」）。

## 安全边界（必须如实理解）

- 口令是**明文**存在 `runs/public_gui_credentials.json`，并按用户选择**明文显示**在设置页。
- **拿到该口令 == 能启停 5090 上的训练**。配置台可以启动/停止训练任务。
- 插件**不会**动 `dsh-pocket` 自己的隧道（目标 3081，用户用它连 DSH），
  只碰本项目脚本记录的子进程。
- 建议：查看台（只读）可以常开；配置台用完就关。

## 测试

```powershell
$node = "$env:LOCALAPPDATA\Programs\DeepSeek Harness\resources\runtime\primary-runtime\dependencies\node\bin\node.exe"
& $node --test test/host.test.mjs      # 16 项宿主端控制检验
& $node test/e2e-http.mjs              # 真实 HTTP 路由验证
& $node test/e2e-lifecycle.mjs         # 启停闭环（会真的起/停隧道）
```

宿主端 16 项已通过**变异测试**验证可证伪：把 `running` 改成只看凭据文件、把端口探测
改成恒真，两项检查都被精确抓到（15/1 与 14/2 失败），还原后 16/16 全绿。

## 已修复的上游 bug（2026-10-15）

开发本插件时发现 `tools/start_public_gui.py` 的真 bug：cloudflared 日志是**追加**写的，
旧实现用 `URL_RE.search(全文)` 取**第一条**域名，于是第二次启动会把**上一次残留的
旧域名**记进凭据文件——脚本报成功、端口在监听、状态显示 running=true，但外网打开是
Cloudflare **530**。这正是本项目最忌讳的「不崩、只给错误答案」。

已修（取新增区间内最后一个域名 + 调用点传 `since`），并新增
`tools/check_tunnel_domain.py`（10 项）钉住。修复后实测凭据记录的域名真实可用。
