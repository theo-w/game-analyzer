"""Reports router — /api/reports/* endpoints."""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse

from src.database import OperationLogRepository
from src.web_common import get_current_user
from src.data_resolution import get_user_comments_data, get_user_metrics_data
from src.services.report_helpers import (
    analyze_trends,
    generate_html_period_report,
    generate_product_details,
    generate_recommendations,
    generate_report_summary,
)
from src.report_generator import send_report_email
from src.report_scheduler import report_scheduler

logger = logging.getLogger(__name__)

router = APIRouter(tags=["reports"])


# ── helpers ──────────────────────────────────────────────────────────────────

def _period_report_html(username: str, report_type: str, product_ids: Optional[str]) -> str:
    metrics = get_user_metrics_data(username)
    products = [p.strip() for p in product_ids.split(",") if p.strip()] if product_ids else None
    return generate_html_period_report(report_type, metrics, products)


def _archive_period_report(
    username: str,
    report_type: str,
    product_ids: Optional[str],
    report_html: str,
) -> Optional[str]:
    from src.services.analysis_archive import archive_report_run

    selected = [p.strip() for p in (product_ids or "").split(",") if p.strip()]
    if not selected:
        metrics = get_user_metrics_data(username)
        selected = sorted({str(m.get("product")) for m in metrics if m.get("product")})[:5]
    comments = get_user_comments_data(username)
    metrics = get_user_metrics_data(username)
    if not selected:
        return None
    filtered_metrics = [m for m in metrics if str(m.get("product")) in selected]
    filtered_comments = [c for c in comments if str(c.get("product") or c.get("产品")) in selected]
    return archive_report_run(
        username=username,
        report_type=report_type,
        product_ids=selected,
        metrics=filtered_metrics,
        comments=filtered_comments,
        html_excerpt=report_html[:4000],
    )


# ── routes ────────────────────────────────────────────────────────────────────

@router.get("/api/reports/generate")
async def generate_report(
    current_user=Depends(get_current_user),
    report_type: str = Query("weekly"),
    product_ids: Optional[str] = Query(None),
    time_period: Optional[str] = Query(None),
):
    selected_products = product_ids.split(",") if product_ids else []

    metrics_data = get_user_metrics_data(current_user.username)
    comments_data = get_user_comments_data(current_user.username)

    if time_period:
        metrics_data = [m for m in metrics_data if m.get("cycle") == time_period]
        comments_data = [c for c in comments_data if c.get("cycle") == time_period]

    metrics_data = [m for m in metrics_data if m.get("product") in selected_products]
    comments_data = [c for c in comments_data if c.get("product") in selected_products]

    report_data = {
        "report_type": report_type,
        "generated_at": datetime.now().isoformat(),
        "products": selected_products,
        "summary": generate_report_summary(metrics_data, comments_data, report_type),
        "product_details": generate_product_details(metrics_data),
        "trends": analyze_trends(metrics_data),
        "recommendations": generate_recommendations(metrics_data, comments_data),
    }

    OperationLogRepository.log(current_user.username, "generate_report", f"Generated {report_type} report")
    return {"success": True, "data": report_data}


@router.post("/api/reports/send")
async def send_report_email(
    current_user=Depends(get_current_user),
    report_type: str = Query("weekly"),
    product_ids: Optional[str] = Query(None),
    time_period: Optional[str] = Query(None),
    to_email: Optional[str] = Query(None),
):
    """发送报告邮件"""
    if not to_email:
        to_email = current_user.email

    selected_products = product_ids.split(",") if product_ids else []

    success = await report_scheduler.send_report_email(to_email, report_type, selected_products, time_period)

    if success:
        OperationLogRepository.log(current_user.username, "send_report", f"Sent {report_type} report to {to_email}")
        return {"success": True, "message": f"报告已发送到 {to_email}"}
    else:
        return {"success": False, "message": "发送失败，请检查SMTP配置"}


@router.post("/api/reports/schedule")
async def schedule_report(
    current_user=Depends(get_current_user),
    schedule_type: str = Query(...),
    to_email: str = Query(...),
    product_ids: Optional[str] = Query(None),
    hour: int = Query(9),
):
    """创建定时报告任务"""
    selected_products = product_ids.split(",") if product_ids else []

    if schedule_type == "daily":
        await report_scheduler.schedule_daily_report(to_email, selected_products, hour)
    elif schedule_type == "weekly":
        await report_scheduler.schedule_weekly_report(to_email, selected_products, weekday=0, hour=hour)
    elif schedule_type == "monthly":
        await report_scheduler.schedule_monthly_report(to_email, selected_products, day=1, hour=hour)
    else:
        raise HTTPException(status_code=400, detail="不支持的调度类型")

    OperationLogRepository.log(current_user.username, "schedule_report", f"Scheduled {schedule_type} report to {to_email}")
    return {"success": True, "message": f"{schedule_type}报告已设置定时推送"}


