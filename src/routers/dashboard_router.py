"""Dashboard config CRUD and report sharing."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Request

from database import DashboardConfigRepository, OperationLogRepository, SharedReportRepository
from src.auth import UserInDB
from src.web_common import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["dashboard"])

_IS_PRODUCTION = os.getenv("APP_ENV", "development").lower() == "production"


def _api_error(exc: Exception, user_msg: str = "操作失败，请稍后重试") -> str:
    logger.exception("Dashboard API error: %s", exc)
    return user_msg if _IS_PRODUCTION else str(exc)


def _sanitize_report_fields(node) -> None:
    """递归净化 report_data 中所有 html/html_excerpt 字符串字段（原地修改）。"""
    from src.html_sanitizer import sanitize_rich_html

    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, str) and key in ("html", "html_excerpt"):
                node[key] = sanitize_rich_html(value)
            else:
                _sanitize_report_fields(value)
    elif isinstance(node, list):
        for item in node:
            _sanitize_report_fields(item)


# ---------------------------------------------------------------------------
# Dashboard config
# ---------------------------------------------------------------------------

@router.get("/api/dashboard/list")
async def list_dashboards(current_user: UserInDB = Depends(get_current_user)):
    dashboards = DashboardConfigRepository.get_all(current_user.username)
    for d in dashboards:
        if "layout" in d and isinstance(d["layout"], str):
            d["layout"] = json.loads(d["layout"])
    return {"success": True, "dashboards": dashboards}


@router.get("/api/dashboard/{dashboard_id}")
async def get_dashboard(
    dashboard_id: int,
    current_user: UserInDB = Depends(get_current_user),
):
    dashboard = DashboardConfigRepository.get_by_id(dashboard_id)
    if not dashboard:
        return {"success": False, "message": "仪表盘不存在"}
    if dashboard["username"] != current_user.username:
        return {"success": False, "message": "无权限访问此仪表盘"}
    if "layout" in dashboard and isinstance(dashboard["layout"], str):
        dashboard["layout"] = json.loads(dashboard["layout"])
    return {"success": True, "dashboard": dashboard}


@router.post("/api/dashboard/save")
async def save_dashboard(
    request: Request,
    current_user: UserInDB = Depends(get_current_user),
):
    body = await request.json()
    name = body.get("name")
    layout = body.get("layout")
    is_default = body.get("is_default", 0)

    if not name or not layout:
        return {"success": False, "message": "仪表盘名称和布局配置不能为空"}

    dashboard_id = DashboardConfigRepository.create(
        current_user.username, name, layout, is_default
    )
    if dashboard_id:
        OperationLogRepository.log(
            current_user.username, "save_dashboard", f"Saved dashboard: {name}"
        )
        return {"success": True, "dashboard_id": dashboard_id}
    return {"success": False, "message": "保存失败"}


@router.put("/api/dashboard/{dashboard_id}")
async def update_dashboard(
    dashboard_id: int,
    request: Request,
    current_user: UserInDB = Depends(get_current_user),
):
    dashboard = DashboardConfigRepository.get_by_id(dashboard_id)
    if not dashboard:
        return {"success": False, "message": "仪表盘不存在"}
    if dashboard["username"] != current_user.username:
        return {"success": False, "message": "无权限修改此仪表盘"}

    body = await request.json()
    name = body.get("name", dashboard["name"])
    layout = body.get("layout", json.loads(dashboard["layout"]))
    is_default = body.get("is_default", dashboard["is_default"])

    if DashboardConfigRepository.update(dashboard_id, name, layout, is_default):
        OperationLogRepository.log(
            current_user.username, "update_dashboard", f"Updated dashboard: {name}"
        )
        return {"success": True}
    return {"success": False, "message": "更新失败"}


@router.delete("/api/dashboard/{dashboard_id}")
async def delete_dashboard(
    dashboard_id: int,
    current_user: UserInDB = Depends(get_current_user),
):
    dashboard = DashboardConfigRepository.get_by_id(dashboard_id)
    if not dashboard:
        return {"success": False, "message": "仪表盘不存在"}
    if dashboard["username"] != current_user.username:
        return {"success": False, "message": "无权限删除此仪表盘"}

    if DashboardConfigRepository.delete(dashboard_id):
        OperationLogRepository.log(
            current_user.username, "delete_dashboard", f"Deleted dashboard: {dashboard_id}"
        )
        return {"success": True}
    return {"success": False, "message": "删除失败"}


# ---------------------------------------------------------------------------
# Report sharing
# ---------------------------------------------------------------------------

@router.post("/api/report/share")
async def share_report(
    request: Request,
    current_user: UserInDB = Depends(get_current_user),
):
    body = await request.json()
    report_type = body.get("report_type", "daily")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", str(report_type or "")):
        report_type = "custom"
    report_data = body.get("report_data", {})
    expires_hours = body.get("expires_hours", 24)

    # 分享内容是公开端点渲染的用户输入，落库前对富文本字段做白名单净化
    _sanitize_report_fields(report_data)

    expires_at = (
        (datetime.now(timezone.utc) + timedelta(hours=expires_hours)).isoformat()
        if expires_hours > 0
        else None
    )

    share_token = SharedReportRepository.create_share(
        current_user.username, report_type, report_data, expires_at
    )

    if share_token:
        base = str(request.base_url).rstrip("/")
        share_url = f"{base}/shared/{share_token}"
        OperationLogRepository.log(
            current_user.username, "share_report", f"Shared report: {report_type}"
        )
        try:
            from src.services.analysis_archive import archive_report_run
            from src.data_resolution import get_user_comments_data, get_user_metrics_data

            product_ids = report_data.get("products") or report_data.get("product_ids") or []
            if isinstance(product_ids, str):
                product_ids = [p.strip() for p in product_ids.split(",") if p.strip()]
            archive_report_run(
                username=current_user.username,
                report_type=report_type,
                product_ids=product_ids,
                metrics=get_user_metrics_data(current_user.username),
                comments=get_user_comments_data(current_user.username),
                share_token=share_token,
            )
        except Exception:
            pass
        return {"success": True, "share_token": share_token, "share_url": share_url}

    return {"success": False, "message": "分享失败"}


@router.get("/api/report/shared/{share_token}")
async def get_shared_report(share_token: str):
    """Public endpoint — no auth required."""
    report = SharedReportRepository.get_by_token(share_token)
    if not report:
        return {"success": False, "message": "分享链接已过期或不存在"}

    report_data = (
        json.loads(report["report_data"])
        if isinstance(report["report_data"], str)
        else report["report_data"]
    )

    return {
        "success": True,
        "report": {
            "report_type": report["report_type"],
            "report_data": report_data,
            "created_at": report["created_at"],
            "expires_at": report["expires_at"],
        },
    }


@router.get("/api/report/history")
async def get_report_history(current_user: UserInDB = Depends(get_current_user)):
    reports = SharedReportRepository.get_user_reports(current_user.username)
    for r in reports:
        if "report_data" in r and isinstance(r["report_data"], str):
            r["report_data"] = json.loads(r["report_data"])
    return {"success": True, "reports": reports}
