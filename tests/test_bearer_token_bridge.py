"""Bearer header is bridged to ?token= for legacy API routes."""

from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient

from src.auth import create_access_token
from src.web_app import app

@pytest.fixture
def client():
    return TestClient(app)

def test_api_options_accepts_bearer_without_query_token(client):
    token = create_access_token({"sub": "admin"})
    response = client.get(
        "/api/options",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("success") is True
    assert "products" in body

def test_bearer_wins_over_stale_query_token(client):
    """Regression: stale ?token= must not override a valid Bearer header."""
    token = create_access_token({"sub": "admin"})
    response = client.get(
        "/api/metrics?token=invalid-stale-token",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
