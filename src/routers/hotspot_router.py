"""行业热点文章存档页（只读）。

降级处置（2026-09-19）：依上线前预设阈值（30 天自然访问 <10 且搜索展示 <100）
停止 AI 生成，页面转为静态存档并加溯源说明。原生成链路（选题发现、AI 润色、
AI 生成、自定义选题、归档写入）已移除，完整实现见 git 历史。
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from src.services.analysis_archive import AnalysisArchiveRepository
from src.web_common import get_current_user
from src.web_constants import BASE_DIR

router = APIRouter(tags=["hotspot"])


def _read_template(name: str) -> str:
    path = os.path.join(BASE_DIR, "templates", name)
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


@router.get("/hotspot", response_class=HTMLResponse)
async def hotspot_page():
    return _read_template("hotspot.html")


@router.get("/api/hotspot/archive")
async def list_hotspot_archive(
    request: Request,
    token: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    user = await get_current_user(request, token)
    articles = AnalysisArchiveRepository.list_hotspot_articles(user.username, limit=limit)
    return {
        "success": True,
        "articles": articles,
        "total": AnalysisArchiveRepository.count_hotspot_articles(user.username),
    }


@router.post("/api/hotspot/generate")
async def hotspot_generate_disabled():
    """AI 生成已按降级处置停用，保留端点以给出明确语义（410 Gone）。"""
    raise HTTPException(
        status_code=410,
        detail=(
            "AI 文章生成已于 2026-09-19 依预设阈值停用"
            "（上线后 30 天自然访问 <10 且搜索展示 <100，触发降级处置）。"
            "已有文章转为静态存档，可在 /hotspot 查看。"
        ),
    )
