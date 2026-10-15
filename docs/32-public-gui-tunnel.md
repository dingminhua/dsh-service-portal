# 32 · 外网访问两个 GUI（随机域名 + 随机口令）

> **给 AI 的一句话**：用户要「在外网打开训练配置台和模型查看台」时，**唯一正确入口**是
>
> ```
> python -X utf8 tools/start_public_gui.py
> ```
>
> 它自己做三件事：拉起 GUI（没跑就拉）→ 生成**随机口令**并起 Basic Auth 代理 → 用 cloudflared
> 生成**随机域名**并建隧道。**不要**试图「在 dsh-pocket 那个域名后面加路径」——那条路走不通，
> 原因见第 2 节。**不要**把 8810/8811 直接交给隧道：那两个 GUI **完全没有认证**，
> 直连等于把「启动/停止训练」的权限公开给任何拿到域名的人。

更新：2026-10-15 · 实现：`tools/start_public_gui.py`、`tools/tunnel_auth.py` · 检验：`tools/check_tunnel_auth.py`

---

## 1. 用户要什么 / 怎么做

| 我想干的事 | 命令 |
| :--- | :--- |
| **在 DSH 设置页点按钮开关**（推荐） | 装 `dsh-service-portal` 插件 → 设置里打开「对外服务门户」 |
| 开外网访问（两个随机域名） | `python -X utf8 tools/start_public_gui.py` |
| **一个域名 + 路径**（`/train/`、`/viewer/`） | `python -X utf8 tools/start_public_gui.py --single-domain` |
| 只开某一个（train / viewer） | `python -X utf8 tools/start_public_gui.py --only viewer` |
| 看当前域名、口令、是否存活 | `python -X utf8 tools/start_public_gui.py --status` |
| 关掉外网入口 | `python -X utf8 tools/start_public_gui.py --stop` |
| 指定口令（不建议） | `--password '...'`（≥12 字符，否则拒绝启动） |
| 指定 cloudflared / python | `--cloudflared <path>` / `--python <path>` |

### DSH 插件：`dsh-service-portal`（门户根插件，2026-10-15）

本仓库根目录即插件本体（包名/id=`dsh-service-portal`），以 DSH 的 **link 本地插件**方式安装
（与 `dsh-ldvh` 同类）。它在设置页提供「对外服务门户」一节：一键开启/关闭、
显示连接地址与口令。**这是门户的通用功能，不绑定任何具体服务**——服务清单
（`services.json`）决定开放什么；本插件的两个 GUI 只是内置默认清单。

**它是启动器，不是第二份实现**：底层仍然调本仓库的 `tools/start_public_gui.py`，
所以隧道/认证/路径分流只有一份实现、一套控制检验。理由与取舍见仓库 README。

```powershell
$dsh = "$env:LOCALAPPDATA\Programs\DeepSeek Harness\resources\runtime\cli\bin\dsh.cmd"
& $dsh plugin --profile desktop add "link:D:/DshProject/dsh-service-portal"
# 装完需要重启 DSH（插件在宿主进程里加载）
```

> 迁移说明：2026-10-15 曾有专用子插件 `dsh-poker-viewer`（ld-rl-poker 外网开关），
> 其功能已**吸收进根插件**成为通用门户能力，子插件目录已删除。若旧 profile 仍装着
> `dsh-poker-viewer`，用 `dsh plugin --profile desktop remove dsh-poker-viewer` 移除。

> **⚠ 2026-10-15 踩过的坑（启动致命错误）**：插件原先声明了
> `dsh.client.platform = "web"`，但 `package.json` 的 `exports` 里**没有**
> `"./client"`，产物也错放在 `client/client.js`。DSH 客户端模块扫描按
> `<包名>/client` 解析前端入口时抛 **`ERR_PACKAGE_PATH_NOT_EXPORTED`** ——
> 这是**启动期致命错误，整个 host 起不来**。WorkBuddy 检测到后在
> `~/.dsh/profiles/desktop/cordis.patch.yml` 里写入 `disabled: true` 把插件隔离，
> 才救回启动。
>
> **为什么之前的 26 项测试没发现**：那些测试只验证 `lib/index.js` 自身能否跑，
> 从没验证**包对外声明的入口是否真能解析**。现已补上——用 Node 自己的解析器
> （DSH 用的就是它）按 `<包名>/client` 真解析一遍，并已通过变异测试证明可证伪
> （删掉 `./client` 导出后该检查立刻失败）。
>
> 修复：`exports` 补 `"./client": "./lib/client.js"`，产物改出到 `lib/`，
> 并按家族规范补 `icon` 字段。**插件必须出现在 profile 的 `dsh.profile.bundles`
> 里**才会加载（只在 `dependencies` 里不够——这正是接口一直 404 的原因）。

