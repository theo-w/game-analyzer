"""Commercial POC flow — runs first (test_00_*) to avoid session / load interference."""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.helpers import (
    DEMO_PASSWORD,
    DEMO_USER,
    clear_auth_state,
    dismiss_onboarding,
    wait_wizard_complete,
)

pytestmark = pytest.mark.browser


def test_commercial_welcome_to_work_flow(page: Page) -> None:
    """welcome → login → guide demo → export → work guidance."""
    dismiss_onboarding(page)
    clear_auth_state(page)
    page.goto("/")
    expect(page.locator("h1")).to_contain_text("舆情分析工作台")

    page.get_by_role("button", name=re.compile(r"一键体验 Demo")).click()
    page.wait_for_url(re.compile(r"/login\?redirect=.*guide"), timeout=15_000)
    page.locator("#username").fill(DEMO_USER)
    page.locator("#password").fill(DEMO_PASSWORD)
    page.locator("#login-form button[type='submit']").click()
    page.wait_for_url(re.compile(r"/guide"), timeout=20_000)
    wait_wizard_complete(page, timeout_ms=180_000)

    expect(page.locator("#actions-card")).to_be_visible(timeout=10_000)
    expect(page.locator("#actions-table-wrap")).to_contain_text(re.compile(r"P0|P1|P2"))

    page.locator("#btn-export-actions-csv").click()

    page.goto("/work")
    expect(page.get_by_text("📋 落地指导")).to_be_visible()
    expect(page.locator(".wg-steps li")).to_have_count(4, timeout=10_000)
    expect(page.locator("#actions-root")).to_contain_text(re.compile(r"P0|P1|暂无行动"))
