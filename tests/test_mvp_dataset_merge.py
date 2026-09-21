import json
import os
import tempfile

from src.services.mvp_dataset_merge import _strip_platform_products, merge_platform_dataset

def test_strip_platform_products_replaces_only_matching_gp_rows():
    existing = {
        "comments": [
            {"product": "com.a", "platform": "Google Play", "内容": "old-a"},
            {"product": "com.b", "platform": "Google Play", "内容": "keep-b"},
            {"product": "730", "platform": "Steam", "内容": "steam"},
        ],
        "metrics": [
            {"product": "com.a", "platform": "Google Play", "metric": "抓取评论数", "值": 1},
            {"product": "com.b", "platform": "Google Play", "metric": "抓取评论数", "值": 2},
        ],
        "games": [
            {"package_id": "com.a", "platform": "Google Play", "name": "A"},
            {"package_id": "com.b", "platform": "Google Play", "name": "B"},
        ],
    }
    stripped = _strip_platform_products(existing, platform="Google Play", product_ids=["com.a"])
    assert [c["内容"] for c in stripped["comments"]] == ["keep-b", "steam"]
    assert [m["product"] for m in stripped["metrics"]] == ["com.b"]
    assert [g["package_id"] for g in stripped["games"]] == ["com.b"]

def test_merge_platform_dataset_accumulates_google_play_batches():
    with tempfile.TemporaryDirectory() as tmp:
        batch_a = {
            "source": "google_play_public",
            "platform": "Google Play",
            "games": [{"package_id": "com.a", "name": "A", "platform": "Google Play"}],
            "comments": [{"product": "com.a", "platform": "Google Play", "内容": "a1", "rating": 5}],
            "metrics": [{"product": "com.a", "platform": "Google Play", "metric": "抓取评论数", "值": 1}],
            "review_counts": {"com.a": 1},
        }
        batch_b = {
            "source": "google_play_public",
            "platform": "Google Play",
            "games": [{"package_id": "com.b", "name": "B", "platform": "Google Play"}],
            "comments": [{"product": "com.b", "platform": "Google Play", "内容": "b1", "rating": 2}],
            "metrics": [{"product": "com.b", "platform": "Google Play", "metric": "抓取评论数", "值": 1}],
            "review_counts": {"com.b": 1},
        }
        merge_platform_dataset(
            batch_a,
            platform="Google Play",
            output_dir=tmp,
            platform_artifact_name="google_play_dataset.json",
        )
        merge_platform_dataset(
            batch_b,
            platform="Google Play",
            output_dir=tmp,
            platform_artifact_name="google_play_dataset.json",
        )
        with open(os.path.join(tmp, "google_play_dataset.json"), encoding="utf-8") as handle:
            payload = json.load(handle)
        products = {row["product"] for row in payload.get("comments") or []}
        assert products == {"com.a", "com.b"}
        assert len(payload.get("analysis", {}).get("product_reports") or []) == 2
