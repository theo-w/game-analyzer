"""Ensure the shared demo account has offline MVP artifacts for presentations."""

from __future__ import annotations

import os

from src.database import demo_accounts_enabled
from src.mvp_data import get_mvp_comments_and_metrics
from src.services.demo_pack import write_demo_artifacts_only
from src.services.mvp_storage import resolve_mvp_output_dir


def ensure_demo_user_seed(username: str = "demo") -> bool:
    """Write offline CS2/Dota demo crawl data when the demo user has none."""
    if not demo_accounts_enabled():
        return False
    output_dir = resolve_mvp_output_dir(username)
    _, _, source = get_mvp_comments_and_metrics(output_dir)
    if source:
        return False
    write_demo_artifacts_only(output_dir)
    return True
