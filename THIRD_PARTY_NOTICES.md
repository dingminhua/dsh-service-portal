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
| `dsh-pocket` | <https://github.com/shaobeichen/dsh-pocket> | **设计参照**（非代码复用）：门户形态、Host 三分类认证、fail-closed 兜底、登录限速阈值、`cf-connecting-ip` 信任边界、二维码/移动端体验 | **GPL-2.0**（详见下文 §五） |
| `dsh-web-mobile` | <https://github.com/mexiaosqwq/dsh-web-mobile> | 移动端适配的**设计源头**（dsh-pocket 移植自它）；本项目未直接使用其代码 | **MIT** |

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

## 五、`dsh-pocket` 与 GPL-2.0 边界（重要）

`dsh-pocket` 采用 **GPL-2.0**（强 copyleft），是本项目唯一一个「非宽松许可」的参照对象。
因此这里把边界写清楚，避免将来有人误判。

### 我们用了它什么

**只用了设计判断，没有用代码。** 具体参照点（逐条可在本仓库代码中对应）：

| 参照的设计 | 本仓库实现位置 |
| :--- | :--- |
| 把 Host 分成 `loopback` / `lan` / `public`，按类别决定认证强度 | `tools/portal_proxy.py::classify_host()` |
| **fail-closed**：认不出的 Host 一律当公网 | 同上，且有 20 项分类检验（含自建域名必须判公网） |
| 公网必验、内网可免、回环免验的认证矩阵 | `open_classes` 配置 + `_needs_auth()` |
| 登录失败限速阈值（单 IP 5 次 / 60 秒锁 + 全局阈值） | `tools/portal_proxy.py::RateLimiter` |
| `cf-connecting-ip` 仅在源地址为 loopback 时可信 | `tools/portal_proxy.py::client_ip()` |
| 自定义登录页（避免浏览器原生认证框） | `tools/portal_login.py` |
| 扫码即用、移动端单列布局 | `tools/portal_console.py` |

### 为什么这不构成衍生作品

1. **语言与结构不同**：`dsh-pocket` 是 JavaScript（`lib/proxy.mjs`、`lib/tunnel.mjs`、`client/`），
   本项目门户是 Python（`tools/portal_*.py`）。文件、函数、数据流均为独立设计。
2. **接口不兼容**：双方 HTTP 端点、cookie/口令存储格式、配置键名都不一样，无法互相替换或对接。
3. **无代码片段**：本仓库不含其任何源码片段、常量表、注释文本或资源文件。
   （自检：在本仓库搜索 `dsh_pocket_token`、`classifyHost`、`createRateLimiter`、
   `TRANSPORT_API_CLIENT_SHIM` 等其标识符，均无命中。）
4. **参照的是结论而非表达**：认证矩阵、限速阈值、「自建域名必须当公网」这类是**功能性判断**，
   属于思想而非受版权保护的表达；我们按自己的结构重新实现，并配了本项目自己的控制检验。

据此，本项目的 MIT 许可**不因参照 GPL-2.0 项目而受传染**。

### 红线（必须遵守）

- ❌ **不要把 `dsh-pocket` 的源码片段拷进本仓库** —— 一旦发生，整个项目须按 GPL-2.0 分发义务
  处理，MIT 声明即失效（这是许可合规事故，不是小事）。
- ❌ 不要复制它的 `client/`（前端资源）或 `lib/proxy.mjs` 的任何代码/注释文本。
- ✅ 可以继续参考其**公开文档描述的行为与设计取舍**，并用本项目自己的代码实现。
- ✅ 若将来确实需要其某项实现，先在 issue 里明确讨论许可影响，再决定是否整体转 GPL-2.0。

### 为什么仍然致谢

它是这个门户形态的直接灵感来源（尤其是 fail-closed 那条：反着写就会让自建域名绕过认证，
这是用真实安全问题换来的结论）。作者 `shaobeichen` 把 `dsh-pocket` 开源出来，
本项目才有一个「内网 + 外网、扫码即用」的成熟体验可以对照。**注明许可与边界，是对作者
工作最基本的尊重，也让后来的读者能自己判断。**
