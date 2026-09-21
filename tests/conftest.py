"""Shared pytest fixtures and hermetic test environment."""

from __future__ import annotations

import os
import tempfile

import pytest

# 把 sqlite 开发库和 MVP 产物目录重定向到临时目录。必须在模块级设置（早于 pytest
# 收集/导入任何测试模块）：database.py 在 import 时就会执行 init_database() 建表，
# mvp_pipeline.DEFAULT_OUTPUT_DIR 也在 import 时固化。
# GA_SQLITE_PATH / GA_MVP_OUTPUT_DIR 分别由 src/database.py 和 src/mvp_pipeline.py 读取。
_TEST_STATE_DIR = tempfile.mkdtemp(prefix="ga-pytest-")
os.environ["GA_SQLITE_PATH"] = os.path.join(_TEST_STATE_DIR, "game_analyzer.db")
os.environ["GA_MVP_OUTPUT_DIR"] = os.path.join(_TEST_STATE_DIR, "mvp")


@pytest.fixture(scope="session", autouse=True)
def _hermetic_test_env() -> None:
    """Disable rate limits and use isolated flags for API tests."""
    os.environ.setdefault("GA_E2E_DISABLE_RATE_LIMIT", "1")
    os.environ.setdefault("APP_ENV", "development")
    os.environ.setdefault("ALLOW_DEMO_ACCOUNTS", "true")


@pytest.fixture(scope="session", autouse=True)
def _seed_demo_dataset() -> None:
    """Offline CS2/Dota artifacts so demo APIs have tenant-scoped real data in CI."""
    from src.services.demo_seed import ensure_demo_user_seed

    ensure_demo_user_seed()


@pytest.fixture(autouse=True)
def _reset_abuse_event_tables() -> None:
    """Prevent IP/device registration limits from leaking across tests (shared SQLite)."""
    from src.database import db_manager

    for table in (
        "registration_events",
        "device_trial_claims",
        "device_accounts",
        "login_events",
    ):
        try:
            db_manager.execute(f"DELETE FROM {table}")
        except Exception:
            pass
    yield
