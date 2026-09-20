"""Data config, collect & export router — /api/data/config/*, /api/data/collect/*, /api/export/*"""
import csv
import logging
from datetime import datetime
from io import BytesIO, StringIO
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from src.data_collector import data_collector
from src.database import ImportedDataRepository, OperationLogRepository
from src.web_common import get_current_user
from src.data_resolution import get_user_comments_data, get_user_metrics_data
from src.web_common import mask_config_secrets
from src.web_constants import AVAILABLE_PRODUCTS

logger = logging.getLogger(__name__)

router = APIRouter(tags=["data-config"])


# ── /api/data/config ──────────────────────────────────────────────────────────

@router.get("/api/data/config/status")
async def get_data_config_status(current_user=Depends(get_current_user)):
    """获取数据采集配置状态"""
    config_status = data_collector.validate_api_keys()
    instructions = data_collector.get_configuration_instructions()

    return {
        "success": True,
        "configured": {
            "steam": config_status["steam"],
            "google_play": config_status["google_play"],
            "app_store": config_status["app_store"],
        },
        "instructions": instructions,
    }


@router.get("/api/data/config")
async def get_data_source_config(current_user=Depends(get_current_user)):
    """获取所有数据源配置"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="只有管理员可以查看数据源配置")

    from src.database import DataSourceConfigRepository
    configs = DataSourceConfigRepository.get_all()

    return {"success": True, "configs": [mask_config_secrets(config) for config in configs]}


@router.put("/api/data/config/{platform}")
async def update_data_source_config(
    platform: str,
    request: Request,
    current_user=Depends(get_current_user),
):
    """更新数据源配置"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="只有管理员可以更新数据源配置")

    if platform not in ["steam", "google_play", "app_store"]:
        raise HTTPException(status_code=400, detail="不支持的平台")

    body = await request.json()

    from src.database import DataSourceConfigRepository
    success = DataSourceConfigRepository.create_or_update(platform, body)

    if success:
        data_collector._load_config_from_db()
        OperationLogRepository.log(current_user.username, "update_data_source_config", f"Updated config for {platform}")
        return {"success": True, "message": f"{platform} 配置更新成功"}
    else:
        return {"success": False, "message": "配置更新失败"}


