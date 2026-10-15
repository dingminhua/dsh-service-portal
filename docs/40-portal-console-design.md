# 门户控制台改造设计（对齐 dsh-pocket 体验）

> 2026-10-15。目标：把「服务清单 JSON + 设置页总开关」升级为**自己的网页控制台**，
> 内网/外网两种访问方式，页面上自己管理服务与路由。
>
> 参照实现：`D:\DshProject\dsh-pocket`（shaobeichen/dsh-pocket v2.11.0，MIT）。

## 一、参照对象的关键设计（读源码得出）

| dsh-pocket 的做法 | 我们照搬的判断 |
| :--- | :--- |
| `classifyHost(host)` → `loopback` / `lan` / `public` 三分类 | **照搬**。这是内外网并存的核心：同一进程按 Host 决定要不要密码 |
| fail-closed 兜底：认不出的 Host 按**公网**处理 | **照搬**。宁可多要一次密码，也不能让自建域名绕过认证 |
| 公网始终要密码；局域网可开关；loopback 免密 | **照搬**（用户已确认：内网免密、外网必须口令） |
| 登录页是自定义 HTML（不弹浏览器原生框） | 已完成（上一轮改造） |
| 登录限速：单 IP 5 次失败锁 60s + 全局阈值 | **照搬** |
| `cf-connecting-ip` 仅在源地址是 loopback 时信任 | **照搬**。否则直连端口的人可以伪造 IP 绕过限速 |
| 会话 cookie 与 dsh web 进程绑定（重启要重输） | 已等价实现（会话密钥随进程随机） |
| 二维码 / 手机适配 | **照搬**（用纯 Python 生成 SVG 二维码，不引入依赖） |
| 隧道自动下载 cloudflared（多镜像源） | **复用已有**：本机已有 cloudflared，先不自己下载 |

## 二、新架构

```
                      ┌──────────────── 门户进程（一个端口，比如 8899）─────────────┐
   内网 http://192.168.x.x:8899  ──┐                                              │
                                  ├─▶ classifyHost() ─▶ 控制台页 / 认证 / 代理     │
   外网 https://xxx.trycloudflare ─┘        │                                     │
                                            ├─ /                → 控制台页（服务管理）
                                            ├─ /_auth/login     → 口令登录
                                            ├─ /_api/*          → 控制台 API（增删改查/开关）
                                            └─ /<mount>/...     → 代理到对应上游服务
                                                              └──────────────────┘
```

**与现状最大的区别**：不再需要 `services.json` 手工配置 + 重启。服务是**运行时可变的注册表**，
在控制台页面上增删改，立即生效（无需重建隧道）。

### 组件划分（各自独立文件，接口固定）

| 文件 | 职责 | 关键接口 |
| :--- | :--- | :--- |
| `tools/portal_registry.py` | **服务注册表**：增删改查 + 持久化 JSON | `Registry(path)`；`.list() .add() .update() .remove() .set_enabled()` |
| `tools/portal_proxy.py` | **三分类认证代理**：Host 分类、认证、限速、转发 | `make_portal_server(...)`；`classify_host() / classify_source()` |
| `tools/portal_console.py` | **控制台页面**：HTML 渲染（服务列表/表单/二维码） | `console_html(state, ...)`；`qr_svg() / qr_data_uri()` |
| `tools/portal_login.py` | 登录页 + 会话（**已存在**） | 保持不动，扩展 `classify` 支持 |
| `tools/start_public_gui.py` | 启动器：拉起服务 + 起门户 + 建隧道 | 加 `--portal-port` 等 |

### 数据流

1. 用户在控制台点「添加服务」→ `POST /_api/services` → `Registry.add()` → 落盘 → 页面刷新显示
2. 用户点某服务的「开启」→ `POST /_api/services/<key>/enable` → 注册表置位 → **确保该服务已拉起** → 状态变绿
3. 用户点服务链接 → `GET /<mount>/...` → 代理按注册表找到上游 → 转发
4. 外网访客访问任何路径 → classify=public → 无有效会话 → 登录页
5. 内网访客访问控制台 → classify=lan → **免密**直接看到控制台（按用户选择）

### 服务条目模型（注册表）

```jsonc
{
  "key": "train",              // 唯一标识，用于 URL 与 API
  "name": "训练配置台",         // 显示名
  "mount": "/train",           // 路由路径（用户在页面上设）
  "target": "127.0.0.1:8810",  // 上游地址（可手填，也可由脚本拉起）
  "script": "gui/server.py",   // 可选：拉起用的脚本（相对 hostRepo）
  "cwd": "",                   // 可选：工作目录（相对 hostRepo）
  "enabled": true,             // 是否对外开放（用户在页面上开关）
  "autoStart": false,          // 门户启动时是否自动拉起
  "note": ""                   // 备注
}
```

### 认证策略（照搬 dsh-pocket 的矩阵）

| Host 分类 | 控制台页 | 代理服务 | 说明 |
| :--- | :--- | :--- | :--- |
| `loopback`（127.x/localhost） | 免密 | 免密 | 本机/隧道回连 |
| `lan`（私网 IP/单标签名） | **免密**（用户已选） | 免密 | 同一 WiFi |
| `public`（其余一切） | **必须口令** | **必须口令** | 含自建域名（fail-closed） |

> ⚠️ 关键安全点：**fail-closed**。判断不出分类时按 `public` 处理。

## 三、控制检验清单（每条都要有可证伪的项）

- **分类**：`192.168.x` / `10.x` / `172.16-31.x` / `100.64.x`(CGNAT) / `*.local` / 单标签名 → lan；
  `localhost`/`127.x`/`::1` → loopback；`xxx.trycloudflare.com` / 公网 IP / **自建域名** → public；
  畸形/空 Host → **public（fail-closed）**
- **认证**：public 无会话 → 登录页且**不触达上游**；lan → 免密可看控制台；loopback → 免密
- **限速**：连续 5 次错口令 → 锁 60s；正确口令清空计数；`cf-connecting-ip` 仅在 loopback 源时信任
- **注册表**：增删改查、key 唯一性、mount 格式校验（必须以 / 开头、不与保留路径冲突）、
  持久化后重读一致、损坏文件不崩
- **控制台**：列服务、显示内外网地址、显示二维码、逐服务开关按钮、未启用服务不代理

## 四、分期

1. **本期**：注册表 + 三分类代理 + 控制台页 + 启动器接入 + 插件集成 + 控制检验 + 文档
2. 后续（可选）：cloudflared 自动下载、命名隧道固定域名、服务健康检查定时刷新
