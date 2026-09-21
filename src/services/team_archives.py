"""Team-visible shared analysis archives."""

from __future__ import annotations

from typing import Any, Dict, List

from src.services.analysis_archive import AnalysisArchiveRepository


def list_team_shared_archives(team_id: int, viewer_username: str) -> Dict[str, Any]:
    from src.team_management import TeamRepository

    members = TeamRepository.get_team_members(team_id)
    member_names = {m.get("username") for m in members if m.get("username")}
    if viewer_username not in member_names:
        return {"success": False, "message": "无权查看该团队归档", "archives": []}

    archives: List[Dict[str, Any]] = []
    for username in sorted(member_names):
        for row in AnalysisArchiveRepository.list_for_user(username, limit=30):
            token = row.get("share_token")
            if not token:
                continue
            archives.append(
                {
                    "archive_id": row.get("archive_id"),
                    "title": row.get("title"),
                    "category": row.get("category"),
                    "owner": username,
                    "share_token": token,
                    "share_url": f"/shared/{token}",
                    "updated_at": row.get("updated_at") or row.get("created_at"),
                    "tags": row.get("tags") or [],
                }
            )
    archives.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
    return {
        "success": True,
        "team_id": team_id,
        "archives": archives,
        "total": len(archives),
    }
