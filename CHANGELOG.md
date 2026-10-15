# Changelog

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