"""Team collaboration management API."""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request

from src.auth import UserInDB
from src.web_common import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["teams"])

_IS_PRODUCTION = os.getenv("APP_ENV", "development").lower() == "production"


def _api_error(exc: Exception, user_msg: str = "操作失败，请稍后重试") -> str:
    logger.exception("Teams API error: %s", exc)
    return user_msg if _IS_PRODUCTION else str(exc)


def _init_team_tables():
    from src.team_management import init_team_tables
    init_team_tables()


@router.get("/api/teams")
async def get_user_teams(current_user: UserInDB = Depends(get_current_user)):
    try:
        from src.team_management import TeamRepository
        _init_team_tables()
        teams = TeamRepository.get_user_teams(current_user.username)
        return {"success": True, "teams": teams, "total": len(teams)}
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": _api_error(e)}


@router.post("/api/teams")
async def create_team(
    request: Request,
    current_user: UserInDB = Depends(get_current_user),
):
    try:
        from src.team_management import TeamRepository
        _init_team_tables()

        body = await request.json()
        team_data = {
            "name": body.get("name"),
            "description": body.get("description", ""),
            "owner_id": current_user.username,
        }

        team_id = TeamRepository.create_team(team_data)
        if team_id:
            TeamRepository.add_member(team_id, current_user.username, "admin")
            return {"success": True, "team_id": team_id, "message": "团队创建成功"}
        return {"success": False, "message": "创建团队失败"}
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": _api_error(e)}


@router.get("/api/teams/{team_id}/members")
async def get_team_members(
    team_id: int,
    current_user: UserInDB = Depends(get_current_user),
):
    try:
        from src.team_management import TeamRepository
        _init_team_tables()

        members = TeamRepository.get_team_members(team_id)
        if members is None:
            return {"success": False, "message": "团队不存在或无权访问", "members": []}
        return {"success": True, "members": members}
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": _api_error(e), "members": []}


@router.get("/api/teams/{team_id}/archives")
async def get_team_shared_archives(
    team_id: int,
    current_user: UserInDB = Depends(get_current_user),
):
    try:
        from src.team_management import init_team_tables
        from src.services.team_archives import list_team_shared_archives

        init_team_tables()
        return list_team_shared_archives(team_id, current_user.username)
    except Exception as e:
        return {"success": False, "message": _api_error(e), "archives": []}


@router.post("/api/teams/{team_id}/members")
async def add_team_member(
    team_id: int,
    request: Request,
    current_user: UserInDB = Depends(get_current_user),
):
    try:
        from src.team_management import TeamRepository
        _init_team_tables()

        role = TeamRepository.get_member_role(team_id, current_user.username)
        if role not in ["admin"]:
            raise HTTPException(status_code=403, detail="需要管理员权限")

        body = await request.json()
        success = TeamRepository.add_member(
            team_id, body.get("username"), body.get("role", "viewer")
        )
        if success:
            return {"success": True, "message": "成员添加成功"}
        return {"success": False, "message": "添加成员失败"}
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": _api_error(e)}


@router.delete("/api/teams/{team_id}/members/{username}")
async def remove_team_member(
    team_id: int,
    username: str,
    current_user: UserInDB = Depends(get_current_user),
):
    try:
        from src.team_management import TeamRepository
        _init_team_tables()

        role = TeamRepository.get_member_role(team_id, current_user.username)
        if role not in ["admin"] and current_user.username != username:
            raise HTTPException(status_code=403, detail="需要管理员权限")

        success = TeamRepository.remove_member(team_id, username)
        if success:
            return {"success": True, "message": "成员移除成功"}
        return {"success": False, "message": "移除成员失败"}
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": _api_error(e)}
