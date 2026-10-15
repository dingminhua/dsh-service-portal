# 第三方开源声明（Third-Party Notices）

> 本文件记录本仓库在设计、实现与外观上参考或借鉴的开源项目，以及各自的许可证与合规要求。
>
> 通用平台与构建依赖（`@deepseek-ai/*`、`cloudflared` 等）的许可证随各自 npm 包 / 二进制自动
> 携带，不属于本文档范围。
>
> 若你对本文件的完整性有疑问或发现遗漏，请提交 issue 或 PR。

## 一、项目缘起

本项目（对外服务门户）最初长在 **`ld-rl-poker`** 仓库里，为了把它的训练配置台/模型查看台放到外网。
2026-10-15 拆分为独立基础设施仓库 `dsh-service-portal`：门户本身与德州扑克无关，任何本地服务
都能用同一套「一个域名 + 一个口令 + 按需挂载」。拆分后本仓库**不 import 任何宿主代码**，两侧
通过服务清单（`services.json`）解耦。

## 二、参考项目清单

| 项目 | 仓库 | 参考内容 | 许可证 |
| --- | --- | --- | --- |
| `ld-rl-poker`（自研） | 本机 `D:\DshProject\ld-rl-poker` | 门户的三个 Python 工具（隧道启动器、认证代理、机器状态采集）最初实现于此，随迁移带入并继续演化 | **MIT**（Copyright (c) 2026 LaoDing） |
| `dsh-connect-workbuddy` | <https://github.com/dingminhua/dsh-connect-workbuddy> | 插件家族品牌图标（`client/icon.ts` 内联的 64px data URI，逐字节相同）；设置卡片外观风格 | **MIT**（Copyright (c) 2026 LaoDing） |
| `dsh-connect-trae` | <https://github.com/dingminhua/dsh-connect-trae> | `dsm-*` 卡片样式与 `row.*` 文案键约定（经 `dsh-subagent-default-model` 承继） | **MIT**（Copyright (c) 2026 LaoDing） |
| `dsh-subagent-default-model` | <https://github.com/dingminhua/dsh-subagent-default-model> | 插件家族的卡片 CSS 与品牌图标基准 | **MIT**（Copyright (c) 2026 LaoDing） |
| Cloudflare `cloudflared` | <https://github.com/cloudflare/cloudflared> | quick tunnel 二进制（随机 trycloudflare 域名）；不随本仓库分发 | **Apache-2.0**（Cloudflare） |
| `dsh-pocket` | DeepSeek Harness 运行时 | 提供 `cloudflared.exe` 的常用安装位置（`~/.dsh/dsh-pocket/bin/`）；本仓库不依赖其隧道 | DeepSeek |

> 迁移说明：专用子插件 `dsh-poker-viewer` 已不存在（2026-10-15 功能吸收进根插件、
> 目录删除），故不再单列条目；其能力已并入本仓库（门户插件 + Python 工具）。

## 三、随包分发

本文件已列入 `package.json` 的 `files` 白名单，随 npm 包一同分发，确保最终用户在安装包内即可
看到完整的第三方声明。入包文件为：

- `lib/`（宿主端 + 客户端产物）
- `icons/`（家族品牌图标）
- `cordis.patch.yml`、`README.md`、`README.en.md`、`CHANGELOG.md`、`THIRD_PARTY_NOTICES.md`、`LICENSE`

## 四、使用方式

- **借鉴设计思路 + 独立实现**：三个 Python 工具的原始实现来自 `ld-rl-poker`（同作者，迁移授权无
  障碍），迁入后持续演化并配齐控制检验；插件本体（`lib/index.js`、`client/`）为本仓库独立编写。
- **家族图标复用**：`client/icon.ts` 内联的 64px 品牌 data URI 与 `dsh-connect-workbuddy` /
  `dsh-connect-trae` 完全一致（同作者家族资产，MIT），未做任何修改。
- **除此之外不复制源码**：`cloudflared` 为外部二进制，运行时按 PATH / 常见位置查找，不打包分发。
- **后续引入依赖时**：引入任何新的外部依赖、或复用其他项目代码时，必须同步更新本文件，并遵守
  对应许可证的署名与声明要求。