# 发布流程（Release Flow）

> 本文档是 `dsh-service-portal` 的**唯一权威发布流程**。发布前请通读一遍。

## 前置条件

- npm 已登录：`npm whoami` 应显示 `dmh2002`（若报 `need auth`，先 `npm login`）。
- 账号若开启 2FA：`npm publish` 时需**在浏览器确认一步**。
- GitHub 仓库：`https://github.com/dingminhua/dsh-service-portal`（默认分支 `main`）。
- `gh` 已登录且带 `repo` 权限：`gh auth status` 应显示 `Logged in to github.com account
  dingminhua`、scope 含 `repo`（第 7 步要用）。

## 每次发布的完整步骤

### 1. 确认代码、测试与版权

```bash
cd D:/DshProject/dsh-service-portal
$node = "$env:LOCALAPPDATA\Programs\DeepSeek Harness\resources\runtime\primary-runtime\dependencies\node\bin\node.exe"
& $node client/build.mjs            # 重建客户端产物
& $node --test test/host.test.mjs   # 18 项宿主端控制检验
& $node --test test/client.test.mjs # 14 项客户端契约检验
grep -F "Copyright (c) 2026 LaoDing" LICENSE
```

> 本项目以 MIT 许可证发布，版权归属必须保持为 **LaoDing**；发布前不得把 LICENSE 中的版权主体
> 改成 npm 账号、GitHub 账号或其他名称。

### 2. 运行基础设施控制检验（**不得跳过**）

```powershell
python -X utf8 tools\check_tunnel_auth.py
python -X utf8 tools\check_tunnel_domain.py
python -X utf8 tools\check_host_metrics.py
python -X utf8 tools\check_plugin.py
```

> 依赖缺失时这些脚本应「跳过并返回 2」，不得静默通过——这是本项目的硬纪律，发布前必须亲眼看到
> 返回 0 或 2（跳过）且无 FAIL。

### 3. 核对溯源与致谢（**不得跳过**）

```bash
grep -F "THIRD_PARTY_NOTICES.md" package.json   # 应在 files 白名单内
grep -F "ld-rl-poker" THIRD_PARTY_NOTICES.md    # 开源声明里的来源仍在
grep -F "dsh-connect-workbuddy" THIRD_PARTY_NOTICES.md
```

核对清单：

- [ ] `THIRD_PARTY_NOTICES.md` 在 `package.json` 的 `files` 白名单中，随包分发
- [ ] README 与 README.en.md 的致谢章节列出全部参考项目及许可证
- [ ] 若引入了新的外部依赖或复用了他人代码，`THIRD_PARTY_NOTICES.md` 已同步更新

### 4. 更新版本号

手动改 `package.json` 的 `version` 字段。后续步骤以目标版本号 `X.Y.Z` 指代。

### 5. 更新 CHANGELOG.md

在 `CHANGELOG.md` 顶部新增一节 `## X.Y.Z (YYYY-MM-DD)`，按 `Features` / `Fixes` / `Docs`
分组记录本次变更。

### 6. 提交并打 git tag

```bash
cd D:/DshProject/dsh-service-portal
git add package.json CHANGELOG.md README.md README.en.md THIRD_PARTY_NOTICES.md LICENSE
git commit -m "chore: 版本升级至 X.Y.Z"
git tag -a vX.Y.Z -m "vX.Y.Z: <一句话说明>"
git push origin main
git push origin vX.Y.Z
```

> ⚠️ **tag 必须指向包含本次代码的提交**。若目标 tag 已存在且指向旧提交，需先删除并强制移动，
> 修正后用 `git rev-list -n1 vX.Y.Z` 确认指向当前 HEAD。
> **打完 tag 别忘了第 7 步。**

### 7. 发布到 npm

```bash
cd D:/DshProject/dsh-service-portal
npm publish        # dsh-service-portal
```

> ⚠️ **发布前必须 `npm run build` 重建客户端产物**，并确认 `lib/client.js` 存在且
> `exports["./client"]` 指向它——2026-10-15 曾因产物缺失导致 DSH 启动期
> `ERR_PACKAGE_PATH_NOT_EXPORTED` 致命错误。
>
> npm 只发布 `package.json` 的 `files` 白名单内容（`lib`、`icons`、`cordis.patch.yml`、README、
> CHANGELOG、声明、LICENSE）。`npm pack --dry-run` 可预览将发布的文件清单。

### 8. 创建 GitHub Release

```bash
cd D:/DshProject/dsh-service-portal
gh release create vX.Y.Z --title "vX.Y.Z — <一句话说明>" --notes "见 CHANGELOG.md" --verify-tag
```

> npm 与 GitHub 是两条独立通道：**`npm publish` 成功不会自动创建 Release**，CI 也不会。第 7、8 步
> 都要做，漏做 GitHub Release 只影响展示，但补做即可（与当时创建等效）。

### 9. 提交市场收录（如未收录）

见 [awesome-dsh-plugin-submission/README.md](awesome-dsh-plugin-submission/README.md)。
一个 PR 最多收录 3 条；只改自己的条目。

## 发布后核对

```bash
npm view dsh-service-portal version            # 应等于 X.Y.Z
gh release view vX.Y.Z                          # 应存在且指向 tag
npm pack --dry-run | grep -c "^dsh"             # 文件清单里应有 lib/ 与 README
```

## 常见问题

- **`npm publish` 输出里没有 `+ dsh-service-portal@X.Y.Z`**：版本号没变或登录态失效。先
  `npm publish --dry-run` 预览，再 `npm whoami` 确认登录。
- **`npm whoami` 报 E401**：`~/.npmrc` 里的 `_authToken` 已失效（注意它偶尔会回显缓存的旧结果）。
  先 `npm login --auth-type=web` 重新登录再发布。
- **本地开发与发布的关系**：本地开发用 `link:` 安装，与 npm 发布互不影响；npm 发布的是 `lib/`、
  README 等静态文件，同一份源码。
- **GitHub 上没有本次 Release / `gh release list` 看不到新版本**：第 7 步漏了。补做即可——版本、
  tag、正文都还在仓库里，事后补建与当时创建完全等效。
- **`gh release create` 报 `tag not found`**：tag 还没推。先完成第 6 步的 `git push origin vX.Y.Z`。
  不要为了通过而去掉 `--verify-tag`。
- **LICENSE 版权被改动**：发布前 `grep -F "Copyright (c) 2026 LaoDing" LICENSE` 必须命中；
  若被改成其他名称，先还原再发布。