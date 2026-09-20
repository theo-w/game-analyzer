"""AI analysis, simulated advanced analytics, and realtime WebSocket."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from src.advanced_analytics import get_advanced_analytics
from src.auth import LLM_CONFIG, LLM_PROVIDERS
from src.api_meta import with_simulated
from src.data_resolution import (
    get_user_comments_data,
    get_user_metrics_data,
    resolve_user_data_source,
)
from src.services.engagement_funnel import (
    build_path_distribution_from_comments,
    data_basis_label as engagement_basis_label,
    resolve_funnel_for_product,
    resolve_journey_for_product,
)
from src.services.real_metrics_analytics import (
    resolve_cohort_for_product,
    resolve_realtime_for_product,
)
from src.mvp_data import get_mvp_analysis, mvp_validation_passed, product_matches
from src.services.legacy_ai_report import (
    generate_action_plan,
    generate_issues_diagnosis,
    generate_new_product_trends,
    generate_optimization_suggestions,
    generate_product_trends,
)
from src.services.product_name_resolver import build_product_name_map, label_for_products
from src.services.llm_client import llm_is_configured, parse_json_from_llm, complete_prompt
from src.services.llm_mvp_summary import summarize_mvp_with_llm
from src.web_common import get_current_user

router = APIRouter(tags=["analytics"])

analytics = get_advanced_analytics()
active_connections: list = []


def _parse_product_ids(product_ids: Optional[str]) -> List[str]:
    if not product_ids or not str(product_ids).strip():
        return ["all"]
    parts = [p.strip() for p in str(product_ids).split(",") if p.strip()]
    return parts or ["all"]


def _filter_metrics_by_products(metrics_data: list, products: List[str]) -> list:
    if not products or products == ["all"]:
        return metrics_data
    return [
        row
        for row in metrics_data
        if any(product_matches(row, product) for product in products)
    ]


def _advanced_data_basis(username: str) -> str:
    source = resolve_user_data_source(username) or "empty"
    if source in {"mvp_steam", "taptap_public", "google_play_public", "mvp_multi"}:
        return source
    if source == "imported":
        return "imported"
    return "mock_data"


def _annotate_advanced_response(
    payload: Dict,
    *,
    simulated: bool,
    basis: str,
    note: str = "",
) -> Dict:
    enriched = {
        **payload,
        "simulated": simulated,
        "data_basis": basis,
        "data_basis_label": engagement_basis_label(basis),
    }
    if note:
        enriched["data_note"] = note
    return enriched


async def generate_ai_report_with_llm(products: List[str], product_names: dict, time_label: str):
    selected = [product_names[p] for p in products if p in product_names]
    product_label = ", ".join(selected) if selected else "全部产品"
    prompt = f"""你是一位专业的游戏数据分析顾问。请基于以下信息生成一份游戏数据分析报告：

产品：{product_label}
时间周期：{time_label}

