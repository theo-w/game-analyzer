"""Competitor workbench: genre grouping, side-by-side compare, feature matrix, MVP snapshots."""

from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from src.mvp_data import get_mvp_analysis, get_mvp_comments_and_metrics, mvp_validation_passed
from src.mvp_pipeline import DEFAULT_OUTPUT_DIR
from src.services.game_genre import infer_product_genre
from src.services.game_intel import BREAKDOWN_SECTIONS


def normalize_compare_id(value: str) -> str:
    raw = str(value or "").strip()
    if raw.startswith("steam_"):
        return raw.replace("steam_", "", 1)
    if raw.startswith("taptap_"):
        return raw.replace("taptap_", "", 1)
    if raw.startswith("google_play_"):
        return raw.replace("google_play_", "", 1)
    return raw


def resolve_compare_row(raw_id: str) -> tuple[str, str]:
    """Return (game_id, product_id) for library/MVP lookups."""
    raw = str(raw_id or "").strip()
    if not raw:
        return "", ""
    if raw.startswith(("ref_", "game_")):
        return raw, raw
    if raw.startswith("taptap_"):
        pid = normalize_compare_id(raw)
        return f"taptap_{pid}", pid
    if raw.startswith("google_play_"):
        pid = normalize_compare_id(raw)
        return f"google_play_{pid}", pid
    if raw.startswith("steam_"):
        pid = normalize_compare_id(raw)
        return f"steam_{pid}", pid
    pid = normalize_compare_id(raw)
    if pid.isdigit():
        return f"steam_{pid}", pid
    return raw, raw


def library_game_id(product_id: str, platform: str = "") -> str:
    pid = normalize_compare_id(product_id)
    if str(product_id).startswith("ref_"):
        return str(product_id)
    if str(product_id).startswith("taptap_") or str(platform).lower() == "taptap":
        return f"taptap_{pid}" if pid else str(product_id)
    if str(product_id).startswith("google_play_") or str(platform).lower() == "google_play":
        return f"google_play_{pid}" if pid else str(product_id)
    return f"steam_{pid}" if pid else str(product_id)


