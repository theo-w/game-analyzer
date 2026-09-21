"""数据边界护栏：看板不得重新出现依赖内部数据的分析入口。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from src.web_app import app

    return TestClient(app)


def test_verifiable_endpoints_not_blocked(client):
    # 真实数据能力不受影响(未登录返回 401 而非 410)
    for path in ("/api/ai_analysis", "/api/agent/status"):
        res = client.get(path)
        assert res.status_code != 410, path


def test_dashboard_no_longer_has_unverifiable_entries(client):
    html = client.get("/dashboard").text
    # 入口按钮已移除
    assert 'onclick="showAdvancedAnalysis()"' not in html
    assert 'onclick="showABTestPlatform()"' not in html
    # 快捷键入口已移除
    assert "Ctrl/Cmd + A: 打开高级分析" not in html
    assert "打开高级分析面板" not in html
    assert "切换高级分析标签页" not in html
