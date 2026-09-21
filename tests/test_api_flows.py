from collections import Counter
import hashlib
import hmac
import json
import uuid

import httpx
import pytest
import pytest_asyncio

from src.web_app import app


def _register_headers() -> dict:
    uid = uuid.uuid4().hex
    return {
        "X-Device-Id": f"dev_flow_{uid[:16]}",
        # RFC 5737-style TEST-NET; four octets from uuid to avoid IP limit collisions in suite runs.
        "X-Forwarded-For": (
            f"198.51.{int(uid[0:2], 16) % 254 + 1}.{int(uid[2:4], 16) % 254 + 1}"
        ),
    }


async def _post_form(client, path, data):
    response = await client.post(path, data=data)
    assert response.status_code == 200, response.text
    return response.json()


@pytest_asyncio.fixture
async def api_client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.asyncio
async def test_agent_can_access_support_console_api(api_client):
    token_data = await _post_form(
        api_client,
        "/token",
        {"username": "agent1", "password": "agent123"},
    )
    token = token_data["access_token"]

    me_response = await api_client.get("/api/agent/me", params={"token": token})
    assert me_response.status_code == 200, me_response.text
    me_payload = me_response.json()
    assert me_payload["success"] is True
    assert me_payload["data"]["role"] == "agent"

    dashboard_response = await api_client.get("/api/agent/dashboard", params={"token": token})
    assert dashboard_response.status_code == 200, dashboard_response.text
    assert dashboard_response.json()["success"] is True

    page_response = await api_client.get("/agent/console")
    assert page_response.status_code == 200
    assert "人工客服控制台" in page_response.text