def _metrics_by_product(metrics: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = defaultdict(dict)
    for row in metrics:
        pid = str(row.get("product") or row.get("产品") or "")
        if not pid:
            continue
        name = str(row.get("metric") or row.get("指标") or "")
        val = row.get("值") if row.get("值") is not None else row.get("value")
        grouped[pid][name] = val
    return grouped


def _product_report_map(analysis: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    if not analysis:
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for report in analysis.get("product_reports") or []:
        pid = str(report.get("product") or "")
        if pid:
            out[pid] = report
    return out


def _truncate(text: str, limit: int = 120) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _breakdown_summary(game_id: str) -> Dict[str, str]:
    from src.services.game_intel import GameplayBreakdownRepository

    row = GameplayBreakdownRepository.get(game_id) or {}
    summary: Dict[str, str] = {}
    for key, _title, _hint in BREAKDOWN_SECTIONS:
        val = row.get(key) or ""
        summary[key] = _truncate(val, 160) if val else ""
    return summary


def build_compare_payload(
    ids: Sequence[str],
    *,
    username: Optional[str] = None,
) -> Dict[str, Any]:
    """Build side-by-side compare rows for library game_ids and/or Steam product ids."""
    comments, metrics, mvp_source = get_mvp_comments_and_metrics()
    analysis = get_mvp_analysis() if mvp_validation_passed() else None
    reports = _product_report_map(analysis)
    metric_map = _metrics_by_product(metrics)

    from src.services.game_intel import GameLibraryRepository

    items: List[Dict[str, Any]] = []
    for raw_id in ids:
        raw_id = str(raw_id).strip()
        if not raw_id:
            continue
        game_id, product_id = resolve_compare_row(raw_id)

        game = GameLibraryRepository.get(game_id)
        if not game and product_id.isdigit():
            alt_prefix = "taptap_" if game_id.startswith("steam_") else "steam_"
            game = GameLibraryRepository.get(f"{alt_prefix}{product_id}")

        name = (game or {}).get("name") or reports.get(product_id, {}).get("product_name") or product_id
        genre = (game or {}).get("genre") or infer_product_genre(product_id, name)
        report = reports.get(product_id, {})
        kpis = dict(metric_map.get(product_id, {}))
        if report:
            kpis.setdefault("样本好评率", report.get("positive_rate"))
            kpis.setdefault("样本评论数", report.get("sample_size"))

        product_comments = [
            c
            for c in comments
            if str(c.get("product") or c.get("产品") or "") == product_id
        ]
        neg = [c for c in product_comments if (c.get("sentiment") or c.get("情感")) == "negative"]
        pos = [c for c in product_comments if (c.get("sentiment") or c.get("情感")) == "positive"]

        themes = Counter()
        for theme_row in report.get("top_negative_themes") or []:
            themes[theme_row.get("theme", "other")] += int(theme_row.get("count") or 0)

        items.append(
            {
                "id": product_id,
                "game_id": game_id,
                "name": name,
                "genre": genre,
                "source": (game or {}).get("source") or mvp_source or "unknown",
                "kpis": kpis,
                "positive_rate": report.get("positive_rate"),
                "risk_level": report.get("risk_level"),
                "recommendation": report.get("recommendation"),
                "themes": [{"theme": t, "count": c} for t, c in themes.most_common(5)],
                "breakdown_summary": _breakdown_summary(game_id),
                "sample_reviews": {
                    "positive": [
                        _truncate(c.get("内容") or c.get("content") or "", 200)
                        for c in pos[:2]
                    ],
                    "negative": [
                        _truncate(c.get("内容") or c.get("content") or "", 200)
                        for c in neg[:2]
                    ],
                },
            }
        )

    data_source = mvp_source or "library"
    if username:
        from src.data_resolution import resolve_user_data_source

        data_source = resolve_user_data_source(username)

    return {
        "success": True,
        "items": items,
        "count": len(items),
        "data_source": data_source,
        "data_trust": _trust_label(data_source),
    }


def build_feature_matrix(ids: Sequence[str]) -> Dict[str, Any]:
    from src.services.game_intel import GameLibraryRepository, GameplayBreakdownRepository

    sections = [{"key": k, "title": t} for k, t, _h in BREAKDOWN_SECTIONS]
    rows: List[Dict[str, Any]] = []
    for raw_id in ids:
        raw_id = str(raw_id).strip()
        if not raw_id:
            continue
        game_id, product_id = resolve_compare_row(raw_id)
        game = GameLibraryRepository.get(game_id) or {}
        if not game and product_id.isdigit():
            alt_prefix = "taptap_" if game_id.startswith("steam_") else "steam_"
            game = GameLibraryRepository.get(f"{alt_prefix}{product_id}") or {}
        breakdown = GameplayBreakdownRepository.get(game_id) or {}
        if not breakdown and product_id.isdigit():
            alt_prefix = "taptap_" if game_id.startswith("steam_") else "steam_"
            breakdown = GameplayBreakdownRepository.get(f"{alt_prefix}{product_id}") or {}
        name = game.get("name") or product_id
        cells: Dict[str, str] = {}
        for key, _title, _hint in BREAKDOWN_SECTIONS:
            val = (breakdown.get(key) or "").strip()
            if not val:
                cells[key] = "—"
            elif len(val) < 40:
                cells[key] = "✓ " + val
            else:
                cells[key] = "✓ " + _truncate(val, 80)
        rows.append({"game_id": game_id, "name": name, "genre": game.get("genre"), "cells": cells})
    return {"success": True, "sections": sections, "rows": rows}


def _trust_label(source: str) -> Dict[str, str]:
    labels = {
        "mvp_steam": {"label": "Steam 真实数据", "level": "high", "hint": "公开商店与评论抓取"},
        "taptap_public": {"label": "TapTap 真实数据", "level": "high", "hint": "TapTap 公开评论抓取"},
        "google_play_public": {"label": "Google Play 真实数据", "level": "high", "hint": "Google Play 公开评论样本"},
        "mvp_multi": {"label": "Steam + TapTap 真实数据", "level": "high", "hint": "多平台公开评论抓取"},
        "imported": {"label": "用户导入", "level": "high", "hint": "来自您上传的数据集"},
        "cached": {"label": "缓存数据", "level": "medium", "hint": "24 小时内采集缓存"},
        "mock": {"label": "演示数据", "level": "low", "hint": "仅用于功能演示，不可作商业结论"},
        "empty": {
            "label": "暂无数据",
            "level": "low",
            "hint": "请先在分析向导抓取竞品，或导入 CSV",
        },
    }
    return labels.get(source, {"label": source, "level": "medium", "hint": ""})


def data_provenance_payload(username: str) -> Dict[str, Any]:
    from src.data_resolution import resolve_user_data_source

    source = resolve_user_data_source(username)
    trust = _trust_label(source)
    show_mock_warning = source in ("mock", "empty")
    return {
        "success": True,
        "source": source,
        "trust": trust,
        "show_mock_warning": show_mock_warning,
        "collapse_demo_metrics": source in ("mvp_steam", "imported"),
    }


def save_mvp_snapshot(
    analysis: Dict[str, Any],
    output_dir: str = DEFAULT_OUTPUT_DIR,
) -> Optional[str]:
    """Persist a dated MVP analysis snapshot for timeline replay."""
    if not analysis:
        return None
    snapshots_dir = os.path.join(output_dir, "snapshots")
    os.makedirs(snapshots_dir, exist_ok=True)
    captured_at = datetime.now(timezone.utc).isoformat()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    slim_reports = []
    for report in analysis.get("product_reports") or []:
        slim_reports.append(
            {
                "product": report.get("product"),
                "product_name": report.get("product_name"),
                "positive_rate": report.get("positive_rate"),
                "sample_size": report.get("sample_size"),
                "risk_level": report.get("risk_level"),
                "top_negative_themes": report.get("top_negative_themes"),
            }
        )
    payload = {
        "captured_at": captured_at,
        "summary": analysis.get("summary"),
        "product_reports": slim_reports,
    }
    path = os.path.join(snapshots_dir, f"{stamp}.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)

    index_path = os.path.join(snapshots_dir, "index.json")
    index_rows: List[Dict[str, Any]] = []
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as handle:
            index_rows = json.load(handle) or []
    index_rows.append({"id": stamp, "captured_at": captured_at, "file": f"{stamp}.json"})
    index_rows.sort(key=lambda r: r.get("captured_at") or "", reverse=True)
    with open(index_path, "w", encoding="utf-8") as handle:
        json.dump(index_rows[:50], handle, ensure_ascii=False, indent=2)
    return path


def list_mvp_snapshots(output_dir: str = DEFAULT_OUTPUT_DIR) -> List[Dict[str, Any]]:
    index_path = os.path.join(output_dir, "snapshots", "index.json")
    if not os.path.exists(index_path):
        return []
    with open(index_path, "r", encoding="utf-8") as handle:
        return json.load(handle) or []


def load_mvp_snapshot(snapshot_id: str, output_dir: str = DEFAULT_OUTPUT_DIR) -> Optional[Dict[str, Any]]:
    safe = re.sub(r"[^0-9A-Za-z]", "", snapshot_id or "")
    if not safe:
        return None
    path = os.path.join(output_dir, "snapshots", f"{safe}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def compare_snapshots(
    snapshot_a: str,
    snapshot_b: str,
    output_dir: str = DEFAULT_OUTPUT_DIR,
) -> Dict[str, Any]:
    a = load_mvp_snapshot(snapshot_a, output_dir)
    b = load_mvp_snapshot(snapshot_b, output_dir)
    if not a or not b:
        return {"success": False, "message": "快照不存在"}
    map_a = {str(r["product"]): r for r in a.get("product_reports") or []}
    map_b = {str(r["product"]): r for r in b.get("product_reports") or []}
    products = sorted(set(map_a) | set(map_b))
    deltas: List[Dict[str, Any]] = []
    for pid in products:
        ra, rb = map_a.get(pid), map_b.get(pid)
        if not ra or not rb:
            continue
        rate_a = float(ra.get("positive_rate") or 0)
        rate_b = float(rb.get("positive_rate") or 0)
        deltas.append(
            {
                "product": pid,
                "product_name": rb.get("product_name") or ra.get("product_name"),
                "positive_rate_before": rate_a,
                "positive_rate_after": rate_b,
                "delta": round(rate_b - rate_a, 1),
            }
        )
    deltas.sort(key=lambda x: abs(x.get("delta") or 0), reverse=True)
    return {
        "success": True,
        "snapshot_a": {"id": snapshot_a, "captured_at": a.get("captured_at")},
        "snapshot_b": {"id": snapshot_b, "captured_at": b.get("captured_at")},
        "deltas": deltas,
    }


ANALYSIS_FRAMEWORK = {
    "competitor_analysis": [
        "界定竞品圈：同品类、同平台、相近商业模式",
        "产品档案：品类、核心循环、付费模型、版本节奏",
        "市场表现：规模、排名、增长（有数据时）",
        "用户口碑：评分、评论主题、正负向证据",
        "横向对比：KPI + 功能矩阵",
        "机会威胁：SWOT / 预警",
        "可执行建议：版本、运营、投放（附复测指标）",
    ],
    "breakdown_sections": [
        {"key": k, "title": t, "hint": h} for k, t, h in BREAKDOWN_SECTIONS
    ],
    "data_review": [
        "选定时间窗口与产品范围",
        "对比核心 KPI 与口碑指标变化",
        "归因：版本、活动、舆情事件",
        "输出复盘结论与下一轮实验假设",
    ],
}
