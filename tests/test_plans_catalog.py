"""Plans catalog consistency with auth.PLANS."""

from __future__ import annotations

from src.auth import PLANS
from src.plans_catalog import list_plans_for_api, sync_billing_pricing_plans


def test_list_plans_for_api_matches_auth():
    plans = list_plans_for_api()
    assert len(plans) == len(PLANS)
    by_id = {p["id"]: p for p in plans}
    for pid, cfg in PLANS.items():
        row = by_id[pid]
        assert row["name"] == cfg.name
        assert row["api_quota"] == cfg.api_quota
        assert row["games_limit"] == cfg.games_limit


def test_sync_billing_pricing_plans():
    from src.billing import PRICING_PLANS

    sync_billing_pricing_plans(PRICING_PLANS)
    pro = PRICING_PLANS["pro"]
    assert pro["features"]["max_games"] == PLANS["pro"].games_limit
    assert pro["features"]["api_quota_monthly"] == PLANS["pro"].api_quota