@router.delete("/api/reports/schedule")
async def cancel_scheduled_report(
    current_user=Depends(get_current_user),
    schedule_type: str = Query(...),
    to_email: str = Query(...),
):
    """取消定时报告任务"""
    task_name = f"{schedule_type}_{to_email}"
    success = report_scheduler.cancel_scheduled_task(task_name)

    if success:
        OperationLogRepository.log(current_user.username, "cancel_report", f"Cancelled {schedule_type} report for {to_email}")
        return {"success": True, "message": "定时任务已取消"}
    else:
        return {"success": False, "message": "未找到该定时任务"}


@router.get("/api/reports/schedule/list")
async def get_scheduled_reports(current_user=Depends(get_current_user)):
    """获取所有定时报告任务"""
    tasks = report_scheduler.get_scheduled_tasks()
    return {"success": True, "tasks": tasks}


@router.get("/api/reports/daily")
async def generate_daily_report(
    current_user=Depends(get_current_user),
    product_ids: Optional[str] = Query(None),
    date: Optional[str] = Query(None),
):
    try:
        report_html = _period_report_html(current_user.username, "daily", product_ids)
        _archive_period_report(current_user.username, "daily", product_ids, report_html)
        return HTMLResponse(content=report_html, media_type="text/html")
    except Exception as e:
        logger.exception("Daily report error: %s", e)
        return {"success": False, "message": str(e)}


@router.get("/api/reports/weekly")
async def generate_weekly_report(
    current_user=Depends(get_current_user),
    product_ids: Optional[str] = Query(None),
    week_start: Optional[str] = Query(None),
):
    try:
        report_html = _period_report_html(current_user.username, "weekly", product_ids)
        _archive_period_report(current_user.username, "weekly", product_ids, report_html)
        return HTMLResponse(content=report_html, media_type="text/html")
    except Exception as e:
        logger.exception("Weekly report error: %s", e)
        return {"success": False, "message": str(e)}


@router.get("/api/reports/monthly")
async def generate_monthly_report(
    current_user=Depends(get_current_user),
    product_ids: Optional[str] = Query(None),
    month: Optional[str] = Query(None),
):
    try:
        report_html = _period_report_html(current_user.username, "monthly", product_ids)
        _archive_period_report(current_user.username, "monthly", product_ids, report_html)
        return HTMLResponse(content=report_html, media_type="text/html")
    except Exception as e:
        logger.exception("Monthly report error: %s", e)
        return {"success": False, "message": str(e)}


@router.post("/api/reports/send-generated")
async def send_report(
    current_user=Depends(get_current_user),
    report_type: str = Query("daily"),
    product_ids: Optional[str] = Query(None),
    to_email: str = Query(None),
):
    if not to_email:
        raise HTTPException(status_code=400, detail="Email address is required")

    try:
        if report_type == "daily":
            report_html = _period_report_html(current_user.username, "daily", product_ids)
            subject = "【游戏数据分析引擎】日报"
        elif report_type == "weekly":
            report_html = _period_report_html(current_user.username, "weekly", product_ids)
            subject = "【游戏数据分析引擎】周报"
        elif report_type == "monthly":
            report_html = _period_report_html(current_user.username, "monthly", product_ids)
            subject = "【游戏数据分析引擎】月报"
        else:
            return {"success": False, "message": "Invalid report type"}

        result = send_report_email(report_html, to_email, subject)
        return result
    except Exception as e:
        logger.exception("Send report error: %s", e)
        return {"success": False, "message": str(e)}


@router.get("/api/reports/types")
async def get_report_types(current_user=Depends(get_current_user)):
    return {
        "success": True,
        "types": [
            {"id": "daily", "name": "日报", "description": "每日数据汇总报告"},
            {"id": "weekly", "name": "周报", "description": "每周数据汇总及同比分析"},
            {"id": "monthly", "name": "月报", "description": "每月数据汇总及同比/环比分析"},
        ],
    }