@router.delete("/api/data/config/{platform}")
async def delete_data_source_config(
    platform: str,
    current_user=Depends(get_current_user),
):
    """删除数据源配置"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="只有管理员可以删除数据源配置")

    from src.database import DataSourceConfigRepository
    success = DataSourceConfigRepository.delete(platform)

    if success:
        data_collector._load_config_from_db()
        OperationLogRepository.log(current_user.username, "delete_data_source_config", f"Deleted config for {platform}")
        return {"success": True, "message": f"{platform} 配置删除成功"}
    else:
        return {"success": False, "message": "配置删除失败"}


# ── /api/data/collect ─────────────────────────────────────────────────────────

@router.get("/api/data/collect/all")
async def collect_all_data(
    current_user=Depends(get_current_user),
    product_ids: Optional[str] = Query(None),
):
    """批量采集所有产品数据"""
    products = AVAILABLE_PRODUCTS
    if product_ids:
        selected_ids = product_ids.split(",")
        products = [p for p in products if p["id"] in selected_ids]

    # 给每个产品添加平台信息
    platforms = ["steam", "google_play", "app_store"]
    products_with_platform = []
    for i, product in enumerate(products):
        products_with_platform.append({
            **product,
            "platform": platforms[i % len(platforms)],
            "app_id": f"{product['id']}_id",
        })

    results = await data_collector.collect_all_products(products_with_platform)

    success_count = sum(1 for r in results if r.get("success", False) or r.get("mock", False))

    total_cached_metrics = 0
    total_cached_comments = 0

    for i, result in enumerate(results):
        if result.get("success") or result.get("mock"):
            product = products[i] if i < len(products) else {}
            product_name = product.get("name", product.get("id", "unknown"))
            platform = result.get("platform", "unknown")

            metrics_data = result.get("metrics", {})
            cached_metrics = []

            for key, value in metrics_data.items():
                cached_metrics.append({
                    "product": product_name,
                    "platform": platform,
                    "metric": key,
                    "值": float(value) if isinstance(value, (int, float)) else 0.0,
                    "date": datetime.now().strftime("%Y-%m-%d"),
                })

            cached_comments = []
            if "reviews" in result:
                for review in result["reviews"]:
                    cached_comments.append({
                        "product": product_name,
                        "platform": platform,
                        "review_id": review.get("id"),
                        "rating": review.get("rating"),
                        "title": review.get("title"),
                        "content": review.get("content"),
                        "author": review.get("author"),
                        "date": review.get("date"),
                        "helpful_count": review.get("helpful_count", 0),
                    })

            if cached_metrics:
                saved = ImportedDataRepository.save_cached_metrics(cached_metrics)
                total_cached_metrics += saved
            if cached_comments:
                saved = ImportedDataRepository.save_cached_comments(cached_comments)
                total_cached_comments += saved

    OperationLogRepository.log(
        current_user.username,
        "data_collection",
        f"批量采集{len(products)}个产品数据 - 成功: {success_count}",
        None,
    )

    return {
        "success": True,
        "total": len(products),
        "successful": success_count,
        "results": results,
        "cached": {
            "metrics": total_cached_metrics,
            "comments": total_cached_comments,
        },
    }


@router.get("/api/data/collect/{platform}")
async def collect_platform_data(
    platform: str,
    current_user=Depends(get_current_user),
    identifier: Optional[str] = Query(None),
):
    """手动触发特定平台数据采集"""
    platforms = {
        "steam": data_collector.fetch_steam_data,
        "google_play": data_collector.fetch_google_play_data,
        "app_store": data_collector.fetch_app_store_data,
    }

    if platform not in platforms:
        raise HTTPException(status_code=400, detail="不支持的平台")

    collector_func = platforms[platform]
    result = await collector_func(identifier)

    cached_metrics = []
    cached_comments = []

    if result.get("success") or result.get("mock"):
        product_name = identifier or platform
        metrics_data = result.get("metrics", {})

        for key, value in metrics_data.items():
            cached_metrics.append({
                "product": product_name,
                "platform": platform,
                "metric": key,
                "值": float(value) if isinstance(value, (int, float)) else 0.0,
                "date": datetime.now().strftime("%Y-%m-%d"),
            })

        if "reviews" in result:
            for review in result["reviews"]:
                cached_comments.append({
                    "product": product_name,
                    "platform": platform,
                    "review_id": review.get("id"),
                    "rating": review.get("rating"),
                    "title": review.get("title"),
                    "content": review.get("content"),
                    "author": review.get("author"),
                    "date": review.get("date"),
                    "helpful_count": review.get("helpful_count", 0),
                })

        if cached_metrics:
            ImportedDataRepository.save_cached_metrics(cached_metrics)
        if cached_comments:
            ImportedDataRepository.save_cached_comments(cached_comments)

    OperationLogRepository.log(
        current_user.username,
        "data_collection",
        f"采集{platform}数据: {identifier or 'all'} - {'成功' if result.get('success') else '使用模拟数据'}",
        None,
    )

    return {
        "success": True,
        "data": result,
        "cached": {
            "metrics": len(cached_metrics),
            "comments": len(cached_comments),
        },
    }


# ── /api/export ───────────────────────────────────────────────────────────────

@router.get("/api/export/csv")
async def export_csv(
    current_user=Depends(get_current_user),
    product_ids: Optional[str] = Query(None),
    time_period: Optional[str] = Query(None),
    data_source: Optional[str] = Query(None),
):
    metrics_data = get_user_metrics_data(current_user.username)

    selected_products = product_ids.split(",") if product_ids else []
    if time_period:
        metrics_data = [m for m in metrics_data if m.get("cycle") == time_period]
    metrics_data = [m for m in metrics_data if m.get("product") in selected_products]

    output = StringIO()
    if metrics_data:
        all_fields = set()
        for item in metrics_data:
            all_fields.update(item.keys())
        fieldnames = list(all_fields)
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(metrics_data)

    csv_content = output.getvalue()

    return StreamingResponse(
        StringIO(csv_content),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@router.get("/api/export/excel")
async def export_excel(
    current_user=Depends(get_current_user),
    product_ids: Optional[str] = Query(None),
    time_period: Optional[str] = Query(None),
    data_source: Optional[str] = Query(None),
    fields: Optional[str] = Query(None),
):
    metrics_data = get_user_metrics_data(current_user.username)
    comments_data = get_user_comments_data(current_user.username)

    selected_products = product_ids.split(",") if product_ids else []
    if time_period:
        metrics_data = [m for m in metrics_data if m.get("cycle") == time_period]
        comments_data = [c for c in comments_data if c.get("cycle") == time_period]
    metrics_data = [m for m in metrics_data if m.get("product") in selected_products]
    comments_data = [c for c in comments_data if c.get("product") in selected_products]

    if fields:
        selected_fields = fields.split(",")
        metrics_data = [
            {k: v for k, v in m.items() if k in selected_fields or k in ["product", "cycle"]}
            for m in metrics_data
        ]
        comments_data = [
            {k: v for k, v in c.items() if k in selected_fields or k in ["product", "cycle"]}
            for c in comments_data
        ]

    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for product in selected_products:
            product_metrics = [m for m in metrics_data if m.get("product") == product]
            product_comments = [c for c in comments_data if c.get("product") == product]

            if product_metrics:
                df_pm = pd.DataFrame(product_metrics)
                sheet_name = f"{product[:10]}_指标"[:31]
                df_pm.to_excel(writer, sheet_name=sheet_name, index=False)

            if product_comments:
                df_pc = pd.DataFrame(product_comments)
                sheet_name = f"{product[:10]}_评论"[:31]
                df_pc.to_excel(writer, sheet_name=sheet_name, index=False)

        if metrics_data:
            df_metrics = pd.DataFrame(metrics_data)
            df_metrics.to_excel(writer, sheet_name="汇总_指标", index=False)
        if comments_data:
            df_comments = pd.DataFrame(comments_data)
            df_comments.to_excel(writer, sheet_name="汇总_评论", index=False)

        summary_data = []
        for product in selected_products:
            product_metrics = [m for m in metrics_data if m.get("product") == product]
            if product_metrics:
                summary_data.append({
                    "产品": product,
                    "数据条数": len(product_metrics),
                    "平均下载量": sum(m.get("downloads", 0) for m in product_metrics) / len(product_metrics),
                    "总收入": sum(m.get("revenue", 0) for m in product_metrics),
                    "平均评分": sum(m.get("rating", 0) for m in product_metrics) / len(product_metrics),
                })

        if summary_data:
            df_summary = pd.DataFrame(summary_data)
            df_summary.to_excel(writer, sheet_name="统计摘要", index=False)

    output.seek(0)

    filename = f"game_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )
