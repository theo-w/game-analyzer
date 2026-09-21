"""Core data and reporting API routes."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Request

from src.data_catalog import (
    derive_data_catalog,
    enrich_catalog_from_context,
    restrict_catalog_to_dataset,
)
from src.data_resolution import resolve_user_dataset
from src.mvp_data import (
    build_mvp_report_payload,
    filter_records,
    get_mvp_analysis,
    mvp_validation_passed,
)
from src.services.llm_client import llm_is_configured
from src.services.llm_mvp_summary import summarize_mvp_with_llm
from src.web_common import get_current_user

router = APIRouter(tags=["data"])


from src.analytics_engine import run_business_intelligence_report


def _filter_catalog_for_user(
    comments: List[dict],
    metrics: List[dict],
    username: str,
) -> dict:
    try:
        from src.services.game_intel import GameLibraryRepository

        if hasattr(GameLibraryRepository, "purge_noise_games"):
            GameLibraryRepository.purge_noise_games(username=username)
    except Exception:
        pass
    catalog = derive_data_catalog(comments or [], metrics or [])
    return enrich_catalog_from_context(catalog, username=username)


async def _resolve_user(request: Request, token: Optional[str]):
    return await get_current_user(request, token)


@router.get("/api/comments")
async def get_comments(
    request: Request,
    token: Optional[str] = Query(None),
    product: Optional[str] = Query(None),
    products: Optional[str] = Query(None),
    product_ids: Optional[str] = Query(None),
    time_period: Optional[str] = Query(None),
    platform: Optional[str] = Query(None),
    data_source: Optional[str] = Query(None),
    sentiment: Optional[str] = Query(None),
):
    current_user = await _resolve_user(request, token)
    source, comments, metrics = resolve_user_dataset(current_user.username)
    product_list = None
    raw_products = products or product_ids
    if raw_products:
        product_list = [p.strip() for p in raw_products.split(",") if p.strip()]
    filtered_comments, _ = filter_records(
        comments or [],
        [],
        product=product,
        products=product_list,
        data_source=data_source,
        platform=platform,
        time_period=time_period,
        sentiment=sentiment,
    )
    catalog = restrict_catalog_to_dataset(
        _filter_catalog_for_user(comments or [], metrics or [], current_user.username),
        comments or [],
        metrics or [],
    )
    return {
        "success": True,
        "data": filtered_comments,
        "total": len(comments or []),
        "filtered_count": len(filtered_comments),
        "source": source,
        "catalog": catalog,
        "filters": {
            "product": product,
            "products": raw_products,
            "time_period": time_period,
            "platform": platform or data_source,
            "sentiment": sentiment,
        },
    }


@router.get("/api/metrics")
async def get_metrics(
    request: Request,
    token: Optional[str] = Query(None),
    product: Optional[str] = Query(None),
    products: Optional[str] = Query(None),
    product_ids: Optional[str] = Query(None),
    time_period: Optional[str] = Query(None),
    platform: Optional[str] = Query(None),
    data_source: Optional[str] = Query(None),
):
    current_user = await _resolve_user(request, token)
    source, comments, metrics = resolve_user_dataset(current_user.username)
    product_list = None
    raw_products = products or product_ids
    if raw_products:
        product_list = [p.strip() for p in raw_products.split(",") if p.strip()]
    _, filtered_metrics = filter_records(
        [],
        metrics or [],
        product=product,
        products=product_list,
        data_source=data_source,
        platform=platform,
        time_period=time_period,
    )
    catalog = restrict_catalog_to_dataset(
        _filter_catalog_for_user(comments or [], metrics or [], current_user.username),
        comments or [],
        metrics or [],
    )
    return {
        "success": True,
        "data": filtered_metrics,
        "total": len(metrics or []),
        "filtered_count": len(filtered_metrics),
        "source": source,
        "catalog": catalog,
        "filters": {
            "product": product,
            "products": raw_products,
            "time_period": time_period,
            "platform": platform or data_source,
        },
    }


@router.get("/api/report")
async def get_report(
    request: Request,
    token: Optional[str] = Query(None),
    product: Optional[str] = Query(None),
    time_period: Optional[str] = Query(None),
    data_source: Optional[str] = Query(None),
    products: Optional[str] = Query(None),
    include_llm_summary: bool = Query(False),
):
    current_user = await _resolve_user(request, token)
    source, comments, metrics = resolve_user_dataset(current_user.username)

    product_list = products.split(",") if products else None
    if product_list and current_user.games_limit > 0 and len(product_list) > current_user.games_limit:
        raise HTTPException(
            status_code=403,
            detail=f"超出游戏数量限制（当前计划限制：{current_user.games_limit}款）",
        )

    filtered_comments, filtered_metrics = filter_records(
        comments or [],
        metrics or [],
        product=product,
        products=product_list,
        data_source=data_source,
        time_period=time_period,
    )

    if source == "mvp_steam" and mvp_validation_passed():
        report = build_mvp_report_payload(filtered_comments, filtered_metrics)
        analysis_mode = "mvp_steam_verified"
        if include_llm_summary and llm_is_configured():
            analysis = get_mvp_analysis()
            if analysis:
                llm_layer = await summarize_mvp_with_llm(analysis)
                if llm_layer:
                    report["executive_summary"] = llm_layer["executive_summary"]
                    report["llm_summary"] = llm_layer
                    analysis_mode = "mvp_steam_verified_llm_summary"
    else:
        report = run_business_intelligence_report(filtered_comments, filtered_metrics)
        analysis_mode = "legacy_template"

    return {
        "success": True,
        "data": report,
        "comments": filtered_comments,
        "metrics": filtered_metrics,
        "source": source,
        "analysis_mode": analysis_mode,
        "validation_passed": mvp_validation_passed() if source == "mvp_steam" else None,
        "filters": {
            "product": product,
            "products": products,
            "time_period": time_period,
            "data_source": data_source,
        },
    }