插件自带的 HTTP 接口（挂在宿主 webServer，`prefix` 路由）：

| 方法 | 路径 | 作用 |
| :--- | :--- | :--- |
| GET | `/service-portal/api/status` | 状态：是否运行、模式、地址、口令、端点 |
| POST | `/service-portal/api/start` | 启动（默认单域名+路径） |
| POST | `/service-portal/api/stop` | 停止 |

**两种模式的区别**：

| | 默认（两个随机域名） | `--single-domain`（一个域名 + 路径） |
| :--- | :--- | :--- |
| 外网 URL | `https://A.trycloudflare.com` + `https://B.trycloudflare.com` | `https://X.trycloudflare.com/train/` 与 `/viewer/` |
| 代理端口 | 8890 / 8891（每个站一个） | 8899（一个代理内部按前缀分流） |
| 页面改动要求 | 无 | 页面需按 `location.pathname` 推导前缀（**已实现**） |
| 适用场景 | 最省事 | 想要「一个入口，路径区分」 |

启动后脚本会打印**两个外网 URL + 用户名 + 口令**，同时落盘：

| 文件 | 内容 | 是否机密 |
| :--- | :--- | :--- |
| `runs/public_gui_credentials.json` | 用户名、**明文口令**、两个 URL | **是，勿外发、勿入库**（已 gitignore） |
| `runs/public_gui_state.json` | 本次启动的 PID（供 `--stop`） | 否 |
| `runs/public_gui_logs/*.log` | 各子进程日志（含 cloudflared 的域名 banner） | 否 |

给 AI 的取用方式（不要在回答里凭空编 URL）：

```powershell
python -X utf8 tools/start_public_gui.py --status     # 人类可读
# 或机器可读：
Get-Content runs\public_gui_credentials.json -Raw -Encoding UTF8 | ConvertFrom-Json
```

> 注意：PowerShell 读该文件**必须带 `-Encoding UTF8`**，否则中文被按 ANSI 解码、
> `ConvertFrom-Json` 直接报错（实测踩过，症状是口令变量变空）。

---

## 2. 为什么不能「在 dsh-pocket 现有域名后面加路径」（重要，别重复踩）

用户最初的想法是：既然 dsh-pocket 已经把 DSH 的 Web GUI 暴露到外网（他正在外网用），
那能不能在**同一个域名**后面加 `/train`、`/viewer` 就打开这两个页面？

**在那个既有域名上不行，有两个硬障碍：**

1. **dsh-pocket 用的是 cloudflared quick tunnel，是「单目标整站转发」。**
   实测其命令行就是 `cloudflared.exe --no-autoupdate tunnel --url http://127.0.0.1:3081 --protocol http2`
   —— 转发目标写死一个端口，**没有按路径分流的能力**。而且它由插件管理，
   我们**不该也不能**改它（用户正通过它与 AI 对话，动它等于断线）。
2. **两个 GUI 的页面原本全部用绝对路径引用资源与 API**（`/api/...`、`/vendor/...`、
   `/gtowizard_adapter.js`），挂到子路径下这些请求会打到域名根 → 全线 404。

**本方案的解法（已实现并实测）：另起一条自己的隧道 + 一层按路径分流的认证代理，
并让两个页面按 `location.pathname` 推导前缀。**

- 用**自己的** cloudflared 实例（不碰 dsh-pocket 那条），
- 代理 `tools/tunnel_auth.py --mounts '/train=127.0.0.1:8810,/viewer=127.0.0.1:8811'`
  按最长前缀分流并剥掉前缀，
- 两个页面各自算 `const BASE = <当前路径前缀>`，把 `fetch('/api/...')` 变成
  `fetch(BASE + '/api/...')`；挂在域名根时 `BASE` 为空串，**行为与改动前完全一致**。

于是 `--single-domain` 模式下：

```
https://<随机>.trycloudflare.com/train/   -> 127.0.0.1:8810 配置台
https://<随机>.trycloudflare.com/viewer/  -> 127.0.0.1:8811 查看台
https://<随机>.trycloudflare.com/         -> 落地页（列出两个入口，同样要口令）
```

**仍未做的**：把这三个入口放到**固定自有域名**下。那需要自有域名接入 Cloudflare
并用 **named tunnel** 写 ingress（quick tunnel 的域名每次启动都会变）。
「路径分流」本身已经可用；缺的只是「域名固定」。

---

## 1.5 机器状态条：CPU / 内存 / 显存 / GPU 利用率（2026-10-15）

**需求**：远程查看时要知道「这台机器现在到底在干什么」，两个页面都要显示这四项。

**实现**：`tools/host_metrics.py`（采集）+ 两个 GUI 的只读路由 `GET /api/host`
+ 两个页面顶部的状态条（每 5 秒轮询）。**不复杂**：核心是一个采集模块。

### 设计第一原则：读不到就说读不到，绝不画成 0

这是本项目「不崩、只给错误答案」纪律在监控场景的直接应用。远程的人**看不见机器**，
只能信这个面板；把缺失值画成 0 会让他以为机器空闲，而实际可能在满载或读数已坏。

| 情形 | 显示 |
| :--- | :--- |
| 真的 0%（机器空闲） | `0.0%` |
| 读不到（驱动异常 / nvidia-smi 的 `N/A` / 依赖缺失） | `—` + 明确错误文字 |
| HTTP 请求失败 | 全部清成 `—`（不保留陈旧值冒充当前状态） |

### 实现要点（都是实测踩出来的）

| 点 | 说明 |
| :--- | :--- |
| **psutil 首次调用恒为 0** | 实测 `psutil.cpu_percent()` 第一次返回 `0.0`（无基线）。模块先建立 0.35s 基线窗口再取差分，否则新连接第一屏会显示近 0% |
| **绝不在 GUI 进程里 import torch** | `torch.cuda` 初始化会建立 CUDA 上下文、占用显存并干扰正在跑的训练。GPU 信息一律走 `nvidia-smi` 外部进程 |
| **nvidia-smi 开销 46–54ms/次** | 不能每个 HTTP 请求都起子进程 → 带 1.5s TTL 缓存；`force` 可绕过 |
| **`N/A` / `[N/A]` 必须变 null** | 部分驱动会这样输出；兜底成 0 就是最危险的那种误读。多卡只取第一张（本项目单张 5090），并读回卡名以便确认没读错 |
| **超时与降级** | `nvidia-smi` 5s 超时（驱动卡死不能拖住 HTTP）；采集崩溃仍返回结构化 payload，HTTP 层不 500 |

### 控制检验

```
python -X utf8 tools/check_all.py --only "Host metrics"
```

`check_host_metrics.py` **23 项** + `check_host_metrics_pages.py` **23 项**，全部通过。
覆盖：`N/A`/`[N/A]`→null、非零退出/二进制缺失→error、字段数不足拒绝、
换 nvidia-smi 输出读数跟着变（反例控制）、真实负载下 CPU>0（正面控制）、
TTL 命中与 `force` 绕过、采集崩溃不 500、摘要行缺值显示「—」而非 `0%`、
两页面状态条存在且**既有页面契约不被破坏**。

**变异测试**（证明可证伪）：把 `N/A` 兜底成 `0.0` → 2 项失败；摘要行缺值显示 `0%`
→ 1 项失败；忽略 TTL → 2 项失败；全部被精确抓到。

**独立对拍**（2026-10-15）：模块报 CPU 3.4–4.5% 时，Windows 计数器
`\Processor(_Total)\% Processor Time` 报 2.9–3.7%；GPU 23% 对 `nvidia-smi` 的 24%，
两者一致。

