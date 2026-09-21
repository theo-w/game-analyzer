"""End-to-end API smoke: scores → AI report → archive."""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio

from src.services.analysis_archive import AnalysisArchiveRepository
from src.services.competitor_scores import CompetitorScoreRepository
from src.services.game_intel import GameLibraryRepository, seed_default_library
from src.services.scenario_ai import generate_competitor_scenario_report
from src.web_app import app


@pytest_asyncio.fixture
async def api_client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.fixture(autouse=True)
def _seed():
    seed_default_library()


@pytest.mark.asyncio
async def test_competitor_report_includes_dimension_scores(monkeypatch):
    monkeypatch.setattr("src.services.scenario_ai.llm_is_configured", lambda: False)
    games = GameLibraryRepository.list_games()
    ids = [g["game_id"] for g in games[:2]]
    CompetitorScoreRepository.upsert("demo", ids[0], {"gameplay": 5, "ux": 4, "retention": 3})
    report = await generate_competitor_scenario_report(ids, username="demo")
    assert report["success"] is True
    assert report.get("dimension_scores")
    assert any(s.get("title") == "六维评分对比" for s in report.get("sections") or [])
    assert report["facts"].get("score_summary")


@pytest.mark.asyncio
async def test_full_pipeline_scores_report_archive(api_client, monkeypatch):
    monkeypatch.setattr("src.services.scenario_ai.llm_is_configured", lambda: False)
    token = (
        await api_client.post("/token", data={"username": "demo", "password": "demo123"})
    ).json()["access_token"]
    games = GameLibraryRepository.list_games()
    ids = [g["game_id"] for g in games[:2]]
    gid = ids[0]

    save = await api_client.put(
        "/api/games/compare/scores",
        params={"token": token},
        json={"game_id": gid, "scores": {"gameplay": 4, "monetization": 3, "ux": 5}},
    )
    assert save.status_code == 200

    report_res = await api_client.post(
        "/api/scenarios/competitor/report",
        params={"token": token},
        json={"ids": ids},
    )
    report = report_res.json()
    assert report["success"] is True
    rows = {r["game_id"]: r for r in report.get("dimension_scores") or []}
    assert rows[gid]["scores"]["gameplay"] == 4
    assert rows[gid]["is_custom"] is True

    arch = await api_client.post(
        "/api/scenarios/archive",
        params={"token": token},
        json={"report": report},
    )
    assert arch.status_code == 200
    archive_id = arch.json()["archive_id"]
    row = AnalysisArchiveRepository.get(archive_id, "demo")
    assert row
    snap = row.get("snapshot_json") or {}
    assert snap.get("dimension_scores")
    assert "六维评分" in (row.get("body_markdown") or "")


@pytest.mark.asyncio
async def test_version_import_paste(api_client):
    token = (
        await api_client.post("/token", data={"username": "demo", "password": "demo123"})
    ).json()["access_token"]
    gid = GameLibraryRepository.list_games()[0]["game_id"]
    res = await api_client.post(
        f"/api/games/library/{gid}/versions/import",
        params={"token": token},
        json={"mode": "paste", "text": "v1.0 | 2024-01-01 | 首发版本"},
    )
    assert res.status_code == 200
    assert res.json()["created"] == 1


def test_parse_version_import_text():
    from src.services.game_versions import parse_version_import_text

    rows = parse_version_import_text("v2.0 | 2024-06-01 | 大更新")
    assert rows[0]["version_label"] == "v2.0"
    assert rows[0]["change_summary"] == "大更新"
