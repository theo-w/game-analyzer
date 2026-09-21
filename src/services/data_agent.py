"""数据 Agent 管道: 爬取结果 -> 清洗(去水军) -> LLM标签 -> embedding -> Supabase存储 -> 聚合。

设计:
- 输入: 用户 MVP 数据集 JSON 或任意 {games, comments, metrics} 字典
- 步骤可独立开关: clean / label / embed / store / aggregate
- 每步幂等(按 review_id upsert); LLM/embedding/Supabase 不可用时自动降级,
  保证管道在任何环境可跑通
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.mvp_pipeline import DEFAULT_OUTPUT_DIR

PLATFORM_MAP = {
    "steam": "steam", "taptap": "taptap", "google play": "google_play",
    "googleplay": "google_play", "app store": "app_store", "appstore": "app_store",
}


def normalize_platform(raw: Any) -> str:
    return PLATFORM_MAP.get(str(raw or "").strip().lower(), str(raw or "steam").strip().lower())


def _pick(review: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in review and review[key] not in (None, ""):
            return review[key]
    return default


def review_content(review: Dict[str, Any]) -> str:
    return str(_pick(review, "内容", "content", "text", "comment", default="") or "")


def review_rating(review: Dict[str, Any]) -> Optional[float]:
    val = _pick(review, "评分", "rating", "score", "star", "stars")
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def review_author(review: Dict[str, Any]) -> str:
    return str(_pick(review, "作者", "author", "user", "username", "nickname", default="") or "")


def review_date(review: Dict[str, Any]) -> str:
    return str(_pick(review, "日期", "时间", "review_date", "date", "timestamp", default="") or "")


def review_product(review: Dict[str, Any]) -> str:
    return str(_pick(review, "product", "app_id", "game_id", "product_id", default="") or "")


def review_product_name(review: Dict[str, Any]) -> str:
    return str(_pick(review, "product_name", "name", "game", "title", default="") or "")


def stable_review_id(review: Dict[str, Any]) -> str:
    content = review_content(review)
    key = "|".join([
        review_product(review),
        normalize_platform(review.get("platform")),
        review_author(review),
        content.strip()[:500],
        review_date(review),
    ])
    digest = hashlib.md5(key.encode("utf-8")).hexdigest()[:16]
    return f"rev_{digest}"


def normalize_review(review: Dict[str, Any], idx: int = 0) -> Dict[str, Any]:
    """把中英文键评论归一化为内部结构(保留 raw 原始字段)。"""
    return {
        "review_id": stable_review_id(review),
        "game_id": review_product(review),
        "platform": normalize_platform(review.get("platform")),
        "author": review_author(review),
        "title": str(_pick(review, "标题", "title", default="") or ""),
        "content": review_content(review),
        "lang": str(_pick(review, "语言", "lang", "language", default="") or ""),
        "rating": review_rating(review),
        "helpful": int(_pick(review, "有帮助", "helpful", "likes", default=0) or 0),
        "review_date": review_date(review),
        "raw": {k: v for k, v in review.items() if k not in ("内容", "content", "text")},
    }


# ---------------------------------------------------------------------------
# 数据集加载
# ---------------------------------------------------------------------------

def resolve_dataset(username: str = "") -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    base = os.path.abspath(DEFAULT_OUTPUT_DIR)
    candidates: List[str] = []
    if username:
        candidates += [
            os.path.join(base, "users", username, "steam_dataset.json"),
            os.path.join(base, "users", username, "dataset.json"),
            os.path.join(base, f"{username}.json"),
        ]
    candidates += [
        os.path.join(base, "steam_dataset.json"),
        os.path.join(base, "dataset.json"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    return json.load(handle), path
            except (OSError, ValueError):
                continue
    return None, None


def _save_dataset(dataset: Dict[str, Any], path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(dataset, handle, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 管道
# ---------------------------------------------------------------------------

def _review_records(dataset: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_reviews = dataset.get("comments") or []
    return [normalize_review(r, i) for i, r in enumerate(raw_reviews)]


async def run_data_agent(
    username: str = "",
    dataset_path: str = "",
    *,
    steps: Optional[List[str]] = None,
    use_llm: bool = True,
    embed_batch: int = 64,
    save_back: bool = True,
) -> Dict[str, Any]:
    """运行 Agent 管道, 返回分步统计与聚合结果。"""
    from src.services import supabase_store
    from src.services.noise_detector import apply_noise_flags, detect_noise
    from src.services.review_labeler import label_reviews
    from src.services.theme_clustering import cluster_reviews, llm_theme_for_cluster

    steps = steps or ["clean", "label", "embed", "cluster", "store", "aggregate"]
    dataset = None
    path = dataset_path
    if path:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                dataset = json.load(handle)
        except (OSError, ValueError) as exc:
            return {"success": False, "error": f"数据集读取失败: {exc}"}
    if dataset is None:
        dataset, path = resolve_dataset(username)
        if dataset is None:
            return {"success": False, "error": f"未找到用户 {username or '默认'} 的数据集,请先抓取"}

    reviews = _review_records(dataset)
    games = dataset.get("games") or []
    metrics = dataset.get("metrics") or []
    report: Dict[str, Any] = {
        "success": True,
        "username": username or "default",
        "dataset_path": path,
        "source_reviews": len(reviews),
        "games": len(games),
        "steps": {},
    }

    # 1) clean
    if "clean" in steps:
        flags = await detect_noise(reviews, embeddings=None, use_llm=use_llm)
        apply_noise_flags(reviews, flags)
        noise_count = sum(1 for r in reviews if r.get("is_noise"))
        report["steps"]["clean"] = {
            "total": len(reviews),
            "noise": noise_count,
            "clean": len(reviews) - noise_count,
            "flags_by_type": dict(Counter(f["flag_type"] for f in flags)),
        }
        report["noise_flags"] = flags

    # 2) label
    labels: List[Dict[str, Any]] = []
    if "label" in steps:
        try:
            labels = await label_reviews(reviews, batch_size=30)
        except Exception as exc:
            labels = []
            report["steps"]["label"] = {"error": str(exc)}
        by_id = {l["review_id"]: l for l in labels}
        for review in reviews:
            label = by_id.get(review["review_id"]) or {}
            review["label"] = label
        report["steps"]["label"] = {
            "labeled": len(labels),
            "sentiment": dict(Counter((l.get("sentiment") or "neutral") for l in labels)),
        }

    # 3) embed
    embeddings: Dict[str, List[float]] = {}
    if "embed" in steps:
        try:
            from src.services.llm_client import embed_texts

            to_embed = [r for r in reviews if r.get("content", "").strip()]
            for i in range(0, len(to_embed), embed_batch):
                batch = to_embed[i : i + embed_batch]
                vectors = await embed_texts([r["content"] for r in batch])
                for review, vec in zip(batch, vectors):
                    embeddings[review["review_id"]] = list(vec)
            report["steps"]["embed"] = {"embedded": len(embeddings), "dim": _embed_dim()}
        except Exception as exc:
            report["steps"]["embed"] = {"error": str(exc), "embedded": len(embeddings)}

    # 4) cluster: 基于向量聚类 + LLM 提炼主题(在 LLM 标签之后, 聚合之前)
    clusters: List[Dict[str, Any]] = []
    theme_rows: List[Dict[str, Any]] = []
    if "cluster" in steps and embeddings:
        try:
            clusters = cluster_reviews(reviews, embeddings)
            for cluster in clusters:
                theme = await llm_theme_for_cluster(reviews, cluster)
                theme_rows.append({
                    **cluster,
                    "theme_name": theme.get("theme_name"),
                    "description": theme.get("description"),
                    "key_issues": theme.get("key_issues") or [],
                })
            report["steps"]["cluster"] = {
                "clusters": len(clusters),
                "members": sum(c.get("member_count", 0) for c in clusters),
            }
        except Exception as exc:
            report["steps"]["cluster"] = {"error": str(exc)}

    # 5) store -> Supabase
    if "store" in steps and supabase_store.enabled():
        try:
            supabase_store.ensure_schema()
            game_rows = [
                {
                    "game_id": g.get("app_id") or g.get("game_id") or str(g.get("id", "")),
                    "platform": normalize_platform(g.get("platform", "steam")),
                    "name": g.get("name") or g.get("product_name") or "unknown",
                    "genre": g.get("genre"),
                    "metadata": g,
                }
                for g in games
            ]
            review_rows = [
                {**r, "username": username or None}
                for r in reviews
            ]
            metric_rows = [
                {
                    "game_id": m.get("product") or m.get("app_id") or m.get("game_id") or "",
                    "platform": normalize_platform(m.get("platform", "steam")),
                    "metric_date": str(m.get("date") or m.get("日期") or ""),
                    "metric_type": str(m.get("metric") or m.get("指标") or "unknown"),
                    "value": _to_float(m.get("值") or m.get("value")),
                    "raw": m,
                }
                for m in metrics
            ]
            stats = supabase_store.write_batch(
                games=game_rows,
                reviews=review_rows,
                labels=labels,
                embeddings=[
                    {"review_id": rid, "embedding": vec, "model": "default"}
                    for rid, vec in embeddings.items()
                ],
                noise_flags=report.get("noise_flags") or [],
                metrics=metric_rows,
                theme_clusters=theme_rows,
            )
            report["steps"]["store"] = stats
        except Exception as exc:
            report["steps"]["store"] = {"error": str(exc)}
    elif "store" in steps:
        report["steps"]["store"] = {"error": "SUPABASE_DATABASE_URL 未配置,跳过存储"}

    # 5) aggregate
    if "aggregate" in steps or True:
        clean_reviews = [r for r in reviews if not r.get("is_noise")]
        sent = Counter((r.get("label") or {}).get("sentiment") for r in clean_reviews)
        topics = Counter()
        for r in clean_reviews:
            for t in (r.get("label") or {}).get("topics", []):
                topics[t] += 1
        ratings = [r["rating"] for r in clean_reviews if r.get("rating") is not None]
        report["aggregate"] = {
            "clean_reviews": len(clean_reviews),
            "noise_reviews": len(reviews) - len(clean_reviews),
            "sentiment": {k: v for k, v in sent.items() if k},
            "top_topics": topics.most_common(10),
            "avg_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
            "clusters": [
                {
                    "cluster_id": c.get("cluster_id"),
                    "theme_name": c.get("theme_name"),
                    "description": c.get("description"),
                    "key_issues": c.get("key_issues"),
                    "member_count": c.get("member_count"),
                    "avg_similarity": c.get("avg_similarity"),
                    "representative_review_id": c.get("representative_review_id"),
                }
                for c in theme_rows
            ],
        }

    # 6) 写回数据集(供现有报告/看板消费 is_noise/label)
    if save_back and path:
        original = dataset.get("comments") or []
        norm_by_raw = {}
        for review, raw in zip(reviews, original):
            norm_by_raw[id(raw)] = review
        updated_comments = []
        for raw in original:
            norm = norm_by_raw.get(id(raw))
            if norm:
                raw["is_noise"] = bool(norm.get("is_noise"))
                raw["noise_reasons"] = norm.get("noise_reasons", [])
                raw["noise_flags"] = norm.get("noise_flags", [])
                if norm.get("label"):
                    raw["label"] = norm["label"]
            updated_comments.append(raw)
        dataset["comments"] = updated_comments
        dataset["agent"] = {
            "processed_at": _now_iso(),
            "steps": list(steps),
            "summary": report.get("aggregate", {}),
        }
        if theme_rows:
            dataset["themes"] = [
                {k: c.get(k) for k in ("cluster_id", "theme_name", "description", "key_issues", "member_count", "avg_similarity")}
                for c in theme_rows
            ]
        try:
            _save_dataset(dataset, path)
            report["saved_back"] = True
        except OSError as exc:
            report["saved_back"] = False
            report["save_back_error"] = str(exc)

    return report


def _embed_dim() -> int:
    try:
        return int(os.getenv("EMBEDDING_DIM", "1536").strip())
    except ValueError:
        return 1536


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
