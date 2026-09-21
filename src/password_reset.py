"""Password reset tokens (email delivery optional; dev returns link in API)."""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple

from src.auth import get_password_hash
from src.database import UserRepository, db_manager

RESET_TOKEN_TTL_MINUTES = 60


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def ensure_password_reset_table() -> None:
    db_manager.execute(
        """
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            token_hash TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used_at TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    db_manager.execute(
        "CREATE INDEX IF NOT EXISTS idx_password_reset_hash ON password_reset_tokens(token_hash)"
    )


def create_reset_token_for_email(email: str) -> Tuple[bool, Dict[str, str]]:
    """Issue a reset token for the given email. Returns (found, payload)."""
    ensure_password_reset_table()
    user = UserRepository.get_by_email(email)
    if not user:
        return False, {"message": "若该邮箱已注册，我们将发送重置说明。"}

    username = user["username"]
    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_token)
    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(minutes=RESET_TOKEN_TTL_MINUTES)).isoformat()

    db_manager.execute(
        """
        INSERT INTO password_reset_tokens (username, token_hash, expires_at, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (username, token_hash, expires_at, now.isoformat()),
    )

    base = (
        os.getenv("PUBLIC_DEMO_BASE_URL", "").strip().rstrip("/")
        or os.getenv("APP_PUBLIC_URL", "").strip().rstrip("/")
        or "http://127.0.0.1:8080"
    )
    reset_url = f"{base}/reset-password?token={raw_token}"
    payload = {
        "message": "若该邮箱已注册，我们将发送重置说明。",
        "username": username,
        "reset_url": reset_url,
    }
    if os.getenv("APP_ENV", "development").lower() != "production":
        payload["dev_reset_url"] = reset_url
    return True, payload


def reset_password_with_token(token: str, new_password: str) -> Tuple[bool, str]:
    ensure_password_reset_table()
    if not token or not new_password or len(new_password) < 6:
        return False, "密码至少 6 位"

    row = db_manager.execute_one(
        """
        SELECT * FROM password_reset_tokens
        WHERE token_hash = ? AND used_at IS NULL
        ORDER BY id DESC LIMIT 1
        """,
        (_hash_token(token),),
    )
    if not row:
        return False, "重置链接无效或已使用"

    expires_at = datetime.fromisoformat(str(row["expires_at"]).replace("Z", "+00:00"))
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires_at:
        return False, "重置链接已过期，请重新申请"

    username = row["username"]
    UserRepository.update(
        username,
        {"hashed_password": get_password_hash(new_password)},
    )
    used_at = datetime.now(timezone.utc).isoformat()
    db_manager.execute(
        "UPDATE password_reset_tokens SET used_at = ? WHERE id = ?",
        (used_at, row["id"]),
    )
    return True, "密码已重置，请使用新密码登录"
