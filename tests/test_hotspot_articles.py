"""行业热点文章存档（只读）测试。

2026-09-19 AI 生成链路依预设阈值降级移除：页面转为静态存档并加溯源说明，
生成端点返回 410，原选题/润色/自定义端点已删除。
"""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio

from src.services.analysis_archive import AnalysisArchiveRepository
from src.web_app import app
from database import db_manager


@pytest_asyncio.fixture
async def api_client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


async def _demo_token(api_client: httpx.AsyncClient) -> str:
    resp = await api_client.post("/token", data={"username": "demo", "password": "demo123"})
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_hotspot_page_renders_archive_notice(api_client):
    page = await api_client.get("/hotspot")
    assert page.status_code == 200
    assert "文章存档" in page.text
    assert "内容溯源" in page.text
    assert "降级说明" in page.text


@pytest.mark.asyncio
async def test_generate_endpoint_returns_410(api_client):
    resp = await api_client.post("/api/hotspot/generate", json={"product_id": "730"})
    assert resp.status_code == 410
    assert "停用" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_generation_flow_endpoints_removed(api_client):
    token = await _demo_token(api_client)
    for method, url in (
        ("GET", "/api/hotspot/topics"),
        ("POST", "/api/hotspot/suggest"),
        ("POST", "/api/hotspot/custom"),
        ("GET", "/api/hotspot/facts"),
        ("POST", "/api/hotspot/archive"),
    ):
        resp = await api_client.request(method, url, params={"token": token})
        assert resp.status_code in (404, 405), f"{method} {url} 应已随生成链路移除"


@pytest.mark.asyncio
async def test_archive_requires_auth(api_client):
    resp = await api_client.get("/api/hotspot/archive")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_archive_listing_returns_seeded_article(api_client):
    token = await _demo_token(api_client)

    archive_id = AnalysisArchiveRepository.create(
        username="demo",
        title="存档测试 · 《CS2》口碑复盘",
        report_type="hotspot",
        category="行业热点",
        product_ids=["730"],
        body_markdown="# 存档测试\n\n正文内容",
        snapshot={
            "angle": "sentiment_crash",
            "facts": {"product_name": "CS2", "sample_size": 123, "data_basis": "demo"},
        },
    )
    other_id = AnalysisArchiveRepository.create(
        username="demo",
        title="非热点归档不应出现在热点存档",
        report_type="review",
        category="数据复盘",
        product_ids=["730"],
        body_markdown="# 数据复盘",
    )

    try:
        resp = await api_client.get("/api/hotspot/archive", params={"token": token})
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        article = next(a for a in payload["articles"] if a["archive_id"] == archive_id)
        assert article["body_markdown"].startswith("# 存档测试")
        assert article["snapshot_json"]["facts"]["sample_size"] == 123
        assert all(a["archive_id"] != other_id for a in payload["articles"])
        assert payload["total"] >= len(payload["articles"])
    finally:
        db_manager.execute(
            "DELETE FROM analysis_archives WHERE archive_id IN (?, ?)",
            (archive_id, other_id),
        )
