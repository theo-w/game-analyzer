"""Customer support and agent console routes."""

from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from src.database import UserRepository
from src.deps import is_admin, require_admin, require_support_staff
from src.web_common import get_current_user
from src.web_constants import BASE_DIR


def _agent_can_access_chat(chat: dict, username: str, admin: bool) -> bool:
    if admin or not chat:
        return bool(chat)
    assigned = (chat.get("assigned_agent") or "").strip()
    return not assigned or assigned == username


def _agent_can_access_ticket(ticket: dict, username: str, admin: bool) -> bool:
    if admin or not ticket:
        return bool(ticket)
    assigned = (ticket.get("agent_id") or "").strip()
    return not assigned or assigned == username

router = APIRouter(tags=["support"])

@router.get("/api/support/knowledge-base")
async def get_knowledge_base(token: Optional[str] = Query(None)):
    """获取知识库文章列表"""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    
    try:
        await get_current_user(token)
        
        from src.support import knowledge_base
        articles = knowledge_base.get_popular_articles(10)
        
        return {"success": True, "data": articles}
    
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.get("/api/support/knowledge-base/search")
async def search_knowledge_base(query: str, token: Optional[str] = Query(None)):
    """搜索知识库文章"""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    
    try:
        await get_current_user(token)
        
        from src.support import knowledge_base
        articles = knowledge_base.search_articles(query)
        
        return {"success": True, "data": articles}
    
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.get("/api/support/knowledge-base/article/{article_id}")
async def get_knowledge_base_article(article_id: str, token: Optional[str] = Query(None)):
    """获取知识库文章详情"""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    
    try:
        await get_current_user(token)
        
        from src.support import knowledge_base
        article = knowledge_base.get_article(article_id)
        
        if article:
            return {"success": True, "data": article}
        else:
            return {"success": False, "message": "文章不存在"}
    
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.get("/api/support/tickets")
async def get_user_tickets(token: Optional[str] = Query(None)):
    """获取用户工单列表"""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    
    try:
        current_user = await get_current_user(token)
        
        from src.support import ticket_system
        tickets = ticket_system.get_user_tickets(current_user.username)
        
        return {"success": True, "data": tickets}
    
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/api/support/tickets")
async def create_ticket(
    token: Optional[str] = Query(None),
    subject: str = Body(...),
    priority: str = Body(default="medium"),
    message: str = Body(...),
    chat_id: Optional[str] = Body(default=None),
):
    """创建工单"""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    
    try:
        current_user = await get_current_user(token)
        
        from src.support import ticket_system
        result = ticket_system.create_ticket(
            current_user.username, subject, message, priority, chat_id=chat_id
        )
        
        return {"success": True, "ticket_id": result['ticket_id'], "status": result['status'], "chat_id": chat_id}
    
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.get("/api/support/chat/start")
async def start_chat(token: Optional[str] = Query(None)):
    """开始在线聊天"""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    
    try:
        current_user = await get_current_user(token)
        if current_user.role in ("admin", "agent"):
            raise HTTPException(
                status_code=403,
                detail="坐席账号请使用「客服工作台」处理客户会话，勿在用户端发起咨询",
            )

        from src.support import live_chat
        result = live_chat.start_chat(current_user.username)

        return {
            "success": True,
            "chat_id": result["chat_id"],
            "resumed": result.get("resumed", False),
        }
    
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.get("/api/support/chat/messages/{chat_id}")
async def get_chat_messages(chat_id: str, token: Optional[str] = Query(None)):
    """获取聊天消息"""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    
    try:
        current_user = await get_current_user(token)
        from src.support import live_chat

        chat = live_chat.get_chat(chat_id)
        if not chat:
            raise HTTPException(status_code=404, detail="会话不存在")
        owner = chat.get("username")
        if owner != current_user.username and current_user.role not in ("admin", "agent"):
            raise HTTPException(status_code=403, detail="无权查看该会话")

        messages = live_chat.get_messages(chat_id, for_display=True)

        return {
            "success": True,
            "data": messages,
            "chat_owner": owner,
            "chat_status": chat.get("status"),
            "assigned_agent": chat.get("assigned_agent"),
        }
    
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/api/support/chat/send")
async def send_chat_message(
    token: Optional[str] = Query(None),
    chat_id: str = Body(...),
    message: str = Body(...)
):
    """发送聊天消息（包含AI自动回复）"""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    
    try:
        current_user = await get_current_user(token)
        if current_user.role in ("admin", "agent"):
            raise HTTPException(
                status_code=403,
                detail="坐席请通过客服工作台回复，不要在用户端发送消息",
            )

        from src.support import live_chat, ai_chatbot

        try:
            live_chat.assert_customer_can_access_chat(chat_id, current_user.username)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        live_chat.add_message(chat_id, current_user.username, message)

        ai_result = await ai_chatbot.process_message_async(
            chat_id, current_user.username, message
        )
        
        return {
            "success": True,
            "ai_replied": bool(ai_result.get("ai_replied")),
            "ai_reason": ai_result.get("reason"),
            "chat_status": (live_chat.get_chat(chat_id) or {}).get("status"),
        }
    
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/api/support/chat/escalate")
async def escalate_chat_to_ticket(
    token: Optional[str] = Query(None),
    chat_id: str = Body(...),
    subject: Optional[str] = Body(default=None),
    message: Optional[str] = Body(default=None),
):
    """将会话升级为工单并转人工"""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")

    try:
        current_user = await get_current_user(token)
        from src.support import live_chat, ticket_system

        chat = live_chat.get_chat(chat_id)
        if not chat or chat.get('username') != current_user.username:
            return {"success": False, "message": "会话不存在或无权限"}

        ticket = ticket_system.create_ticket_from_chat(
            chat_id,
            current_user.username,
            subject=subject or f'用户申请人工客服 ({chat_id})',
            message=message or '用户从在线客服申请转人工处理',
            priority='high',
        )
        return {"success": True, "ticket_id": ticket["ticket_id"], "chat_id": chat_id}
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.get("/api/support/tickets/{ticket_id}")
async def get_ticket_detail(ticket_id: str, token: Optional[str] = Query(None)):
    """获取工单详情（含回复）"""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")

    try:
        current_user = await get_current_user(token)
        from src.support import ticket_system

        ticket = ticket_system.get_ticket(ticket_id)
        if not ticket:
            return {"success": False, "message": "工单不存在"}
        if ticket.get("username") != current_user.username and current_user.role != "admin":
            assigned = (ticket.get("agent_id") or "").strip()
            if current_user.role != "agent" or (assigned and assigned != current_user.username):
                return {"success": False, "message": "无权限查看该工单"}
        return {"success": True, "data": ticket}
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.get("/api/support/chat/end/{chat_id}")
async def end_chat(chat_id: str, token: Optional[str] = Query(None)):
    """结束聊天"""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    
    try:
        current_user = await get_current_user(token)
        from src.support import live_chat

        try:
            live_chat.assert_customer_can_access_chat(chat_id, current_user.username)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        live_chat.end_chat(chat_id)
        
        return {"success": True}
    
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": str(e)}