---

## 3. 链路与端口

**默认模式（两个随机域名）：**

```
https://<随机A>.trycloudflare.com   ->  127.0.0.1:8890 (认证代理)  ->  127.0.0.1:8810 配置台
https://<随机B>.trycloudflare.com   ->  127.0.0.1:8891 (认证代理)  ->  127.0.0.1:8811 查看台
```

**单域名 + 路径模式（`--single-domain`）：**

```
https://<随机>.trycloudflare.com/         -> 落地页（列出入口，需口令）
                              /train/     -> 127.0.0.1:8899 (认证代理，剥前缀) -> 127.0.0.1:8810
                              /viewer/    -> 127.0.0.1:8899 (同一个代理，按前缀分流) -> 127.0.0.1:8811
```

| 角色 | 端口 | 谁启动 | 说明 |
| :--- | :--- | :--- | :--- |
| 配置台 | 8810 | 手动 / 本脚本 | `gui/server.py`，可启停训练 |
| 查看台 | 8811 | 手动 / 本脚本 | `gui/viewer_server.py --port 8811` |
| 认证代理（默认） | 8890 / 8891 | 本脚本 | 每站一个，只绑 127.0.0.1 |
| 认证代理（单域名） | 8899 | 本脚本 | 一个代理内含多个挂载点 |
| 隧道 | — | 本脚本 | 复用 dsh-pocket 自带的 `cloudflared.exe` |

**边界（不得混为一谈）**：

- **不会动** dsh-pocket 的那条隧道（目标 3081）——用户正通过它与 AI 对话，动它等于断线。
- `--stop` **只停本脚本记录的进程**（隧道 + 代理 + 本脚本拉起的 GUI），不碰用户手开的 GUI。
- 端口 8890/8891 若被占用，脚本**跳过并报错**，不会静默改端口。

---

## 4. 安全边界（必须对用户讲清）

- 本轮加的是 **HTTP Basic Auth**：口令随机、16 字符、只在 HTTPS 上传输（quick tunnel 自带 TLS）。
  **它挡不住**中间人以外的场景没问题，但**不等于**完整鉴权体系：没有速率限制、没有会话、
  没有二次验证。域名 + 口令泄露即等于完全控制，尤其是**配置台可以启停训练、直接占用 5090**。
- 口令**不进命令行**（走 `GUI_TUNNEL_PASSWORD` 环境变量），因为命令行会被
  `Get-CimInstance Win32_Process` 看到；但**明文落在 `runs/public_gui_credentials.json`**，
  该文件已 gitignore，**仍不应随意外发/截图**。
- 建议用法：**查看台（只读）可以常开外网；配置台只在需要时开**，用完 `--stop`。
- 隧道域名是随机的（trycloudflare 子域），但会出现在 cloudflared 日志与浏览器历史里，
  **随机域名 ≠ 安全**，真正的关卡是口令。

---

## 5. 控制检验（新增功能必配，已挂入统一入口）

```
python -X utf8 tools/check_all.py --only "Public GUI tunnel auth"
```

实测 **35 项全部通过、0 失败、0 跳过、退出码 0**（2026-10-15，
本地 stub 上游，不依赖 GUI 在跑，也不产生任何公网入口）。拦的是能「不崩、只给错误答案」的那几类：

