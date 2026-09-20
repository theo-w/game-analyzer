"""Resolve comments/metrics for API handlers (imported > MVP > cached > mock)."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

from src.database import ImportedDataRepository
from src.data_catalog import metrics_dataset_usable
from src.mvp_data import get_mvp_comments_and_metrics, mvp_validation_passed, record_product
from src.services.mvp_storage import resolve_mvp_output_dir

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "..", "mock_data")

TEST_ONLY_PRODUCTS = frozenset({"test", "demo", "unknown"})


def load_data(file_path: str) -> Any:
    try:
        with open(file_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            if isinstance(data, list):
                return data
            raise ValueError("Data loaded is not a list.")
    except FileNotFoundError:
        print(f"错误：找不到文件 {file_path}")
        return None
    except json.JSONDecodeError as exc:
        print(f"错误：JSON解析失败，请检查 {file_path} 文件。错误信息: {exc}")
        return None


def get_comments_data() -> List[Dict]:
    data = load_data(os.path.join(DATA_DIR, "comments.json"))
    return data or []


def get_metrics_data() -> List[Dict]:
    data = load_data(os.path.join(DATA_DIR, "metrics.json"))
    return data or []


METRIC_REPO_EXCLUDED = (
    "id",
    "username",
    "created_at",
    "installs",
    "revenue",
    "active_users",
    "sessions",
    "avg_session_duration",
    "retention_1d",
    "retention_7d",
    "retention_30d",
)

COMMENT_REPO_EXCLUDED = (
    "id",
    "username",
    "created_at",
    "review_id",
    "rating",
    "title",
    "content",
    "author",
    "date",
    "helpful_count",
    "sentiment",
)


def _normalize_export_value(key: str, value: Any) -> Any:
    if key == "值" and isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _strip_repo_fields(records: List[Dict], excluded_keys: Tuple[str, ...]) -> List[Dict]:
    filtered: List[Dict] = []
    for record in records:
        filtered_record = {
            key: _normalize_export_value(key, value)
            for key, value in record.items()
            if key not in excluded_keys
            and value is not None
            and value != ""
            and value not in (0, 0.0)
        }
        filtered.append(filtered_record)
    return filtered


def _product_ids_in_records(records: List[Dict]) -> set:
    return {record_product(row) for row in records if record_product(row)}


def comments_dataset_usable(records: List[Dict[str, Any]]) -> bool:
    if not records:
        return False
    products = _product_ids_in_records(records)
    if not products or products <= TEST_ONLY_PRODUCTS:
        return False
    return True


def cached_metrics_usable(records: List[Dict[str, Any]]) -> bool:
    if not records:
        return False
    if metrics_dataset_usable(records):
        return True
    products = _product_ids_in_records(records)
    return bool(products - TEST_ONLY_PRODUCTS)


def resolve_user_dataset(username: str) -> Tuple[str, List[Dict], List[Dict]]:
    """用户数据集单一解析入口, 返回 (来源标签, comments, metrics)。

    优先级 imported > mvp > cached > empty; 标签与数据在同一次解析中产生,
    避免 source 标注与实际数据口径漂移。
    """
    imported_comments = ImportedDataRepository.get_comments(username)
    imported_metrics = ImportedDataRepository.get_metrics(username)

    mvp_source: Optional[str] = None
    mvp_comments: List[Dict] = []
    mvp_metrics: List[Dict] = []
    if not imported_comments or not imported_metrics:
        mvp_comments, mvp_metrics, mvp_source = get_mvp_comments_and_metrics(
            resolve_mvp_output_dir(username)
        )

    if imported_comments or imported_metrics:
        source = "imported"
    elif mvp_source:
        source = mvp_source
    else:
        cached_metrics = ImportedDataRepository.get_cached_metrics(max_age_hours=24)
        cached_comments = ImportedDataRepository.get_cached_comments(max_age_hours=24)
        source = (
            "cached"
            if (cached_comments and comments_dataset_usable(cached_comments))
            or (cached_metrics and cached_metrics_usable(cached_metrics))
            else "empty"
        )

    if imported_comments:
        comments: List[Dict] = _strip_repo_fields(imported_comments, COMMENT_REPO_EXCLUDED)
    elif mvp_source and mvp_comments:
        comments = _apply_noise_filter(mvp_comments)
    else:
        cached = ImportedDataRepository.get_cached_comments(max_age_hours=24)
        comments = (
            _apply_noise_filter(_strip_repo_fields(cached, ("id", "cached_at")))
            if cached and comments_dataset_usable(cached)
            else []
        )

    if imported_metrics:
        metrics: List[Dict] = _strip_repo_fields(imported_metrics, METRIC_REPO_EXCLUDED)
    elif mvp_source and mvp_metrics:
        metrics = mvp_metrics
    else:
        cached = ImportedDataRepository.get_cached_metrics(max_age_hours=24)
        metrics = (
            _strip_repo_fields(cached, ("id", "cached_at"))
            if cached and cached_metrics_usable(cached)
            else []
        )

    return source, comments, metrics


def resolve_user_data_source(username: str) -> str:
    return resolve_user_dataset(username)[0]


def get_user_comments_data(username: str) -> List[Dict]:
    return resolve_user_dataset(username)[1]


def get_user_metrics_data(username: str) -> List[Dict]:
    return resolve_user_dataset(username)[2]


def _noise_exclusion_enabled() -> bool:
    return os.getenv("REPORT_EXCLUDE_NOISE", "false").strip().lower() in {"1", "true", "yes", "on"}


def _apply_noise_filter(comments):
    """REPORT_EXCLUDE_NOISE=true 时剔除被 Agent 标记为水军/噪音的评论。"""
    if not _noise_exclusion_enabled():
        return comments
    out = []
    for c in comments or []:
        if not (isinstance(c, dict) and c.get("is_noise")):
            out.append(c)
    return out