# ==================== 人工客服后台 API ====================

@router.get("/agent/console", response_class=HTMLResponse)
async def agent_console_page():
    """人工客服控制台页面（鉴权在浏览器端 + 各 API 完成，避免页面级 403 闪退）"""
    with open(os.path.join(BASE_DIR, "templates", "agent_console.html"), "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@router.get("/api/agent/me")
async def agent_me(token: Optional[str] = Query(None)):
    """当前客服账号信息（角色、姓名）"""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)
    require_support_staff(current_user)
    return {
        "success": True,
        "data": {
            "username": current_user.username,
            "full_name": current_user.full_name,
            "role": current_user.role,
            "is_admin": is_admin(current_user),
        },
    }


@router.get("/api/agent/inbox")
async def get_agent_inbox(token: Optional[str] = Query(None)):
    """统一收件箱：在线会话 + 工单"""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")

    try:
        current_user = await get_current_user(token)
        require_support_staff(current_user)

        from src.support import agent_console
        items = agent_console.get_unified_inbox(
            agent_username=current_user.username,
            admin_view=is_admin(current_user),
        )
        return {"success": True, "data": items}
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.get("/api/agent/dashboard")
async def agent_dashboard(token: Optional[str] = Query(None)):
    """获取客服仪表盘统计"""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    
    try:
        current_user = await get_current_user(token)
        require_support_staff(current_user)
        
        from src.support import agent_console
        stats = agent_console.get_dashboard_stats()
        
        return {"success": True, "data": stats}
    
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.get("/api/agent/chats")
async def get_agent_chats(status: Optional[str] = Query(None), token: Optional[str] = Query(None)):
    """获取所有对话列表"""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    
    try:
        current_user = await get_current_user(token)
        require_support_staff(current_user)
        
        from src.support import agent_console
        chats = agent_console.get_all_chats(
            status,
            agent_username=current_user.username,
            admin_view=is_admin(current_user),
        )
        chats = agent_console.enrich_chat_summaries(chats)
        
        return {"success": True, "data": chats}
    
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.get("/api/agent/chat/{chat_id}")
async def get_agent_chat_detail(chat_id: str, token: Optional[str] = Query(None)):
    """获取对话详情"""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    
    try:
        current_user = await get_current_user(token)
        require_support_staff(current_user)
        
        from src.support import agent_console
        chat = agent_console.get_chat_detail(chat_id)
        if not _agent_can_access_chat(chat, current_user.username, is_admin(current_user)):
            raise HTTPException(status_code=403, detail="该会话已分配给其他坐席")
        
        return {"success": True, "data": chat}
    
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/api/agent/chat/reply")
async def agent_reply(
    token: Optional[str] = Query(None),
    chat_id: str = Body(...),
    message: str = Body(...)
):
    """人工客服回复消息"""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    
    try:
        current_user = await get_current_user(token)
        require_support_staff(current_user)
        
        from src.support import agent_console
        chat = agent_console.get_chat_detail(chat_id)
        if not _agent_can_access_chat(chat, current_user.username, is_admin(current_user)):
            raise HTTPException(status_code=403, detail="该会话已分配给其他坐席")
        agent_console.reply_to_chat(chat_id, current_user.username, message)
        
        return {"success": True}
    
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/api/agent/chat/claim")
async def claim_chat_for_agent(
    token: Optional[str] = Query(None),
    chat_id: str = Body(..., embed=True),
):
    """坐席接手会话（接手后 AI 不再自动回复）。"""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    try:
        current_user = await get_current_user(token)
        require_support_staff(current_user)
        from src.support import agent_console

        chat = agent_console.get_chat_detail(chat_id)
        if not _agent_can_access_chat(chat, current_user.username, is_admin(current_user)):
            raise HTTPException(status_code=403, detail="该会话已分配给其他坐席")
        agent_console.claim_chat(chat_id, current_user.username)
        return {"success": True, "message": "已接手，AI 将不再自动回复此会话"}
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/api/agent/chat/release-ai")
async def release_chat_to_ai(
    token: Optional[str] = Query(None),
    chat_id: str = Body(..., embed=True),
):
    """恢复 AI 自动回复（适用于误接手或已处理完毕的会话）。"""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    try:
        current_user = await get_current_user(token)
        require_support_staff(current_user)
        from src.support import agent_console

        chat = agent_console.get_chat_detail(chat_id)
        if not _agent_can_access_chat(chat, current_user.username, is_admin(current_user)):
            raise HTTPException(status_code=403, detail="无权操作该会话")
        agent_console.release_to_ai(chat_id)
        return {"success": True, "message": "已恢复 AI 自动回复"}
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/api/agent/chat/transfer")
async def transfer_to_human(
    token: Optional[str] = Query(None),
    chat_id: str = Body(..., embed=True),
):
    """将对话转交给人工客服"""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    
    try:
        current_user = await get_current_user(token)
        require_support_staff(current_user)
        
        from src.support import agent_console
        agent_console.transfer_to_human(chat_id, current_user.username)
        
        return {"success": True}
    
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.get("/api/agent/staff")
async def list_support_agents(token: Optional[str] = Query(None)):
    """管理员：列出人工坐席账号"""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)
    require_admin(current_user)
    users = UserRepository.get_all() or []
    agents = [
        {
            "username": u["username"],
            "full_name": u.get("full_name") or u["username"],
            "email": u.get("email"),
            "is_active": bool(u.get("is_active", 1)),
        }
        for u in users
        if u.get("role") == "agent"
    ]
    return {"success": True, "data": agents}


