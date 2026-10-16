# 市场收录目录（Awesome DSH Plugin Submission）

本目录存放本项目提交到 [Awesome DSH Plugin](https://github.com/awesome-dsh-plugin/awesome-dsh-plugin)
注册表的**草稿**。正式提交以 PR 形式存在于该仓库，本目录是本地镜像与操作说明。

## 收录条目

- **文件**：`dingminhua__dsh-service-portal.yml`
- **状态**：草稿（尚未提交 PR）
- **分类**：`remote`（对外服务门户：隧道 + 认证代理 + 按需开放本机服务）
- **前置要求核对**：
  - [x] 仓库根 `package.json` 声明 `dsh.bundle.patch: ./cordis.patch.yml`
  - [x] 仓库打 `dsh-plugin` topic（已确认，另含 deepseek-harness / cloudflared 等共 6 个）
  - [x] 仓库满 1 天（createdAt `2026-10-15T04:31:46Z`，已 > 1 天；贡献指南**已取消**提交数门槛）
  - [x] 官方包声明合规：`@deepseek-ai/*` 走 `peerDependencies`；cordis 范围带显式预发布分支
  - [x] 补截图：`docs/assets/` 三张（窄屏浅色 / 窄屏深色 / 宽屏），根目录 `screenshots.json` 已声明
  - [x] 运行期脚本随包分发：`files` 白名单含 `tools`（v0.8.6 修复，见 CHANGELOG）

## 收录目录规范（依据 [contributing.md](https://github.com/awesome-dsh-plugin/awesome-dsh-plugin/blob/main/contributing.md)）

- 每个插件一个 YAML：`data/plugins/<owner>__<repo>.yml`
- 字段：
  - `url`：与仓库地址**完全一致**（monorepo 子包则指向子目录）
  - `name`：`owner/repo`（monorepo 子包用 `owner/repo#subname`）
  - `category`：有效值之一（本项目为 `remote`）
  - `description.en`：必填，一行，以句号结尾；含 `: ` 必须加引号
  - `description.zh`：可选，维护者会补
- 前置要求：
  - 仓库 `package.json` 声明 `dsh.bundle` manifest（本项目已满足）
  - 仓库打 `dsh-plugin` topic
  - 仓库满 1 天、提交数 ≥ 10（CI 自动检查）
- README（`README.md` / `README.zh.md`）由脚本生成，**不要手工编辑**；改 YAML 后执行：
  ```sh
  npm ci
  node scripts/generate-readme.mjs
  ```
- 一个 PR 最多收录 3 条；只改自己的条目。

## 更新步骤（改条目内容时）

1. 修改本目录的 `dingminhua__dsh-service-portal.yml` 草稿
2. 在 fork 分支（如 `add-dsh-service-portal`）上同步修改
   `data/plugins/dingminhua__dsh-service-portal.yml`
3. 重新生成 README（见上）
4. 推送，PR 自动重跑 CI