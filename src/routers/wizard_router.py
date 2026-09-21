"""Analysis wizard routes — one-page AppID → report flow."""

from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse

from src.database import OperationLogRepository
from src.mvp_pipeline import search_steam_games
from src.services.action_tasks import export_actions_content, normalize_action_items
from src.services.analysis_wizard import resolve_game_inputs, run_analysis_wizard
from src.services.retest_loop import retest_from_archive
from src.services.taptap_pipeline import resolve_taptap_inputs, search_taptap_games
from src.services.google_play_pipeline import resolve_google_play_inputs, search_google_play_games
from src.services.demo_pack import bootstrap_demo_pack
from src.web_common import get_current_user
from src.web_constants import BASE_DIR

router = APIRouter(tags=["wizard"])


def _read_template(name: str) -> str:
    path = os.path.join(BASE_DIR, "templates", name)
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


@router.get("/guide", response_class=HTMLResponse)
async def analysis_wizard_page():
    return _read_template("wizard.html")


@router.get("/welcome", response_class=HTMLResponse)
async def landing_page():
    return RedirectResponse(url="/", status_code=307)


@router.get("/work", response_class=HTMLResponse)
async def work_guidance_page():
    return _read_template("work.html")


@router.get("/import", response_class=HTMLResponse)
async def import_data_page():
    return _read_template("import_data.html")


@router.post("/api/wizard/export/actions")
async def wizard_export_actions(
    token: Optional[str] = Query(None),
    body: dict = Body(default_factory=dict),
    fmt: str = Query("csv", alias="format"),
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    await get_current_user(token)
    items = normalize_action_items(body.get("action_items") or (body.get("report") or {}).get("action_items"))
    if not items:
        raise HTTPException(status_code=400, detail="行动清单为空")
    title = ((body.get("report") or {}).get("title") or "actions").replace("/", "-")[:40]
    content, media_type, ext = export_actions_content(items, fmt, title=title)
    return PlainTextResponse(
        content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{title}-actions.{ext}"'},
    )


@router.post("/api/wizard/retest")
async def wizard_retest(
    token: Optional[str] = Query(None),
    body: dict = Body(default_factory=dict),
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    user = await get_current_user(token)
    archive_id = body.get("archive_id")
    if not archive_id:
        raise HTTPException(status_code=400, detail="archive_id required")
    return await retest_from_archive(
        str(archive_id),
        username=user.username,
        max_reviews=int(body.get("max_reviews") or 50),
        auto_archive=body.get("auto_archive", True) is not False,
    )


@router.get("/api/wizard/search")
async def wizard_search(
    token: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    platform: str = Query("steam"),
    limit: int = Query(8, ge=1, le=20),
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    await get_current_user(token)
    term = (q or "").strip()
    if len(term) < 2:
        return {"success": True, "results": []}
    import asyncio

    try:
        if (platform or "steam").lower() == "taptap":
            results = await asyncio.to_thread(search_taptap_games, term, limit=limit)
        elif (platform or "steam").lower() == "google_play":
            results = await asyncio.to_thread(search_google_play_games, term, limit=limit)
        else:
            results = await asyncio.to_thread(search_steam_games, term, limit=limit)
    except Exception as exc:
        return {"success": False, "message": str(exc), "results": []}
    return {"success": True, "results": results, "platform": platform}


@router.post("/api/wizard/resolve")
async def wizard_resolve(
    token: Optional[str] = Query(None),
    body: dict = Body(default_factory=dict),
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    await get_current_user(token)
    raw = body.get("app_ids") or body.get("games") or body.get("input") or ""
    plat = (body.get("platform") or "steam").lower()
    if plat == "taptap":
        return resolve_taptap_inputs(raw)
    if plat == "google_play":
        return resolve_google_play_inputs(raw)
    return resolve_game_inputs(raw)


@router.post("/api/wizard/run")
async def wizard_run(
    request: Request,
    token: Optional[str] = Query(None),
    body: dict = Body(default_factory=dict),
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    user = await get_current_user(token)

    raw_ids = body.get("app_ids") or body.get("appIds") or body.get("ids") or body.get("games") or []
    if not raw_ids:
        raise HTTPException(status_code=400, detail="请提供 1–5 个游戏名或 AppID")
    platform = (body.get("platform") or "steam").lower()

    result = await run_analysis_wizard(
        raw_ids,
        username=user.username,
        platform=platform,
        max_reviews=int(body.get("max_reviews") or 50),
        skip_crawl=bool(body.get("skip_crawl")),
        auto_archive=body.get("auto_archive", True) is not False,
    )
    OperationLogRepository.log(
        user.username,
        "analysis_wizard",
        f"platform={platform} apps={','.join(result.get('app_ids') or [])} success={result.get('success')}",
    )
    return result


@router.post("/api/wizard/export/markdown")
async def wizard_export_markdown(
    token: Optional[str] = Query(None),
    body: dict = Body(default_factory=dict),
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    await get_current_user(token)
    report = body.get("report") or {}
    md = report.get("markdown") or ""
    if not md:
        raise HTTPException(status_code=400, detail="报告 Markdown 为空")
    title = (report.get("title") or "analysis").replace("/", "-")[:60]
    return PlainTextResponse(
        content=md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{title}.md"'},
    )


@router.post("/api/demo/bootstrap")
async def demo_bootstrap(token: Optional[str] = Query(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    user = await get_current_user(token)
    result = await bootstrap_demo_pack(username=user.username)
    OperationLogRepository.log(user.username, "demo_bootstrap", str(result.get("archive_id")))
    return result


@router.get("/shared/{share_token}", response_class=HTMLResponse)
async def shared_report_page(share_token: str):
    return _read_template("shared_report.html")
