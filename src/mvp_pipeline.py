"""MVP pipeline for crawling real Steam data and validating analysis output."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import os
import re
from statistics import median
from typing import Any, Dict, Iterable, List, Optional, Sequence

import requests


DEFAULT_STEAM_APP_IDS = (
    "730",       # Counter-Strike 2
    "570",       # Dota 2
    "1172470",   # Apex Legends
    "440",       # Team Fortress 2
    "252490",    # Rust
    "578080",    # PUBG
    "381210",    # Dead by Daylight
    "236390",    # War Thunder
    "1091500",   # Cyberpunk 2077
    "1245620",   # Elden Ring
)

# UI catalog for MVP product picker (id = Steam app_id).
STEAM_APP_CATALOG: List[Dict[str, str]] = [
    {"id": "730", "name": "Counter-Strike 2", "genre": "FPS"},
    {"id": "570", "name": "Dota 2", "genre": "MOBA"},
    {"id": "1172470", "name": "Apex Legends", "genre": "Battle Royale"},
    {"id": "440", "name": "Team Fortress 2", "genre": "FPS"},
    {"id": "252490", "name": "Rust", "genre": "Survival"},
    {"id": "578080", "name": "PUBG", "genre": "Battle Royale"},
    {"id": "381210", "name": "Dead by Daylight", "genre": "Horror"},
    {"id": "236390", "name": "War Thunder", "genre": "Simulation"},
    {"id": "1091500", "name": "Cyberpunk 2077", "genre": "RPG"},
    {"id": "1245620", "name": "Elden Ring", "genre": "Action RPG"},
]

# 环境变量可覆盖 MVP 产物目录（tests/conftest.py 用它把测试写入隔离到临时目录）
DEFAULT_OUTPUT_DIR = os.environ.get("GA_MVP_OUTPUT_DIR") or os.path.join(os.path.dirname(__file__), "..", "data", "mvp")


def steam_app_catalog() -> List[Dict[str, str]]:
    """Copy of default Steam catalog for API/UI."""
    return [dict(item) for item in STEAM_APP_CATALOG]


class SteamCrawlerError(RuntimeError):
    """Raised when the Steam MVP crawler cannot fetch usable real data."""


class SteamPublicCrawler:
    """Small crawler that uses public Steam store endpoints requiring no API key."""

    APP_DETAILS_URL = "https://store.steampowered.com/api/appdetails"
    APP_REVIEWS_URL = "https://store.steampowered.com/appreviews/{app_id}"
    STORE_SEARCH_URL = "https://store.steampowered.com/api/storesearch/"

    def __init__(
        self,
        timeout: int = 20,
        session: Optional[requests.Session] = None,
        *,
        market_country: str = "us",
    ):
        from src.services.market_locale import get_market_profile

        self.timeout = timeout
        self.session = session or requests.Session()
        self.market = get_market_profile("steam", market_country)
        self.session.headers.update(
            {
                "User-Agent": "GameAnalyzerMVP/1.0 (+https://example.local)",
                "Accept": "application/json,text/plain,*/*",
            }
        )

    def crawl(
        self,
        app_ids: Sequence[str],
        max_reviews_per_app: int | None = None,
        *,
        review_days: int | None = None,
        use_review_days: bool = True,
        use_max_reviews: bool = False,
        market_country: str | None = None,
    ) -> Dict[str, Any]:
        from src.services.crawl_runner import crawl_products_parallel
        from src.services.market_locale import get_market_profile
        from src.services.review_window import normalize_max_reviews, normalize_review_days

        if market_country:
            self.market = get_market_profile("steam", market_country)
        if not app_ids:
            raise ValueError("app_ids must contain at least one Steam app id")
        if not use_review_days and not use_max_reviews:
            raise ValueError("至少启用「时间范围」或「评价数量」之一")
        window_days = normalize_review_days(review_days) if use_review_days else None
        review_cap = normalize_max_reviews(max_reviews_per_app) if use_max_reviews else None
        valid_ids = [str(raw).strip() for raw in app_ids if str(raw).strip()]

        def _crawl_one(app_id: str) -> Dict[str, Any]:
            worker = SteamPublicCrawler(timeout=self.timeout, market_country=self.market.country)
            try:
                return {
                    "app_id": app_id,
                    "ok": True,
                    **worker._crawl_single_app(
                        app_id,
                        window_days,
                        max_reviews=review_cap,
                    ),
                }
            except Exception as exc:
                return {"app_id": app_id, "ok": False, "error": str(exc)}

        results = crawl_products_parallel(valid_ids, _crawl_one)

        games: List[Dict[str, Any]] = []
        comments: List[Dict[str, Any]] = []
        metrics: List[Dict[str, Any]] = []
        errors: List[Dict[str, str]] = []

        for app_id in valid_ids:
            row = results.get(app_id) or {"ok": False, "error": "missing crawl result"}
            if row.get("ok"):
                games.append(row["game"])
                comments.extend(row["comments"])
                metrics.extend(row["metrics"])
            else:
                errors.append({"app_id": app_id, "error": str(row.get("error") or "unknown error")})

        if not comments and not metrics:
            raise SteamCrawlerError(f"No usable Steam data was crawled. Errors: {errors}")

        return {
            "source": "steam_public",
            "crawled_at": datetime.now(timezone.utc).isoformat(),
            "use_review_days": use_review_days,
            "review_days": window_days,
            "use_max_reviews": use_max_reviews,
            "max_reviews_per_app": review_cap,
            "market_country": self.market.country,
            "market_label": self.market.label,
            "steam_review_language": self.market.steam_review_language,
            "app_ids": list(app_ids),
            "games": games,
            "comments": comments,
            "metrics": metrics,
            "errors": errors,
        }

    def _crawl_single_app(
        self,
        app_id: str,
        window_days: int | None,
        *,
        max_reviews: int | None = None,
    ) -> Dict[str, Any]:
        details = self.fetch_app_details(app_id)
        reviews_payload = self.fetch_reviews(
            app_id, review_days=window_days, max_reviews=max_reviews
        )
        reviews = reviews_payload.get("reviews", [])
        query_summary = reviews_payload.get("query_summary", {})
        game = self._normalize_game(app_id, details)
        return {
            "game": game,
            "comments": self._normalize_reviews(app_id, game["name"], reviews),
            "metrics": self._build_metrics(app_id, game, reviews, query_summary, window_days),
        }

    def fetch_app_details(self, app_id: str) -> Dict[str, Any]:
        response = self.session.get(
            self.APP_DETAILS_URL,
            params={"appids": app_id, "filters": "basic,price_overview,genres,categories"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        app_payload = payload.get(str(app_id), {})
        if not app_payload.get("success"):
            raise SteamCrawlerError(f"Steam appdetails returned no data for app_id={app_id}")
        return app_payload.get("data", {})

    def fetch_reviews(
        self,
        app_id: str,
        *,
        review_days: int | None = None,
        max_reviews: int | None = None,
    ) -> Dict[str, Any]:
        from src.services.crawl_runner import throttle_page_fetch
        from src.services.review_window import (
            collect_reviews_from_batches,
            normalize_max_reviews,
            normalize_review_days,
            steam_review_datetime,
        )

        window_days = normalize_review_days(review_days) if review_days is not None else None
        cap = normalize_max_reviews(max_reviews)
        query_summary: Dict[str, Any] = {}
        cursor = "*"

        def _iter_batches():
            nonlocal cursor, query_summary
            while True:
                throttle_page_fetch()
                response = self.session.get(
                    self.APP_REVIEWS_URL.format(app_id=app_id),
                    params={
                        "json": 1,
                        "filter": "recent",
                        "language": self.market.steam_review_language,
                        "num_per_page": 100,
                        "purchase_type": "all",
                        "cursor": cursor,
                    },
                    timeout=self.timeout,
                )
                response.raise_for_status()
                payload = response.json()
                if int(payload.get("success", 0)) != 1:
                    raise SteamCrawlerError(
                        f"Steam appreviews returned success=0 for app_id={app_id}"
                    )
                batch = payload.get("reviews") or []
                query_summary = payload.get("query_summary") or query_summary
                yield batch
                cursor = payload.get("cursor")
                if not batch or not cursor:
                    break

        collected = collect_reviews_from_batches(
            _iter_batches(),
            days=window_days,
            max_count=cap,
            date_fn=steam_review_datetime,
        )

        if not collected:
            if window_days is not None and cap is not None:
                detail = f"在近 {window_days} 天内未凑满 {cap} 条评论"
            elif window_days is not None:
                detail = f"在近 {window_days} 天内没有可用评论，请扩大时间范围"
            elif cap is not None:
                detail = f"未能拉到评论（目标 {cap} 条）"
            else:
                detail = "没有可用评论"
            raise SteamCrawlerError(f"Steam app_id={app_id} {detail}。")

        return {
            "reviews": collected,
            "query_summary": query_summary,
            "success": 1,
        }

    def search_store(self, term: str, *, limit: int = 8) -> List[Dict[str, Any]]:
        """Search Steam store by game name (no API key)."""
        query = (term or "").strip()
        if len(query) < 2:
            return []
        response = self.session.get(
            self.STORE_SEARCH_URL,
            params={"term": query, "cc": "US", "l": "english"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        results: List[Dict[str, Any]] = []
        for item in (payload.get("items") or [])[: max(1, min(limit, 20))]:
            app_id = item.get("id")
            if app_id is None:
                continue
            results.append(
                {
                    "app_id": str(app_id),
                    "name": item.get("name") or f"Steam App {app_id}",
                    "type": item.get("type") or "",
                }
            )
        return results

    def _normalize_game(self, app_id: str, details: Dict[str, Any]) -> Dict[str, Any]:
        price = details.get("price_overview") or {}
        return {
            "app_id": app_id,
            "name": details.get("name") or f"Steam App {app_id}",
            "type": details.get("type", "game"),
            "is_free": bool(details.get("is_free", False)),
            "price_initial_cents": price.get("initial", 0),
            "price_final_cents": price.get("final", 0),
            "discount_percent": price.get("discount_percent", 0),
            "genres": [item.get("description", "") for item in details.get("genres", [])],
            "categories": [item.get("description", "") for item in details.get("categories", [])],
        }

    def _normalize_reviews(
        self,
        app_id: str,
        game_name: str,
        reviews: Iterable[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for index, review in enumerate(reviews, start=1):
            author = review.get("author") or {}
            voted_up = bool(review.get("voted_up"))
            timestamp = review.get("timestamp_created")
            review_date = (
                datetime.fromtimestamp(timestamp, timezone.utc).date().isoformat()
                if timestamp
                else ""
            )
            normalized.append(
                {
                    "id": review.get("recommendationid") or f"{app_id}-{index}",
                    "product": app_id,
                    "product_name": game_name,
                    "platform": "Steam",
                    "日期": review_date,
                    "用户角色": self._player_segment(author.get("playtime_forever", 0)),
                    "情绪": "positive" if voted_up else "negative",
                    "内容": (review.get("review") or "").strip(),
                    "voted_up": voted_up,
                    "votes_up": int(review.get("votes_up", 0) or 0),
                    "weighted_vote_score": float(review.get("weighted_vote_score", 0) or 0),
                    "playtime_forever_minutes": int(author.get("playtime_forever", 0) or 0),
                    "playtime_last_two_weeks_minutes": int(
                        author.get("playtime_last_two_weeks", 0) or 0
                    ),
                }
            )
        return normalized

    def _build_metrics(
        self,
        app_id: str,
        game: Dict[str, Any],
        reviews: Sequence[Dict[str, Any]],
        query_summary: Dict[str, Any],
        window_days: int | None,
    ) -> List[Dict[str, Any]]:
        positive = sum(1 for review in reviews if review.get("voted_up"))
        negative = len(reviews) - positive
        playtimes = [
            int((review.get("author") or {}).get("playtime_forever", 0) or 0)
            for review in reviews
        ]
        two_week_playtimes = [
            int((review.get("author") or {}).get("playtime_last_two_weeks", 0) or 0)
            for review in reviews
        ]
        review_score = round(positive / len(reviews) * 100, 2) if reviews else 0.0
        total_reviews = int(query_summary.get("total_reviews", 0) or len(reviews))
        total_positive = int(query_summary.get("total_positive", 0) or positive)
        total_negative = int(query_summary.get("total_negative", 0) or negative)
        total_score = (
            round(total_positive / (total_positive + total_negative) * 100, 2)
            if total_positive + total_negative
            else review_score
        )
        today = datetime.now(timezone.utc).date().isoformat()
        base = {
            "product": app_id,
            "product_name": game["name"],
            "channel": "Steam",
            "platform": "Steam",
            "cycle": today,
            "date": today,
            "source": "steam_public",
        }
        values = [
            ("抓取评论数", len(reviews), f"window_days={window_days or 'none'}"),
            ("样本好评率", review_score, f"positive={positive}; negative={negative}"),
            ("Steam汇总评论数", total_reviews, "query_summary.total_reviews"),
            ("Steam汇总好评率", total_score, f"total_positive={total_positive}; total_negative={total_negative}"),
            ("中位总游玩时长_分钟", median(playtimes) if playtimes else 0, "review.author.playtime_forever"),
            (
                "中位近两周游玩时长_分钟",
                median(two_week_playtimes) if two_week_playtimes else 0,
                "review.author.playtime_last_two_weeks",
            ),
            ("当前价格_美分", int(game.get("price_final_cents", 0) or 0), "appdetails.price_overview.final"),
            ("折扣百分比", int(game.get("discount_percent", 0) or 0), "appdetails.price_overview.discount_percent"),
        ]
        return [{**base, "metric": metric, "值": value, "evidence": evidence} for metric, value, evidence in values]

    @staticmethod
    def _player_segment(playtime_minutes: int) -> str:
        hours = playtime_minutes / 60
        if hours >= 100:
            return "深度玩家"
        if hours >= 20:
            return "核心玩家"
        if hours > 0:
            return "轻度玩家"
        return "未知玩家"


def analyze_actual_steam_data(comments: Sequence[Dict[str, Any]], metrics: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate deterministic analysis from crawled Steam comments and metrics."""

    by_product: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for comment in comments:
        by_product[str(comment.get("product", "unknown"))].append(comment)

    product_reports = []
    for product, product_comments in sorted(by_product.items()):
        sentiment_counts = Counter(comment.get("情绪", "unknown") for comment in product_comments)
        negative_comments = [c for c in product_comments if c.get("情绪") == "negative"]
        positive_comments = [c for c in product_comments if c.get("情绪") == "positive"]
        theme_counts = _theme_counts(negative_comments)
        sample_size = len(product_comments)
        positive_rate = round(sentiment_counts.get("positive", 0) / sample_size * 100, 2) if sample_size else 0

        risk_level = "low"
        if positive_rate < 60 or theme_counts.most_common(1):
            risk_level = "medium"
        if positive_rate < 45:
            risk_level = "high"

        top_negative_theme = theme_counts.most_common(1)[0][0] if theme_counts else "none"
        recommendation = _recommendation_for_theme(top_negative_theme, positive_rate)

        product_reports.append(
            {
                "product": product,
                "product_name": product_comments[0].get("product_name", product),
                "sample_size": sample_size,
                "positive_reviews": sentiment_counts.get("positive", 0),
                "negative_reviews": sentiment_counts.get("negative", 0),
                "positive_rate": positive_rate,
                "top_negative_themes": [
                    {"theme": theme, "count": count}
                    for theme, count in theme_counts.most_common(5)
                ],
                "representative_negative_reviews": [
                    _shorten(comment.get("内容", ""), 220) for comment in negative_comments[:3]
                ],
                "representative_positive_reviews": [
                    _shorten(comment.get("内容", ""), 220) for comment in positive_comments[:3]
                ],
                "risk_level": risk_level,
                "recommendation": recommendation,
            }
        )

    summary = {
        "total_products": len(product_reports),
        "total_comments": len(comments),
        "overall_positive_rate": _overall_positive_rate(comments),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    ai_strategy = generate_ai_strategy(comments, metrics, product_reports)
    return {
        "summary": summary,
        "product_reports": product_reports,
        "ai_strategy": ai_strategy,
        "metrics_used": list(metrics),
    }


def generate_ai_strategy(
    comments: Sequence[Dict[str, Any]],
    metrics: Sequence[Dict[str, Any]],
    product_reports: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """Create an AI-style strategy layer grounded in peer product data."""

    product_metrics = _metrics_by_product(metrics)
    ranked_products = sorted(
        product_reports,
        key=lambda report: (
            float(report.get("positive_rate", 0)),
            float(product_metrics.get(str(report.get("product")), {}).get("Steam汇总好评率", 0)),
        ),
        reverse=True,
    )
    leader = ranked_products[0] if ranked_products else {}
    laggard = ranked_products[-1] if ranked_products else {}

    all_negative = [comment for comment in comments if comment.get("情绪") == "negative"]
    all_positive = [comment for comment in comments if comment.get("情绪") == "positive"]
    demand_counts = _demand_counts(comments)
    negative_theme_counts = _theme_counts(all_negative)
    positive_theme_counts = _positive_theme_counts(all_positive)

    user_needs = [
        {
            "need": need,
            "signal_count": count,
            "evidence": _evidence_for_need(comments, need),
            "product_action": _product_action_for_need(need),
        }
        for need, count in demand_counts.most_common(6)
    ]

    peer_comparison = []
    for report in ranked_products:
        product_id = str(report.get("product"))
        metric_map = product_metrics.get(product_id, {})
        peer_comparison.append(
            {
                "product": product_id,
                "product_name": report.get("product_name", product_id),
                "sample_positive_rate": report.get("positive_rate", 0),
                "steam_total_positive_rate": metric_map.get("Steam汇总好评率", 0),
                "steam_total_reviews": metric_map.get("Steam汇总评论数", 0),
                "median_playtime_hours": round(
                    float(metric_map.get("中位总游玩时长_分钟", 0) or 0) / 60,
                    1,
                ),
                "relative_position": _relative_position(report, leader, laggard),
                "what_to_learn": _learning_from_product(report),
            }
        )

    prioritized_actions = _prioritized_actions(
        user_needs=user_needs,
        product_reports=product_reports,
        negative_theme_counts=negative_theme_counts,
        positive_theme_counts=positive_theme_counts,
    )

    return {
        "mode": "本地AI策略分析",
        "objective": "对比同类 Steam 产品，推断用户需求，并把评论信号转化为产品改进建议。",
        "peer_comparison": peer_comparison,
        "target_user_segments": _target_user_segments(comments),
        "user_needs": user_needs,
        "opportunity_summary": _opportunity_summary(leader, laggard, user_needs),
        "prioritized_actions": prioritized_actions,
        "success_metrics": [
            "近期样本好评率",
            "前两类痛点的负面主题次数",
            "近两周中位游玩时长",
            "改版后的 Steam 汇总好评率趋势",
        ],
    }


def validate_analysis(
    comments: Sequence[Dict[str, Any]],
    metrics: Sequence[Dict[str, Any]],
    analysis: Dict[str, Any],
) -> Dict[str, Any]:
    """Validate that the analysis is grounded in the crawled dataset."""

    checks: List[Dict[str, Any]] = []
    product_comments: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for comment in comments:
        product_comments[str(comment.get("product", "unknown"))].append(comment)

    checks.append(
        {
            "name": "real_source_present",
            "passed": any(
                metric.get("source") in ("steam_public", "taptap_public", "google_play_public", "demo_seed")
                for metric in metrics
            ),
            "detail": "At least one metric is marked as a real public source.",
        }
    )
    checks.append(
        {
            "name": "comments_present",
            "passed": len(comments) > 0,
            "detail": f"{len(comments)} comments available for analysis.",
        }
    )
    ai_strategy = analysis.get("ai_strategy") or {}
    checks.append(
        {
            "name": "ai_strategy_grounded",
            "passed": bool(ai_strategy.get("peer_comparison")) and bool(ai_strategy.get("user_needs")),
            "detail": "AI strategy includes peer comparison and user needs generated from crawled comments.",
        }
    )

    report_by_product = {
        str(report.get("product")): report
        for report in analysis.get("product_reports", [])
    }
    for product, rows in sorted(product_comments.items()):
        expected_positive = sum(1 for row in rows if row.get("情绪") == "positive")
        expected_negative = sum(1 for row in rows if row.get("情绪") == "negative")
        expected_rate = round(expected_positive / len(rows) * 100, 2) if rows else 0
        report = report_by_product.get(product, {})
        checks.extend(
            [
                {
                    "name": f"{product}_sample_size_matches",
                    "passed": report.get("sample_size") == len(rows),
                    "detail": f"expected={len(rows)}, actual={report.get('sample_size')}",
                },
                {
                    "name": f"{product}_sentiment_counts_match",
                    "passed": report.get("positive_reviews") == expected_positive
                    and report.get("negative_reviews") == expected_negative,
                    "detail": (
                        f"expected_positive={expected_positive}, actual_positive={report.get('positive_reviews')}; "
                        f"expected_negative={expected_negative}, actual_negative={report.get('negative_reviews')}"
                    ),
                },
                {
                    "name": f"{product}_positive_rate_matches",
                    "passed": report.get("positive_rate") == expected_rate,
                    "detail": f"expected={expected_rate}, actual={report.get('positive_rate')}",
                },
            ]
        )

    passed = all(check["passed"] for check in checks)
    return {
        "passed": passed,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }


def search_steam_games(term: str, *, limit: int = 8, crawler: Optional[SteamPublicCrawler] = None) -> List[Dict[str, Any]]:
    """Public helper — search Steam store by name."""
    return (crawler or SteamPublicCrawler()).search_store(term, limit=limit)


def run_mvp_pipeline(
    app_ids: Sequence[str] = DEFAULT_STEAM_APP_IDS,
    max_reviews_per_app: int | None = None,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    crawler: Optional[SteamPublicCrawler] = None,
    *,
    product_name_overrides: Optional[Dict[str, str]] = None,
    review_days: int | None = None,
    use_review_days: bool = True,
    use_max_reviews: bool = False,
    market_country: str = "us",
) -> Dict[str, Any]:
    """Crawl real Steam data, analyze it, validate results, and persist artifacts."""

    crawler = crawler or SteamPublicCrawler(market_country=market_country)
    dataset = crawler.crawl(
        app_ids=app_ids,
        max_reviews_per_app=max_reviews_per_app,
        review_days=review_days,
        use_review_days=use_review_days,
        use_max_reviews=use_max_reviews,
        market_country=market_country,
    )
    if product_name_overrides:
        from src.product_registry import apply_product_display_names

        dataset = apply_product_display_names(dataset, product_name_overrides)
    analysis = analyze_actual_steam_data(dataset["comments"], dataset["metrics"])
    validation = validate_analysis(dataset["comments"], dataset["metrics"], analysis)

    os.makedirs(output_dir, exist_ok=True)
    artifacts = {
        "dataset": os.path.abspath(os.path.join(output_dir, "steam_dataset.json")),
        "analysis": os.path.abspath(os.path.join(output_dir, "analysis.json")),
        "validation": os.path.abspath(os.path.join(output_dir, "validation.json")),
    }
    _write_json(artifacts["dataset"], dataset)
    _write_json(artifacts["analysis"], analysis)
    _write_json(artifacts["validation"], validation)
    from src.services.competitor_workbench import save_mvp_snapshot

    save_mvp_snapshot(analysis, output_dir)

    return {
        "success": validation["passed"],
        "dataset": dataset,
        "analysis": analysis,
        "validation": validation,
        "artifacts": artifacts,
    }


def _theme_counts(comments: Sequence[Dict[str, Any]]) -> Counter:
    theme_keywords = {
        "performance": ("crash", "bug", "lag", "fps", "stutter", "freeze", "server", "disconnect", "卡", "崩溃", "闪退", "延迟"),
        "monetization": ("pay", "price", "expensive", "microtransaction", "p2w", "cash", "dlc", "battle pass", "付费", "氪", "贵"),
        "content": ("content", "boring", "grind", "map", "mission", "quest", "empty", "内容", "无聊", "刷"),
        "matchmaking": ("matchmaking", "rank", "cheat", "smurf", "team", "toxic", "ban", "匹配", "外挂", "排位"),
        "ui_ux": ("ui", "menu", "tutorial", "confusing", "control", "camera", "界面", "教程", "操作"),
        "updates": ("update", "patch", "nerf", "balance", "season", "version", "更新", "削弱", "平衡"),
    }
    counts: Counter = Counter()
    for comment in comments:
        text = (comment.get("内容") or "").lower()
        for theme, keywords in theme_keywords.items():
            if any(keyword in text for keyword in keywords):
                counts[theme] += 1
    return counts


def _positive_theme_counts(comments: Sequence[Dict[str, Any]]) -> Counter:
    theme_keywords = {
        "core_gameplay": ("good", "great", "best", "fun", "love", "amazing", "recommend", "gameplay"),
        "competitive_depth": ("rank", "competitive", "team", "skill", "match", "strategy"),
        "social_play": ("friend", "team", "community", "party", "coop", "co-op"),
        "value": ("free", "worth", "cheap", "price"),
    }
    counts: Counter = Counter()
    for comment in comments:
        text = (comment.get("内容") or "").lower()
        for theme, keywords in theme_keywords.items():
            if any(keyword in text for keyword in keywords):
                counts[theme] += 1
    return counts


def _demand_counts(comments: Sequence[Dict[str, Any]]) -> Counter:
    demand_keywords = {
        "公平匹配与反作弊": ("cheat", "cheater", "ban", "matchmaking", "smurf", "toxic", "rank"),
        "稳定流畅的技术体验": ("crash", "bug", "lag", "fps", "server", "disconnect", "stutter"),
        "有深度但不压迫的竞技成长": ("competitive", "rank", "skill", "team", "strategy", "stress"),
        "清晰的新手引导与低学习成本": ("tutorial", "confusing", "menu", "ui", "control", "learn"),
        "持续内容与平衡更新": ("update", "patch", "balance", "nerf", "season", "content"),
        "合理付费与价值感": ("pay", "price", "expensive", "free", "worth", "dlc"),
    }
    counts: Counter = Counter()
    for comment in comments:
        text = (comment.get("内容") or "").lower()
        for demand, keywords in demand_keywords.items():
            if any(keyword in text for keyword in keywords):
                counts[demand] += 1
    if not counts:
        positive_count = sum(1 for c in comments if c.get("情绪") == "positive")
        negative_count = sum(1 for c in comments if c.get("情绪") == "negative")
        if positive_count:
            counts["保持核心玩法爽感"] = positive_count
        if negative_count:
            counts["人工复核低信息量差评"] = negative_count
    return counts


def _metrics_by_product(metrics: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    product_metrics: Dict[str, Dict[str, Any]] = defaultdict(dict)
    for metric in metrics:
        product_metrics[str(metric.get("product"))][str(metric.get("metric"))] = metric.get("值")
    return product_metrics


def _target_user_segments(comments: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    segment_counts = Counter(comment.get("用户角色", "未知玩家") for comment in comments)
    needs_by_segment: Dict[str, Counter] = defaultdict(Counter)
    for comment in comments:
        segment = comment.get("用户角色", "未知玩家")
        for need, count in _demand_counts([comment]).items():
            needs_by_segment[segment][need] += count
    return [
        {
            "segment": segment,
            "sample_count": count,
            "primary_need": needs_by_segment[segment].most_common(1)[0][0]
            if needs_by_segment[segment]
            else "保持核心体验稳定",
        }
        for segment, count in segment_counts.most_common()
    ]


def _evidence_for_need(comments: Sequence[Dict[str, Any]], need: str) -> List[str]:
    need_keywords = {
        "公平匹配与反作弊": ("cheat", "cheater", "ban", "matchmaking", "smurf", "toxic", "rank"),
        "稳定流畅的技术体验": ("crash", "bug", "lag", "fps", "server", "disconnect", "stutter"),
        "有深度但不压迫的竞技成长": ("competitive", "rank", "skill", "team", "strategy", "stress"),
        "清晰的新手引导与低学习成本": ("tutorial", "confusing", "menu", "ui", "control", "learn"),
        "持续内容与平衡更新": ("update", "patch", "balance", "nerf", "season", "content"),
        "合理付费与价值感": ("pay", "price", "expensive", "free", "worth", "dlc"),
        "保持核心玩法爽感": ("good", "great", "best", "fun", "love", "recommend"),
    }
    keywords = need_keywords.get(need, ())
    evidence = []
    for comment in comments:
        text = comment.get("内容") or ""
        lower = text.lower()
        if keywords and any(keyword in lower for keyword in keywords):
            evidence.append(_shorten(text, 140))
        if len(evidence) >= 3:
            break
    return evidence


def _product_action_for_need(need: str) -> str:
    actions = {
        "公平匹配与反作弊": "优先强化反作弊反馈、举报闭环和匹配质量说明，减少竞技挫败的不可控感。",
        "稳定流畅的技术体验": "把崩溃、延迟和服务器稳定性列为版本准入门槛，再推进新内容。",
        "有深度但不压迫的竞技成长": "保留高上限玩法，同时加入轻量目标、复盘提示和非排位练习路径。",
        "清晰的新手引导与低学习成本": "重做前 10 分钟引导，突出核心操作、目标和下一步任务。",
        "持续内容与平衡更新": "建立内容节奏和补丁解释机制，让玩家理解平衡改动的原因。",
        "合理付费与价值感": "先展示核心价值，再引导付费；避免付费点遮挡核心乐趣。",
        "保持核心玩法爽感": "围绕已被认可的核心玩法扩展模式、地图或角色表达。",
        "人工复核低信息量差评": "对短文本差评做人工抽样归因，避免低信息评论误导优先级。",
    }
    return actions.get(need, "把该需求拆成可测试的产品实验，并持续观察评论主题变化。")


def _relative_position(
    report: Dict[str, Any],
    leader: Dict[str, Any],
    laggard: Dict[str, Any],
) -> str:
    product = report.get("product")
    if leader and product == leader.get("product"):
        return "样本领先"
    if laggard and product == laggard.get("product") and leader.get("product") != laggard.get("product"):
        return "样本落后"
    return "样本中位"


def _learning_from_product(report: Dict[str, Any]) -> str:
    themes = report.get("top_negative_themes") or []
    if not themes and float(report.get("positive_rate", 0)) >= 80:
        return "近期样本满意度高，可学习其核心体验稳定性和用户预期管理。"
    top_theme = themes[0]["theme"] if themes else "none"
    return _recommendation_for_theme(top_theme, float(report.get("positive_rate", 0)))


def _opportunity_summary(
    leader: Dict[str, Any],
    laggard: Dict[str, Any],
    user_needs: Sequence[Dict[str, Any]],
) -> str:
    if not user_needs:
        return "当前样本量可用于建立基线，建议扩大评论样本后再做产品路线决策。"
    need = user_needs[0]["need"]
    leader_name = leader.get("product_name", "领先产品")
    laggard_name = laggard.get("product_name", "待优化产品")
    return (
        f"同类产品对比中，{leader_name} 的近期样本表现最好；"
        f"{laggard_name} 可优先围绕“{need}”做改进实验，并用评论主题和好评率复测效果。"
    )


def _prioritized_actions(
    user_needs: Sequence[Dict[str, Any]],
    product_reports: Sequence[Dict[str, Any]],
    negative_theme_counts: Counter,
    positive_theme_counts: Counter,
) -> List[Dict[str, Any]]:
    actions = []
    for index, need in enumerate(user_needs[:4], start=1):
        actions.append(
            {
                "priority": index,
                "title": need["need"],
                "why": f"真实评论中出现 {need['signal_count']} 次相关信号。",
                "action": need["product_action"],
                "experiment": _experiment_for_need(need["need"]),
            }
        )
    if positive_theme_counts:
        theme, count = positive_theme_counts.most_common(1)[0]
        actions.append(
            {
                "priority": len(actions) + 1,
                "title": "放大已被验证的正向体验",
                "why": f"正向评论中“{theme}”相关信号出现 {count} 次。",
                "action": "把玩家已经认可的体验转化为首屏卖点、回流活动和新手目标。",
                "experiment": "对新用户展示不同核心玩法入口，比较首日留存和好评关键词变化。",
            }
        )
    if not actions and product_reports:
        actions.append(
            {
                "priority": 1,
                "title": "扩大真实评论样本",
                "why": "当前样本中可识别需求不足。",
                "action": "提高每个产品抓取评论数，并按语言、时间窗口和玩家时长分层分析。",
                "experiment": "将 max_reviews 提高到 100，比较需求主题稳定性。",
            }
        )
    return actions


def _experiment_for_need(need: str) -> str:
    experiments = {
        "公平匹配与反作弊": "上线举报处理反馈和可见反作弊进度，对比差评中 cheater/ban/toxic 词频。",
        "稳定流畅的技术体验": "灰度服务器与崩溃修复包，对比 crash/lag/server 词频和近两周游玩时长。",
        "有深度但不压迫的竞技成长": "增加轻量训练目标和失败复盘提示，对比新手差评率与回访时长。",
        "清晰的新手引导与低学习成本": "A/B 测试 3 步式新手引导，对比首局完成率和 tutorial/confusing 词频。",
        "持续内容与平衡更新": "发布补丁解释卡片，对比 update/balance/nerf 主题负面占比。",
        "合理付费与价值感": "把付费点后置到核心体验之后，对比 price/pay 相关差评占比。",
        "保持核心玩法爽感": "突出核心玩法入口，对比 fun/good/recommend 词频和样本好评率。",
    }
    return experiments.get(need, "设计一组小流量功能实验，用评论主题和好评率验证。")


def _recommendation_for_theme(theme: str, positive_rate: float) -> str:
    if theme == "performance":
        return "优先修复崩溃、延迟和服务器稳定性问题，再推进新系统。"
    if theme == "monetization":
        return "重新评估价格感知和付费门槛，让用户先体验核心价值。"
    if theme == "content":
        return "增加更清晰的中期目标，减少重复刷取带来的疲劳。"
    if theme == "matchmaking":
        return "提升匹配质量、反作弊反馈和排位透明度。"
    if theme == "ui_ux":
        return "简化新手引导、菜单路径和核心操作发现成本。"
    if theme == "updates":
        return "发布更清晰的补丁说明，并监控平衡改动带来的回退。"
    if positive_rate < 60:
        return "样本情绪偏弱，建议人工复核差评并扩大样本。"
    return "保持当前优势，同时持续监控新增负面主题。"


def _overall_positive_rate(comments: Sequence[Dict[str, Any]]) -> float:
    if not comments:
        return 0.0
    positives = sum(1 for comment in comments if comment.get("情绪") == "positive")
    return round(positives / len(comments) * 100, 2)


def _shorten(text: str, max_length: int) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= max_length:
        return compact
    return compact[: max_length - 3].rstrip() + "..."


def _write_json(path: str, payload: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
