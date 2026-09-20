"""LLM-assisted gameplay breakdown generation for the game library."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.auth import LLM_CONFIG, LLM_PROVIDERS

from src.mvp_data import get_mvp_analysis, get_mvp_comments_and_metrics, mvp_validation_passed
from src.services.game_intel import (
    BREAKDOWN_SECTIONS,
    GameLibraryRepository,
    GameplayBreakdownRepository,
    _template_breakdown_for_genre,
    generate_breakdown_from_comments,
)
from src.services.llm_client import complete_prompt, llm_is_configured, parse_json_from_llm

BREAKDOWN_KEYS = [key for key, _, _ in BREAKDOWN_SECTIONS] + ["analysis_notes"]


def _resolve_product_id(game: Dict[str, Any]) -> str:
    steam_id = (game.get("steam_app_id") or "").strip()
    if steam_id:
        return steam_id
    game_id = game.get("game_id") or ""
    if game_id.startswith("steam_"):
        return game_id.replace("steam_", "", 1)
    return ""


def _find_product_report(analysis: Optional[Dict[str, Any]], product_id: str) -> Optional[Dict[str, Any]]:
    if not analysis or not product_id:
        return None
    for report in analysis.get("product_reports") or []:
        if str(report.get("product") or "") == product_id:
            return report
    return None


def build_breakdown_context(game_id: str) -> Optional[Dict[str, Any]]:
    """Compact facts for LLM — profile, MVP metrics, review themes (no bulk raw comments)."""
    game = GameLibraryRepository.get(game_id)
    if not game:
        return None

    product_id = _resolve_product_id(game)
    context: Dict[str, Any] = {
        "game_profile": {
            "game_id": game.get("game_id"),
            "name": game.get("name"),
            "genre": game.get("genre"),
            "sub_genre": game.get("sub_genre"),
            "platforms": game.get("platforms") or [],
            "business_model": game.get("business_model"),
            "developer": game.get("developer"),
            "tags": game.get("tags") or [],
            "summary": game.get("summary"),
            "steam_app_id": game.get("steam_app_id"),
            "source": game.get("source"),
        },
        "mvp_data_available": False,
        "review_signals": None,
        "metrics_snapshot": [],
    }

    if mvp_validation_passed() and product_id:
        comments, metrics, _ = get_mvp_comments_and_metrics()
        product_comments = [
            c
            for c in comments
            if str(c.get("product") or c.get("产品") or "") == product_id
        ]
        product_metrics = [
            m for m in metrics if str(m.get("product") or m.get("产品") or "") == product_id
        ]
        if product_comments or product_metrics:
            context["mvp_data_available"] = True
            analysis = get_mvp_analysis() or {}
            report = _find_product_report(analysis, product_id)
            if report:
                context["review_signals"] = {
                    "sample_size": report.get("sample_size"),
                    "positive_rate": report.get("positive_rate"),
                    "risk_level": report.get("risk_level"),
                    "top_negative_themes": (report.get("top_negative_themes") or [])[:5],
                    "recommendation": report.get("recommendation"),
                    "representative_negative_reviews": (
                        report.get("representative_negative_reviews") or []
                    )[:2],
                    "representative_positive_reviews": (
                        report.get("representative_positive_reviews") or []
                    )[:2],
                }
            context["metrics_snapshot"] = [
                {
                    "metric": row.get("metric") or row.get("指标"),
                    "value": row.get("value") or row.get("数值"),
                    "cycle": row.get("cycle") or row.get("周期"),
                }
                for row in product_metrics[:12]
            ]

    existing = GameplayBreakdownRepository.get(game_id)
    if existing:
        context["existing_breakdown"] = {
            key: (existing.get(key) or "")[:400] for key in BREAKDOWN_KEYS if existing.get(key)
        }

    competitors = []
    for cid in game.get("competitor_ids") or []:
        comp = GameLibraryRepository.get(cid)
        if comp:
            competitors.append(
                {"name": comp.get("name"), "genre": comp.get("genre"), "tags": comp.get("tags") or []}
            )
    if competitors:
        context["linked_competitors"] = competitors[:6]

    return context


def _build_prompt(context: Dict[str, Any], *, refine: bool = False) -> str:
    section_lines = "\n".join(f'  "{key}": "…"' for key in BREAKDOWN_KEYS)
    mode = "优化并充实已有拆解" if refine and context.get("existing_breakdown") else "从零生成玩法拆解"
    grounded = (
        "必须优先使用 review_signals 与 metrics_snapshot 中的真实信号；"
        "若 mvp_data_available 为 false，则基于品类常识与档案信息推断，并在 analysis_notes 中标注「待实机验证」。"
    )
    return (
        "你是资深游戏策划与竞品分析师，擅长 GameRefinery 式玩法拆解。\n"
        f"任务：为下列游戏{mode}，输出结构化 JSON（仅 JSON，不要 Markdown 代码块）。\n"
        f"{grounded}\n"
        "每个字段 2-4 句中文，具体可执行，避免空泛营销话术。\n"
        "benchmarks 字段列出 2-3 个可对标的竞品名与可借鉴机制。\n"
        "analysis_notes 需说明依据来源（MVP 评论 / 品类模板 / 人工档案）。\n\n"
        f"上下文 JSON：\n{json.dumps(context, ensure_ascii=False)}\n\n"
        "输出格式：\n"
        "{\n"
        f"{section_lines}\n"
        "}"
    )


def _normalize_breakdown(raw: Dict[str, Any], *, provider_label: str, model: str) -> Dict[str, Any]:
    breakdown: Dict[str, Any] = {}
    for key in BREAKDOWN_KEYS:
        value = raw.get(key)
        if value is not None:
            breakdown[key] = str(value).strip()
    notes = breakdown.get("analysis_notes", "")
    stamp = f"【AI生成 {datetime.now().strftime('%Y-%m-%d %H:%M')} · {provider_label}/{model}】"
    if stamp not in notes:
        breakdown["analysis_notes"] = (notes + "\n\n" + stamp).strip() if notes else stamp
    breakdown["auto_generated"] = True
    return breakdown


def _heuristic_fallback(game_id: str, game: Dict[str, Any]) -> Dict[str, Any]:
    product_id = _resolve_product_id(game)
    if mvp_validation_passed() and product_id:
        comments, _, _ = get_mvp_comments_and_metrics()
        return generate_breakdown_from_comments(game_id, game.get("name", ""), comments, product_id)
    return _template_breakdown_for_genre(game.get("genre", ""), game.get("name", ""))


async def generate_breakdown_with_ai(
    game_id: str,
    *,
    refine: bool = False,
    save: bool = True,
    current_breakdown: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Generate gameplay breakdown via configured LLM.
    Falls back to heuristic template when LLM is unavailable or parsing fails.
    """
    game = GameLibraryRepository.get(game_id)
    if not game:
        return {"success": False, "message": "游戏不存在"}

    context = build_breakdown_context(game_id)
    if not context:
        return {"success": False, "message": "无法构建分析上下文"}

    if refine and current_breakdown:
        context["existing_breakdown"] = {
            key: str(current_breakdown.get(key) or "")[:800] for key in BREAKDOWN_KEYS
        }
    elif refine and not context.get("existing_breakdown"):
        return {
            "success": False,
            "message": "当前没有可优化的拆解内容，请先填写或使用「AI 生成拆解」",
        }

    if not llm_is_configured():
        breakdown = _heuristic_fallback(game_id, game)
        if save:
            GameplayBreakdownRepository.upsert(game_id, breakdown)
        return {
            "success": True,
            "using_llm": False,
            "message": "未配置 LLM，已使用规则引擎生成初稿。管理员可在「系统管理 → LLM配置」接入 OpenAI/Ollama 等。",
            "breakdown": breakdown,
            "saved": save,
        }

    provider = LLM_CONFIG.get("provider", "")
    provider_label = LLM_PROVIDERS.get(provider, {}).get("name", provider)
    model = LLM_CONFIG.get("model", "")

    try:
        prompt = _build_prompt(context, refine=refine)
        response_text = await complete_prompt(prompt, max_tokens=2800)
        parsed = parse_json_from_llm(response_text)
        if not parsed:
            raise RuntimeError("LLM 返回内容无法解析为 JSON")

        breakdown = _normalize_breakdown(parsed, provider_label=provider_label, model=model)
        if save:
            GameplayBreakdownRepository.upsert(game_id, breakdown)

        return {
            "success": True,
            "using_llm": True,
            "llm_provider": provider_label,
            "llm_model": model,
            "grounded_in": "mvp_steam" if context.get("mvp_data_available") else "profile_only",
            "breakdown": breakdown,
            "saved": save,
        }
    except Exception as exc:
        print(f"Gameplay breakdown LLM failed: {exc}")
        breakdown = _heuristic_fallback(game_id, game)
        notes = breakdown.get("analysis_notes", "")
        breakdown["analysis_notes"] = (
            f"{notes}\n\n【LLM 失败回退】{exc}".strip()
            if notes
            else f"【LLM 失败回退】{exc}"
        )
        if save:
            GameplayBreakdownRepository.upsert(game_id, breakdown)
        return {
            "success": True,
            "using_llm": False,
            "message": f"AI 生成失败，已回退规则引擎：{exc}",
            "breakdown": breakdown,
            "saved": save,
        }
