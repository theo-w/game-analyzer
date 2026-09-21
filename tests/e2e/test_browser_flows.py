"""Playwright browser E2E: login, dashboard, compare, library, pricing, team."""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.helpers import login, wait_dashboard_ready

pytestmark = pytest.mark.browser


def test_login_dashboard_kpis(page: Page) -> None:
    login(page, redirect_path="/dashboard")
    wait_dashboard_ready(page)
    expect(page.locator("#product-select option")).not_to_have_count(0, timeout=15_000)


def test_compare_workbench_loads_cards(page: Page) -> None:
    login(page, redirect_path="/dashboard")
    page.goto("/games/compare")
    expect(page.locator("h1")).to_contain_text("竞品分析")

    expect(page.locator("#game-picker option")).not_to_have_count(0, timeout=15_000)
    expect(page.locator("#compare-grid article.card, #compare-grid .card")).not_to_have_count(
        0, timeout=20_000
    )


def test_compare_ai_report_tab(page: Page) -> None:
    login(page, redirect_path="/dashboard")
    page.goto("/games/compare")
    expect(page.locator("#game-picker option")).not_to_have_count(0, timeout=15_000)
    expect(page.locator("#compare-grid article.card, #compare-grid .card")).not_to_have_count(
        0, timeout=20_000
    )

    page.get_by_role("button", name=re.compile(r"AI 总结")).click()
    expect(page.locator("#panel-ai")).to_be_visible()
    page.locator("#btn-gen-ai").click()
    expect(page.locator("#ai-status")).to_contain_text(
        re.compile(r"规则报告|AI 报告|生成失败"), timeout=25_000
    )
    page.wait_for_function(
        """() => {
            const el = document.getElementById('ai-report-output');
            if (!el) return false;
            return (el.innerHTML || '').includes('sr-result')
                || (el.innerHTML || '').includes('sr-section')
                || (el.innerHTML || '').includes('sr-empty');
        }""",
        timeout=25_000,
    )
    expect(page.locator("#ai-report-output")).not_to_contain_text("生成失败")


def test_game_library_lists_entries(page: Page) -> None:
    login(page, redirect_path="/dashboard")
    page.goto("/games/library")
    expect(page.locator("#game-list .game-item").first).to_be_visible(timeout=15_000)


def test_pricing_shows_api_remaining(page: Page) -> None:
    login(page, redirect_path="/dashboard")
    page.goto("/pricing")
    expect(page.locator("#currentPlan")).to_be_visible(timeout=15_000)
    expect(page.locator("#apiQuota")).to_contain_text(re.compile(r"\d+ / \d+|无限制"))
    expect(page.locator("#demo-payment-notice")).to_be_visible()
    expect(page.locator("#demo-payment-notice")).to_contain_text(re.compile(r"演示"))


def test_team_page_after_login(page: Page) -> None:
    login(page, redirect_path="/dashboard")
    page.goto("/team")
    expect(page.locator("h1")).to_contain_text("团队协作")
    expect(page.locator("#team-list")).to_be_visible(timeout=15_000)
