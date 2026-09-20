"""Shared helpers for payment, secrets masking, and auth delegation."""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from src.auth import PLANS, UserInDB
from src.database import OperationLogRepository, UserRepository, get_db_connection
from src.deps import get_current_user, resolve_user_from_token

# Re-export for routers: Depends(get_current_user) and await get_current_user(token).


def mask_secret(value: Optional[str]) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}...{value[-4:]}"


def is_masked_secret(value: Optional[str]) -> bool:
    """True when value looks like a masked API key from the admin UI."""
    if not value:
        return False
    if value == "****":
        return True
    return "..." in value and len(value) < 24


def mask_config_secrets(config: Dict[str, Any]) -> Dict[str, Any]:
    from src.web_constants import SENSITIVE_CONFIG_FIELDS

    masked = dict(config)
    for field in SENSITIVE_CONFIG_FIELDS:
        if field in masked:
            masked[f"has_{field}"] = bool(masked.get(field))
            masked[field] = mask_secret(masked.get(field))
    return masked


def verify_payment_signature(raw_body: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def mark_order_paid(order: Dict[str, Any], transaction_id: str) -> Dict[str, Any]:
    expires_at = (datetime.now() + timedelta(days=365)).isoformat()
    plan = PLANS[order["plan_id"]]
    games_limit = plan.games_limit if plan.games_limit > 0 else 999999
    api_quota = plan.api_quota if plan.api_quota > 0 else 999999
    now = datetime.now().isoformat()

    # 订单状态与用户套餐/限额必须同事务落库, 避免已支付但套餐未升级
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE orders
            SET payment_status = 'paid', transaction_id = ?, paid_at = ?, expires_at = ?, updated_at = ?
            WHERE order_id = ?
            """,
            (
                transaction_id,
                now,
                expires_at,
                now,
                order["order_id"],
            ),
        )
        cursor.execute(
            'UPDATE users SET plan_id = ?, games_limit = ?, api_quota = ?, updated_at = ? WHERE username = ?',
            (order["plan_id"], games_limit, api_quota, now, order["username"]),
        )
        conn.commit()

    OperationLogRepository.log(
        order["username"],
        "payment_completed",
        f'Payment completed for order: {order["order_id"]}, plan: {order["plan_id"]}',
    )
    return {"plan_id": order["plan_id"], "expires_at": expires_at}


async def get_user_by_token(token: str) -> UserInDB:
    """Alias for manual auth call sites."""
    return await get_current_user(token)
