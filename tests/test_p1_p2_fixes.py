"""Tests for P1/P2 reliability fixes."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta

import httpx
import pytest
import pytest_asyncio

from src.web_app import app


async def _token(client, username="demo", password="demo123"):
    response = await client.post(
        "/token",
        data={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest_asyncio.fixture
async def api_client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.asyncio
async def test_health_endpoint(api_client):
    response = await api_client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"


@pytest.mark.asyncio
async def test_share_report_create_and_fetch_with_expiry(api_client):
    token = await _token(api_client, "admin", "admin123")
    report_data = {"title": "测试报告", "value": 42}

    create = await api_client.post(
        "/api/report/share",
        params={"token": token},
        json={"report_type": "daily", "report_data": report_data, "expires_hours": 24},
    )
    assert create.status_code == 200, create.text
    body = create.json()
    assert body["success"] is True
    assert body["share_token"]
    assert "shared/" in body["share_url"]

    fetch = await api_client.get(f"/api/report/shared/{body['share_token']}")
    assert fetch.status_code == 200
    assert fetch.json()["success"] is True
    assert fetch.json()["report"]["report_data"]["value"] == 42


@pytest.mark.asyncio
async def test_share_report_expired_returns_not_found(api_client):
    from src.database import db_manager

    expired_token = uuid.uuid4().hex
    db_manager.insert(
        "shared_reports",
        {
            "share_token": expired_token,
            "username": "admin",
            "report_type": "daily",
            "report_data": json.dumps({"x": 1}),
            "expires_at": (datetime.now() - timedelta(hours=1)).isoformat(),
            "created_at": datetime.now().isoformat(),
        },
    )

    fetch = await api_client.get(f"/api/report/shared/{expired_token}")
    assert fetch.json()["success"] is False


@pytest.mark.asyncio
async def test_conversation_history_isolated_by_user(api_client):
    token_demo = await _token(api_client, "demo", "demo123")
    token_admin = await _token(api_client, "admin", "admin123")

    await api_client.post(
        "/api/conversation",
        params={"token": token_demo},
        json={"message": "demo only", "conversation_id": "iso-test"},
    )
    demo_hist = await api_client.get(
        "/api/conversation/history",
        params={"token": token_demo, "conversation_id": "iso-test"},
    )
    admin_hist = await api_client.get(
        "/api/conversation/history",
        params={"token": token_admin, "conversation_id": "iso-test"},
    )
    assert demo_hist.json()["history"]
    assert admin_hist.json()["history"] == []


@pytest.mark.asyncio
async def test_end_chat_requires_owner(api_client):
    from src.support import LiveChat

    chat = LiveChat.start_chat("demo")
    chat_id = chat["chat_id"]
    admin_token = await _token(api_client, "admin", "admin123")

    forbidden = await api_client.get(
        f"/api/support/chat/end/{chat_id}",
        params={"token": admin_token},
    )
    assert forbidden.status_code == 403

    demo_token = await _token(api_client, "demo", "demo123")
    allowed = await api_client.get(
        f"/api/support/chat/end/{chat_id}",
        params={"token": demo_token},
    )
    assert allowed.status_code == 200
    assert allowed.json()["success"] is True


@pytest.mark.asyncio
async def test_llm_providers_requires_auth(api_client):
    response = await api_client.get("/api/llm/providers")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_llm_providers_list_with_auth(api_client):
    token = await _token(api_client, "admin", "admin123")
    response = await api_client.get("/api/llm/providers", params={"token": token})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    ids = {p["id"] for p in body["providers"]}
    assert "openai" in ids
    assert "ollama" in ids


@pytest.mark.asyncio
async def test_import_template_requires_auth(api_client):
    response = await api_client.get("/api/import/template", params={"dataset_type": "metrics"})
    assert response.status_code == 401
