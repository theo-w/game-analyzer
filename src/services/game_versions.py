"""Per-game version / patch iteration history."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.database import db_manager

VERSION_CHANGE_TYPES = ["major", "minor", "patch", "balance", "content", "other"]


def _now() -> str:
    return datetime.now().isoformat()


class GameVersionRepository:
    @staticmethod
    def list_for_game(game_id: str, *, limit: int = 50) -> List[Dict[str, Any]]:
        rows = db_manager.execute(
            """
            SELECT version_id, game_id, version_label, released_at, change_summary,
                   change_type, source, created_at
            FROM game_version_history
            WHERE game_id = ?
            ORDER BY COALESCE(released_at, created_at) DESC
            LIMIT ?
            """,
            (game_id, limit),
        ) or []
        return [dict(row) for row in rows]

    @staticmethod
    def create(game_id: str, data: Dict[str, Any]) -> str:
        version_id = data.get("version_id") or uuid.uuid4().hex[:12]
        payload = {
            "version_id": version_id,
            "game_id": game_id,
            "version_label": (data.get("version_label") or "未命名版本").strip(),
            "released_at": data.get("released_at") or _now()[:10],
            "change_summary": data.get("change_summary") or "",
            "change_type": data.get("change_type") or "update",
            "source": data.get("source") or "manual",
            "created_at": _now(),
        }
        db_manager.insert("game_version_history", payload)
        return version_id

    @staticmethod
    def update(version_id: str, data: Dict[str, Any]) -> bool:
        allowed = {"version_label", "released_at", "change_summary", "change_type", "source"}
        updates = {k: data[k] for k in allowed if k in data}
        if not updates:
            return False
        parts = [f"{k} = ?" for k in updates]
        params = list(updates.values()) + [version_id]
        db_manager.execute(
            f"UPDATE game_version_history SET {', '.join(parts)} WHERE version_id = ?",
            tuple(params),
        )
        return True

    @staticmethod
    def delete(version_id: str) -> bool:
        db_manager.execute(
            "DELETE FROM game_version_history WHERE version_id = ?",
            (version_id,),
        )
        return True

    @staticmethod
    def get(version_id: str) -> Optional[Dict[str, Any]]:
        row = db_manager.execute_one(
            "SELECT * FROM game_version_history WHERE version_id = ?",
            (version_id,),
        )
        return dict(row) if row else None


def parse_version_import_text(text: str) -> List[Dict[str, Any]]:
    """Parse bulk version lines: 'v1.2 | 2024-01-01 | 更新摘要' per line."""
    rows: List[Dict[str, Any]] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 3:
            rows.append(
                {
                    "version_label": parts[0],
                    "released_at": parts[1],
                    "change_summary": parts[2],
                    "change_type": parts[3] if len(parts) > 3 else "update",
                    "source": "import",
                }
            )
        elif len(parts) == 2:
            rows.append(
                {
                    "version_label": parts[0],
                    "released_at": parts[1][:10] if parts[1] else "",
                    "change_summary": "",
                    "change_type": "update",
                    "source": "import",
                }
            )
        else:
            rows.append(
                {
                    "version_label": parts[0],
                    "change_summary": parts[0],
                    "change_type": "update",
                    "source": "import",
                }
            )
    return rows


def import_versions_from_mvp_signals(game_id: str, product_id: str) -> List[str]:
    """Create version stubs from MVP analysis update/balance themes in reviews."""
    from src.mvp_data import get_mvp_analysis, mvp_validation_passed

    if not mvp_validation_passed():
        return []
    analysis = get_mvp_analysis() or {}
    report = None
    for row in analysis.get("product_reports") or []:
        if str(row.get("product")) == str(product_id):
            report = row
            break
    if not report:
        return []

    created: List[str] = []
    captured = (analysis.get("generated_at") or "")[:10]
    themes = report.get("top_negative_themes") or []
    update_themes = {"updates", "update", "balance", "patch", "content"}
    hits = [t for t in themes if str(t.get("theme", "")).lower() in update_themes]
    if hits:
        for th in hits[:3]:
            vid = GameVersionRepository.create(
                game_id,
                {
                    "version_label": f"MVP信号 · {th.get('theme', 'update')}",
                    "released_at": captured,
                    "change_summary": (
                        f"评论中「{th.get('theme')}」主题提及 {th.get('count', 0)} 次（MVP 样本）。"
                        " 建议对照 Steam 更新公告补充正式版本号。"
                    ),
                    "change_type": "content",
                    "source": "mvp_signal",
                },
            )
            created.append(vid)
    elif report.get("recommendation"):
        vid = GameVersionRepository.create(
            game_id,
            {
                "version_label": "MVP信号 · 口碑复盘",
                "released_at": captured,
                "change_summary": report.get("recommendation"),
                "change_type": "other",
                "source": "mvp_signal",
            },
        )
        created.append(vid)
    return created


def import_versions_from_steam_news(
    game_id: str,
    app_id: str,
    *,
    max_items: int = 8,
) -> Dict[str, Any]:
    """Import version rows from Steam public news feed."""
    from src.services.steam_news import fetch_steam_news_items

    app_id = str(app_id or "").strip()
    if not app_id:
        return {"created": [], "skipped": 0, "fetched": 0, "error": "missing_app_id"}

    existing = {
        (row.get("version_label") or "", (row.get("released_at") or "")[:10])
        for row in GameVersionRepository.list_for_game(game_id, limit=200)
    }
    news_rows = fetch_steam_news_items(app_id, count=max_items)
    if not news_rows:
        return {"created": [], "skipped": 0, "fetched": 0, "error": "no_steam_news"}

    created: List[str] = []
    skipped = 0
    for row in news_rows:
        key = (row.get("version_label") or "", (row.get("released_at") or "")[:10])
        if key in existing:
            skipped += 1
            continue
        payload = {
            "version_label": row.get("version_label") or "Steam 更新",
            "released_at": row.get("released_at") or _now()[:10],
            "change_summary": row.get("change_summary") or "",
            "change_type": row.get("change_type") or "minor",
            "source": "steam_news",
        }
        created.append(GameVersionRepository.create(game_id, payload))
        existing.add(key)

    return {
        "created": created,
        "skipped": skipped,
        "fetched": len(news_rows),
    }
