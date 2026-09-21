"""Comments/metrics APIs return data for demo users."""

from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient

from src.auth import create_access_token
from src.web_app import app

@pytest.fixture
def client():
    return TestClient(app)

def test_comments_and_metrics_for_demo(client):
    token = create_access_token({"sub": "demo"})
    comments = client.get("/api/comments", params={"token": token})
    assert comments.status_code == 200, comments.text
    body = comments.json()
    assert body["success"] is True
    assert body["total"] > 0
    assert body["filtered_count"] > 0

    metrics = client.get("/api/metrics", params={"token": token})
    assert metrics.status_code == 200, metrics.text
    mbody = metrics.json()
    assert mbody["success"] is True
    assert mbody["total"] > 0
    assert mbody["filtered_count"] > 0

def test_api_user_accepts_bearer_header(client):
    token = create_access_token({"sub": "demo"})
    response = client.get(
        "/api/user",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    assert response.json().get("username") == "demo"
