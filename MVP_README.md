# Game Analyzer MVP

Multi-platform crawl pipeline: public reviews → normalized schema → analysis → dashboard sync.

## Platforms

| Channel | CLI / API | Notes |
|---------|-----------|-------|
| Steam | `run_mvp.py --app-ids 730,570` | No API key; public store + reviews |
| TapTap | 分析向导 `/guide`（平台选 TapTap） | TapTap `webapiv2` + `X-UA` |
| Google Play | 分析向导 `/guide`（平台选 Google Play） | `google-play-scraper` |

## CLI (Steam batch)

```bash
python3 run_mvp.py --app-ids 730,570,117247 --review-days 30
python3 run_mvp.py --app-ids 730 --no-use-review-days --use-max-reviews --max-reviews 1000
```

## Artifacts (`data/mvp/`)

- `steam_dataset.json` — comments + sample metrics (all channels write here)
- `analysis.json`
- `validation.json`

## FastAPI endpoints

```text
POST /api/wizard/run  {"app_ids": "730,570", "platform": "steam", "max_reviews": 200}
GET  /guide           分析向导页（原 /mvp 已 301 重定向至此）
```

Crawl pacing (optional env):

- `GA_CRAWL_DELAY_SECONDS` — pause between review pages (default `0.4`)
- `GA_CRAWL_MAX_WORKERS` — parallel products per channel (default `3`, max `8`)

Google Play review locale (important for global games):

- Reviews default to `en` / `us` (`GOOGLE_PLAY_REVIEW_LANG` / `GOOGLE_PLAY_REVIEW_COUNTRY`)
- Search still defaults to `zh` / `cn` (`GOOGLE_PLAY_SEARCH_LANG` / `GOOGLE_PLAY_SEARCH_COUNTRY`)
- Using `zh/cn` for reviews often returns far fewer comments for international package IDs

## Dashboard sync

Crawls write to `data/mvp/steam_dataset.json`. The dashboard reads the **same file** via `/api/metrics` — no separate import. See `/trust` or the in-dashboard data-flow guide.

Priority (`src/data_resolution.py`):

1. User CSV import (owner metrics)
2. MVP crawl artifacts (Steam / TapTap / Google Play)
3. 24h cache
4. Empty — dashboard shows crawl-first guidance (mock fallback removed)

When MVP artifacts exist, these APIs prefer real crawled data:

- `GET /api/report` — rule-based analysis
- `GET /api/ai_analysis` — grounded `ai_strategy` from MVP run
- `GET /api/comments` and `GET /api/metrics` — `source: mvp_steam` / `mvp_multi`
