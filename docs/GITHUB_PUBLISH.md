# GitHub 仓库说明与发布指南

**当前 canonical 仓库：** https://github.com/alex-Tesla3/game-analyzer  
**CI：** https://github.com/alex-Tesla3/game-analyzer/actions

本目录即独立项目根；日常开发可直接在本仓库 `git push origin main`，无需再从 monorepo 导出。

---

## 日常同步到 GitHub

```bash
cd game_analyzer   # 或你的本地克隆路径
git status
git add -A
git commit -m "your message"
git push origin main
```

推送后 GitHub Actions（`.github/workflows/ci.yml`）自动跑单元测试与 Playwright E2E。

### 更新仓库元数据（Topics / Homepage）

```bash
PUBLIC_DEMO_BASE_URL=https://your-app.onrender.com ./scripts/polish_github.sh
```

或仅更新描述与 Topics：

```bash
./scripts/polish_github.sh
```

---

## 从 Hermes monorepo 导出（历史方式，可选）

若主开发仍在 `Hermes-Agent/game_analyzer/` 子目录，可导出到独立仓库：

### 方式 A：subtree split

```bash
cd /path/to/Hermes-Agent
git subtree split --prefix=game_analyzer -b game-analyzer-export
git push git@github.com:alex-Tesla3/game-analyzer.git game-analyzer-export:main
```

### 方式 B：rsync 导出

```bash
cd game_analyzer
GITHUB_USER=alex-Tesla3 ./scripts/publish_github.sh
```

### 方式 C：手动 rsync

```bash
rsync -a --exclude '.venv' --exclude '__pycache__' --exclude 'data/' \
  --exclude '.env' --exclude '.DS_Store' \
  Hermes-Agent/game_analyzer/ ~/Projects/game-analyzer/
cd ~/Projects/game-analyzer
git add -A && git commit -m "Sync from monorepo" && git push origin main
```

---

## README 建议结构（已对齐本仓库）

1. **首屏** — 一句话 + CI 徽章 + GitHub 链接 + 截图  
2. **数据流** — 抓取 → `data/mvp/` → 看板（不隔离）  
3. **Quick start** — `pip install -r requirements.txt` + `./scripts/dev.sh`  
4. **多平台** — Steam / TapTap / Google Play（`google-play-scraper`）  
5. **链接** — `docs/RESUME.md`、`docs/PROJECT_SHOWCASE.md`、`/trust`  
6. **Topics** — `fastapi` `game-analytics` `bi-dashboard` `python` `playwright` `steam`

## GitHub About 设置

| 字段 | 建议值 |
|------|--------|
| **Website** | `https://<your-deploy>/showcase` 或仓库 README |
| **Description** | Full-stack game BI & competitor intelligence — Steam/TapTap/Google Play crawl → dashboard |
| **Topics** | fastapi, python, playwright, game-analytics, dashboard, pytest, docker |

## 发布前 smoke test

```bash
./scripts/run_tests.sh -q
PLAYWRIGHT_CHANNEL=chrome ./scripts/run_browser_e2e.sh
./scripts/dev.sh
curl http://127.0.0.1:8080/api/health
```

期望：`{"status":"ok", ...}`。抓取冒烟（需网络）：

```bash
curl -X POST http://127.0.0.1:8080/api/wizard/run -H "Content-Type: application/json" \
  -d '{"app_ids": "730", "platform": "steam", "max_reviews": 3}'
```

## 部署固定 Demo

| 平台 | 说明 |
|------|------|
| **Render** | 连接本仓库 → Blueprint `render.yaml`（推荐） |
| Railway | 见 `docs/DEPLOY.md` |
| Fly.io | `./scripts/deploy_fly.sh`（需绑卡） |
| 临时分享 | `./scripts/share_demo.sh` → `/tmp/game-analyzer-tunnel.url` |

部署后设置 `PUBLIC_DEMO_BASE_URL`，`/showcase` 显示公网横幅。

## 勿提交到 GitHub

- `.env`、`.venv/`、`data/`（含 SQLite、MVP 产物）、`output.jsonl`
- 真实 API 密钥、`config/config.json` 中的生产密钥

`.workbuddy/` 工作笔记可按需纳入版本库（已支持）。

## 相关文档

| 文档 | 用途 |
|------|------|
| [README.md](../README.md) | 仓库首页 |
| [DEPLOY.md](./DEPLOY.md) | Render / Railway / Docker |
| [RESUME_PASTE.md](./RESUME_PASTE.md) | 简历终稿 |
| [PROJECT_SHOWCASE.md](./PROJECT_SHOWCASE.md) | 架构与作品集 |
| [PROJECT_HEALTH.md](./PROJECT_HEALTH.md) | 上线前自检 |