@pytest.mark.asyncio
async def test_speech_transcribe_without_openai_key_returns_hint(api_client):
    token_data = await _post_form(
        api_client,
        "/token",
        {"username": "demo", "password": "demo123"},
    )
    token = token_data["access_token"]

    response = await api_client.post(
        "/api/speech/transcribe",
        params={"token": token},
        files={"file": ("speech.webm", b"fake-audio", "audio/webm")},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["success"] is False
    assert payload.get("message")


@pytest.mark.asyncio
async def test_agent_claim_and_release_ai_accept_json_body(api_client):
    """Single-field Body endpoints must accept {\"chat_id\": ...} from the console."""
    demo_token = (await _post_form(api_client, "/token", {"username": "demo", "password": "demo123"}))[
        "access_token"
    ]
    start = await api_client.get("/api/support/chat/start", params={"token": demo_token})
    assert start.status_code == 200, start.text
    chat_id = start.json()["chat_id"]

    agent_token = (await _post_form(api_client, "/token", {"username": "agent1", "password": "agent123"}))[
        "access_token"
    ]
    claim = await api_client.post(
        f"/api/agent/chat/claim?token={agent_token}",
        json={"chat_id": chat_id},
    )
    assert claim.status_code == 200, claim.text
    assert claim.json()["success"] is True

    release = await api_client.post(
        f"/api/agent/chat/release-ai?token={agent_token}",
        json={"chat_id": chat_id},
    )
    assert release.status_code == 200, release.text
    assert release.json()["success"] is True


@pytest.mark.asyncio
async def test_admin_can_create_product(api_client):
    token_data = await _post_form(
        api_client,
        "/token",
        {"username": "admin", "password": "admin123"},
    )

    response = await api_client.post(
        "/api/products",
        params={"token": token_data["access_token"]},
        json={"name": "回归测试游戏", "platform": "steam", "identifier": "123456"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["success"] is True
    assert payload["product_id"].startswith("steam_")


@pytest.mark.asyncio
async def test_production_payment_confirmation_requires_server_callback(api_client, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("PAYMENT_TEST_MODE", "false")

    username = f"prod_pay_{uuid.uuid4().hex[:8]}"
    password = "prod-pay-password"
    register_response = await api_client.post(
        "/register",
        data={"username": username, "email": f"{username}@example.com", "password": password},
        headers=_register_headers(),
    )
    assert register_response.status_code == 200, register_response.text

    token_data = await _post_form(
        api_client,
        "/token",
        {"username": username, "password": password},
    )
    token = token_data["access_token"]

    order_response = await api_client.post(
        "/api/payment/create-order",
        params={"token": token},
        json={"plan_id": "pro", "payment_method": "wechat"},
    )
    assert order_response.status_code == 200, order_response.text
    order_id = order_response.json()["order_id"]

    confirm_response = await api_client.post(
        "/api/payment/confirm",
        params={"token": token},
        json={"order_id": order_id, "transaction_id": "client-side-confirm"},
    )

    assert confirm_response.status_code == 403


@pytest.mark.asyncio
async def test_payment_webhook_requires_valid_signature(api_client, monkeypatch):
    monkeypatch.setenv("PAYMENT_WEBHOOK_SECRET", "test-webhook-secret")
    monkeypatch.setenv("APP_ENV", "development")

    username = f"pay_user_{uuid.uuid4().hex[:8]}"
    password = "pay-test-password"
    register_response = await api_client.post(
        "/register",
        data={"username": username, "email": f"{username}@example.com", "password": password},
        headers=_register_headers(),
    )
    assert register_response.status_code == 200, register_response.text

    token_data = await _post_form(
        api_client,
        "/token",
        {"username": username, "password": password},
    )
    token = token_data["access_token"]

    order_response = await api_client.post(
        "/api/payment/create-order",
        params={"token": token},
        json={"plan_id": "pro", "payment_method": "wechat"},
    )
    assert order_response.status_code == 200, order_response.text
    order_id = order_response.json()["order_id"]

    payload = {
        "order_id": order_id,
        "payment_status": "paid",
        "transaction_id": "webhook-transaction",
    }
    raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    bad_response = await api_client.post(
        "/api/payment/webhook",
        content=raw_body,
        headers={"X-Payment-Signature": "bad-signature"},
    )
    assert bad_response.status_code == 401

    signature = hmac.new(
        b"test-webhook-secret",
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    good_response = await api_client.post(
        "/api/payment/webhook",
        content=raw_body,
        headers={"X-Payment-Signature": signature},
    )

    assert good_response.status_code == 200, good_response.text
    assert good_response.json()["success"] is True


@pytest.mark.asyncio
async def test_llm_config_masks_api_key(api_client):
    token_data = await _post_form(
        api_client,
        "/token",
        {"username": "admin", "password": "admin123"},
    )
    token = token_data["access_token"]

    update_response = await api_client.put(
        "/api/llm/config",
        params={"token": token},
        json={"provider": "openai", "model": "gpt-4o-mini", "api_key": "sk-test-secret-123456"},
    )
    assert update_response.status_code == 200, update_response.text

    config_response = await api_client.get("/api/llm/config", params={"token": token})
    assert config_response.status_code == 200, config_response.text
    config = config_response.json()["config"]

    assert config["has_api_key"] is True
    assert config["api_key"] != "sk-test-secret-123456"
    assert "..." in config["api_key"]

    preserve_response = await api_client.put(
        "/api/llm/config",
        params={"token": token},
        json={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "api_key": config["api_key"],
            "temperature": 0.5,
        },
    )
    assert preserve_response.status_code == 200, preserve_response.text

    after_response = await api_client.get("/api/llm/config", params={"token": token})
    after_config = after_response.json()["config"]
    assert after_config["has_api_key"] is True
    assert after_config["temperature"] == 0.5


@pytest.mark.asyncio
async def test_ollama_config_persists_default_endpoint(api_client):
    token_data = await _post_form(
        api_client,
        "/token",
        {"username": "admin", "password": "admin123"},
    )
    token = token_data["access_token"]

    update_response = await api_client.put(
        "/api/llm/config",
        params={"token": token},
        json={"provider": "ollama", "model": "llama3.2", "endpoint": ""},
    )
    assert update_response.status_code == 200, update_response.text

    config_response = await api_client.get("/api/llm/config", params={"token": token})
    config = config_response.json()["config"]
    assert config["provider"] == "ollama"
    assert config["endpoint"] == "http://localhost:11434"


@pytest.mark.asyncio
async def test_imported_data_is_used_before_mock_data(api_client):
    username = f"import_user_{uuid.uuid4().hex[:8]}"
    password = "import-password"

    register_response = await api_client.post(
        "/register",
        data={"username": username, "email": f"{username}@example.com", "password": password},
        headers=_register_headers(),
    )
    assert register_response.status_code == 200, register_response.text

    token_data = await _post_form(
        api_client,
        "/token",
        {"username": username, "password": password},
    )
    token = token_data["access_token"]

    imported_metric = {
        "product": "customer_game",
        "channel": "Steam",
        "cycle": "pilot_week",
        "metric": "用户总下载量",
        "值": 12345,
    }
    imported_comment = {
        "product": "customer_game",
        "platform": "Steam",
        "日期": "2026-05-17",
        "用户角色": "试点用户",
        "情绪": "positive",
        "内容": "真实导入数据已经进入分析链路。",
    }

    import_response = await api_client.post(
        "/api/import",
        params={"token": token},
        json={"metrics": [imported_metric], "comments": [imported_comment]},
    )
    assert import_response.status_code == 200, import_response.text
    assert import_response.json()["counts"] == {"metrics": 1, "comments": 1}

    metrics_response = await api_client.get("/api/metrics", params={"token": token})
    assert metrics_response.status_code == 200, metrics_response.text
    metrics_payload = metrics_response.json()
    assert metrics_payload["source"] == "imported"
    assert metrics_payload["data"] == [imported_metric]

    report_response = await api_client.get(
        "/api/report",
        params={"token": token, "product": "customer_game", "time_period": "pilot_week"},
    )
    assert report_response.status_code == 200, report_response.text
    report_payload = report_response.json()
    assert report_payload["success"] is True
    assert report_payload["metrics"] == [imported_metric]
    assert report_payload["comments"] == [imported_comment]


@pytest.mark.asyncio
async def test_csv_file_import_feeds_metrics_api(api_client):
    username = f"csv_import_user_{uuid.uuid4().hex[:8]}"
    password = "csv-import-password"

    register_response = await api_client.post(
        "/register",
        data={"username": username, "email": f"{username}@example.com", "password": password},
        headers=_register_headers(),
    )
    assert register_response.status_code == 200, register_response.text

    token_data = await _post_form(
        api_client,
        "/token",
        {"username": username, "password": password},
    )
    token = token_data["access_token"]

    csv_content = (
        "product,channel,cycle,metric,值\n"
        "csv_game,Steam,csv_week,用户总下载量,6789\n"
    ).encode("utf-8")

    import_response = await api_client.post(
        "/api/import/file",
        params={"token": token, "dataset_type": "metrics"},
        files={"file": ("metrics.csv", csv_content, "text/csv")},
    )
    assert import_response.status_code == 200, import_response.text
    assert import_response.json()["counts"] == {"metrics": 1, "comments": 0}

    metrics_response = await api_client.get("/api/metrics", params={"token": token})
    assert metrics_response.status_code == 200, metrics_response.text
    metrics_payload = metrics_response.json()
    assert metrics_payload["source"] == "imported"
    assert metrics_payload["data"][0]["product"] == "csv_game"
    assert metrics_payload["data"][0]["值"] == 6789


@pytest.mark.asyncio
async def test_import_template_downloads_csv(api_client):
    token_data = await _post_form(
        api_client,
        "/token",
        {"username": "demo", "password": "demo123"},
    )
    response = await api_client.get(
        "/api/import/template",
        params={"dataset_type": "metrics", "token": token_data["access_token"]},
    )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert "product,channel,cycle,metric" in response.text


@pytest.mark.asyncio
async def test_csv_import_reports_missing_columns(api_client):
    username = f"bad_csv_user_{uuid.uuid4().hex[:8]}"
    password = "bad-csv-password"

    register_response = await api_client.post(
        "/register",
        data={"username": username, "email": f"{username}@example.com", "password": password},
        headers=_register_headers(),
    )
    assert register_response.status_code == 200, register_response.text

    token_data = await _post_form(
        api_client,
        "/token",
        {"username": username, "password": password},
    )
    token = token_data["access_token"]

    csv_content = "product,channel,cycle\ncsv_game,Steam,csv_week\n".encode("utf-8")
    response = await api_client.post(
        "/api/import/file",
        params={"token": token, "dataset_type": "metrics"},
        files={"file": ("bad_metrics.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["message"] == "导入数据校验失败"
    assert "metric" in detail["missing_columns"]
    assert "值 或 value" in detail["missing_columns"]


def test_no_duplicate_route_method_pairs():
    route_pairs = [
        (route.path, tuple(sorted(getattr(route, "methods", []) or [])))
        for route in app.routes
        if getattr(route, "path", None) and getattr(route, "methods", None)
    ]
    duplicates = [pair for pair, count in Counter(route_pairs).items() if count > 1]

    assert duplicates == []
