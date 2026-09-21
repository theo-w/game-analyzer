"""Game library & gameplay breakdown routes."""

from __future__ import annotations

import os
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from src.database import OperationLogRepository
from src.services.game_intel import (
    BUSINESS_MODELS,
    GENRE_PRESETS,
    GameLibraryRepository,
    GameplayBreakdownRepository,
    _template_breakdown_for_genre,
    get_game_detail,
    seed_default_library,
    sync_library_from_mvp,
)
from src.services.game_versions import GameVersionRepository, VERSION_CHANGE_TYPES
from src.services.game_versions import (
    import_versions_from_mvp_signals,
    import_versions_from_steam_news,
    parse_version_import_text,
)
from src.services.game_intel_ai import generate_breakdown_with_ai
from src.services.llm_client import llm_is_configured
from src.web_common import get_current_user
from src.web_constants import BASE_DIR

router = APIRouter(tags=["game-intel"])


@router.get("/games/library", response_class=HTMLResponse)
async def game_library_page():
    path = os.path.join(BASE_DIR, "templates", "game_library.html")
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


@router.get("/api/games/library/meta")
async def library_meta(token: Optional[str] = Query(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    await get_current_user(token)
    return {
        "success": True,
        "genres": GENRE_PRESETS,
        "business_models": BUSINESS_MODELS,
        "llm_configured": llm_is_configured(),
    }


@router.get("/api/games/library")
async def list_library(
    token: Optional[str] = Query(None),
    genre: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    user = await get_current_user(token)
    games = GameLibraryRepository.list_games(
        username=user.username,
        genre=genre,
        search=search,
    )
    return {"success": True, "games": games, "total": len(games)}


@router.get("/api/games/library/{game_id}")
async def get_library_item(game_id: str, token: Optional[str] = Query(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    await get_current_user(token)
    detail = get_game_detail(game_id)
    if not detail:
        raise HTTPException(status_code=404, detail="游戏不存在")
    return {"success": True, **detail}


@router.post("/api/games/library")
async def create_library_item(
    request: Request,
    token: Optional[str] = Query(None),
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    user = await get_current_user(token)
    body = await request.json()
    if not body.get("name"):
        raise HTTPException(status_code=400, detail="游戏名称不能为空")

    game_id = GameLibraryRepository.create({**body, "username": user.username})
    if body.get("breakdown"):
        GameplayBreakdownRepository.upsert(game_id, body["breakdown"])
    elif not GameplayBreakdownRepository.get(game_id):
        GameplayBreakdownRepository.upsert(
            game_id,
            _template_breakdown_for_genre(body.get("genre", ""), body["name"]),
        )

    OperationLogRepository.log(user.username, "game_library_create", f"Created {game_id}")
    return {"success": True, "game_id": game_id}


@router.put("/api/games/library/{game_id}")
async def update_library_item(
    game_id: str,
    request: Request,
    token: Optional[str] = Query(None),
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    user = await get_current_user(token)
    if not GameLibraryRepository.get(game_id):
        raise HTTPException(status_code=404, detail="游戏不存在")

    body = await request.json()
    GameLibraryRepository.update(game_id, body)
    if body.get("breakdown"):
        GameplayBreakdownRepository.upsert(game_id, body["breakdown"])

    OperationLogRepository.log(user.username, "game_library_update", f"Updated {game_id}")
    return {"success": True}


@router.delete("/api/games/library/{game_id}")
async def delete_library_item(game_id: str, token: Optional[str] = Query(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    user = await get_current_user(token)
    if not GameLibraryRepository.get(game_id):
        raise HTTPException(status_code=404, detail="游戏不存在")
    GameLibraryRepository.soft_delete(game_id)
    OperationLogRepository.log(user.username, "game_library_delete", f"Deleted {game_id}")
    return {"success": True}


@router.put("/api/games/library/{game_id}/breakdown")
async def save_breakdown(
    game_id: str,
    request: Request,
    token: Optional[str] = Query(None),
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    user = await get_current_user(token)
    if not GameLibraryRepository.get(game_id):
        raise HTTPException(status_code=404, detail="游戏不存在")
    body = await request.json()
    body["auto_generated"] = False
    GameplayBreakdownRepository.upsert(game_id, body)
    OperationLogRepository.log(user.username, "gameplay_breakdown_save", game_id)
    return {"success": True}


@router.post("/api/games/library/{game_id}/breakdown/generate-ai")
async def generate_ai_breakdown(
    game_id: str,
    request: Request,
    token: Optional[str] = Query(None),
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    user = await get_current_user(token)
    if not GameLibraryRepository.get(game_id):
        raise HTTPException(status_code=404, detail="游戏不存在")

    body: dict = {}
    try:
        body = await request.json()
    except Exception:
        body = {}

    result = await generate_breakdown_with_ai(
        game_id,
        refine=bool(body.get("refine")),
        save=body.get("save", True),
        current_breakdown=body.get("current_breakdown"),
    )
    if result.get("success"):
        OperationLogRepository.log(
            user.username,
            "gameplay_breakdown_ai",
            f"{game_id} llm={result.get('using_llm')}",
        )
    return result


@router.post("/api/games/library/sync-mvp")
async def sync_mvp_library(token: Optional[str] = Query(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    user = await get_current_user(token)
    result = sync_library_from_mvp(user.username)
    if result.get("success"):
        OperationLogRepository.log(user.username, "game_library_sync_mvp", str(result))
    return result


@router.post("/api/games/library/seed")
async def seed_library(token: Optional[str] = Query(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    await get_current_user(token)
    seed_default_library()
    games = GameLibraryRepository.list_games()
    return {"success": True, "total": len(games)}


@router.get("/api/games/library/{game_id}/versions")
async def list_game_versions(game_id: str, token: Optional[str] = Query(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    await get_current_user(token)
    if not GameLibraryRepository.get(game_id):
        raise HTTPException(status_code=404, detail="游戏不存在")
    return {
        "success": True,
        "versions": GameVersionRepository.list_for_game(game_id),
        "change_types": VERSION_CHANGE_TYPES,
    }


@router.post("/api/games/library/{game_id}/versions")
async def create_game_version(
    game_id: str,
    request: Request,
    token: Optional[str] = Query(None),
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    user = await get_current_user(token)
    if not GameLibraryRepository.get(game_id):
        raise HTTPException(status_code=404, detail="游戏不存在")
    body = await request.json()
    if not body.get("version_label"):
        raise HTTPException(status_code=400, detail="版本号不能为空")
    version_id = GameVersionRepository.create(game_id, body)
    OperationLogRepository.log(user.username, "game_version_create", f"{game_id}:{version_id}")
    return {"success": True, "version_id": version_id}


@router.put("/api/games/library/{game_id}/versions/{version_id}")
async def update_game_version(
    game_id: str,
    version_id: str,
    request: Request,
    token: Optional[str] = Query(None),
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    user = await get_current_user(token)
    row = GameVersionRepository.get(version_id)
    if not row or row.get("game_id") != game_id:
        raise HTTPException(status_code=404, detail="版本记录不存在")
    body = await request.json()
    GameVersionRepository.update(version_id, body)
    OperationLogRepository.log(user.username, "game_version_update", version_id)
    return {"success": True}


@router.delete("/api/games/library/{game_id}/versions/{version_id}")
async def delete_game_version(
    game_id: str,
    version_id: str,
    token: Optional[str] = Query(None),
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    user = await get_current_user(token)
    row = GameVersionRepository.get(version_id)
    if not row or row.get("game_id") != game_id:
        raise HTTPException(status_code=404, detail="版本记录不存在")
    GameVersionRepository.delete(version_id)
    OperationLogRepository.log(user.username, "game_version_delete", version_id)
    return {"success": True}


@router.post("/api/games/library/{game_id}/versions/import")
async def import_game_versions(
    game_id: str,
    request: Request,
    token: Optional[str] = Query(None),
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    user = await get_current_user(token)
    game = GameLibraryRepository.get(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="游戏不存在")
    body = await request.json()
    mode = body.get("mode") or "paste"
    created: List[str] = []
    if mode == "paste":
        for row in parse_version_import_text(body.get("text") or ""):
            created.append(GameVersionRepository.create(game_id, row))
    elif mode == "mvp_signals":
        pid = body.get("product_id") or game.get("steam_app_id") or game_id.replace("steam_", "", 1)
        created = import_versions_from_mvp_signals(game_id, str(pid))
    elif mode == "steam_news":
        pid = body.get("product_id") or game.get("steam_app_id") or game_id.replace("steam_", "", 1)
        result = import_versions_from_steam_news(game_id, str(pid), max_items=int(body.get("max_items") or 8))
        created = result.get("created") or []
        if not created and result.get("error"):
            return {
                "success": True,
                "created": 0,
                "version_ids": [],
                "warning": result.get("error"),
                "fetched": result.get("fetched", 0),
            }
        return {
            "success": True,
            "created": len(created),
            "version_ids": created,
            "skipped": result.get("skipped", 0),
            "fetched": result.get("fetched", 0),
        }
    else:
        raise HTTPException(status_code=400, detail="mode 应为 paste、mvp_signals 或 steam_news")
    OperationLogRepository.log(user.username, "game_version_import", f"{game_id}:{len(created)}")
    return {"success": True, "created": len(created), "version_ids": created}