@router.post("/api/agent/assign/chat")
async def assign_chat_to_agent(
    token: Optional[str] = Query(None),
    chat_id: str = Body(...),
    agent_username: str = Body(...),
):
    """管理员：将会话分配给坐席"""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)
    require_admin(current_user)
    target = UserRepository.get_by_username(agent_username)
    if not target or target.get("role") != "agent":
        raise HTTPException(status_code=400, detail="目标坐席不存在")
    from src.support import agent_console
    agent_console.assign_chat(chat_id, agent_username)
    return {"success": True, "message": f"已分配给 {agent_username}"}


@router.post("/api/agent/assign/ticket")
async def assign_ticket_to_agent(
    token: Optional[str] = Query(None),
    ticket_id: str = Body(...),
    agent_username: str = Body(...),
):
    """管理员：将工单分配给坐席"""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)
    require_admin(current_user)
    target = UserRepository.get_by_username(agent_username)
    if not target or target.get("role") != "agent":
        raise HTTPException(status_code=400, detail="目标坐席不存在")
    from src.support import agent_console
    agent_console.assign_ticket(ticket_id, agent_username)
    return {"success": True, "message": f"已分配给 {agent_username}"}


@router.get("/api/agent/tickets")
async def get_agent_tickets(token: Optional[str] = Query(None)):
    """获取所有工单（管理员）"""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    
    try:
        current_user = await get_current_user(token)
        require_support_staff(current_user)
        
        from src.support import agent_console
        tickets = agent_console.get_all_tickets_for_staff(
            agent_username=current_user.username,
            admin_view=is_admin(current_user),
        )
        
        return {"success": True, "data": tickets}
    
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.put("/api/agent/ticket/{ticket_id}")
async def update_ticket_status(
    ticket_id: str,
    token: Optional[str] = Query(None),
    status: str = Body(...)
):
    """更新工单状态"""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    
    try:
        current_user = await get_current_user(token)
        require_support_staff(current_user)
        
        from src.support import ticket_system
        ticket = ticket_system.get_ticket(ticket_id)
        if not _agent_can_access_ticket(ticket, current_user.username, is_admin(current_user)):
            raise HTTPException(status_code=403, detail="该工单已分配给其他坐席")
        success = ticket_system.update_ticket(ticket_id, {'status': status})
        
        return {"success": success}
    
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/api/agent/ticket/{ticket_id}/reply")
async def reply_to_ticket(
    ticket_id: str,
    token: Optional[str] = Query(None),
    message: str = Body(...)
):
    """回复工单"""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    
    try:
        current_user = await get_current_user(token)
        require_support_staff(current_user)
        
        from src.support import agent_console, ticket_system
        ticket = ticket_system.get_ticket(ticket_id)
        if not _agent_can_access_ticket(ticket, current_user.username, is_admin(current_user)):
            raise HTTPException(status_code=403, detail="该工单已分配给其他坐席")
        if not is_admin(current_user):
            agent_console.assign_ticket(ticket_id, current_user.username)
        ticket_system.add_reply(ticket_id, current_user.username, message, is_agent=True)
        
        return {"success": True}
    
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": str(e)}


if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("🚀 游戏数据分析引擎 Web 服务启动中...")
    print("📍 访问地址: http://localhost:8080")
    print("📖 API文档: http://localhost:8080/api-docs")
    print("🔐 登录页面: http://localhost:8080/login")
    print("   开发环境默认账号: admin/admin123；生产环境请配置 INITIAL_ADMIN_PASSWORD")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8080)
