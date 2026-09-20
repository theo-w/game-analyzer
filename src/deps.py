"""Shared FastAPI dependencies."""

from __future__ import annotations

import logging
from typing import Optional, Union

from fastapi import HTTPException, Query, Request, status
from jose import JWTError, jwt

from src.auth import PLANS
from src.api_limits import effective_api_quota, effective_plan_id
from src.auth import ALGORITHM, SECRET_KEY, TokenData, UserInDB
from src.database import UserRepository

logger = logging.getLogger(__name__)

SUPPORT_STAFF_ROLES = frozenset({"admin", "agent"})


def is_admin(user: UserInDB) -> bool:
    return user.role == "admin"


def is_support_staff(user: UserInDB) -> bool:
    return user.role in SUPPORT_STAFF_ROLES


def require_admin(user: UserInDB) -> None:
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="只有管理员可以执行此操作")


def require_support_staff(user: UserInDB) -> None:
    if not is_support_staff(user):
        raise HTTPException(status_code=403, detail="权限不足")


def _extract_token(request: Request, token_query: Optional[str]) -> Optional[str]:
    """JWT from Authorization header (preferred) or query param (legacy)."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[len("Bearer ") :]
    if token_query:
        logger.debug(
            "Token via query param (deprecated). path=%s",
            request.url.path,
        )
        return token_query
    return None


def resolve_user_from_token(token: str) -> UserInDB:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception

    user_data = UserRepository.get_by_username(token_data.username)
    if user_data is None:
        raise credentials_exception

    plan_id = effective_plan_id(user_data)
    plan_defaults = PLANS.get(plan_id, PLANS["free"])

    return UserInDB(
        id=user_data["username"],
        username=user_data["username"],
        email=user_data.get("email", ""),
        full_name=user_data.get("full_name", ""),
        disabled=not bool(user_data.get("is_active", 1)),
        role=user_data.get("role", "user"),
        plan=plan_id,
        games_limit=int(user_data.get("games_limit") or plan_defaults.games_limit),
        api_quota=effective_api_quota(user_data),
        hashed_password=user_data.get("hashed_password", ""),
    )


async def get_current_user(
    request_or_token: Union[Request, str, None] = None,
    token: Optional[str] = Query(None),
) -> UserInDB:
    """FastAPI Depends or legacy ``await get_current_user(jwt_string)``."""
    resolved: Optional[str] = None
    if isinstance(request_or_token, Request):
        resolved = _extract_token(request_or_token, token)
    elif isinstance(request_or_token, str) and request_or_token:
        resolved = request_or_token
    elif token:
        resolved = token

    if not resolved:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return resolve_user_from_token(resolved)
