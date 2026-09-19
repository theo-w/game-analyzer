"""Medium-tier anti-abuse: IP/device registration limits, trial-once-per-device, shared free quota."""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from database import db_manager
from src.api_limits import effective_plan_id

_DEVICE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{8,64}$")

# 登录失败锁定：同一用户名 15 分钟内失败 10 次 → 锁定 15 分钟（内存态，进程重启即清零）
_LOGIN_LOCK = threading.Lock()
_LOGIN_FAILURES: Dict[str, List[datetime]] = {}
LOGIN_FAILURE_THRESHOLD = 10
LOGIN_FAILURE_WINDOW_MINUTES = 15
# 键数护栏：/token 未认证，防幽灵用户名探测把字典撑到无界（触发时清扫过期条目）
LOGIN_FAILURE_MAX_KEYS = 10000


@dataclass(frozen=True)
class AbuseLimits:
    ip_register_per_24h: int = 2
    ip_register_per_7d: int = 5
    device_register_per_30d: int = 2
    device_free_pool_monthly: int = 1000
    ip_distinct_logins_per_hour_block_register: int = 5


LIMITS = AbuseLimits()


def client_ip(request) -> str:
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if forwarded:
        return forwarded
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def normalize_device_id(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    value = str(raw).strip()
    if not _DEVICE_ID_RE.match(value):
        return None
    return value


def extract_device_id(request) -> Optional[str]:
    header = request.headers.get("x-device-id") or request.headers.get("X-Device-Id")
    if header:
        return normalize_device_id(header)
    if hasattr(request, "query_params"):
        return normalize_device_id(request.query_params.get("device_id"))
    return None


def _since_iso(hours: int = 0, days: int = 0) -> str:
    return (datetime.now() - timedelta(hours=hours, days=days)).isoformat()


def check_login_locked(username: str) -> bool:
    """该用户名是否处于登录失败锁定窗口内。"""
    key = (username or "").strip().lower()
    if not key:
        return False
    cutoff = datetime.now() - timedelta(minutes=LOGIN_FAILURE_WINDOW_MINUTES)
    with _LOGIN_LOCK:
        failures = [t for t in _LOGIN_FAILURES.get(key, []) if t > cutoff]
        if not failures:
            # 未命中不留条目，避免幽灵用户名探测撑爆内存
            _LOGIN_FAILURES.pop(key, None)
            return False
        _LOGIN_FAILURES[key] = failures
        return len(failures) >= LOGIN_FAILURE_THRESHOLD


def record_login_failure(username: str) -> None:
    key = (username or "").strip().lower()
    if not key:
        return
    with _LOGIN_LOCK:
        _LOGIN_FAILURES.setdefault(key, []).append(datetime.now())
        if len(_LOGIN_FAILURES[key]) > 100:
            del _LOGIN_FAILURES[key][: -LOGIN_FAILURE_THRESHOLD]
        if len(_LOGIN_FAILURES) > LOGIN_FAILURE_MAX_KEYS:
            cutoff = datetime.now() - timedelta(minutes=LOGIN_FAILURE_WINDOW_MINUTES)
            expired = [k for k, v in _LOGIN_FAILURES.items() if not any(t > cutoff for t in v)]
            for k in expired:
                _LOGIN_FAILURES.pop(k, None)


def record_login_success(username: str) -> None:
    _LOGIN_FAILURES.pop((username or "").strip().lower(), None)


def count_registrations_by_ip(ip: str, *, hours: int = 0, days: int = 0) -> int:
    since = _since_iso(hours=hours, days=days)
    row = db_manager.execute_one(
        "SELECT COUNT(*) AS c FROM registration_events WHERE ip_address = ? AND created_at >= ?",
        (ip, since),
    )
    return int(row["c"]) if row else 0


def count_registrations_by_device(device_id: str, days: int = 30) -> int:
    since = _since_iso(days=days)
    row = db_manager.execute_one(
        """
        SELECT COUNT(*) AS c FROM registration_events
        WHERE device_id = ? AND created_at >= ?
        """,
        (device_id, since),
    )
    return int(row["c"]) if row else 0


def distinct_logins_by_ip_last_hour(ip: str) -> int:
    since = _since_iso(hours=1)
    row = db_manager.execute_one(
        """
        SELECT COUNT(DISTINCT username) AS c FROM login_events
        WHERE ip_address = ? AND created_at >= ?
        """,
        (ip, since),
    )
    return int(row["c"]) if row else 0


def device_trial_already_claimed(device_id: Optional[str]) -> bool:
    if not device_id:
        return False
    row = db_manager.execute_one(
        "SELECT 1 FROM device_trial_claims WHERE device_id = ? LIMIT 1",
        (device_id,),
    )
    return row is not None


def email_taken(email: str) -> bool:
    row = db_manager.execute_one(
        "SELECT username FROM users WHERE LOWER(email) = LOWER(?) LIMIT 1",
        (email.strip(),),
    )
    return row is not None


def validate_registration(
    *,
    email: str,
    ip: str,
    device_id: Optional[str],
) -> Optional[str]:
    """Return Chinese error message if registration should be blocked."""
    if not device_id:
        return "请刷新页面后重试（缺少设备标识）"

    if email_taken(email):
        return "该邮箱已被注册，请直接登录或更换邮箱"

    if count_registrations_by_ip(ip, hours=24) >= LIMITS.ip_register_per_24h:
        return "该网络注册过于频繁，请 24 小时后再试或联系客服"

    if count_registrations_by_ip(ip, days=7) >= LIMITS.ip_register_per_7d:
        return "该网络本周注册次数已达上限，请联系客服"

    if device_id and count_registrations_by_device(device_id, days=30) >= LIMITS.device_register_per_30d:
        return "该设备 30 天内注册账号数已达上限"

    if distinct_logins_by_ip_last_hour(ip) >= LIMITS.ip_distinct_logins_per_hour_block_register:
        return "该网络登录账号过多，暂时无法注册新账号，请稍后再试"

    return None


def trial_eligible(device_id: Optional[str]) -> bool:
    if not device_id:
        return True
    return not device_trial_already_claimed(device_id)


def record_registration(
    *,
    username: str,
    email: str,
    ip: str,
    device_id: Optional[str],
    trial_granted: bool,
) -> None:
    now = datetime.now().isoformat()
    db_manager.insert(
        "registration_events",
        {
            "username": username,
            "email": email.strip().lower(),
            "ip_address": ip,
            "device_id": device_id,
            "trial_granted": 1 if trial_granted else 0,
            "created_at": now,
        },
    )
    if device_id:
        link_device_account(device_id, username)
    if trial_granted and device_id:
        db_manager.insert(
            "device_trial_claims",
            {"device_id": device_id, "username": username, "claimed_at": now},
        )


def record_login(*, username: str, ip: str, device_id: Optional[str]) -> None:
    now = datetime.now().isoformat()
    db_manager.insert(
        "login_events",
        {
            "username": username,
            "ip_address": ip,
            "device_id": device_id,
            "created_at": now,
        },
    )
    if device_id:
        link_device_account(device_id, username)


def link_device_account(device_id: str, username: str) -> None:
    now = datetime.now().isoformat()
    existing = db_manager.execute_one(
        "SELECT device_id FROM device_accounts WHERE device_id = ? AND username = ?",
        (device_id, username),
    )
    if existing:
        db_manager.execute(
            "UPDATE device_accounts SET last_seen_at = ? WHERE device_id = ? AND username = ?",
            (now, device_id, username),
        )
    else:
        db_manager.insert(
            "device_accounts",
            {
                "device_id": device_id,
                "username": username,
                "first_seen_at": now,
                "last_seen_at": now,
            },
        )


def _device_usage_key(device_id: str) -> str:
    return f"device_api_usage:{device_id}:{datetime.now().strftime('%Y%m')}"


def get_device_api_usage(device_id: str) -> int:
    from src.cache import get_cache

    return int(get_cache().get(_device_usage_key(device_id)) or 0)


def increment_device_api_usage(device_id: str) -> int:
    from src.cache import get_cache

    cache = get_cache()
    key = _device_usage_key(device_id)
    count = int(cache.get(key) or 0) + 1
    cache.set(key, count, expire_seconds=32 * 24 * 3600)
    return count


def _user_counts_toward_device_pool(user_row: dict) -> bool:
    if not user_row:
        return False
    if user_row.get("role") in ("admin", "agent"):
        return False
    plan = effective_plan_id(user_row)
    if plan in ("pro", "enterprise"):
        if user_row.get("is_trial") and user_row.get("trial_end_date"):
            try:
                if datetime.fromisoformat(user_row["trial_end_date"]) >= datetime.now():
                    return False
            except ValueError:
                pass
        if plan == "enterprise":
            return False
        paid_order = db_manager.execute_one(
            """
            SELECT 1 FROM orders
            WHERE username = ? AND payment_status = 'paid' AND plan_id IN ('pro', 'enterprise')
            LIMIT 1
            """,
            (user_row["username"],),
        )
        if paid_order:
            return False
    return True


def check_device_free_pool(
    device_id: Optional[str], username: str, user_row: dict
) -> Tuple[bool, int, int]:
    """Free-tier accounts on the same device share a monthly API pool."""
    if not device_id or not _user_counts_toward_device_pool(user_row):
        return True, 0, -1
    used = get_device_api_usage(device_id)
    quota = LIMITS.device_free_pool_monthly
    return used < quota, used, quota


def list_linked_accounts(
    *, ip: Optional[str] = None, device_id: Optional[str] = None, limit: int = 50
) -> List[dict]:
    results: List[dict] = []
    if device_id:
        rows = db_manager.execute(
            """
            SELECT da.device_id, da.username, da.first_seen_at, da.last_seen_at, u.email, u.plan_id
            FROM device_accounts da
            LEFT JOIN users u ON u.username = da.username
            WHERE da.device_id = ?
            ORDER BY da.last_seen_at DESC
            LIMIT ?
            """,
            (device_id, limit),
        )
        results.extend(rows or [])
    if ip:
        rows = db_manager.execute(
            """
            SELECT DISTINCT username, ip_address, MAX(created_at) AS last_seen
            FROM login_events
            WHERE ip_address = ?
            GROUP BY username
            ORDER BY last_seen DESC
            LIMIT ?
            """,
            (ip, limit),
        )
        for row in rows or []:
            results.append(
                {
                    "ip_address": row["ip_address"],
                    "username": row["username"],
                    "last_seen_at": row["last_seen"],
                }
            )
    return results
