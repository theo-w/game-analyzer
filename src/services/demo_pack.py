"""Demo bootstrap: offline MVP sample + sample archive for presentations."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from src.mvp_pipeline import analyze_actual_steam_data, run_mvp_pipeline, validate_analysis
from src.services.analysis_archive import AnalysisArchiveRepository
from src.services.game_intel import seed_default_library, sync_library_from_mvp
from src.services.scenario_ai import generate_competitor_scenario_report

DEMO_APP_IDS = ["730", "570"]


class _DemoCrawler:
    """Minimal offline Steam-like dataset for demos (no network)."""

    _GAMES = {
        "730": "Counter-Strike 2",
        "570": "Dota 2",
        "1172470": "Apex Legends",
    }

    def crawl(self, app_ids: List[str], max_reviews_per_app: int = 20, review_days=None, **kwargs):
        # **kwargs: run_mvp_pipeline 会持续新增抓取参数(review_days 等),
        # 离线 demo 数据与这些参数无关, 吞掉即可避免 TypeError
        comments: List[Dict[str, Any]] = []
        metrics: List[Dict[str, Any]] = []
        for pid in app_ids:
            name = self._GAMES.get(pid, f"Steam App {pid}")
            comments.extend(
                [
                    {
                        "product": pid,
                        "product_name": name,
                        "platform": "Steam",
                        "情绪": "positive",
                        "内容": f"{name} is fun and competitive, great with friends.",
                    },
                    {
                        "product": pid,
                        "product_name": name,
                        "platform": "Steam",
                        "情绪": "negative",
                        "内容": "Too many cheaters in matchmaking and server lag issues.",
                    },
                    {
                        "product": pid,
                        "product_name": name,
                        "platform": "Steam",
                        "情绪": "negative",
                        "内容": "Recent update broke balance, need better patch notes.",
                    },
                ]
            )
            metrics.append(
                {
                    "product": pid,
                    "product_name": name,
                    "platform": "Steam",
                    "source": "steam_public",
                    "metric": "抓取评论数",
                    "值": 3,
                }
            )
            metrics.append(
                {
                    "product": pid,
                    "product_name": name,
                    "platform": "Steam",
                    "source": "steam_public",
                    "metric": "样本好评率",
                    "值": "66.7%",
                }
            )
        return {
            "source": "demo_seed",
            "app_ids": list(app_ids),
            "games": [{"app_id": p, "name": self._GAMES.get(p, p)} for p in app_ids],
            "comments": comments,
            "metrics": metrics,
            "errors": [],
        }


async def bootstrap_demo_pack(username: str = "demo", output_dir: str = None) -> Dict[str, Any]:
    """Write demo MVP artifacts, sync library, create one sample archived report."""
    from src.services.mvp_storage import resolve_mvp_output_dir

    out = output_dir or resolve_mvp_output_dir(username)
    crawler = _DemoCrawler()
    pipeline = run_mvp_pipeline(
        app_ids=DEMO_APP_IDS[:2],
        max_reviews_per_app=20,
        output_dir=out,
        crawler=crawler,
    )
    seed_default_library()
    sync = sync_library_from_mvp(username, output_dir=out)
    game_ids = [f"steam_{pid}" for pid in DEMO_APP_IDS[:2]]

    report = await generate_competitor_scenario_report(game_ids, username=username)
    archive_id = None
    if report.get("success"):
        from src.services.scenario_ai import archive_scenario_report

        archive_id = archive_scenario_report(username, report)

    return {
        "success": True,
        "mvp_validation": pipeline.get("validation", {}).get("passed"),
        "library_sync": sync,
        "game_ids": game_ids,
        "archive_id": archive_id,
        "artifacts_dir": out,
    }


def write_demo_artifacts_only(output_dir: str) -> Dict[str, Any]:
    """Sync helper: persist demo JSON without full bootstrap side effects."""
    os.makedirs(output_dir, exist_ok=True)
    dataset = _DemoCrawler().crawl(DEMO_APP_IDS[:2], 20)
    analysis = analyze_actual_steam_data(dataset["comments"], dataset["metrics"])
    validation = validate_analysis(dataset["comments"], dataset["metrics"], analysis)
    paths = {}
    for name, payload in (
        ("steam_dataset.json", dataset),
        ("analysis.json", analysis),
        ("validation.json", validation),
    ):
        path = os.path.join(output_dir, name)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        paths[name] = path
    return {"success": validation.get("passed", False), "paths": paths}