| 检验 | 拦的 bug |
| :--- | :--- |
| 无凭据 / 错口令 / 错用户名 → 401 且带 `WWW-Authenticate` | 认证形同虚设；401 不带 challenge 则浏览器不弹密码框，用户以为服务坏了 |
| 被拒请求**上游命中 0 次**（单上游与挂载模式各一组） | 先转发再校验——未授权请求其实已经打到能启停训练的上游 |
| 正确凭据 → 200 且 body 与上游**逐字节一致** | 认证过了但转发吞了/改了内容（页面能开、数据是错的） |
| 路径+查询串（含 `%7C`）与 POST body（含中文）原样转发 | 查看台 `/combos?path=..` 与配置台 `/api/train/start` 被破坏 |
| 换上游 → 返回内容跟着变（反例控制） | 硬编码 / 缓存导致「都得好数」 |
| 上游不可达 → **502** | 返回 200 空 body（界面显示空数据，比报错更危险） |
| **前缀剥离**：`/train/api/x` → 上游 `/api/x`；`/train` 与 `/train/` → `/` | 子路径挂载时路径错位（页面白屏 / API 全 404） |
| **反例**：不带前缀的 `/api/runs` 必须原样转发 | 「什么都往前缀上凑」——把根路径请求也改写 |
| **多挂载点**：`/train` 与 `/viewer` 落到**不同**上游；最长前缀优先 | 两个站被路由到同一个上游（看起来能开、内容是另一个站的） |
| **落地页**：根路径给落地页且**同样需要认证**；未知前缀 **404** | 落地页免密泄露；未知前缀被落地页兜底成「看起来能用」 |
| 前缀归一化 `train`/`/train`/`/train/` 等价，`''`/`/`/None` 为空 | 配置写法不一致导致挂载点错位 |
| 函数层 + **真实 CLI 层**都拒绝空/弱口令 | 空口令也能启动，等于外网无密码 |
| 环境变量通道优先于 `--password` | 口令被迫写进命令行 |

> 实测价值：本检验在开发中**真的抓到过一个 bug** —— 未匹配前缀返回了 200 落地页而非 404
> （「拼错的路径看起来能用」），已修。

### 真实公网验收（2026-10-15，一次性）

除控制检验外，还从**真实外网 URL** 做了验证（HTTPS 打 trycloudflare 公网域名）：

**A) 默认模式（两个随机域名）**

| 探测 | 结果 |
| :--- | :--- |
| 无口令 / 错口令（两个站） | **401** |
| 正确口令取页面 | **200**，配置台 77496 B、查看台 148484 B —— 与本地页面文件字节数吻合 |
| 正确口令取 API | `train /api/config/list` 200 / 113 B；`viewer /api/runs` 200 / 30986 B |
| 未授权 POST | **401**（被代理拦在转发之前） |
| 授权 POST 打不存在的端点 | 上游自己的 **501/404** —— 证明写通道穿透，且**未触发任何训练** |

**B) 单域名 + 路径模式（`--single-domain`）**

| 探测（同一域名） | 结果 |
| :--- | :--- |
| `/` 无口令 → **401**；有口令 → **200** 落地页（408 B） | 落地页不免密 |
| `/train`、`/train/` 有口令 → **200**（78156 B） | 无尾斜杠也工作 |
| `/train/api/config/list` → 200（113 B）；`/train/api/presets` → 200（15275 B） | 配置台 API 在子路径下可用 |
| `/viewer` 无口令 → 401；`/viewer/` 有口令 → 200（148992 B） | |
| `/viewer/api/runs` → 200（30986 B） | 查看台 API 在子路径下可用 |
| `/viewer/vendor/gtowizard/assets/*.css` → 200（2887 B） | **静态资源**在子路径下可用 |
| `/viewer/gtowizard_adapter.js` → 200（2783 B） | 适配脚本可用 |
| `/nosuch/x` → **404** | 未知前缀不兜底 |

**C) 浏览器端真实渲染（headless Chrome，2026-10-15）**

| 页面 | 根路径 | 子路径 `/train/`、`/viewer/` |
| :--- | :--- | :--- |
| 查看台 | DOM 197655 B、13×13 网格已渲染、12 个 run 已从 API 载入 | DOM **197655 B（与根路径完全一致）**、网格已渲染、12 个 run 已载入、**零资源错误** |
| 配置台 | 预设下拉可载入 | DOM 67997 B、`presetList` 内 **7 个 option 已由 API 填充**、**零资源错误** |

同时从公网抓回的页面里，用**页面自己的 `BASE` 函数**（原文，非重写）验证：
`/`、`/train`、`/train/`、`/viewer`、`/viewer/`、`/foo/bar/`、`/index.html` 全部推导正确，
根路径得空串（= 改动前行为不变）。

### 对既有验收的影响（已跑，不得省略）

| 既有检查 | 结果 |
| :--- | :--- |
| `check_viewer_industry_standard.py`（读 `viewer_page.html` 源码，含第 12 项 GTO Wizard 实况复刻） | **12 项、失败 0**（3 项跳过=缺归档旧模型产物，属既有依赖缺失） |
| `check_config_gui.py` 里「页面必须含 `/api/presets`」的断言 | 仍通过 —— 因此页面的 `/api/...` **字面量被刻意保留**，只在实际请求时拼 `BASE` |
| `gui/server.py`、`gui/viewer_server.py` | **一行未改**（`git diff --stat` 为空)；改的是 `config_page.html` 与 `viewer_page.html` 两个页面 |
| `check_gpu_gui.py` | 运行失败，但**与本次改动无关**：它第 95 行断言 `srv.equal_initial_stack(...)`，而 `gui/server.py` 里只有 `gpu_initial_stack`（既有断言/函数名不匹配，我未改 `server.py`） |

### 7. 域名解析 bug（2026-10-15 开发插件时实测发现并修复）

**症状**：第二次（及以后）启动外网入口时，脚本报「隧道已建立」成功、代理端口在监听、
状态接口显示 `running=true`，但**凭据文件里记的是一个已经失效的地址**，外网打开是
Cloudflare **530**。首次启动正常，所以很容易被当成"偶发网络问题"。

**根因**：cloudflared 的 banner 是**追加**写进日志的。旧实现用
`URL_RE.search(整个日志)` 取**第一条**匹配 —— 于是第二次启动抓到的是上一次残留的
旧域名，本次真正可用的新域名从未被记录。

这是本项目最忌讳的「**不崩、只给错误答案**」：链路每一环都"看起来正常"，
只有真的从外网访问才发现打不开。

**修复**：`start_tunnel()` 记录启动前的日志字节数，`read_url(since=...)` 只解析
**本次新增区间**，并取其中**最后一个**域名（`findall()[-1]`）。

**控制检验**：`tools/check_tunnel_domain.py`（10 项，已挂统一入口），覆盖
「取最后一个而非第一个」「反例：不等于旧域名」「累积多次启动仍取最新」
「新增区间为空时返回 None 而不回退拿旧域名」「真错误返回 None 不编造」
「非 trycloudflare 域名不误认」，以及两条钉住调用点的源码级断言。

**实测复核**：修复后经插件重启，凭据记录的域名
`harper-equivalent-cups-thomas.trycloudflare.com` 正是日志中最后一个创建的域名，
且真实可用（无口令 401、有口令页面 200 共 78156/148992 字节）。

**边界**：以上只证明「认证 + 路径分流 + 转发 + 页面/接口/静态资源可达 + 页面 JS 正常渲染」。
**不构成**：策略质量、训练正确性、均衡收敛，也不证明该口令方案具备完善鉴权能力（见第 4 节）。

---

## 6. 常见问题

| 症状 | 原因 / 处理 |
| :--- | :--- |
| 浏览器一直弹密码框不进页面 | 用户名或口令不符；用 `--status` 看当前口令（口令每次重启都会换） |
| 域名打不开（DNS/连接失败） | quick tunnel 的域名是临时的，cloudflared 进程可能已退出；重跑启动脚本换新域名 |
| `--stop` 后说删了凭据但仍能打开 | 浏览器缓存了 Basic Auth；换无痕窗口确认，并检查 `--status` 是否全部「已停止」 |
| 端口 8890/8891/8899 被占用 | 上次没干净退出；`--stop`，或改 `TARGETS` / `--single-port` |
| 中文乱码 / `ConvertFrom-Json` 报错 | 读凭据文件必须 `-Encoding UTF8` |
| 子路径下页面白屏、控制台一堆 404 | 页面必须从 `location.pathname` 推导 `BASE`；本项目两个页面**已改好**。若你自己复制了旧页面文件，需同样处理 |
| `/train` 打开是别的站 / 内容错乱 | 挂载点前缀冲突；代理按**最长前缀优先**匹配，检查 `--mounts` 是否有重叠前缀 |
| 想让域名固定 | 需要自有域名 + **named tunnel**（ingress 写路径规则）。**路径分流本身已可用**（`--single-domain`）；缺的只是「域名固定」，当前未做 |
