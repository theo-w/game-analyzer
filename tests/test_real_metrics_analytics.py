import os
from src.services.real_metrics_analytics import (
    build_realtime_from_data,
    build_review_weekly_cohort,
    resolve_realtime_for_product,
)

def _comment(product, date, score=5, playtime=3000):
    return {
        "product": product,
        "日期": date,
        "score": score,
        "rating": score,
        "情绪": "positive" if score >= 4 else "negative",
        "playtime_forever_minutes": playtime,
        "内容": "good game with enough detail for analysis",
    }

def test_realtime_uses_weekly_review_trend():
    comments = [
        _comment("730", "2026-05-01", 5),
        _comment("730", "2026-05-02", 4),
        _comment("730", "2026-05-10", 2),
        _comment("730", "2026-05-11", 5),
        _comment("730", "2026-05-12", 5),
    ]
    payload = build_realtime_from_data("730", comments, [])
    assert payload is not None
    assert payload["data_basis"] == "review_sample"
    assert payload["review_sample_count"] == 5
    assert len(payload["revenue_trend"]) >= 1
    assert payload["online_users"] is None
    assert payload["chart_metric"] == "reviews"

def test_weekly_cohort_differs_by_product_engagement():
    comments = [
        _comment("730", "2026-05-01", 5, 5000),
        _comment("730", "2026-05-02", 5, 4000),
        _comment("730", "2026-05-03", 5, 4500),
        _comment("730", "2026-05-04", 4, 3500),
        _comment("730", "2026-05-05", 5, 4200),
        _comment("730", "2026-05-06", 5, 4100),
        _comment("730", "2026-05-07", 4, 3900),
        _comment("730", "2026-05-08", 5, 5000),
        _comment("570", "2026-05-01", 2, 100),
        _comment("570", "2026-05-02", 2, 50),
        _comment("570", "2026-05-03", 3, 80),
        _comment("570", "2026-05-04", 2, 60),
        _comment("570", "2026-05-05", 1, 0),
        _comment("570", "2026-05-06", 2, 20),
        _comment("570", "2026-05-07", 2, 10),
        _comment("570", "2026-05-08", 1, 0),
    ]
    c730 = build_review_weekly_cohort("730", comments)
    c570 = build_review_weekly_cohort("570", comments)
    assert c730 and c570
    assert c730["summary"]["avg_retention_d7"] != c570["summary"]["avg_retention_d7"]

def test_resolve_realtime_returns_mock_when_empty():
    payload, basis, simulated = resolve_realtime_for_product("730", [], [])
    assert payload is None
    assert simulated is True
    assert basis == "mock_data"
