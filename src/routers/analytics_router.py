"""评论 AI 分析（基于公开抓取数据的规则模板 + 可选 LLM 摘要）。"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from src.auth import LLM_CONFIG, LLM_PROVIDERS
from src.data_resolution import resolve_user_data_source
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


def _parse_product_ids(product_ids: Optional[str]) -> List[str]:
    if not product_ids or not str(product_ids).strip():
        return ["all"]
    parts = [p.strip() for p in str(product_ids).split(",") if p.strip()]
    return parts or ["all"]


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
