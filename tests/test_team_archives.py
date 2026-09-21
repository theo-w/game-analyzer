"""Tests for team shared archives."""

from __future__ import annotations

from unittest.mock import patch

from src.services.team_archives import list_team_shared_archives


@patch("src.services.team_archives.AnalysisArchiveRepository.list_for_user")
@patch("src.team_management.TeamRepository.get_team_members")
def test_list_team_shared_archives(mock_members, mock_list):
    mock_members.return_value = [
        {"username": "demo", "role": "admin"},
        {"username": "agent1", "role": "viewer"},
    ]
    mock_list.side_effect = lambda u, **kw: (
        [{"archive_id": "a1", "title": "Demo 报告", "share_token": "tok1", "category": "竞品分析", "updated_at": "2026-05-31"}]
        if u == "demo"
        else []
    )
    out = list_team_shared_archives(1, "demo")
    assert out["success"] is True
    assert out["total"] == 1
    assert out["archives"][0]["owner"] == "demo"


@patch("src.team_management.TeamRepository.get_team_members")
def test_list_team_shared_archives_forbidden(mock_members):
    mock_members.return_value = [{"username": "other", "role": "admin"}]
    out = list_team_shared_archives(1, "demo")
    assert out["success"] is False
