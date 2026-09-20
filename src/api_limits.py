"""API rate limiting and per-user monthly quota tracking."""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Tuple

from jose import JWTError, jwt

from src.auth import ALGORITHM, SECRET_KEY
from src.cache import get_rate_limiter, get_cache
from src.database import UserRepository

EXEMPT_PATH_PREFIXES = (
    "/static/",
    "/api/health",
    "/api/auth/forgot-password",
    "/api/auth/reset-password",
    "/token",
    "/register",
    "/login",
    "/forgot-password",
    "/reset-password",
    "/shared/",
    "/docs",
    "/openapi.json",
    "/redoc",
)

EXEMPT_EXACT = {"/", "/favicon.ico"}


def is_exempt_path(path: str) -> bool:
    if path in EXEMPT_EXACT:
        return True
    return any(path.startswith(prefix) for prefix in EXEMPT_PATH_PREFIXES)


def extract_bearer_token(request) -> Optional[str]:
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    token = request.query_params.get("token")
    return token.strip() if token else None


def decode_username(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None


def effective_plan_id(user_row: dict) -> str:
    plan_id = user_row.get("plan_id") or "free"
    if user_row.get("is_trial") and user_row.get("trial_end_date"):
        try:
            if datetime.fromisoformat(user_row["trial_end_date"]) < datetime.now():
                return "free"
        except ValueError:
            pass
    return plan_id


def effective_api_quota(user_row: dict) -> int:
    quota = int(user_row.get("api_quota") or 1000)
    if effective_plan_id(user_row) == "free" and user_row.get("is_trial"):
        try:
            if user_row.get("trial_end_date") and datetime.fromisoformat(
                user_row["trial_end_date"]
            ) < datetime.now():
                from src.auth import PLANS

                return PLANS["free"].api_quota
        except ValueError:
            pass
    return quota


def _quota_key(username: str) -> str:
    return f"api_usage:{username}:{datetime.now().strftime('%Y%m')}"


def get_api_usage(username: str) -> int:
    return int(get_cache().get(_quota_key(username)) or 0)


def increment_api_usage(username: str) -> int:
    cache = get_cache()
    key = _quota_key(username)
    count = int(cache.get(key) or 0) + 1
    cache.set(key, count, expire_seconds=32 * 24 * 3600)
    return count


def check_ip_rate_limit(client_ip: str) -> bool:
    limiter = get_rate_limiter()
    return limiter.is_allowed(f"ip:{client_ip}")


def check_user_api_quota(username: str) -> Tuple[bool, int, int]:
    row = UserRepository.get_by_username(username)
    if not row:
        return True, 0, 0
    if row.get("role") in ("admin", "agent"):
        return True, 0, -1
    quota = effective_api_quota(row)
    if quota < 0:
        return True, 0, -1
    used = get_api_usage(username)
    return used < quota, used, quota
