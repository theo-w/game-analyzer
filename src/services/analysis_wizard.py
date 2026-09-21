"""One-shot analysis wizard: Steam AppIDs → crawl → library → report → archive."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

from src.mvp_data import get_mvp_analysis, load_mvp_artifact, mvp_validation_passed
from src.mvp_pipeline import DEFAULT_OUTPUT_DIR, run_mvp_pipeline, search_steam_games
from src.services.taptap_pipeline import resolve_taptap_inputs, run_taptap_pipeline, search_taptap_games
from src.services.google_play_pipeline import (
    resolve_google_play_inputs,
    run_google_play_pipeline,
    search_google_play_games,
)
from src.services.competitor_workbench import library_game_id
from src.services.game_intel import sync_library_from_mvp
from src.services.mvp_storage import resolve_mvp_output_dir
from src.services.scenario_ai import (
    archive_scenario_report,
    build_action_items,
    generate_competitor_scenario_report,
)

_STEAM_APP_ID_RE = re.compile(r"^\d{1,10}$")

# Common nicknames → AppID (lowercase keys)
_STEAM_ALIASES: Dict[str, str] = {
    "cs2": "730",
    "csgo": "730",
    "counter-strike 2": "730",
    "counter strike 2": "730",
    "dota2": "570",
    "dota 2": "570",
    "apex": "1172470",
    "apex legends": "1172470",
    "pubg": "578080",
    "rust": "252490",
    "elden ring": "1245620",
    "cyberpunk": "1091500",
    "cyberpunk 2077": "1091500",
}


def split_input_tokens(raw: Sequence[str] | str) -> List[str]:
    if isinstance(raw, str):
        parts: List[str] = []
        for segment in re.split(r"[\n,;]+", raw.strip()):
            token = segment.strip()
            if token:
                parts.append(token)
        return parts
    return [str(x).strip() for x in raw if str(x).strip()]


def normalize_app_ids(raw: Sequence[str] | str) -> List[str]:
    ids: List[str] = []
    for part in split_input_tokens(raw):
        token = part
        if part.startswith("steam_"):
            token = part.replace("steam_", "", 1)
        if _STEAM_APP_ID_RE.match(token) and token not in ids:
            ids.append(token)
    return ids


def _alias_app_id(token: str) -> Optional[str]:
    key = token.strip().lower()
    return _STEAM_ALIASES.get(key)


def resolve_game_inputs(
    raw: Sequence[str] | str,
    *,
    max_games: int = 5,
    search_limit: int = 5,
) -> Dict[str, Any]:
    """Resolve a mix of AppIDs, aliases, and game names to Steam AppIDs."""
    tokens = split_input_tokens(raw)
    if not tokens:
        return {"success": False, "message": "请输入游戏名或 AppID", "app_ids": [], "resolved": []}

    app_ids: List[str] = []
    resolved: List[Dict[str, Any]] = []
    errors: List[str] = []

    for token in tokens:
        if len(app_ids) >= max_games:
            errors.append(f"最多 {max_games} 款，已忽略：{token}")
            continue

        bare = token
        if token.startswith("steam_"):
            bare = token.replace("steam_", "", 1)

        if _STEAM_APP_ID_RE.match(bare):
            if bare not in app_ids:
                app_ids.append(bare)
                resolved.append({"input": token, "app_id": bare, "name": None, "via": "app_id"})
            continue

        alias = _alias_app_id(token)
        if alias:
            if alias not in app_ids:
                app_ids.append(alias)
                resolved.append({"input": token, "app_id": alias, "name": None, "via": "alias"})
            continue

        try:
            hits = search_steam_games(token, limit=search_limit)
        except Exception as exc:
            errors.append(f"「{token}」搜索失败：{exc}")
            continue

        if not hits:
            errors.append(f"未找到 Steam 游戏：{token}")
            continue

        pick = hits[0]
        name_lower = token.strip().lower()
        for hit in hits:
            if (hit.get("name") or "").strip().lower() == name_lower:
                pick = hit
                break

        app_id = str(pick.get("app_id") or "")
        if not app_id or app_id in app_ids:
            if app_id in app_ids:
                resolved.append(
                    {
                        "input": token,
                        "app_id": app_id,
                        "name": pick.get("name"),
                        "via": "search_duplicate",
                    }
                )
            continue

        app_ids.append(app_id)
        entry: Dict[str, Any] = {
            "input": token,
            "app_id": app_id,
            "name": pick.get("name"),
            "via": "search",
        }
        if len(hits) > 1 and (pick.get("name") or "").strip().lower() != name_lower:
            entry["alternatives"] = hits[1:4]
        resolved.append(entry)

    if not app_ids:
        return {
            "success": False,
            "message": "；".join(errors) if errors else "未能解析任何有效游戏",
            "app_ids": [],
            "resolved": resolved,
            "errors": errors,
        }

    return {
        "success": True,
        "app_ids": app_ids,
        "resolved": resolved,
        "errors": errors,
    }


def _game_ids_from_app_ids(app_ids: Sequence[str], platform: str = "steam") -> List[str]:
    return [library_game_id(pid, platform=platform) for pid in app_ids]


async def run_analysis_wizard(
    app_ids: Sequence[str],
    *,
    username: str,
    platform: str = "steam",
    max_reviews: int = 50,
    skip_crawl: bool = False,
    auto_archive: bool = True,
) -> Dict[str, Any]:
    """End-to-end wizard: crawl (optional) → sync → compare report → action items → archive."""
    plat = (platform or "steam").lower()
    if plat == "taptap":
        resolution = resolve_taptap_inputs(app_ids)
        platform_label = "TapTap"
    elif plat == "google_play":
        resolution = resolve_google_play_inputs(app_ids)
        platform_label = "Google Play"
    else:
        resolution = resolve_game_inputs(app_ids)
        platform_label = "Steam"
        plat = "steam"
    if not resolution.get("success"):
        return {
            "success": False,
            "message": resolution.get("message")
            or f"请提供 1–5 个有效的{platform_label}游戏名或 AppID",
            "errors": resolution.get("errors") or [],
            "resolved": resolution.get("resolved") or [],
            "platform": plat,
        }
    normalized = resolution["app_ids"]
    if len(normalized) > 5:
        return {"success": False, "message": "单次最多分析 5 款产品"}

    steps: List[Dict[str, Any]] = []
    resolve_labels = []
    for row in resolution.get("resolved") or []:
        if not row.get("app_id"):
            continue
        label = row.get("name") or row.get("input") or row["app_id"]
        resolve_labels.append(f"{label} ({row['app_id']})")
    if resolve_labels or resolution.get("errors"):
        detail_parts = []
        if resolve_labels:
            detail_parts.append("已识别：" + "、".join(resolve_labels))
        if resolution.get("errors"):
            detail_parts.append("；".join(resolution["errors"]))
        steps.append(
            {
                "id": "resolve",
                "status": "warn" if resolution.get("errors") else "ok",
                "detail": "；".join(detail_parts),
            }
        )

    # 读写统一走同一 MVP 目录: demo bootstrap/抓取产物按用户落盘,
    # 无用户级数据时回退共享目录(保持旧行为)。否则 skip_crawl 读不到
    # 用户级数据会误触发联网抓取, 在 CI/离线环境挂死。
    out_dir = resolve_mvp_output_dir(username)
    if not mvp_validation_passed(out_dir) and mvp_validation_passed():
        out_dir = None

    crawl_ok = True
    crawl_error = None
    if skip_crawl and mvp_validation_passed(out_dir):
        steps.append({"id": "crawl", "status": "skipped", "detail": "使用已有 MVP 数据"})
    else:
        try:
            import asyncio

            pipeline = run_mvp_pipeline
            if plat == "taptap":
                pipeline = run_taptap_pipeline
            elif plat == "google_play":
                pipeline = run_google_play_pipeline
            result = await asyncio.to_thread(
                pipeline,
                app_ids=normalized,
                max_reviews_per_app=max(10, min(max_reviews, 200)),
                output_dir=out_dir or DEFAULT_OUTPUT_DIR,
            )
            crawl_ok = bool(result.get("success"))
            steps.append(
                {
                    "id": "crawl",
                    "status": "ok" if crawl_ok else "warn",
                    "detail": f"抓取 {platform_label} {len(normalized)} 款产品，校验={'通过' if crawl_ok else '部分通过'}",
                    "artifacts": result.get("artifacts"),
                }
            )
        except Exception as exc:
            crawl_ok = False
            crawl_error = str(exc)
            steps.append({"id": "crawl", "status": "error", "detail": crawl_error})

    if not mvp_validation_passed(out_dir):
        dataset = load_mvp_artifact("dataset", out_dir)
        has_data = bool(
            dataset
            and (dataset.get("comments") or dataset.get("metrics"))
        )
        if not has_data:
            return {
                "success": False,
                "message": crawl_error or "MVP 数据未就绪，抓取失败",
                "steps": steps,
            }
        steps.append(
            {
                "id": "validate",
                "status": "warn",
                "detail": "校验未完全通过，将基于已抓取样本继续生成报告",
            }
        )

    sync = sync_library_from_mvp(username, output_dir=out_dir)
    steps.append(
        {
            "id": "sync",
            "status": "ok" if sync.get("success") else "error",
            "detail": sync.get("message") or f"资料库 +{sync.get('created', 0)} / ~{sync.get('updated', 0)}",
        }
    )
    if not sync.get("success"):
        return {"success": False, "message": sync.get("message", "资料库同步失败"), "steps": steps}

    game_ids = _game_ids_from_app_ids(normalized, platform=plat)
    report = await generate_competitor_scenario_report(game_ids, username=username)
    if not report.get("success"):
        steps.append({"id": "report", "status": "error", "detail": report.get("message", "报告生成失败")})
        return {"success": False, "message": report.get("message", "报告生成失败"), "steps": steps}

    mvp_analysis = get_mvp_analysis(out_dir) or {}
    action_items = build_action_items(report.get("facts") or {}, mvp_analysis)
    report["action_items"] = action_items
    report["markdown"] = _append_actions_markdown(report.get("markdown") or "", action_items)
    from src.data_resolution import resolve_user_data_source

    report["data_source"] = (report.get("facts") or {}).get("data_source") or (
        "taptap_public"
        if plat == "taptap"
        else "google_play_public"
        if plat == "google_play"
        else resolve_user_data_source(username)
    )
    report["platform"] = plat

    steps.append(
        {
            "id": "report",
            "status": "ok",
            "detail": "竞品报告已生成" + ("（AI）" if report.get("using_llm") else "（规则引擎）"),
        }
    )

    archive_id = None
    if auto_archive:
        try:
            archive_id = archive_scenario_report(username, report)
            steps.append({"id": "archive", "status": "ok", "detail": f"已归档 #{archive_id[:8]}…"})
        except Exception as exc:
            steps.append({"id": "archive", "status": "warn", "detail": f"归档跳过：{exc}"})

    return {
        "success": True,
        "app_ids": normalized,
        "game_ids": game_ids,
        "resolved": resolution.get("resolved") or [],
        "resolve_warnings": resolution.get("errors") or [],
        "steps": steps,
        "report": report,
        "action_items": action_items,
        "archive_id": archive_id,
        "platform": plat,
        "compare_url": f"/games/compare?ids={','.join(game_ids)}&from=guide",
        "library_url": "/games/library",
    }


def _append_actions_markdown(markdown: str, action_items: List[Dict[str, Any]]) -> str:
    if not action_items:
        return markdown
    lines = [markdown.rstrip(), "", "## 可执行行动清单", ""]
    for item in action_items:
        p = item.get("priority") or "P1"
        lines.append(f"### [{p}] {item.get('title', '')}")
        lines.append(f"- **负责人**：{item.get('owner_role', '制作人')}")
        lines.append(f"- **动作**：{item.get('action', '')}")
        lines.append(f"- **验证指标**：{item.get('verify_metric', '')}")
        if item.get("timeframe"):
            lines.append(f"- **建议周期**：{item['timeframe']}")
        lines.append("")
    return "\n".join(lines)
