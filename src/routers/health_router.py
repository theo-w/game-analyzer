"""Health check endpoint for deploy probes."""

from __future__ import annotations

import os
from datetime import datetime

from fastapi import APIRouter

from src.database import demo_accounts_enabled, config_manager
from src.commercial_config import commercial_status_payload, production_startup_warnings
from src.db_dialect import resolve_database_backend

router = APIRouter(tags=["health"])

APP_VERSION = os.getenv("APP_VERSION", "1.0.0")


@router.get("/api/health")
async def health_check():
    app_env = os.getenv("APP_ENV", "development").lower()
    allow_demo = demo_accounts_enabled()
    db_type, _ = resolve_database_backend(config_manager)
    commercial = commercial_status_payload()
    return {
        "status": "ok",
        "service": "game_analyzer",
        "version": APP_VERSION,
        "environment": app_env,
        "database_type": db_type,
        "demo_accounts_enabled": allow_demo and app_env != "production",
        "deploy_profile": commercial.get("deploy_profile"),
        "payment_mode": commercial.get("payment_mode"),
        "production_warnings": production_startup_warnings(),
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
