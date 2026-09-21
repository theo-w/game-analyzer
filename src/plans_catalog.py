"""Single source of truth for subscription plan metadata (auth + payment + billing)."""

from __future__ import annotations

from typing import Any, Dict, List

from src.auth import PLANS, PlanConfig


def plan_to_api_dict(plan_id: str, plan: PlanConfig) -> Dict[str, Any]:
    """Shape used by /api/plans and pricing.html."""
    return {
        "id": plan_id,
        "name": plan.name,
        "price": int(plan.price),
        "features": list(plan.features),
        "description": plan.description,
        "games_limit": plan.games_limit,
        "api_quota": plan.api_quota,
    }


def list_plans_for_api() -> List[Dict[str, Any]]:
    return [plan_to_api_dict(pid, p) for pid, p in PLANS.items()]


def sync_billing_pricing_plans(pricing_plans: Dict[str, Dict[str, Any]]) -> None:
    """Align legacy billing.PRICING_PLANS limits with auth.PLANS."""
    for plan_id, cfg in PLANS.items():
        bucket = pricing_plans.get(plan_id)
        if not bucket:
            continue
        bucket["name"] = cfg.name
        bucket["description"] = cfg.description
        bucket["price"] = int(cfg.price)
        features = bucket.setdefault("features", {})
        gl = cfg.games_limit
        features["max_games"] = gl if gl >= 0 else None
        aq = cfg.api_quota
        features["api_quota_monthly"] = aq if aq >= 0 else None
