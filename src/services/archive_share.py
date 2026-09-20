"""Create public share links from analysis archives."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from src.database import SharedReportRepository
from src.services.analysis_archive import AnalysisArchiveRepository


def build_report_data_from_archive(archive: Dict[str, Any]) -> Dict[str, Any]:
    """Rebuild a scenario-report-compatible payload for shared viewing."""
    snap = archive.get("snapshot_json") or {}
    platform = snap.get("platform") or "steam"
    data_source = snap.get("data_source")
    if not data_source:
        data_source = (
            "taptap_public"
            if platform == "taptap"
            else "google_play_public"
            if platform == "google_play"
            else "mvp_steam"
        )

    return {
        "success": True,
        "title": archive.get("title") or "分析报告",
        "executive_summary": snap.get("executive_summary") or "",
        "markdown": archive.get("body_markdown") or "",
        "html": archive.get("html_excerpt") or "",
        "sections": snap.get("sections") or [],
        "action_items": snap.get("action_items") or [],
        "dimension_scores": snap.get("dimension_scores") or [],
        "facts": {
            "dimension_scores": snap.get("dimension_scores") or [],
            "score_dimensions": snap.get("score_dimensions") or [],
            "data_source": data_source,
        },
        "score_dimensions": snap.get("score_dimensions") or [],
        "using_llm": snap.get("using_llm"),
        "generated_at": snap.get("generated_at") or archive.get("created_at"),
        "platform": platform,
        "data_source": data_source,
        "scenario": snap.get("scenario") or archive.get("report_type", "").replace("ai_", ""),
        "archive_id": archive.get("archive_id"),
    }


def create_archive_share_link(
    username: str,
    archive_id: str,
    *,
    expires_hours: int = 168,
    base_url: str = "",
) -> Dict[str, Any]:
    archive = AnalysisArchiveRepository.get(archive_id, username)
    if not archive:
        return {"success": False, "message": "归档不存在"}

    existing = archive.get("share_token")
    if existing:
        share_url = f"{base_url.rstrip('/')}/shared/{existing}" if base_url else f"/shared/{existing}"
        return {
            "success": True,
            "share_token": existing,
            "share_url": share_url,
            "reused": True,
        }

    report_data = build_report_data_from_archive(archive)
    expires_at = (
        (datetime.now() + timedelta(hours=expires_hours)).isoformat()
        if expires_hours > 0
        else None
    )
    report_type = archive.get("report_type") or "archive"
    share_token = SharedReportRepository.create_share(
        username,
        report_type,
        report_data,
        expires_at,
    )
    if not share_token:
        return {"success": False, "message": "分享链接创建失败"}

    db_manager_update_share_token(archive_id, username, share_token)
    share_url = f"{base_url.rstrip('/')}/shared/{share_token}" if base_url else f"/shared/{share_token}"
    return {
        "success": True,
        "share_token": share_token,
        "share_url": share_url,
        "reused": False,
    }


def db_manager_update_share_token(archive_id: str, username: str, share_token: str) -> None:
    from src.database import db_manager

    db_manager.execute(
        "UPDATE analysis_archives SET share_token = ?, updated_at = ? WHERE archive_id = ? AND username = ?",
        (share_token, datetime.now().isoformat(), archive_id, username),
    )
