"""HTTP middleware: IP rate limit + authenticated API quota."""

from __future__ import annotations

import os

from fastapi.responses import JSONResponse

from src.database import UserRepository
from src.abuse_guard import (
    check_device_free_pool,
    extract_device_id,
    increment_device_api_usage,
)
from src.api_limits import (
    check_ip_rate_limit,
    check_user_api_quota,
    decode_username,
    extract_bearer_token,
    increment_api_usage,
    is_exempt_path,
)


async def limits_middleware(request, call_next):
    path = request.url.path
    if is_exempt_path(path):
        return await call_next(request)

    if os.getenv("GA_E2E_DISABLE_RATE_LIMIT", "").strip().lower() in ("1", "true", "yes"):
        return await call_next(request)

    client_ip = request.client.host if request.client else "unknown"
    if not check_ip_rate_limit(client_ip):
        return JSONResponse(
            status_code=429,
            content={"success": False, "detail": "请求过于频繁，请稍后再试"},
        )

    if path.startswith("/api/"):
        token = extract_bearer_token(request)
        if token:
            username = decode_username(token)
            if username:
                allowed, used, quota = check_user_api_quota(username)
                if not allowed:
                    return JSONResponse(
                        status_code=429,
                        content={
                            "success": False,
                            "detail": f"本月 API 配额已用完（{used}/{quota}）",
                            "api_usage": used,
                            "api_quota": quota,
                        },
                    )

                device_id = extract_device_id(request)
                user_row = UserRepository.get_by_username(username)
                d_allowed, d_used, d_quota = check_device_free_pool(
                    device_id, username, user_row or {}
                )
                if not d_allowed:
                    return JSONResponse(
                        status_code=429,
                        content={
                            "success": False,
                            "detail": f"该设备本月免费 API 配额已用完（{d_used}/{d_quota}）",
                            "device_api_usage": d_used,
                            "device_api_quota": d_quota,
                        },
                    )

                increment_api_usage(username)
                if device_id and d_quota > 0:
                    increment_device_api_usage(device_id)

    return await call_next(request)
