"""Persist analysis case archives (report + snapshot metadata)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from database import db_manager

ARCHIVE_CATEGORIES = [
    "竞品分析",
    "玩法拆解",
    "数据复盘",
    "行业热点",
    "综合报告",
    "其他",
]

SCENARIO_CATEGORY_MAP = {
    "competitor": "竞品分析",
    "breakdown": "玩法拆解",
    "review": "数据复盘",
    "hotspot": "行业热点",
    "daily": "数据复盘",
    "weekly": "数据复盘",
    "monthly": "数据复盘",
}


def _now() -> str:
    return datetime.now().isoformat()


def _parse_json_field(value: Any, default: Any) -> Any:
    if value is None or value == "":
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _row_to_archive(row: Dict[str, Any]) -> Dict[str, Any]:
    item = dict(row)
    item["product_ids"] = _parse_json_field(item.get("product_ids"), [])
    item["game_ids"] = _parse_json_field(item.get("game_ids"), [])
    item["snapshot_json"] = _parse_json_field(item.get("snapshot_json"), {})
    item["tags"] = _parse_json_field(item.get("tags"), [])
    item.setdefault("category", "")
    item.setdefault("body_markdown", item.get("html_excerpt") or "")
    item.setdefault("parent_archive_id", "")
    return item


class AnalysisArchiveRepository:
    @staticmethod
    def create(
        *,
        username: str,
        title: str,
        report_type: str,
        product_ids: List[str],
        game_ids: Optional[List[str]] = None,
        snapshot: Optional[Dict[str, Any]] = None,
        share_token: Optional[str] = None,
        html_excerpt: str = "",
        body_markdown: str = "",
        category: str = "",
        tags: Optional[List[str]] = None,
        parent_archive_id: str = "",
    ) -> str:
        archive_id = uuid.uuid4().hex[:16]
        now = _now()
        cat = category or SCENARIO_CATEGORY_MAP.get(report_type.replace("ai_", ""), "其他")
        md = body_markdown or html_excerpt or ""
        payload = {
            "archive_id": archive_id,
            "username": username,
            "title": title,
            "report_type": report_type,
            "category": cat,
            "product_ids": json.dumps(product_ids or [], ensure_ascii=False),
            "game_ids": json.dumps(game_ids or [], ensure_ascii=False),
            "snapshot_json": json.dumps(snapshot or {}, ensure_ascii=False),
            "share_token": share_token,
            "html_excerpt": (html_excerpt or md)[:4000],
            "body_markdown": md,
            "tags": json.dumps(tags or [], ensure_ascii=False),
            "parent_archive_id": parent_archive_id or "",
            "created_at": now,
            "updated_at": now,
        }
        db_manager.insert("analysis_archives", payload)
        return archive_id

    @staticmethod
    def update(archive_id: str, username: str, data: Dict[str, Any]) -> bool:
        allowed = {"title", "category", "body_markdown", "html_excerpt", "report_type"}
        updates: Dict[str, Any] = {}
        for key in allowed:
            if key in data:
                updates[key] = data[key]
        if "tags" in data:
            updates["tags"] = json.dumps(data["tags"] or [], ensure_ascii=False)
        if not updates:
            return False
        if "body_markdown" in updates and "html_excerpt" not in updates:
            updates["html_excerpt"] = (updates["body_markdown"] or "")[:4000]
        updates["updated_at"] = _now()
        parts = [f"{k} = ?" for k in updates]
        params = list(updates.values()) + [archive_id, username]
        db_manager.execute(
            f"UPDATE analysis_archives SET {', '.join(parts)} WHERE archive_id = ? AND username = ?",
            tuple(params),
        )
        return True

    @staticmethod
    def list_for_user(
        username: str,
        *,
        limit: int = 50,
        category: Optional[str] = None,
        tag: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        query = """
            SELECT archive_id, title, report_type, category, product_ids, game_ids,
                   share_token, tags, created_at, updated_at, parent_archive_id
            FROM analysis_archives
            WHERE username = ?
        """
        params: List[Any] = [username]
        if category:
            query += " AND category = ?"
            params.append(category)
        if search:
            query += " AND (title LIKE ? OR body_markdown LIKE ? OR html_excerpt LIKE ?)"
            like = f"%{search}%"
            params.extend([like, like, like])
        query += " ORDER BY COALESCE(updated_at, created_at) DESC LIMIT ?"
        params.append(limit)
        rows = db_manager.execute(query, tuple(params)) or []
        out: List[Dict[str, Any]] = []
        for row in rows:
            item = _row_to_archive(dict(row))
            if tag and tag not in (item.get("tags") or []):
                continue
            out.append(item)
        return out

    @staticmethod
    def list_hotspot_articles(username: str, *, limit: int = 50) -> List[Dict[str, Any]]:
        """热点文章存档（含正文），供 /hotspot 静态存档页渲染。

        2026-09-19 AI 生成链路降级移除后，热点文章只读不再新增。
        """
        rows = db_manager.execute(
            """
            SELECT archive_id, title, category, product_ids, snapshot_json,
                   body_markdown, html_excerpt, created_at, updated_at
            FROM analysis_archives
            WHERE username = ? AND report_type = 'hotspot'
            ORDER BY COALESCE(updated_at, created_at) DESC
            LIMIT ?
            """,
            (username, limit),
        ) or []
        return [_row_to_archive(dict(row)) for row in rows]

    @staticmethod
    def count_hotspot_articles(username: str) -> int:
        row = db_manager.execute_one(
            "SELECT COUNT(*) AS n FROM analysis_archives WHERE username = ? AND report_type = 'hotspot'",
            (username,),
        )
        return int(row["n"]) if row else 0

    @staticmethod
    def get(archive_id: str, username: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if username:
            row = db_manager.execute_one(
                "SELECT * FROM analysis_archives WHERE archive_id = ? AND username = ?",
                (archive_id, username),
            )
        else:
            row = db_manager.execute_one(
                "SELECT * FROM analysis_archives WHERE archive_id = ?",
                (archive_id,),
            )
        if not row:
            return None
        return _row_to_archive(dict(row))

    @staticmethod
    def merge_snapshot(archive_id: str, username: str, patch: Dict[str, Any]) -> bool:
        row = AnalysisArchiveRepository.get(archive_id, username)
        if not row:
            return False
        snap = dict(row.get("snapshot_json") or {})
        snap.update(patch or {})
        db_manager.execute(
            "UPDATE analysis_archives SET snapshot_json = ?, updated_at = ? WHERE archive_id = ? AND username = ?",
            (json.dumps(snap, ensure_ascii=False), _now(), archive_id, username),
        )
        return True

    @staticmethod
    def set_parent_archive(archive_id: str, parent_id: str, username: str) -> bool:
        db_manager.execute(
            "UPDATE analysis_archives SET parent_archive_id = ?, updated_at = ? WHERE archive_id = ? AND username = ?",
            (parent_id, _now(), archive_id, username),
        )
        return True

    @staticmethod
    def update_action_items(archive_id: str, username: str, action_items: List[Dict[str, Any]]) -> bool:
        return AnalysisArchiveRepository.merge_snapshot(
            archive_id,
            username,
            {"action_items": action_items},
        )


def archive_report_run(
    *,
    username: str,
    report_type: str,
    product_ids: List[str],
    metrics: List[Dict[str, Any]],
    comments: List[Dict[str, Any]],
    share_token: Optional[str] = None,
    html_excerpt: str = "",
    body_markdown: str = "",
) -> str:
    from src.services.competitor_workbench import library_game_id
    from src.data_resolution import resolve_user_data_source

    platform = "steam"
    for row in metrics:
        plat = str(row.get("platform") or row.get("平台") or "").lower()
        if plat == "taptap":
            platform = "taptap"
            break
        if plat == "google play":
            platform = "google_play"
            break

    names = []
    for pid in product_ids:
        for row in metrics:
            if str(row.get("product")) == str(pid):
                names.append(row.get("product_name") or pid)
                break
        else:
            names.append(str(pid))
    title = f"{report_type} · " + "、".join(names[:3])
    if len(names) > 3:
        title += f" 等{len(names)}款"

    game_ids = [
        library_game_id(str(pid), platform=platform)
        for pid in product_ids
        if str(pid).isdigit()
    ]
    snapshot = {
        "source": resolve_user_data_source(username),
        "platform": platform,
        "product_ids": product_ids,
        "metrics_count": len(metrics),
        "comments_count": len(comments),
        "generated_at": datetime.now().isoformat(),
    }
    return AnalysisArchiveRepository.create(
        username=username,
        title=title,
        report_type=report_type,
        product_ids=product_ids,
        game_ids=game_ids,
        snapshot=snapshot,
        share_token=share_token,
        html_excerpt=html_excerpt,
        body_markdown=body_markdown or html_excerpt,
        category=SCENARIO_CATEGORY_MAP.get(report_type, "综合报告"),
    )
