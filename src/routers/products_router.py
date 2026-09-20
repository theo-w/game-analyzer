"""Product management routes."""

from __future__ import annotations

from typing import Optional

import uuid

from fastapi import APIRouter, Body, HTTPException, Query

from src.database import OperationLogRepository, ProductRepository
from src.web_common import get_current_user

router = APIRouter(tags=["products"])

@router.get("/api/products/management")
async def get_products_management(token: Optional[str] = Query(None)):
    """获取产品管理信息"""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)
    
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="只有管理员可以管理产品")
    
    from src.database import ProductRepository
    
    products = ProductRepository.get_all()
    
    return {
        "success": True,
        "products": products,
        "available_platforms": ["steam", "google_play", "app_store"]
    }

@router.post("/api/products")
async def add_product(
    name: str = Body(...),
    platform: str = Body(...),
    identifier: str = Body(...),
    token: Optional[str] = Query(None)
):
    """添加新产品"""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)
    
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="只有管理员可以添加产品")
    
    from src.database import ProductRepository
    
    if platform not in {"steam", "google_play", "app_store"}:
        raise HTTPException(status_code=400, detail="不支持的平台")
    
    product_id = f"{platform}_{uuid.uuid4().hex[:8]}"
    product_data = {
        "product_id": product_id,
        "name": name,
        "description": "",
        "steam_app_id": identifier if platform == "steam" else "",
        "google_play_id": identifier if platform == "google_play" else "",
        "app_store_id": identifier if platform == "app_store" else "",
        "is_active": 1,
    }
    if not ProductRepository.create(product_data):
        raise HTTPException(status_code=500, detail="产品创建失败")
    
    OperationLogRepository.log(
        current_user.username,
        "product_add",
        f"添加产品: {name} ({platform})",
        None
    )
    
    return {"success": True, "product_id": product_id}
