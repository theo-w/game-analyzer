"""LLM-backed replies for customer-support live chat."""

from __future__ import annotations

from typing import Dict, List

from src.auth import LLM_CONFIG

from src.services.llm_client import (
    call_anthropic_api,
    call_gemini_api,
    call_ollama_api,
    call_openai_api,
    llm_is_configured,
    refresh_llm_config_from_db,
)

SUPPORT_SYSTEM_PROMPT = """你是「游戏数据分析引擎」的在线智能客服。
请用简洁、专业的中文回答，重点介绍：数据看板、评论分析、指标详情、MVP Steam 数据采集、
数据导入、告警、报告、订阅套餐。若用户明确要求人工/投诉/工单，请在回答末尾单独一行写：__ESCALATE_TO_HUMAN__
不要编造不存在的功能。"""


def _history_to_prompt(history: List[Dict], message: str) -> str:
    lines = [SUPPORT_SYSTEM_PROMPT, "", "近期对话："]
    for item in history[-8:]:
        role = item.get("username") or item.get("role") or "user"
        text = item.get("message") or item.get("content") or ""
        if text:
            lines.append(f"{role}: {text}")
    lines.append(f"用户: {message}")
    lines.append("请回复用户：")
    return "\n".join(lines)


async def generate_support_reply(message: str, history: List[Dict]) -> str:
    refresh_llm_config_from_db()
    if not llm_is_configured():
        raise RuntimeError("LLM not configured")

    prompt = _history_to_prompt(history, message)
    provider = LLM_CONFIG.get("provider", "openai")
    model = LLM_CONFIG.get("model", "")
    api_key = LLM_CONFIG.get("api_key", "")
    endpoint = LLM_CONFIG.get("endpoint", "")

    if provider == "openai":
        return await call_openai_api(prompt, api_key, model, endpoint)
    if provider == "ollama":
        return await call_ollama_api(prompt, model, endpoint)
    if provider == "anthropic":
        return await call_anthropic_api(prompt, api_key, model)
    if provider == "gemini":
        return await call_gemini_api(prompt, api_key, model)
    raise RuntimeError(f"Unsupported provider: {provider}")
