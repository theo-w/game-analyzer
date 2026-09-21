"""Editable multi-dimension scores (1–5) for competitor compare."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from src.database import db_manager

COMPETITOR_DIMENSIONS: List[Dict[str, str]] = [
    {"key": "gameplay", "title": "核心玩法"},
    {"key": "monetization", "title": "商业化"},
    {"key": "social", "title": "社交竞技"},
    {"key": "content", "title": "内容量"},
    {"key": "ux", "title": "体验品质"},
    {"key": "retention", "title": "留存设计"},
]

DIMENSION_KEYS = [d["key"] for d in COMPETITOR_DIMENSIONS]


def _now() -> str:
    return datetime.now().isoformat()


def _clamp_score(value: Any) -> Optional[int]:
    try:
        n = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return max(1, min(5, n))


def normalize_scores(raw: Dict[str, Any]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for key in DIMENSION_KEYS:
        if key in raw and raw[key] is not None and raw[key] != "":
            score = _clamp_score(raw[key])
            if score is not None:
                out[key] = score
    return out


def suggest_scores_from_item(item: Dict[str, Any]) -> Dict[str, int]:
    """Heuristic 1–5 scores from MVP compare row when user has not scored yet."""
    try:
        rate = float(item.get("positive_rate") or 0)
    except (TypeError, ValueError):
        rate = 0.0
    base = max(1, min(5, round(rate / 20))) if rate else 3
    risk = (item.get("risk_level") or "").lower()
    if risk in ("high", "critical"):
        base = max(1, base - 1)
    elif risk == "low":
        base = min(5, base + 1)

    scores = {key: base for key in DIMENSION_KEYS}
    themes = item.get("themes") or []
    theme_names = {str(t.get("theme", "")).lower() for t in themes}
    if "monetization" in theme_names or "pay" in theme_names:
        scores["monetization"] = max(1, base - 1)
    if "performance" in theme_names:
        scores["ux"] = max(1, base - 1)
    if "content" in theme_names:
        scores["content"] = max(1, base - 1)
    if "matchmaking" in theme_names or "social" in theme_names:
        scores["social"] = max(1, base - 1)
    return scores


class CompetitorScoreRepository:
    @staticmethod
    def get(username: str, game_id: str) -> Dict[str, int]:
        row = db_manager.execute_one(
            "SELECT scores_json FROM competitor_dimension_scores WHERE username = ? AND game_id = ?",
            (username, game_id),
        )
        if not row:
            return {}
        raw = row.get("scores_json") or "{}"
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            return {}
        return normalize_scores(parsed if isinstance(parsed, dict) else {})

    @staticmethod
    def upsert(username: str, game_id: str, scores: Dict[str, Any]) -> Dict[str, int]:
        clean = normalize_scores(scores)
        payload = {
            "username": username,
            "game_id": game_id,
            "scores_json": json.dumps(clean, ensure_ascii=False),
            "updated_at": _now(),
        }
        existing = db_manager.execute_one(
            "SELECT username FROM competitor_dimension_scores WHERE username = ? AND game_id = ?",
            (username, game_id),
        )
        if existing:
            db_manager.execute(
                """
                UPDATE competitor_dimension_scores
                SET scores_json = ?, updated_at = ?
                WHERE username = ? AND game_id = ?
                """,
                (payload["scores_json"], payload["updated_at"], username, game_id),
            )
        else:
            db_manager.insert("competitor_dimension_scores", payload)
        return clean

    @staticmethod
    def get_batch(
        username: str,
        game_ids: Sequence[str],
        *,
        compare_items: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        item_map = {str(i.get("game_id") or ""): i for i in (compare_items or [])}
        rows: List[Dict[str, Any]] = []
        for gid in game_ids:
            saved = CompetitorScoreRepository.get(username, gid)
            suggested = suggest_scores_from_item(item_map.get(gid, {}))
            merged = {**suggested, **saved}
            rows.append(
                {
                    "game_id": gid,
                    "name": (item_map.get(gid) or {}).get("name") or gid,
                    "scores": merged,
                    "saved": saved,
                    "suggested": suggested,
                    "is_custom": bool(saved),
                }
            )
        return {
            "success": True,
            "dimensions": COMPETITOR_DIMENSIONS,
            "rows": rows,
        }


def build_score_summary(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Rank games by average dimension score."""
    ranked = []
    for row in rows:
        scores = row.get("scores") or {}
        vals = [scores[k] for k in DIMENSION_KEYS if k in scores]
        avg = round(sum(vals) / len(vals), 2) if vals else 0
        ranked.append(
            {
                "game_id": row.get("game_id"),
                "name": row.get("name"),
                "average": avg,
                "scores": scores,
            }
        )
    ranked.sort(key=lambda x: x["average"], reverse=True)
    return ranked
