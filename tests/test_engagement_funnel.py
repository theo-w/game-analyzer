import os
from src.services.engagement_funnel import (
    build_review_engagement_journey,
    resolve_journey_for_product,
)

def _steam_comment(product, playtime, positive=True):
    return {
        "product": product,
        "playtime_forever_minutes": playtime,
        "playtime_last_two_weeks_minutes": 120 if playtime > 0 else 0,
        "情绪": "positive" if positive else "negative",
        "voted_up": positive,
    }

def _mobile_comment(product, score, text="good game"):
    return {
        "product": product,
        "score": score,
        "rating": score,
        "内容": text,
        "情绪": "positive" if score >= 4 else "negative",
    }

def test_review_journey_differs_per_product():
    comments = [
        _steam_comment("730", 3000, True) for _ in range(8)
    ] + [
        _steam_comment("730", 0, False),
        _steam_comment("730", 1500, True),
    ]
    comments += [
        _steam_comment("570", 8000, True) for _ in range(5)
    ] + [
        _steam_comment("570", 500, False) for _ in range(5)
    ]

    j730, basis730, simulated730 = resolve_journey_for_product("730", comments, [])
    j570, basis570, simulated570 = resolve_journey_for_product("570", comments, [])

    assert simulated730 is False
    assert basis730 == "review_engagement"
    assert simulated570 is False

    nodes730 = {n["name"]: n for n in j730["nodes"]}
    nodes570 = {n["name"]: n for n in j570["nodes"]}
    assert nodes730["评论样本"]["count"] == 10
    assert nodes570["评论样本"]["count"] == 10
    assert nodes730["核心玩家(≥20h)"]["conversion_rate"] != nodes570["核心玩家(≥20h)"]["conversion_rate"]

def test_mobile_review_journey_uses_rating_steps():
    comments = [
        _mobile_comment("com.a", 5, "great game with smooth controls"),
        _mobile_comment("com.a", 4, "pretty good overall experience"),
        _mobile_comment("com.a", 2, "bad"),
        _mobile_comment("com.a", 5, "love it"),
        _mobile_comment("com.a", 3, "ok"),
    ]
    journey = build_review_engagement_journey("com.a", comments)
    assert journey is not None
    names = [node["name"] for node in journey["nodes"]]
    assert names[0] == "评论样本"
    assert "有效评分" in names
    assert journey["summary"]["data_basis"] == "review_engagement"

def test_imported_metric_funnel_from_named_metrics():
    from src.services.engagement_funnel import build_metric_funnel

    metrics = [
        {"product": "game_a", "metric": "用户总下载量", "值": 10000},
        {"product": "game_a", "metric": "注册用户", "值": 7200},
        {"product": "game_a", "metric": "新手教程完成", "值": 5400},
        {"product": "game_a", "metric": "首次战斗用户", "值": 4100},
        {"product": "game_a", "metric": "首次付费用户", "值": 900},
    ]
    funnel = build_metric_funnel("game_a", metrics)
    assert funnel is not None
    assert funnel["data_basis"] == "imported_metrics"
    assert funnel["steps"][0]["count"] == 10000
    assert funnel["steps"][-1]["count"] == 900
    assert funnel["steps"][1]["conversion_from_prev"] == 72.0
