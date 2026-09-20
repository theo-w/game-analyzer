"""Authentication, registration, and user admin routes."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse

from src.auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    PLANS,
    create_access_token,
    get_password_hash,
    verify_password,
)
from src.database import OperationLogRepository, UserRepository
from src.password_reset import create_reset_token_for_email, reset_password_with_token
from src.abuse_guard import (
    client_ip,
    extract_device_id,
    list_linked_accounts,
    normalize_device_id,
    record_login,
    record_registration,
    trial_eligible,
    validate_registration,
)
from src.api_limits import effective_api_quota, get_api_usage
from src.web_common import get_current_user
from src.web_constants import ADMIN_FILE, BASE_DIR, LOGIN_FILE

router = APIRouter(tags=["auth"])

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    with open(LOGIN_FILE, 'r', encoding='utf-8') as f:
        return f.read()

@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    path = os.path.join(BASE_DIR, "templates", "forgot_password.html")
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(request: Request):
    path = os.path.join(BASE_DIR, "templates", "reset_password.html")
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

@router.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    with open(ADMIN_FILE, 'r', encoding='utf-8') as f:
        return f.read()

@router.get("/pricing", response_class=HTMLResponse)
async def pricing_page(request: Request):
    with open(os.path.join(BASE_DIR, "templates", "pricing.html"), 'r', encoding='utf-8') as f:
        return f.read()

@router.get("/team", response_class=HTMLResponse)
async def team_page(request: Request):
    with open(os.path.join(BASE_DIR, "templates", "team.html"), 'r', encoding='utf-8') as f:
        return f.read()

@router.get("/api-docs", response_class=HTMLResponse)
async def api_docs_page(request: Request):
    """API文档页面"""
    with open(os.path.join(BASE_DIR, "templates", "api_docs.html"), 'r', encoding='utf-8') as f:
        return f.read()

@router.get("/alerts", response_class=HTMLResponse)
async def alerts_page(request: Request):
    with open(os.path.join(BASE_DIR, "templates", "alerts.html"), 'r', encoding='utf-8') as f:
        return f.read()

@router.post("/token")
async def login_for_access_token(request: Request):
    form_data = await request.form()
    username = form_data.get("username")
    password = form_data.get("password")
    device_id = extract_device_id(request) or normalize_device_id(form_data.get("device_id"))
    
    user_data = UserRepository.get_by_username(username)
    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not verify_password(password, user_data['hashed_password']):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user_data.get('is_active', 1):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    ip = client_ip(request)
    record_login(username=username, ip=ip, device_id=device_id)
    OperationLogRepository.log(username, 'login', f'Login from {ip} device={device_id or "-"}')
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/logout")
async def logout():
    return {"success": True, "message": "Logout successful"}

@router.post("/api/auth/forgot-password")
async def forgot_password(request: Request):
    body = await request.json()
    email = (body.get("email") or "").strip()
    if not email:
        raise HTTPException(status_code=400, detail="请输入邮箱")
    _, payload = create_reset_token_for_email(email)
    response = {"success": True, "message": payload["message"]}
    if os.getenv("APP_ENV", "development").lower() != "production":
        dev_url = payload.get("dev_reset_url")
        if dev_url:
            response["dev_reset_url"] = dev_url
    return response

@router.post("/api/auth/reset-password")
async def reset_password_api(request: Request):
    body = await request.json()
    token = (body.get("token") or "").strip()
    password = body.get("password") or ""
    ok, message = reset_password_with_token(token, password)
    return {"success": ok, "message": message}

@router.post("/register")
async def register_user(request: Request):
    form_data = await request.form()
    username = form_data.get("username")
    email = form_data.get("email")
    password = form_data.get("password")
    device_id = extract_device_id(request) or normalize_device_id(form_data.get("device_id"))
    ip = client_ip(request)
    
    if not username or not email or not password:
        raise HTTPException(status_code=400, detail="缺少必要字段")
    
    if UserRepository.get_by_username(username):
        raise HTTPException(status_code=400, detail="Username already registered")

    block_reason = validate_registration(email=str(email), ip=ip, device_id=device_id)
    if block_reason:
        raise HTTPException(status_code=429, detail=block_reason)

    grant_trial = trial_eligible(device_id)
    free_plan = PLANS["free"]
    if grant_trial:
        trial_end_date = (datetime.now() + timedelta(days=7)).isoformat()
        user_data = {
            'username': username,
            'email': email.strip().lower(),
            'full_name': '',
            'hashed_password': get_password_hash(password),
            'role': 'user',
            'plan_id': 'pro',
            'games_limit': PLANS['pro'].games_limit,
            'api_quota': PLANS['pro'].api_quota,
            'is_active': 1,
            'trial_start_date': datetime.now().isoformat(),
            'trial_end_date': trial_end_date,
            'is_trial': 1,
        }
    else:
        trial_end_date = None
        user_data = {
            'username': username,
            'email': email.strip().lower(),
            'full_name': '',
            'hashed_password': get_password_hash(password),
            'role': 'user',
            'plan_id': 'free',
            'games_limit': free_plan.games_limit,
            'api_quota': free_plan.api_quota,
            'is_active': 1,
            'is_trial': 0,
        }
    
    if UserRepository.create(user_data):
        record_registration(
            username=username,
            email=str(email),
            ip=ip,
            device_id=device_id,
            trial_granted=grant_trial,
        )
        detail = 'New user registered with 7-day trial' if grant_trial else 'New user registered (free plan, device trial used)'
        OperationLogRepository.log(username, 'register', detail)
        payload = {
            "success": True,
            "message": "User registered successfully",
            "trial_granted": grant_trial,
        }
        if grant_trial:
            payload["trial_end_date"] = trial_end_date
            payload["trial_days_remaining"] = 7
        else:
            payload["message"] = "注册成功（该设备已使用过试用，当前为免费版）"
        return payload
    else:
        raise HTTPException(status_code=500, detail="Failed to create user")

@router.get("/api/user")
async def read_users_me(request: Request, token: Optional[str] = Query(None)):
    current_user = await get_current_user(request, token)
    row = UserRepository.get_by_username(current_user.username) or {}
    quota = effective_api_quota(row) if row else int(current_user.api_quota or 1000)
    used = get_api_usage(current_user.username)
    remaining = max(0, quota - used) if quota >= 0 else -1
    payload = current_user.model_dump()
    payload.update(
        {
            "api_usage": used,
            "api_remaining": remaining,
            "api_quota_monthly": quota,
        }
    )
    return payload

@router.get("/api/users")
async def get_users(token: Optional[str] = Query(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)
    
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="只有管理员可以访问此功能")
    
    users_list = UserRepository.get_all()
    
    return {"success": True, "users": users_list}

@router.post("/api/users")
async def create_user(request: Request, token: Optional[str] = Query(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)
    
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="只有管理员可以创建用户")
    
    body = await request.json()
    username = body.get("username")
    email = body.get("email")
    password = body.get("password")
    role = body.get("role", "user")
    plan = body.get("plan", "free")
    
    if role not in ("user", "admin", "agent"):
        raise HTTPException(status_code=400, detail="无效的角色类型")
    if role == "admin" and username != current_user.username:
        pass  # admin may create other admins
    
    if not username or not email or not password:
        raise HTTPException(status_code=400, detail="缺少必要字段")
    
    if UserRepository.get_by_username(username):
        raise HTTPException(status_code=400, detail="用户名已存在")
    
    plan_config = PLANS.get(plan, PLANS["free"])
    
    user_data = {
        'username': username,
        'email': email,
        'full_name': body.get("full_name", ""),
        'hashed_password': get_password_hash(password),
        'role': role,
        'plan_id': plan,
        'games_limit': plan_config.games_limit,
        'api_quota': plan_config.api_quota,
        'is_active': 1
    }
    
    if UserRepository.create(user_data):
        OperationLogRepository.log(current_user.username, 'create_user', f'Created user: {username}')
        return {"success": True, "message": "用户创建成功", "user": {"username": username, "email": email, "role": role, "plan": plan}}
    else:
        raise HTTPException(status_code=500, detail="Failed to create user")

@router.delete("/api/users/{username}")
async def delete_user(username: str, token: Optional[str] = Query(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)
    
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="只有管理员可以删除用户")
    
    if username == current_user.username:
        raise HTTPException(status_code=400, detail="不能删除自己的账户")
    
    if not UserRepository.get_by_username(username):
        raise HTTPException(status_code=404, detail="用户不存在")
    
    if UserRepository.delete(username):
        OperationLogRepository.log(current_user.username, 'delete_user', f'Deleted user: {username}')
        return {"success": True, "message": "用户删除成功"}
    else:
        raise HTTPException(status_code=500, detail="Failed to delete user")

@router.put("/api/users/{username}")
async def update_user(username: str, request: Request, token: Optional[str] = Query(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)
    
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="只有管理员可以更新用户")
    
    if not UserRepository.get_by_username(username):
        raise HTTPException(status_code=404, detail="用户不存在")
    
    body = await request.json()
    user_data = {}
    
    if "email" in body:
        user_data["email"] = body["email"]
    if "full_name" in body:
        user_data["full_name"] = body["full_name"]
    if "role" in body and current_user.username != username:
        user_data["role"] = body["role"]
    if "plan" in body:
        plan = body["plan"]
        user_data["plan_id"] = plan
        plan_config = PLANS.get(plan, PLANS["free"])
        user_data["games_limit"] = plan_config.games_limit
        user_data["api_quota"] = plan_config.api_quota
    if "disabled" in body:
        user_data["is_active"] = 0 if body["disabled"] else 1
    if "games_limit" in body:
        user_data["games_limit"] = body["games_limit"]
    if "api_quota" in body:
        user_data["api_quota"] = body["api_quota"]
    if "password" in body:
        user_data["hashed_password"] = get_password_hash(body["password"])
    
    if UserRepository.update(username, user_data):
        OperationLogRepository.log(current_user.username, 'update_user', f'Updated user: {username}')
        return {"success": True, "message": "用户信息更新成功"}
    else:
        raise HTTPException(status_code=500, detail="Failed to update user")

@router.get("/api/logs/operations")
async def get_operation_logs(
    token: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500)
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)
    
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="只有管理员可以查看操作日志")
    
    logs = OperationLogRepository.get_all(limit=limit)
    return {"success": True, "logs": logs}

@router.get("/api/logs/user/{username}")
async def get_user_operation_logs(
    username: str,
    token: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200)
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)
    
    if current_user.role != "admin" and current_user.username != username:
        raise HTTPException(status_code=403, detail="权限不足")
    
    logs = OperationLogRepository.get_by_username(username, limit=limit)
    return {"success": True, "logs": logs}


@router.get("/api/admin/abuse/linked")
async def admin_abuse_linked_accounts(
    token: Optional[str] = Query(None),
    ip: Optional[str] = Query(None),
    device_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="只有管理员可以查看")

    if not ip and not device_id:
        raise HTTPException(status_code=400, detail="请提供 ip 或 device_id 参数")

    return {
        "success": True,
        "linked": list_linked_accounts(
            ip=ip,
            device_id=normalize_device_id(device_id),
            limit=limit,
        ),
    }