请生成以下内容的JSON格式报告（只需要JSON，不要其他内容）：
{{
    "summary": "总体分析摘要，100字左右",
    "product_trends": [
        {{"product": "产品名", "rating": "良好/中等/较差", "trend": "趋势描述", "change": "+5%"}}
    ],
    "action_plan": {{
        "short_term": ["行动项1", "行动项2", "行动项3"],
        "medium_term": ["行动项1", "行动项2", "行动项3"],
        "long_term": ["行动项1", "行动项2", "行动项3"]
    }}
}}"""
    try:
        response_text = await complete_prompt(prompt)
        report_data = parse_json_from_llm(response_text)
        if not report_data:
            return None
        provider = LLM_CONFIG["provider"]
        report_data["using_llm"] = True
        report_data["llm_provider"] = LLM_PROVIDERS.get(provider, {}).get("name", provider)
        report_data["llm_model"] = LLM_CONFIG.get("model")
        report_data["llm_configured"] = True
        return report_data
    except Exception as exc:
        print(f"LLM调用失败: {exc}")
        return None


@router.websocket("/ws/realtime")
async def websocket_endpoint(websocket: WebSocket, token: Optional[str] = None, product_ids: Optional[str] = None):
    if not token:
        await websocket.close(code=1008, reason="Authentication required")
        return
    
    try:
        current_user = await get_current_user(token)
    except Exception:
        await websocket.close(code=1008, reason="Invalid token")
        return
    
    await websocket.accept()
    try:
        await websocket.send_json({
            "success": False,
            "code": "feature_disabled",
            "message": "实时营收曲线依赖内部业务数据（埋点/经营数据），外部公开数据无法验证，已下线。",
        })
        await websocket.close(code=1000)
    except Exception:
        pass
    if websocket in active_connections:
        active_connections.remove(websocket)


# --- AI analysis ---

@router.get("/api/ai_analysis")
async def get_ai_analysis(
    token: Optional[str] = Query(None),
    product_ids: Optional[str] = Query(None), 
    time_period: Optional[str] = Query(None), 
    data_source: Optional[str] = Query(None)
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)
    source = resolve_user_data_source(current_user.username)

    products = _parse_product_ids(product_ids)

    if source == "mvp_steam" and mvp_validation_passed():
        analysis = get_mvp_analysis() or {}
        strategy = analysis.get("ai_strategy") or {}
        rule_summary = strategy.get("opportunity_summary") or analysis.get("summary") or ""
        product_reports = list(analysis.get("product_reports") or [])
        if products != ["all"]:
            product_reports = [
                report
                for report in product_reports
                if any(product_matches(report, product) for product in products)
            ]
            peer = strategy.get("peer_comparison") or []
            strategy = {
                **strategy,
                "peer_comparison": [
                    row
                    for row in peer
                    if any(
                        product_matches(
                            {
                                "product": row.get("product")
                                or row.get("product_id")
                                or row.get("product_name")
                            },
                            product,
                        )
                        for product in products
                    )
                ],
            }
            if product_reports:
                names = label_for_products(
                    products, build_product_name_map(products, username=current_user.username)
                )
                rule_summary = f"本次分析覆盖 {names}，共 {len(product_reports)} 款产品（基于 MVP 抓取评论）。"
        data = {
            "format": "mvp_steam",
            "summary": rule_summary,
            "rule_based_summary": rule_summary,
            "product_reports": product_reports,
            "ai_strategy": strategy,
            "peer_comparison": strategy.get("peer_comparison", []),
            "user_needs": strategy.get("user_needs", []),
            "prioritized_actions": strategy.get("prioritized_actions", []),
            "using_llm": False,
            "llm_configured": llm_is_configured(),
        }
        llm_layer = await summarize_mvp_with_llm(analysis)
        analysis_mode = "mvp_steam_verified"
        llm_error = None
        if llm_layer:
            data["summary"] = llm_layer["executive_summary"]
            data["using_llm"] = True
            data["llm_provider"] = llm_layer.get("llm_provider")
            data["llm_model"] = llm_layer.get("llm_model")
            data["grounded_in"] = llm_layer.get("grounded_in")
            analysis_mode = "mvp_steam_verified_llm_summary"
        elif llm_is_configured():
            llm_error = (
                "已配置本地/云端 LLM，但生成摘要失败。请确认 Ollama 已启动、模型名称与设置一致，"
                "且 endpoint 为 http://localhost:11434（不要填 /api/generate 路径）。"
            )
        return {
            "success": True,
            "source": source,
            "analysis_mode": analysis_mode,
            "validation_passed": True,
            "llm_error": llm_error,
            "data": data,
        }

    product_names = build_product_name_map(products, username=current_user.username)

    time_label = {
        'week_20': '第20周',
        'week_21': '第21周', 
        'week_22': '第22周',
        'quarter_2': 'Q2季度'
    }.get(time_period, time_period or '全时段')

    product_label = label_for_products(products, product_names)
    
    if LLM_CONFIG.get("api_key") or LLM_CONFIG.get("provider") == "ollama":
        llm_report = await generate_ai_report_with_llm(products, product_names, time_label)
        if llm_report:
            return {
                "success": True,
                "source": source,
                "analysis_mode": "llm",
                "data": llm_report,
            }
    
    ai_report = {
        "summary": f"⚠️ 【默认报告】本次分析覆盖 {product_label}，时间周期为 {time_label}。核心结论：用户对产品核心玩法认可度较高，但付费设计和新手引导需要优化。建议关注付费转化率和用户留存问题，适时推出限时活动提升活跃度。\n\n💡 提示：如需获得AI深度分析，请在配置面板中设置LLM提供商（如OpenAI、Claude、Gemini或Ollama本地模型），或运行 Steam MVP 抓取真实评论。",
        "product_trends": generate_product_trends(products, product_names),
        "new_product_analysis": generate_new_product_trends(),
        "issues_diagnosis": generate_issues_diagnosis(products, product_names),
        "optimization_suggestions": generate_optimization_suggestions(products, product_names),
        "action_plan": generate_action_plan(),
        "using_llm": False,
        "llm_provider": None,
        "llm_model": None,
        "llm_configured": False
    }
    
    return {
        "success": True,
        "source": source,
        "analysis_mode": "legacy_template",
        "simulated": source in ("mock", "empty"),
        "data": ai_report,
    }

@router.get("/api/advanced/journey")
async def get_user_journey(
    token: Optional[str] = Query(None),
    time_range: str = Query("all"),
    product_ids: Optional[str] = Query(None),
    compare_mode: bool = Query(False)
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)
    comments = get_user_comments_data(current_user.username)
    metrics = get_user_metrics_data(current_user.username)
    
    products = _parse_product_ids(product_ids)
    
    if compare_mode and products != ['all']:
        journey_by_product = {}
        path_dist_by_product = {}
        simulated_any = False
        basis_notes: List[str] = []
        basis_set = set()
        
        for product in products:
            journey, basis, simulated = resolve_journey_for_product(product, comments, metrics)
            if simulated:
                journey = analytics['journey'].analyze_user_journey(time_range, [product])
                path_dist_by_product[product] = analytics['journey'].get_path_distribution([product]).get(product, [])
                simulated_any = True
                basis_set.add("mock_data")
            else:
                path_dist_by_product[product] = build_path_distribution_from_comments(product, comments)
                basis_set.add(basis)
                note = (journey.get("summary") or {}).get("data_note")
                if note:
                    basis_notes.append(note)
            journey_by_product[product] = journey
        
        basis = next(iter(basis_set)) if len(basis_set) == 1 else ("mixed" if basis_set else "mock_data")
        return _annotate_advanced_response(
            {
                "success": True,
                "selected_products": products,
                "compare_mode": True,
                "journey_by_product": journey_by_product,
                "path_dist_by_product": path_dist_by_product,
            },
            simulated=simulated_any,
            basis=basis,
            note=basis_notes[0] if basis_notes else "",
        )
    else:
        product_key = products[0] if products and products != ["all"] else "all"
        if product_key == "all":
            journey_data = analytics['journey'].analyze_user_journey(time_range, products)
            path_distribution_data = analytics['journey'].get_path_distribution(products)
            first_product = products[0] if products else 'all'
            path_distribution = path_distribution_data.get(first_product, path_distribution_data.get('all', [])) if isinstance(path_distribution_data, dict) else path_distribution_data
            return _annotate_advanced_response(
                {
                    "success": True,
                    "selected_products": products,
                    "compare_mode": False,
                    "journey": journey_data,
                    "path_distribution": path_distribution,
                },
                simulated=True,
                basis="mock_data",
                note="未选择具体产品时无法按真实评论样本计算，当前为演示模板。",
            )

        journey, basis, simulated = resolve_journey_for_product(product_key, comments, metrics)
        if simulated:
            journey_data = analytics['journey'].analyze_user_journey(time_range, products)
            path_distribution_data = analytics['journey'].get_path_distribution(products)
            first_product = products[0] if products else 'all'
            path_distribution = path_distribution_data.get(first_product, path_distribution_data.get('all', [])) if isinstance(path_distribution_data, dict) else path_distribution_data
            return _annotate_advanced_response(
                {
                    "success": True,
                    "selected_products": products,
                    "compare_mode": False,
                    "journey": journey_data,
                    "path_distribution": path_distribution,
                },
                simulated=True,
                basis="mock_data",
                note="当前账号尚无足够抓取/导入数据，请先于 /mvp 抓取或导入 CSV。",
            )

        path_distribution = build_path_distribution_from_comments(product_key, comments)
        return _annotate_advanced_response(
            {
                "success": True,
                "selected_products": products,
                "compare_mode": False,
                "journey": journey,
                "path_distribution": path_distribution,
            },
            simulated=False,
            basis=basis,
            note=(journey.get("summary") or {}).get("data_note", ""),
        )

@router.get("/api/advanced/funnel")
async def get_funnel_analysis(
    token: Optional[str] = Query(None),
    time_range: str = Query("all"),
    product_ids: Optional[str] = Query(None),
    compare_mode: bool = Query(False)
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)
    comments = get_user_comments_data(current_user.username)
    metrics = get_user_metrics_data(current_user.username)
    
    products = _parse_product_ids(product_ids)
    
    if compare_mode and products != ['all']:
        funnel_by_product = {}
        simulated_any = False
        basis_set = set()
        basis_notes: List[str] = []
        for product in products:
            funnel, basis, simulated = resolve_funnel_for_product(product, comments, metrics)
            if simulated:
                funnel = analytics['funnel'].create_funnel(time_range=time_range, products=[product])
                simulated_any = True
                basis_set.add("mock_data")
            else:
                basis_set.add(basis)
                note = funnel.get("data_note")
                if note:
                    basis_notes.append(note)
            funnel_by_product[product] = funnel
        
        basis = next(iter(basis_set)) if len(basis_set) == 1 else ("mixed" if basis_set else "mock_data")
        return _annotate_advanced_response(
            {
                "success": True,
                "selected_products": products,
                "compare_mode": True,
                "funnel_by_product": funnel_by_product,
            },
            simulated=simulated_any,
            basis=basis,
            note=basis_notes[0] if basis_notes else "",
        )
    else:
        product_key = products[0] if products and products != ["all"] else "all"
        if product_key == "all":
            funnel_data = analytics['funnel'].create_funnel(time_range=time_range, products=products)
            return _annotate_advanced_response(
                {
                    "success": True,
                    "selected_products": products,
                    "compare_mode": False,
                    "funnel": funnel_data,
                },
                simulated=True,
                basis="mock_data",
                note="未选择具体产品时无法按真实数据计算，当前为演示模板。",
            )

        funnel, basis, simulated = resolve_funnel_for_product(product_key, comments, metrics)
        if simulated:
            funnel_data = analytics['funnel'].create_funnel(time_range=time_range, products=products)
            return _annotate_advanced_response(
                {
                    "success": True,
                    "selected_products": products,
                    "compare_mode": False,
                    "funnel": funnel_data,
                },
                simulated=True,
                basis="mock_data",
                note="当前账号尚无足够抓取/导入数据，请先于 /mvp 抓取或导入 CSV。",
            )

        return _annotate_advanced_response(
            {
                "success": True,
                "selected_products": products,
                "compare_mode": False,
                "funnel": funnel,
            },
            simulated=False,
            basis=basis,
            note=funnel.get("data_note", ""),
        )

@router.get("/api/advanced/funnel/compare")
async def compare_funnels(
    token: Optional[str] = Query(None),
    time_range_a: str = Query(""),
    time_range_b: str = Query("")
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    await get_current_user(token)
    
    comparison_data = analytics['funnel'].compare_funnels(time_range_a, time_range_b)
    
    return with_simulated({
        "success": True,
        "comparison": comparison_data
    })

@router.get("/api/advanced/cohort")
async def get_cohort_analysis(
    token: Optional[str] = Query(None),
    cohort_type: str = Query("weekly"),
    date_range: str = Query(None),
    product_ids: Optional[str] = Query(None),
    compare_mode: bool = Query(False)
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)
    comments = get_user_comments_data(current_user.username)
    metrics = get_user_metrics_data(current_user.username)
    
    products = _parse_product_ids(product_ids)
    
    if compare_mode and products != ['all']:
        cohort_by_product = {}
        simulated_any = False
        basis_set = set()
        basis_notes: List[str] = []
        for product in products:
            cohort, basis, simulated = resolve_cohort_for_product(product, comments, metrics)
            if simulated:
                cohort = analytics['cohort'].create_cohort(cohort_type, date_range, [product])
                simulated_any = True
                basis_set.add("mock_data")
            else:
                basis_set.add(basis)
                note = cohort.get("data_note")
                if note:
                    basis_notes.append(note)
            cohort_by_product[product] = cohort
        
        basis = next(iter(basis_set)) if len(basis_set) == 1 else ("mixed" if basis_set else "mock_data")
        return _annotate_advanced_response(
            {
                "success": True,
                "selected_products": products,
                "compare_mode": True,
                "cohort_by_product": cohort_by_product,
            },
            simulated=simulated_any,
            basis=basis,
            note=basis_notes[0] if basis_notes else "",
        )
    else:
        product_key = products[0] if products and products != ["all"] else "all"
        if product_key == "all":
            cohort_data = analytics['cohort'].create_cohort(cohort_type, date_range, products)
            return _annotate_advanced_response(
                {
                    "success": True,
                    "selected_products": products,
                    "compare_mode": False,
                    "cohort": cohort_data,
                },
                simulated=True,
                basis="mock_data",
                note="未选择具体产品时无法按真实评论周样本计算，当前为演示模板。",
            )

        cohort, basis, simulated = resolve_cohort_for_product(product_key, comments, metrics)
        if simulated:
            cohort_data = analytics['cohort'].create_cohort(cohort_type, date_range, products)
            return _annotate_advanced_response(
                {
                    "success": True,
                    "selected_products": products,
                    "compare_mode": False,
                    "cohort": cohort_data,
                },
                simulated=True,
                basis="mock_data",
                note="当前账号尚无足够抓取/导入数据，请先于 /mvp 抓取或导入 CSV。",
            )

        return _annotate_advanced_response(
            {
                "success": True,
                "selected_products": products,
                "compare_mode": False,
                "cohort": cohort,
            },
            simulated=False,
            basis=basis,
            note=cohort.get("data_note", ""),
        )

@router.get("/api/advanced/cohort/{cohort_id}")
async def get_cohort_detail(
    cohort_id: str,
    token: Optional[str] = Query(None)
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    await get_current_user(token)
    
    detail_data = analytics['cohort'].analyze_retention_by_cohort(cohort_id)
    
    return with_simulated({
        "success": True,
        "detail": detail_data
    })

@router.get("/api/advanced/anomaly")
async def get_anomaly_detection(
    token: Optional[str] = Query(None),
    metric_name: str = Query(None),
    current_value: float = Query(None),
    product_ids: Optional[str] = Query(None),
    compare_mode: bool = Query(False)
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    await get_current_user(token)
    
    products = _parse_product_ids(product_ids)
    
    if compare_mode and products != ['all']:
        alerts_by_product = {}
        for product in products:
            alerts_by_product[product] = analytics['anomaly'].get_active_alerts([product])
        
        result = {
            "success": True,
            "selected_products": products,
            "compare_mode": True,
            "alerts_by_product": alerts_by_product
        }
        
        if metric_name and current_value is not None:
            anomaly_result = analytics['anomaly'].detect_anomaly(metric_name, current_value)
            result["anomaly_result"] = anomaly_result
        
        return result
    else:
        active_alerts = analytics['anomaly'].get_active_alerts(products)
        
        if metric_name and current_value is not None:
            anomaly_result = analytics['anomaly'].detect_anomaly(metric_name, current_value)
            return with_simulated({
                "success": True,
                "selected_products": products,
                "compare_mode": False,
                "anomaly_result": anomaly_result,
                "active_alerts": active_alerts
            })
        
        return with_simulated({
            "success": True,
            "selected_products": products,
            "compare_mode": False,
            "active_alerts": active_alerts
        })

@router.post("/api/advanced/anomaly/test")
async def test_anomaly_detection(
    request: Request,
    token: Optional[str] = Query(None)
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    await get_current_user(token)
    
    body = await request.json()
    metric_name = body.get('metric_name', 'revenue')
    current_value = body.get('current_value', 1000)
    
    # 初始化基线（如果还没有）
    analytics['anomaly'].initialize_baseline(metric_name)
    
    anomaly_result = analytics['anomaly'].detect_anomaly(metric_name, current_value)
    notification = analytics['anomaly'].generate_alert_notification(anomaly_result)
    
    return with_simulated({
        "success": True,
        "anomaly_result": anomaly_result,
        "notification": notification
    })

@router.get("/api/advanced/dashboard")
async def get_advanced_dashboard(
    token: Optional[str] = Query(None),
    product_ids: Optional[str] = Query(None),
    compare_mode: bool = Query(False)
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)
    
    products = _parse_product_ids(product_ids)
    comments = get_user_comments_data(current_user.username)
    metrics = get_user_metrics_data(current_user.username)
    
    if compare_mode and products != ['all']:
        realtime_by_product = {}
        simulated_any = False
        basis_set = set()
        basis_notes: List[str] = []
        for product in products:
            realtime, basis, simulated = resolve_realtime_for_product(product, comments, metrics)
            if simulated:
                product_metrics = _filter_metrics_by_products(metrics, [product])
                realtime = analytics['realtime'].calculate_real_time_metrics(product_metrics)
                simulated_any = True
                basis_set.add("mock_data")
            else:
                basis_set.add(basis)
                note = realtime.get("data_note")
                if note:
                    basis_notes.append(note)
            realtime_by_product[product] = realtime
        
        basis = next(iter(basis_set)) if len(basis_set) == 1 else ("mixed" if basis_set else "mock_data")
        return _annotate_advanced_response(
            {
                "success": True,
                "compare_mode": True,
                "realtime_by_product": realtime_by_product,
                "selected_products": products,
            },
            simulated=simulated_any,
            basis=basis,
            note=basis_notes[0] if basis_notes else "",
        )
    else:
        filtered_metrics = _filter_metrics_by_products(metrics, products)
        product_key = products[0] if products and products != ["all"] else "all"

        journey, journey_basis, journey_simulated = (
            resolve_journey_for_product(product_key, comments, metrics)
            if product_key != "all"
            else (None, "mock_data", True)
        )
        if journey_simulated or not journey:
            journey = analytics["journey"].analyze_user_journey(products=products)
            journey_simulated = True
            journey_basis = "mock_data"

        funnel, funnel_basis, funnel_simulated = (
            resolve_funnel_for_product(product_key, comments, metrics)
            if product_key != "all"
            else (None, "mock_data", True)
        )
        if funnel_simulated or not funnel:
            funnel = analytics["funnel"].create_funnel(products=products)
            funnel_simulated = True
            funnel_basis = "mock_data"

        cohort, cohort_basis, cohort_simulated = (
            resolve_cohort_for_product(product_key, comments, metrics)
            if product_key != "all"
            else (None, "mock_data", True)
        )
        if cohort_simulated or not cohort:
            cohort = analytics["cohort"].create_cohort(products=products)
            cohort_simulated = True
            cohort_basis = "mock_data"

        alerts = analytics["anomaly"].get_active_alerts(products)

        if product_key == "all":
            realtime = analytics["realtime"].calculate_real_time_metrics(filtered_metrics)
            simulated_any = True
            basis = _advanced_data_basis(current_user.username)
            if basis == "empty":
                basis = "mock_data"
            note = "未选择具体产品时路径/漏斗/群组为演示模板；实时 KPI 来自指标样本或演示数据。"
        else:
            realtime, rt_basis, rt_simulated = resolve_realtime_for_product(
                product_key, comments, metrics
            )
            if rt_simulated:
                realtime = analytics["realtime"].calculate_real_time_metrics(filtered_metrics)
            simulated_any = rt_simulated or journey_simulated or funnel_simulated or cohort_simulated
            basis_values = {rt_basis, journey_basis, funnel_basis, cohort_basis} - {"mock_data"}
            basis = next(iter(basis_values)) if len(basis_values) == 1 else (
                "mixed" if basis_values else "mock_data"
            )
            note = realtime.get("data_note", "") if not rt_simulated else (
                "当前账号尚无足够抓取/导入数据，请先于 /mvp 抓取或导入 CSV。"
            )

        return _annotate_advanced_response(
            {
                "success": True,
                "compare_mode": False,
                "realtime": realtime,
                "journey": journey,
                "funnel": funnel,
                "cohort": cohort,
                "alerts": alerts,
                "selected_products": products,
            },
            simulated=simulated_any,
            basis=basis,
            note=note,
        )

# =========================================
# Phase 2: 预测分析 API
# =========================================

@router.get("/api/predictive/ltv")
async def predict_ltv(
    token: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    prediction_days: int = Query(30)
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    await get_current_user(token)
    
    ltv_prediction = analytics['predictive'].predict_ltv(user_id, prediction_days)
    
    return with_simulated({
        "success": True,
        "ltv_prediction": ltv_prediction
    })

@router.get("/api/predictive/churn")
async def predict_churn(
    token: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None)
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    await get_current_user(token)
    
    churn_prediction = analytics['predictive'].predict_churn_probability(user_id)
    
    return with_simulated({
        "success": True,
        "churn_prediction": churn_prediction
    })

@router.get("/api/predictive/high-value-users")
async def get_high_value_users(
    token: Optional[str] = Query(None),
    time_range: str = Query("30d"),
    top_percent: int = Query(10)
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    await get_current_user(token)
    
    high_value_users = analytics['predictive'].identify_high_value_users(time_range, top_percent)
    
    return with_simulated({
        "success": True,
        "high_value_users": high_value_users
    })

@router.get("/api/predictive/revenue-forecast")
async def get_revenue_forecast(
    token: Optional[str] = Query(None),
    days: int = Query(30)
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    await get_current_user(token)
    
    revenue_forecast = analytics['predictive'].predict_revenue_forecast(days)
    
    return with_simulated({
        "success": True,
        "revenue_forecast": revenue_forecast
    })

@router.get("/api/predictive/dashboard")
async def get_predictive_dashboard(
    token: Optional[str] = Query(None),
    product_ids: Optional[str] = Query(None),
    compare_mode: bool = Query(False)
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    await get_current_user(token)
    
    products = _parse_product_ids(product_ids)
    
    if compare_mode and products != ['all']:
        predictions_by_product = {}
        for product in products:
            predictions_by_product[product] = {
                "ltv": analytics['predictive'].predict_ltv(),
                "churn": analytics['predictive'].predict_churn_probability(),
                "high_value_users": analytics['predictive'].identify_high_value_users(),
                "revenue_forecast": analytics['predictive'].predict_revenue_forecast(30)
            }
        
        return with_simulated({
            "success": True,
            "selected_products": products,
            "compare_mode": True,
            "predictions_by_product": predictions_by_product
        })
    else:
        # 获取所有预测数据
        ltv = analytics['predictive'].predict_ltv()
        churn = analytics['predictive'].predict_churn_probability()
        high_value = analytics['predictive'].identify_high_value_users()
        forecast = analytics['predictive'].predict_revenue_forecast(30)
        
        return with_simulated({
            "success": True,
            "selected_products": products,
            "compare_mode": False,
            "ltv": ltv,
            "churn": churn,
            "high_value_users": high_value,
            "revenue_forecast": forecast
        })

