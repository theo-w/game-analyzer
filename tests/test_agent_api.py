"""Agent API 测试(离线)。"""

from __future__ import annotations

import json
import os
import shutil
import uuid

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from src.web_app import app

    return TestClient(app)


def _register_and_token(client: TestClient) -> tuple[str, str]:
    username = f"agent_{uuid.uuid4().hex[:8]}"
    password = "agent-test-pass"
    client.post(
        "/register",
        data={"username": username, "email": f"{username}@example.com", "password": password},
        headers={"X-Device-Id": f"device-{username}"},
    )
    res = client.post(
        "/token",
        data={"username": username, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert res.status_code == 200, res.text
    return username, res.json()["access_token"]


def test_agent_status(client, monkeypatch):
    monkeypatch.delenv("SUPABASE_DATABASE_URL", raising=False)
    _, token = _register_and_token(client)
    res = client.get("/api/agent/status", params={"token": token})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["success"] is True
    assert body["supabase_enabled"] is False
    assert "clean" in body["steps"]


def test_agent_process_offline(client, tmp_path, monkeypatch):
    monkeypatch.delenv("SUPABASE_DATABASE_URL", raising=False)
    _, token = _register_and_token(client)

    data = {
        "source": "test",
        "games": [{"app_id": "10", "name": "Counter-Strike"}],
        "comments": [
            {"product": "10", "platform": "Steam", "内容": "Great team game."},
            {"product": "10", "platform": "Steam", "内容": "Great team game."},
            {"product": "10", "platform": "Steam", "内容": "画面很好,手感不错,强烈推荐"},
        ],
        "metrics": [],
    }
    path = tmp_path / "steam_dataset.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    res = client.post(
        "/api/agent/process",
        params={"token": token},
        json={"dataset_path": str(path), "steps": ["clean", "label", "aggregate"], "use_llm": False},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["success"] is True
    assert body["aggregate"]["clean_reviews"] == 1


def test_migrate_endpoint_auth(client, monkeypatch):
    monkeypatch.delenv("SUPABASE_DATABASE_URL", raising=False)
    # 无凭据 -> 401
    res = client.post("/api/agent/migrate", json={})
    assert res.status_code == 401

    # 错误 secret -> 401
    monkeypatch.setenv("MIGRATE_SECRET", "correct-horse")
    res = client.post("/api/agent/migrate", json={}, headers={"X-Migrate-Secret": "wrong"})
    assert res.status_code == 401

    # 正确 secret -> 进入迁移逻辑(未配置 Supabase -> success False, 不报 500)
    res = client.post("/api/agent/migrate", json={}, headers={"X-Migrate-Secret": "correct-horse"})
    assert res.status_code == 200
    assert res.json()["success"] is False
    assert "SUPABASE_DATABASE_URL" in res.json()["error"]


def test_migrate_endpoint_requires_admin(client, monkeypatch):
    monkeypatch.delenv("SUPABASE_DATABASE_URL", raising=False)
    _, token = _register_and_token(client)
    res = client.post("/api/agent/migrate", params={"token": token}, json={})
    assert res.status_code == 403


def test_agent_themes_empty_without_data(client, monkeypatch):
    monkeypatch.delenv("SUPABASE_DATABASE_URL", raising=False)
    _, token = _register_and_token(client)
    res = client.get("/api/agent/themes", params={"token": token})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["success"] is True
    assert body["themes"] == []


def test_agent_themes_from_dataset(client, monkeypatch):
    monkeypatch.delenv("SUPABASE_DATABASE_URL", raising=False)
    username, token = _register_and_token(client)
    # 数据集写到该用户的用户级路径(resolve_dataset 优先读取)，不依赖本地总库文件；
    # data/ 已被 gitignore，finally 自清理，CI 与本地行为一致。
    user_dir = os.path.join("data", "mvp", "users", username)
    os.makedirs(user_dir, exist_ok=True)
    path = os.path.join(user_dir, "steam_dataset.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "themes": [
                    {"cluster_id": "clu_1", "theme_name": "反作弊", "description": "外挂多",
                     "key_issues": ["外挂"], "member_count": 3, "avg_similarity": 0.9}
                ]
            },
            handle,
            ensure_ascii=False,
        )
    try:
        res = client.get("/api/agent/themes", params={"token": token})
        assert res.status_code == 200, res.text
        themes = res.json()["themes"]
        assert len(themes) >= 1
        assert themes[0]["theme_name"] == "反作弊"
    finally:
        shutil.rmtree(user_dir, ignore_errors=True)
