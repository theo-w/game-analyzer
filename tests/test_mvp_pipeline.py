import os
from src.mvp_pipeline import analyze_actual_steam_data, run_mvp_pipeline, validate_analysis

class FakeSteamCrawler:
    def crawl(self, app_ids, max_reviews_per_app, review_days=0, **kwargs):
        return {
            "source": "steam_public",
            "app_ids": list(app_ids),
            "games": [{"app_id": "10", "name": "Counter-Strike"}],
            "comments": [
                {
                    "product": "10",
                    "product_name": "Counter-Strike",
                    "platform": "Steam",
                    "情绪": "positive",
                    "内容": "Great team game.",
                },
                {
                    "product": "10",
                    "product_name": "Counter-Strike",
                    "platform": "Steam",
                    "情绪": "negative",
                    "内容": "Matchmaking has too many cheaters and bad servers.",
                },
            ],
            "metrics": [
                {
                    "product": "10",
                    "platform": "Steam",
                    "source": "steam_public",
                    "metric": "抓取评论数",
                    "值": 2,
                }
            ],
            "errors": [],
        }

def test_analyze_actual_steam_data_counts_are_deterministic():
    comments = FakeSteamCrawler().crawl(["10"], 2)["comments"]
    metrics = FakeSteamCrawler().crawl(["10"], 2)["metrics"]

    analysis = analyze_actual_steam_data(comments, metrics)
    report = analysis["product_reports"][0]

    assert analysis["summary"]["total_comments"] == 2
    assert report["sample_size"] == 2
    assert report["positive_reviews"] == 1
    assert report["negative_reviews"] == 1
    assert report["positive_rate"] == 50.0
    assert report["top_negative_themes"][0]["theme"] == "performance"
    assert analysis["ai_strategy"]["peer_comparison"][0]["product"] == "10"
    assert analysis["ai_strategy"]["user_needs"]
    assert analysis["ai_strategy"]["prioritized_actions"]

def test_validate_analysis_recomputes_counts_from_source_rows():
    dataset = FakeSteamCrawler().crawl(["10"], 2)
    analysis = analyze_actual_steam_data(dataset["comments"], dataset["metrics"])

    validation = validate_analysis(dataset["comments"], dataset["metrics"], analysis)

    assert validation["passed"] is True
    assert all(check["passed"] for check in validation["checks"])
    assert any(check["name"] == "ai_strategy_grounded" for check in validation["checks"])

def test_run_mvp_pipeline_writes_artifacts(tmp_path):
    result = run_mvp_pipeline(
        app_ids=["10"],
        max_reviews_per_app=2,
        output_dir=str(tmp_path),
        crawler=FakeSteamCrawler(),
        use_max_reviews=True,
    )

    assert result["success"] is True
    assert result["artifacts"]["dataset"].endswith("steam_dataset.json")
    assert (tmp_path / "steam_dataset.json").exists()
    assert (tmp_path / "analysis.json").exists()
    assert (tmp_path / "validation.json").exists()
