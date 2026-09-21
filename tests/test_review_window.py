import os
from datetime import datetime, timedelta, timezone

from src.services.review_window import (
    collect_recent_reviews_within_days,
    collect_reviews_from_batches,
    crawl_filter_description,
    filter_raw_reviews_by_days,
    normalize_max_reviews,
    normalize_review_days,
    review_is_within_days,
    steam_review_datetime,
)

def test_normalize_review_days_accepts_allowed_values():
    assert normalize_review_days(0) == 30
    assert normalize_review_days(7) == 7
    assert normalize_review_days(14) == 14
    assert normalize_review_days(30) == 30
    assert normalize_review_days(15) == 30
    assert normalize_review_days("14") == 14

def test_filter_raw_reviews_by_days_keeps_recent_only():
    now = datetime.now(timezone.utc)
    reviews = [
        {"timestamp_created": int((now - timedelta(days=2)).timestamp())},
        {"timestamp_created": int((now - timedelta(days=20)).timestamp())},
        {"timestamp_created": int((now - timedelta(days=5)).timestamp())},
    ]
    kept = filter_raw_reviews_by_days(
        reviews, 7, date_fn=steam_review_datetime, max_count=10
    )
    assert len(kept) == 2

def test_collect_recent_reviews_stops_when_batch_is_older_than_window():
    now = datetime.now(timezone.utc)

    def batches():
        yield [
            {"timestamp_created": int((now - timedelta(days=1)).timestamp())},
            {"timestamp_created": int((now - timedelta(days=3)).timestamp())},
        ]
        yield [
            {"timestamp_created": int((now - timedelta(days=40)).timestamp())},
        ]

    collected = collect_recent_reviews_within_days(
        batches(),
        days=7,
        max_count=10,
        date_fn=steam_review_datetime,
    )
    assert len(collected) == 2

def test_review_is_within_days_rejects_missing_timestamp():
    assert review_is_within_days(None, 7) is False

def test_normalize_max_reviews_accepts_positive_only():
    assert normalize_max_reviews(0) is None
    assert normalize_max_reviews(-1) is None
    assert normalize_max_reviews(1000) == 1000
    assert normalize_max_reviews("500") == 500

def test_collect_reviews_count_only_ignores_calendar_window():
    now = datetime.now(timezone.utc)

    def batches():
        yield [
            {"timestamp_created": int((now - timedelta(days=1)).timestamp())},
            {"timestamp_created": int((now - timedelta(days=40)).timestamp())},
        ]

    collected = collect_reviews_from_batches(
        batches(),
        days=None,
        max_count=2,
        date_fn=steam_review_datetime,
    )
    assert len(collected) == 2

def test_crawl_filter_description_combines_enabled_filters():
    assert crawl_filter_description(
        use_review_days=True,
        review_days=14,
        use_max_reviews=True,
        max_reviews=1000,
    ) == "近 14 天 + 每产品最多 1000 条"
    assert crawl_filter_description(
        use_review_days=False,
        use_max_reviews=True,
        max_reviews=500,
    ) == "每产品最多 500 条"
