# Changelog

## 0.1.0 (2026-10-15)

### Features

- **初始发布**：对外服务门户插件 `dsh-service-portal`（自 `ld-rl-poker` 迁入基础设施仓库）。
  - 一键对外开放本机服务：`cloudflared` 随机域名 + Basic Auth 随机口令。
  - 两种形态：每服务独立随机域名 / 单域名 + 路径前缀（`--single-domain`）。
  - 服务清单驱动（`services.json`），不填用内置默认（ld-rl-poker 的两个 GUI，向后兼容）。
  - DSH 设置页「对外服务门户」一节：一键开启/关闭、显示连接地址与口令（明文，用户选型）。
  - 宿主端 18 项 + 客户端 14 项控制检验；与 `services/poker-viewer` 子插件共享门户基础设施。

### Docs

- 仓库 README 改为插件发布视角（安装 / 工作原理 / 服务清单 / 安全边界 / 控制检验）；
  新增英文版 README.en.md、THIRD_PARTY_NOTICES.md、RELEASING.md、CHANGELOG.md。