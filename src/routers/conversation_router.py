"""LLM conversation API routes."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from src.auth import PLANS
from src.database import UserRepository
from src.services.conversation import (
    clear_conversation_history,
    generate_conversation_reply,
    get_conversation_history,
    set_conversation_history,
)
from src.services.legacy_ai_report import MOCK_PRODUCT_NAMES
from src.web_common import get_current_user

router = APIRouter(tags=["conversation"])

_TIME_LABELS = {
    "week_20": "第20周",
    "week_21": "第21周",
    "week_22": "第22周",
    "quarter_2": "Q2季度",
}


@router.post("/api/conversation")
async def conversation(request: Request, token: Optional[str] = Query(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)

    body = await request.json()
    message = body.get("message", "")
    products = body.get("products", [])
    time_period = body.get("time_period", "")
    conversation_id = body.get("conversation_id", "default")

    if not message:
        return {"success": False, "error": "消息不能为空"}

    selected_products = [MOCK_PRODUCT_NAMES.get(p, p) for p in products if p in MOCK_PRODUCT_NAMES]
    product_label = ", ".join(selected_products) if selected_products else "全部产品"
    time_label = _TIME_LABELS.get(time_period, time_period or "全时段")

    history = get_conversation_history(current_user.username, conversation_id)
    context_prompt = (
        f"当前分析上下文：\n- 产品：{product_label}\n- 时间周期：{time_label}\n\n"
        "你是一位专业的游戏数据分析顾问。用户正在与你进行数据分析相关的对话。"
        "请基于上述上下文信息回答用户的问题。\n\n"
        "如果用户询问的是关于数据分析、趋势、优化建议等内容，请结合上述上下文给出专业建议。\n"
        "如果用户的问题与当前数据无关，请告知用户你只能回答与当前分析数据相关的问题。\n\n"
        f"用户问题：{message}"
    )

    history.append({"role": "user", "content": message})

    try:
        response_text = await generate_conversation_reply(
            context_prompt, current_user.username, conversation_id
        )
    except Exception as exc:
        print(f"对话调用失败: {exc}")
        response_text = "抱歉，AI服务暂时不可用。请稍后再试。"

    history.append({"role": "assistant", "content": response_text})
    if len(history) > 20:
        history = history[-20:]
    set_conversation_history(current_user.username, conversation_id, history)

    return {
        "success": True,
        "response": response_text,
        "conversation_id": conversation_id,
        "history": history[-10:],
    }


@router.post("/api/conversation/clear")
async def clear_conversation(
    conversation_id: str = Query(None),
    token: Optional[str] = Query(None),
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)

    if conversation_id:
        clear_conversation_history(current_user.username, conversation_id)
    else:
        clear_conversation_history(current_user.username, "default")

    return {"success": True, "message": "对话历史已清除"}


@router.get("/api/conversation/history")
async def get_conversation_history_route(
    conversation_id: str = Query("default"),
    token: Optional[str] = Query(None),
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)
    history = get_conversation_history(current_user.username, conversation_id)
    return {"success": True, "history": history[-10:]}


@router.post("/api/upgrade_plan")
async def upgrade_plan(plan_id: str, token: Optional[str] = Query(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)
    if plan_id not in PLANS:
        raise HTTPException(status_code=400, detail="Invalid plan")

    plan = PLANS[plan_id]
    UserRepository.update(
        current_user.username,
        {
            "plan_id": plan_id,
            "games_limit": plan.games_limit,
            "api_quota": plan.api_quota,
            "is_trial": 0,
            "updated_at": __import__("datetime").datetime.now().isoformat(),
        },
    )

    return {
        "success": True,
        "message": f"Successfully upgraded to {plan.name}",
        "plan": plan.model_dump(),
    }
