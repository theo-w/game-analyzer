import json
import os
import pytest

from src.mvp_data import (
    build_mvp_report_payload,
    get_mvp_comments_and_metrics,
    mvp_validation_passed,
)
from src.mvp_pipeline import analyze_actual_steam_data, validate_analysis
from tests.test_mvp_pipeline import FakeSteamCrawler

@pytest.fixture
def mvp_artifacts(tmp_path):
    dataset = FakeSteamCrawler().crawl(["10"], 2)
    analysis = analyze_actual_steam_data(dataset["comments"], dataset["metrics"])
    validation = validate_analysis(dataset["comments"], dataset["metrics"], analysis)
    for name, payload in (
        ("steam_dataset.json", dataset),
        ("analysis.json", analysis),
        ("validation.json", validation),
    ):
        with open(tmp_path / name, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
    return tmp_path

def test_mvp_validation_and_dataset(tmp_path, mvp_artifacts):
    assert mvp_validation_passed(str(mvp_artifacts)) is True
    comments, metrics, source = get_mvp_comments_and_metrics(str(mvp_artifacts))
    assert source in {"mvp_steam", "steam_public"}
    assert len(comments) == 2
    assert len(metrics) >= 1

def test_build_mvp_report_payload(tmp_path, mvp_artifacts):
    comments, metrics, _ = get_mvp_comments_and_metrics(str(mvp_artifacts))
    report = build_mvp_report_payload(comments, metrics, str(mvp_artifacts))
    assert report["mode"] == "mvp_steam"
    assert report["validation_passed"] is True
    assert report["product_reports"]
