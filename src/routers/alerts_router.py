"""Alerts CRUD — user-defined metric alert rules."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from src.database import AlertRepository, OperationLogRepository
from src.auth import UserInDB
from src.web_common import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["alerts"])


def _api_error(exc: Exception, user_msg: str = "操作失败，请稍后重试") -> str:
    import os
    logger.exception("Alerts API error: %s", exc)
    if os.getenv("APP_ENV", "development").lower() == "production":
        return user_msg
    return str(exc)


@router.get("/api/alerts")
async def get_alerts(current_user: UserInDB = Depends(get_current_user)):
    alerts = AlertRepository.get_by_username(current_user.username)
    return {"success": True, "alerts": alerts}


@router.post("/api/alerts")
async def create_alert(
    request: Request,
    current_user: UserInDB = Depends(get_current_user),
):
    body = await request.json()
    alert_data = {
        "username": current_user.username,
        "name": body.get("name", ""),
        "product": body.get("product"),
        "metric": body.get("metric", ""),
        "operator": body.get("operator", ""),
        "threshold": float(body.get("threshold", 0)),
        "email": body.get("email", ""),
    }

    if AlertRepository.create(alert_data):
        OperationLogRepository.log(
            current_user.username, "create_alert", f"Created alert: {alert_data['name']}"
        )
        return {"success": True, "message": "预警规则创建成功"}
    return {"success": False, "message": "创建失败"}


@router.put("/api/alerts/{alert_id}")
async def update_alert(
    alert_id: int,
    request: Request,
    current_user: UserInDB = Depends(get_current_user),
):
    body = await request.json()
    alert_data = {}
    for key in ["name", "product", "metric", "operator", "threshold", "email", "enabled"]:
        if key in body:
            alert_data[key] = float(body[key]) if key == "threshold" else body[key]

    if AlertRepository.update(alert_id, alert_data):
        OperationLogRepository.log(
            current_user.username, "update_alert", f"Updated alert: {alert_id}"
        )
        return {"success": True, "message": "更新成功"}
    return {"success": False, "message": "更新失败"}


@router.delete("/api/alerts/{alert_id}")
async def delete_alert(
    alert_id: int,
    current_user: UserInDB = Depends(get_current_user),
):
    if AlertRepository.delete(alert_id):
        OperationLogRepository.log(
            current_user.username, "delete_alert", f"Deleted alert: {alert_id}"
        )
        return {"success": True, "message": "删除成功"}
    return {"success": False, "message": "删除失败"}


@router.post("/api/alerts/test")
async def test_alert(
    request: Request,
    current_user: UserInDB = Depends(get_current_user),
):
    body = await request.json()
    test_email = body.get("email", "")
    try:
        OperationLogRepository.log(
            current_user.username, "test_alert", f"Test alert sent to: {test_email}"
        )
        return {"success": True, "message": "测试邮件已发送（模拟）"}
    except Exception as e:
        return {"success": False, "message": _api_error(e, "测试失败，请稍后重试")}
