"""LLM executive summary grounded in validated MVP artifacts only."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from src.auth import LLM_PROVIDERS, LLM_CONFIG

from src.mvp_data import mvp_validation_passed
from src.services.llm_client import complete_prompt, llm_is_configured


def build_mvp_facts_for_llm(analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Compact, auditable facts derived from validated MVP analysis — no raw comment bodies."""
    strategy = analysis.get("ai_strategy") or {}
    return {
        "validation_required": True,
        "summary": analysis.get("summary"),
        "product_reports": [
            {
                "product": report.get("product"),
                "product_name": report.get("product_name"),
                "sample_size": report.get("sample_size"),
                "positive_rate": report.get("positive_rate"),
                "risk_level": report.get("risk_level"),
                "top_negative_themes": report.get("top_negative_themes", [])[:3],
                "recommendation": report.get("recommendation"),
            }
            for report in analysis.get("product_reports", [])
        ],
        "user_needs": strategy.get("user_needs", [])[:6],
        "prioritized_actions": strategy.get("prioritized_actions", [])[:4],
        "peer_comparison": strategy.get("peer_comparison", [])[:5],
        "opportunity_summary": strategy.get("opportunity_summary"),
    }


async def summarize_mvp_with_llm(analysis: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
  Generate an executive summary via LLM.
  Only runs when validation.json passed and LLM is configured.
  """
    if not mvp_validation_passed():
        return None
    if not llm_is_configured():
        return None

    facts = build_mvp_facts_for_llm(analysis)
    prompt = (
        "你是游戏产品分析顾问。下面是通过校验的 Steam 真实评论分析事实（JSON）。\n"
        "请仅根据这些事实写一段 120-180 字的中文高管摘要，指出竞品对比结论、"
        "首要用户需求与 1-2 条优先行动。不要编造未出现在 JSON 中的数字或产品名。\n"
        "只输出纯文本，不要 Markdown 代码块。\n\n"
        f"{json.dumps(facts, ensure_ascii=False)}"
    )

    try:
        text = (await complete_prompt(prompt)).strip()
        if not text:
            return None
        provider = LLM_CONFIG["provider"]
        return {
            "executive_summary": text,
            "using_llm": True,
            "llm_provider": LLM_PROVIDERS.get(provider, {}).get("name", provider),
            "llm_model": LLM_CONFIG.get("model"),
            "grounded_in": "mvp_validation_passed",
        }
    except Exception as exc:
        print(f"MVP LLM summary failed: {exc}")
        return None
