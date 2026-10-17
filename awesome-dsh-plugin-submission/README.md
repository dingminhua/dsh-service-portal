# 市场收录目录（Awesome DSH Plugin Submission）

本目录存放本项目提交到 [Awesome DSH Plugin](https://github.com/awesome-dsh-plugin/awesome-dsh-plugin)
注册表的**条目草稿与操作说明**。正式条目以 PR 形式存在于该仓库，本目录是本地镜像。

## 收录条目

- **文件**：`dingminhua__dsh-service-portal.yml`（对应上游 `data/plugins/dingminhua__dsh-service-portal.yml`）
- **状态**：[PR #7566](https://github.com/awesome-dsh-plugin/awesome-dsh-plugin/pull/7566) 已提交（**OPEN**，非草稿），CI 通过：
  - `Submission gate` — pass
  - `check` — pass
  - 合入前等待维护者人工评审（CI 是前置条件，不是结论）
- **分类**：`remote`（对外服务门户：隧道 + 口令登录 + 按路由开放/屏蔽本机服务）
- **前置要求核对**（对照 contributing.md 逐条复核）：
  - [x] 仓库根 `package.json` 声明 `dsh.bundle.patch: ./cordis.patch.yml`，且根目录确有 `cordis.patch.yml`
  - [x] 仓库打 `dsh-plugin` topic（现共 **10** 个 topic：另含 deepseek-harness / cloudflared / remote-access 等）
  - [x] 仓库满 1 天（createdAt `2026-10-15T04:31:46Z`，已满足；贡献指南**无提交数门槛**）
  - [x] 真实可用代码（非占位 / 非纯 README / 非纯聚合包）：host 插件 `lib/index.js`、前端 `client/index.jsx` → `lib/client.js`、Python 门户 `tools/portal_*.py`
  - [x] 官方包声明合规：`@deepseek-ai/*` 走 `peerDependencies`；peer 范围带**显式预发布分支**（如 `>=4.0.1-rc.1 <4.0.5-0 || >=4.0.5-alpha.1 <5.0.0-0`）
  - [x] 截图在**本仓库**声明：根目录 `screenshots.json` 列 **5** 张（`docs/assets/panel-both.png`、`portal-console.png`、`portal-phone.png`、`portal-phone-dark.png`、`portal-wide.png`），均为 1–8 张范围内、相对路径且文件存在
  - [x] 运行期脚本随包分发：`files` 白名单含 `tools`（v0.8.6 修复，见 CHANGELOG）
  - [x] 描述不含营销词，且每条具体声明均可在源码中核对（见下）

## 描述与代码的对应（评审会逐句核对）

| 条目中的说法 | 代码位置 |
| --- | --- |
| any local service | `tools/portal_registry.py` — 通用路由注册表（mount → 上游 `host:port`），不绑定任何具体服务 |
| LAN address | `tools/portal_run.py` 绑定 `0.0.0.0`；`tools/lan_address.py` 选取网卡地址 |
| public cloudflared quick-tunnel domain | `tools/portal_run.py` 启动 `cloudflared tunnel` 并从日志解析 `*.trycloudflare.com` 域名 |
| one password login | `tools/portal_login.py` — 只验口令的登录页，单个口令输入框，无账号字段 |
| per-route open/block gates | `tools/portal_registry.py` 的 `enabled` 与 `set_enabled`；闸门只停止门户转发，不影响上游进程（`tools/check_gate_does_not_stop_upstream.py`） |
| managed from the plugin settings page | `client/index.jsx` 注册 `plugins.bundle.config` 与 `plugins.row.config` |

## 收录目录规范（依据 [contributing.md](https://github.com/awesome-dsh-plugin/awesome-dsh-plugin/blob/main/contributing.md)）

- 每个插件一个 YAML：`data/plugins/<owner>__<repo>.yml`（一个文件就是全部投稿）
- 字段：
  - `url`：与仓库地址**完全一致**（monorepo 子包则指向子目录）
  - `name`：`owner/repo`（monorepo 子包用 `owner/repo#subname`）
  - `category`：有效值之一（本项目为 `remote`）
  - `description.en`：必填，一行，以句号结尾；含 `: `（冒号+空格）必须加引号
  - `description.zh`：可选，维护者会补
  - `tarball`：可选，必须是 GitHub Release 托管的 https `.tgz`；不填则市场走源码构建
  - 手写 `npm:` 键会被校验拒绝——npm 映射由 registry 自动采集
- 前置要求：
  - 仓库 `package.json` 声明 `dsh.bundle` manifest（只声明 `dsh.client` 会失败）
  - 仓库打 `dsh-plugin` topic
  - 仓库满 1 天（CI 自动检查，**无提交数门槛**）
  - 项目活跃维护；描述属实、不带营销词；分类贴合实际功能
  - 纯聚合包（只装别人的插件、自己不带行为）不单独收录
- 截图：在本仓库 `package.json` 旁放 `screenshots.json`（1–8 张，相对路径不得跳出插件目录，或以 GitHub 托管的 https 绝对 URL 给出）。**不要**再往上游 `data/screenshots.json` 加键。
- README（上游 `README.md` / `README.zh.md`）由脚本从 `data/plugins/*.yml` 生成，**不要手工编辑**；合并后会在 `main` 上自动重新生成。本地预览：
  ```sh
  npm ci
  node scripts/generate-readme.mjs
  ```
- 一个 PR 最多收录 3 条；更新自己的条目时**只改自己那一条**。

## 更新步骤（改条目内容时）

1. 修改本目录的 `dingminhua__dsh-service-portal.yml` 草稿
2. 在 fork（`dingminhua/awesome-dsh-plugin`）的分支 `add-dsh-service-portal` 上同步修改
   `data/plugins/dingminhua__dsh-service-portal.yml`
3. 不需要重新生成 README（合并后在 `main` 上自动生成；本地生成也可接受，但必须与数据源一致）
4. 推送到**同一个分支**即可，PR 自动重跑 CI，无需重开 PR
