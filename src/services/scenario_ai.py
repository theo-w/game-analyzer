"""AI + rule-based summary reports for the three core analysis scenarios."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from src.auth import LLM_CONFIG, LLM_PROVIDERS

from src.data_resolution import get_user_comments_data, get_user_metrics_data, resolve_user_data_source
from src.mvp_data import get_mvp_analysis
from src.services.action_tasks import normalize_action_items
from src.services.analysis_archive import AnalysisArchiveRepository
from src.services.competitor_workbench import (
    build_compare_payload,
    build_feature_matrix,
    compare_snapshots,
    normalize_compare_id,
)
from src.services.competitor_scores import (
    COMPETITOR_DIMENSIONS,
    CompetitorScoreRepository,
    build_score_summary,
)
from src.services.game_intel import BREAKDOWN_SECTIONS, GameLibraryRepository, GameplayBreakdownRepository
from src.services.llm_client import (
    clean_llm_report_text,
    complete_prompt_with_retry,
    llm_is_configured,
    llm_is_reachable,
    parse_json_from_llm,
)

_OWNER_BY_THEME = {
    "performance": "程序 / 技术",
    "matchmaking": "程序 / 运营",
    "monetization": "商业化",
    "content": "策划",
    "ui_ux": "UX / 策划",
    "updates": "制作人 / 策划",
}


def _provider_label() -> str:
    p = LLM_CONFIG.get("provider") or ""
    return LLM_PROVIDERS.get(p, {}).get("name", p)


def _report_html(
    title: str,
    executive_summary: str,
    sections: List[Dict[str, str]],
    action_items: Optional[List[Dict[str, Any]]] = None,
    dimension_scores: Optional[List[Dict[str, Any]]] = None,
    score_dimensions: Optional[List[Dict[str, Any]]] = None,
) -> str:
    dim_html = ""
    rows = dimension_scores or []
    dims = score_dimensions or COMPETITOR_DIMENSIONS
    if rows and dims:
        head = "".join(f"<th>{d.get('title', d.get('key', ''))}</th>" for d in dims)
        body_rows = []
        for row in rows:
            scores = row.get("scores") or {}
            cells = "".join(f"<td>{scores.get(d.get('key'), '—')}</td>" for d in dims)
            custom = " ✎" if row.get("is_custom") else ""
            body_rows.append(f"<tr><th>{row.get('name', '')}{custom}</th>{cells}</tr>")
        dim_html = (
            "<section><h3>六维评分</h3><table class=\"dim-scores\">"
            f"<thead><tr><th>游戏</th>{head}</tr></thead><tbody>{''.join(body_rows)}</tbody></table></section>"
        )
    body = dim_html + "".join(
        f"<section><h3>{s.get('title', '')}</h3><p>{s.get('content', '').replace(chr(10), '<br>')}</p></section>"
        for s in sections
    )
    actions_html = ""
    if action_items:
        rows = "".join(
            f"<li><strong>[{a.get('priority', 'P1')}] {a.get('title', '')}</strong>"
            f"<div>负责人：{a.get('owner_role', '—')} · 周期：{a.get('timeframe', '—')}</div>"
            f"<div>动作：{a.get('action', '')}</div>"
            f"<div>验证：{a.get('verify_metric', '')}</div></li>"
            for a in action_items
        )
        actions_html = f"<section><h3>可执行行动清单</h3><ul class=\"action-items\">{rows}</ul></section>"
    return (
        f"<article class=\"scenario-report\"><h2>{title}</h2>"
        f"<p class=\"exec\"><strong>摘要</strong>：{executive_summary}</p>{body}{actions_html}</article>"
    )


def _normalize_llm_sections(raw_sections: Any) -> List[Dict[str, str]]:
    if not isinstance(raw_sections, list):
        return []
    sections: List[Dict[str, str]] = []
    for item in raw_sections:
        if not isinstance(item, dict):
            continue
        title = clean_llm_report_text(str(item.get("title") or ""))
        content = clean_llm_report_text(str(item.get("content") or ""))
        if title or content:
            sections.append({"title": title or "分析", "content": content})
    return sections


def _decode_json_string_fragment(raw: str) -> str:
    wrapped = f'"{raw}"'
    try:
        return json.loads(wrapped)
    except json.JSONDecodeError:
        return raw.replace('\\"', '"').replace("\\n", "\n").replace("\\t", "\t")


def _extract_partial_llm_report(raw: str) -> Optional[Dict[str, Any]]:
    """Best-effort parse when json.loads fails (truncated / slightly invalid JSON)."""
    import re

    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end <= start:
        return None
    snippet = raw[start : end + 1]

    summary_match = re.search(
        r'"executive_summary"\s*:\s*"((?:[^"\\]|\\.)*)"',
        snippet,
        flags=re.DOTALL,
    )
    if not summary_match:
        return None

    summary = _decode_json_string_fragment(summary_match.group(1))
    sections: List[Dict[str, str]] = []
    for sec_match in re.finditer(
        r'\{\s*"title"\s*:\s*"((?:[^"\\]|\\.)*)"\s*,\s*"content"\s*:\s*"((?:[^"\\]|\\.)*)"\s*\}',
        snippet,
        flags=re.DOTALL,
    ):
        sections.append(
            {
                "title": _decode_json_string_fragment(sec_match.group(1)),
                "content": _decode_json_string_fragment(sec_match.group(2)),
            }
        )

    return {"executive_summary": summary, "sections": sections}


_DIM_SECTION_MARKERS = ("六维", "维度评分", "dimension")


def _is_dimension_section(section: Dict[str, str]) -> bool:
    blob = f"{section.get('title', '')}{section.get('content', '')}"
    return any(marker in blob for marker in _DIM_SECTION_MARKERS)


def _preserve_dimension_section(
    rule_sections: List[Dict[str, str]],
    llm_sections: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    """Keep rule-engine dimension scores when the LLM summary omits them."""
    dim_section = next((s for s in rule_sections if _is_dimension_section(s)), None)
    if not dim_section or any(_is_dimension_section(s) for s in llm_sections):
        return llm_sections
    merged = list(llm_sections)
    insert_at = 1 if len(merged) else 0
    merged.insert(insert_at, dim_section)
    return merged


def _merge_llm_into_report(base: Dict[str, Any], raw: str) -> tuple[Dict[str, Any], bool, Optional[str]]:
    """Apply LLM output to a rule-based report shell. Never inject raw JSON into fields."""
    parsed = parse_json_from_llm(raw)
    if not parsed:
        parsed = _extract_partial_llm_report(raw)

    if parsed:
        summary = clean_llm_report_text(str(parsed.get("executive_summary") or ""))
        sections = _normalize_llm_sections(parsed.get("sections"))
        if summary:
            base["executive_summary"] = summary
        if sections:
            base["sections"] = _preserve_dimension_section(base.get("sections") or [], sections)
        if summary or sections:
            return base, True, None

    return base, False, "LLM 返回内容无法解析为 JSON，已使用规则引擎总结"


def _dimension_scores_markdown(
    dimension_scores: Optional[List[Dict[str, Any]]],
    score_dimensions: Optional[List[Dict[str, Any]]] = None,
) -> str:
    rows = dimension_scores or []
    dims = score_dimensions or COMPETITOR_DIMENSIONS
    if not rows or not dims:
        return ""
    lines = ["## 六维评分", ""]
    header = "| 游戏 | " + " | ".join(d.get("title", d.get("key", "")) for d in dims) + " |"
    sep = "| --- | " + " | ".join("---" for _ in dims) + " |"
    lines.extend([header, sep])
    for row in rows:
        scores = row.get("scores") or {}
        cells = [str(scores.get(d.get("key"), "—")) for d in dims]
        custom = " ✎" if row.get("is_custom") else ""
        lines.append(f"| {row.get('name', '')}{custom} | " + " | ".join(cells) + " |")
    lines.append("")
    return "\n".join(lines)


def _finalize_scenario_report(base: Dict[str, Any]) -> Dict[str, Any]:
    title = base.get("title") or "分析报告"
    summary = clean_llm_report_text(str(base.get("executive_summary") or ""))
    sections = _normalize_llm_sections(base.get("sections"))
    facts = base.get("facts") or {}
    dim_rows = base.get("dimension_scores") or facts.get("dimension_scores") or []
    dim_defs = facts.get("score_dimensions") or COMPETITOR_DIMENSIONS
    base["title"] = title
    base["executive_summary"] = summary
    base["sections"] = sections
    base["markdown"] = _to_markdown(
        title,
        summary,
        sections,
        base.get("action_items"),
        dim_rows,
        dim_defs,
    )
    base["html"] = _report_html(title, summary, sections, base.get("action_items"), dim_rows, dim_defs)
    return base


def build_action_items(
    facts: Dict[str, Any],
    mvp_analysis: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Structured actionable tasks for producers / planners."""
    items: List[Dict[str, Any]] = []
    strategy = (mvp_analysis or {}).get("ai_strategy") or {}
    for raw in strategy.get("prioritized_actions") or []:
        items.append(
            {
                "priority": f"P{raw.get('priority', len(items) + 1)}",
                "title": raw.get("title") or "优先行动",
                "owner_role": "制作人 / 策划",
                "action": raw.get("action") or raw.get("why") or "",
                "verify_metric": raw.get("experiment") or "评论主题词频 + 样本好评率",
                "timeframe": "2 周内",
                "source": "mvp_signals",
            }
        )

    products = sorted(
        facts.get("products") or [],
        key=lambda x: float(x.get("positive_rate") or 0),
    )
    if products:
        laggard = products[0]
        if float(laggard.get("positive_rate") or 100) < 60:
            theme = ""
            themes = laggard.get("themes") or []
            if themes:
                theme = themes[0].get("theme") or themes[0].get("name") or ""
            items.append(
                {
                    "priority": "P0",
                    "title": f"修复「{laggard.get('name')}」口碑短板",
                    "owner_role": _OWNER_BY_THEME.get(theme, "制作人"),
                    "action": laggard.get("recommendation")
                    or f"围绕差评主题「{theme or '体验'}」做小步迭代",
                    "verify_metric": "样本好评率 ≥ 55%，相关主题负面词频下降",
                    "timeframe": "本周",
                    "source": "compare",
                }
            )
        leader = products[-1]
        if leader.get("name") and leader != laggard:
            items.append(
                {
                    "priority": "P2",
                    "title": f"学习「{leader.get('name')}」的口碑做法",
                    "owner_role": "策划 / 运营",
                    "action": "拆解领先产品的商店卖点与更新节奏，对照自身差距",
                    "verify_metric": "完成 1 页对标 memo，明确 2 条可迁移动作",
                    "timeframe": "2 周内",
                    "source": "compare",
                }
            )

    score_summary = facts.get("score_summary") or []
    if score_summary:
        weakest = min(score_summary, key=lambda r: float(r.get("average") or 5))
        items.append(
            {
                "priority": "P1",
                "title": f"补齐六维短板：{weakest.get('name')}",
                "owner_role": "制作人",
                "action": "对照六维评分最低项，安排专项评审与迭代排期",
                "verify_metric": "下轮评分均分提升 ≥ 0.5",
                "timeframe": "2 周内",
                "source": "scores",
            }
        )

    if not items:
        items.append(
            {
                "priority": "P1",
                "title": "扩大 Steam 评论样本",
                "owner_role": "数据分析",
                "action": "将 max_reviews 提高到 100+，并按语言分层复测",
                "verify_metric": "每款产品评论样本 ≥ 50，主题词稳定",
                "timeframe": "本周",
                "source": "fallback",
            }
        )

    seen = set()
    deduped: List[Dict[str, Any]] = []
    for row in items:
        key = (row.get("title") or "", row.get("action") or "")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return normalize_action_items(deduped[:6])


def _sync_display_names(facts: Dict[str, Any]) -> None:
    """Ensure dimension score rows use human-readable game names, not internal ids."""
    name_by_gid: Dict[str, str] = {}
    for product in facts.get("products") or []:
        gid = str(product.get("game_id") or "")
        name = str(product.get("name") or "").strip()
        if gid and name and not name.startswith(("steam_", "taptap_")):
            name_by_gid[gid] = name

    for row in facts.get("dimension_scores") or []:
        gid = str(row.get("game_id") or "")
        display = name_by_gid.get(gid)
        current = str(row.get("name") or "")
        if display and (not current or current == gid or current.startswith(("steam_", "taptap_"))):
            row["name"] = display

    for row in facts.get("score_summary") or []:
        gid = str(row.get("game_id") or "")
        display = name_by_gid.get(gid)
        current = str(row.get("name") or "")
        if display and (not current or current == gid or current.startswith(("steam_", "taptap_"))):
            row["name"] = display


def _compact_compare_facts(
    compare: Dict[str, Any],
    matrix: Dict[str, Any],
    *,
    username: str = "",
    game_ids: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    items = []
    id_list: List[str] = []
    for item in compare.get("items") or []:
        gid = item.get("game_id") or ""
        if gid:
            id_list.append(gid)
        items.append(
            {
                "game_id": gid,
                "name": item.get("name"),
                "genre": item.get("genre"),
                "positive_rate": item.get("positive_rate"),
                "risk_level": item.get("risk_level"),
                "themes": item.get("themes"),
                "recommendation": item.get("recommendation"),
                "kpis": {k: v for k, v in (item.get("kpis") or {}).items() if k in (
                    "样本好评率", "Steam汇总好评率", "Steam汇总评论数", "中位总游玩时长_分钟"
                )},
            }
        )
    ids_for_scores = list(game_ids or id_list)
    score_batch = (
        CompetitorScoreRepository.get_batch(
            username,
            ids_for_scores,
            compare_items=compare.get("items") or [],
        )
        if username and ids_for_scores
        else {"rows": [], "dimensions": COMPETITOR_DIMENSIONS}
    )
    score_rows = score_batch.get("rows") or []
    facts = {
        "data_source": compare.get("data_source"),
        "products": items,
        "feature_matrix": (matrix.get("rows") or [])[:5],
        "dimension_scores": score_rows,
        "score_summary": build_score_summary(score_rows),
        "score_dimensions": score_batch.get("dimensions") or COMPETITOR_DIMENSIONS,
    }
    _sync_display_names(facts)
    return facts


def _dimension_score_section(facts: Dict[str, Any]) -> Optional[Dict[str, str]]:
    rows = facts.get("dimension_scores") or []
    if not rows:
        return None
    dim_titles = {d["key"]: d["title"] for d in (facts.get("score_dimensions") or COMPETITOR_DIMENSIONS)}
    lines: List[str] = []
    for row in rows:
        scores = row.get("scores") or {}
        if not scores:
            continue
        vals = list(scores.values())
        avg = round(sum(vals) / len(vals), 2)
        parts = [f"{dim_titles.get(k, k)}{v}" for k, v in scores.items()]
        custom = "（已人工评分）" if row.get("is_custom") else "（含建议分）"
        lines.append(f"· {row.get('name')}：均分 {avg} {custom} — " + "、".join(parts))
    if not lines:
        return None
    ranked = facts.get("score_summary") or []
    if ranked:
        lines.append("")
        lines.append("均分排序：" + " > ".join(f"{r.get('name')}({r.get('average')})" for r in ranked[:5]))
    return {"title": "六维评分对比", "content": "\n".join(lines)}


def _rule_competitor_report(facts: Dict[str, Any]) -> Dict[str, Any]:
    products = facts.get("products") or []
    if not products:
        title = "竞品分析总结"
        exec_summary = "暂无对比产品，请先选择游戏。"
        sections: List[Dict[str, str]] = []
        return {
            "title": title,
            "executive_summary": exec_summary,
            "sections": sections,
            "markdown": _to_markdown(title, exec_summary, sections),
            "html": _report_html(title, exec_summary, sections),
        }

    ranked = sorted(
        products,
        key=lambda x: float(x.get("positive_rate") or 0),
        reverse=True,
    )
    theme_counts: Dict[str, int] = {}
    for p in products:
        for t in p.get("themes") or []:
            theme_counts[t.get("theme", "other")] = theme_counts.get(t.get("theme", "other"), 0) + int(
                t.get("count") or 0
            )
    top_themes = sorted(theme_counts.items(), key=lambda x: -x[1])[:4]

    if len(products) == 1:
        solo = ranked[0]
        name = solo.get("name") or "该产品"
        exec_summary = (
            f"当前仅分析「{name}」单款产品，样本好评率约 {solo.get('positive_rate')}%"
            f"（风险等级：{solo.get('risk_level') or '—'}）。"
            " 如需横向竞品对比，请在向导中再选 1–2 款同类产品。"
        )
        if top_themes:
            exec_summary += " 评论高频主题：" + "、".join(t[0] for t in top_themes) + "。"
        sections = [
            {
                "title": "产品快照",
                "content": (
                    f"· {name}：样本好评率 {solo.get('positive_rate')}%，"
                    f"风险 {solo.get('risk_level') or '—'}\n"
                    f"· 优先关注：{solo.get('recommendation') or '匹配/体验/内容更新'}"
                ),
            },
            {
                "title": "舆情主题",
                "content": (
                    "、".join(t[0] for t in top_themes)
                    if top_themes
                    else "样本中暂未形成明显主题簇，建议扩大抓取窗口。"
                ),
            },
            {
                "title": "建议行动",
                "content": (
                    "1. 补充 1–2 款同类产品后生成横向对比\n"
                    "2. 围绕高频差评主题做小步迭代\n"
                    "3. 结合六维评分与功能矩阵定位短板"
                ),
            },
        ]
        dim_sec = _dimension_score_section(facts)
        if dim_sec:
            sections.insert(1, dim_sec)
        title = f"单品分析 · {name}"
        return {
            "title": title,
            "executive_summary": exec_summary,
            "sections": sections,
            "markdown": _to_markdown(title, exec_summary, sections),
            "html": _report_html(title, exec_summary, sections),
        }

    leader = ranked[0]
    laggard = ranked[-1]
    exec_summary = (
        f"本批 {len(products)} 款产品中，样本口碑领先为「{leader.get('name')}」"
        f"（{leader.get('positive_rate')}%）；"
        f"相对落后为「{laggard.get('name')}」"
        f"（{laggard.get('positive_rate')}%）。"
    )
    if top_themes:
        exec_summary += " 评论高频主题：" + "、".join(t[0] for t in top_themes) + "。"

    sections = [
        {
            "title": "横向对比结论",
            "content": "\n".join(
                f"· {p.get('name')}：样本好评率 {p.get('positive_rate')}%，风险 {p.get('risk_level') or '—'}"
                for p in ranked
            ),
        },
        {
            "title": "机会与威胁",
            "content": (
                f"可学习「{leader.get('name')}」在口碑管理上的做法；"
                f"「{laggard.get('name')}」需优先处理：{(laggard.get('recommendation') or '匹配/体验/内容更新')}"
            ),
        },
        {
            "title": "建议行动",
            "content": "1. 围绕高频差评主题做小步迭代\n2. 用样本好评率+主题词复测\n3. 结合功能矩阵与六维评分补齐短板",
        },
    ]
    dim_sec = _dimension_score_section(facts)
    if dim_sec:
        sections.insert(1, dim_sec)
    title = f"竞品分析总结 · {len(products)} 款产品"
    return {
        "title": title,
        "executive_summary": exec_summary,
        "sections": sections,
        "markdown": _to_markdown(title, exec_summary, sections),
        "html": _report_html(title, exec_summary, sections),
    }


async def generate_competitor_scenario_report(
    ids: Sequence[str],
    *,
    username: str = "",
) -> Dict[str, Any]:
    id_list = [str(x).strip() for x in ids if str(x).strip()]
    if not id_list:
        return {"success": False, "message": "请选择至少一款游戏"}

    compare = build_compare_payload(id_list, username=username or None)
    matrix = build_feature_matrix(id_list)
    facts = _compact_compare_facts(compare, matrix, username=username, game_ids=id_list)
    base = _rule_competitor_report(facts)
    using_llm = False
    llm_error = None

    if llm_is_configured() and await llm_is_reachable():
        prompt = (
            "你是游戏竞品分析顾问。根据以下已校验的对比事实 JSON，输出竞品分析总结报告。\n"
            "要求：只使用 JSON 中出现的产品名与数字；引用游戏时必须使用 products[].name（如「原神」），"
            "禁止输出 game_id 或 AppID（如 taptap_168332、168332）。\n"
            "必须只输出一个 JSON 对象，不要 Markdown 代码块，不要额外说明文字。\n"
            "格式：{\"executive_summary\":\"120-200字纯文本\",\"sections\":[{\"title\":\"标题\",\"content\":\"正文\"}]}\n"
            "sections 需包含：对比结论、六维评分解读（若有 dimension_scores）、用户需求信号、机会点、优先行动（3-4条）。\n\n"
            f"{json.dumps(facts, ensure_ascii=False)}"
        )
        try:
            raw = await complete_prompt_with_retry(prompt, max_tokens=1400, timeout=120, retries=1)
            base, using_llm, llm_error = _merge_llm_into_report(base, raw)
        except Exception as exc:
            llm_error = str(exc)
    elif llm_is_configured():
        llm_error = "LLM 服务不可达，已使用规则引擎"

    base.update(
        {
            "success": True,
            "scenario": "competitor",
            "using_llm": using_llm,
            "llm_provider": _provider_label() if using_llm else None,
            "llm_model": LLM_CONFIG.get("model") if using_llm else None,
            "llm_error": llm_error,
            "llm_configured": llm_is_configured(),
            "facts": facts,
            "dimension_scores": facts.get("dimension_scores"),
            "score_summary": facts.get("score_summary"),
            "generated_at": datetime.now().isoformat(),
        }
    )
    mvp_analysis = get_mvp_analysis() or {}
    base["action_items"] = build_action_items(facts, mvp_analysis)
    return _finalize_scenario_report(base)


def _rule_breakdown_report(games: List[Dict[str, Any]], breakdowns: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not games:
        title = "玩法拆解总结"
        exec_summary = "未找到游戏资料。"
        sections: List[Dict[str, str]] = []
        return {
            "title": title,
            "executive_summary": exec_summary,
            "sections": sections,
            "markdown": _to_markdown(title, exec_summary, sections),
            "html": _report_html(title, exec_summary, sections),
        }

    names = "、".join(g.get("name") or g.get("game_id") for g in games[:3])
    if len(games) > 3:
        names += f" 等{len(games)}款"

    sections = []
    for game, bd in zip(games, breakdowns):
        lines = []
        for key, title, _hint in BREAKDOWN_SECTIONS:
            val = (bd or {}).get(key) or ""
            if val:
                lines.append(f"{title}：{val[:120]}{'…' if len(val) > 120 else ''}")
        sections.append(
            {
                "title": f"「{game.get('name')}」玩法要点",
                "content": "\n".join(lines) if lines else "尚未填写玩法拆解，可使用 AI 生成。",
            }
        )

    genres = {g.get("genre") for g in games if g.get("genre")}
    exec_summary = (
        f"已对 {len(games)} 款产品（{names}）做玩法结构梳理。"
        f"品类覆盖：{'、'.join(sorted(genres)) or '待标注'}。"
        " 建议结合对标竞品验证差异化与商业化设计。"
    )
    title = f"玩法拆解总结 · {len(games)} 款"
    return {
        "title": title,
        "executive_summary": exec_summary,
        "sections": sections,
        "markdown": _to_markdown(title, exec_summary, sections),
        "html": _report_html(title, exec_summary, sections),
    }


async def generate_breakdown_scenario_report(
    game_ids: Sequence[str],
    *,
    username: str = "",
) -> Dict[str, Any]:
    id_list = [str(x).strip() for x in game_ids if str(x).strip()]
    if not id_list:
        return {"success": False, "message": "请选择游戏"}

    games, breakdowns, facts_games = [], [], []
    for gid in id_list:
        game = GameLibraryRepository.get(gid)
        if not game:
            continue
        bd = GameplayBreakdownRepository.get(gid) or {}
        games.append(game)
        breakdowns.append(bd)
        facts_games.append(
            {
                "game_id": gid,
                "name": game.get("name"),
                "genre": game.get("genre"),
                "business_model": game.get("business_model"),
                "breakdown": {k: (bd.get(k) or "")[:300] for k, _, _ in BREAKDOWN_SECTIONS},
            }
        )

    if not games:
        return {"success": False, "message": "游戏不存在，请先同步资料库"}

    facts = {"games": facts_games}
    base = _rule_breakdown_report(games, breakdowns)
    using_llm = False
    llm_error = None

    if llm_is_configured():
        prompt = (
            "你是游戏策划顾问。根据下列游戏的玩法拆解 JSON，写一份玩法对比与借鉴总结。\n"
            "必须只输出一个 JSON 对象，不要 Markdown 代码块，不要额外说明文字。\n"
            "格式：{\"executive_summary\":\"150-220字纯文本\",\"sections\":[{\"title\":\"标题\",\"content\":\"正文\"}]}\n"
            "sections 应含：核心循环对比、商业化差异、差异化亮点、可借鉴清单。\n\n"
            f"{json.dumps(facts, ensure_ascii=False)}"
        )
        try:
            raw = await complete_prompt_with_retry(prompt, max_tokens=1400, timeout=120, retries=1)
            base, using_llm, llm_error = _merge_llm_into_report(base, raw)
        except Exception as exc:
            llm_error = str(exc)

    base.update(
        {
            "success": True,
            "scenario": "breakdown",
            "using_llm": using_llm,
            "llm_provider": _provider_label() if using_llm else None,
            "llm_model": LLM_CONFIG.get("model") if using_llm else None,
            "llm_error": llm_error,
            "llm_configured": llm_is_configured(),
            "facts": facts,
            "generated_at": datetime.now().isoformat(),
        }
    )
    return _finalize_scenario_report(base)


def _rule_review_report(
    *,
    deltas: List[Dict[str, Any]],
    metrics_summary: Dict[str, Any],
    snapshot_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if deltas:
        biggest = deltas[0]
        exec_summary = (
            f"对比快照「{snapshot_meta.get('a', '')}」→「{snapshot_meta.get('b', '')}」，"
            f"变化最大为「{biggest.get('product_name')}」"
            f"（{biggest.get('positive_rate_before')}% → {biggest.get('positive_rate_after')}%）。"
        )
        trend_lines = [
            f"· {d.get('product_name')}：{d.get('delta'):+}%"
            for d in deltas[:8]
        ]
        sections = [
            {"title": "口碑变化", "content": "\n".join(trend_lines)},
            {
                "title": "复盘建议",
                "content": "关注降幅最大产品的版本/舆情节点；对升幅产品总结可复用做法。",
            },
        ]
        title = "数据复盘总结 · 快照对比"
    else:
        exec_summary = (
            f"当前数据池含 {metrics_summary.get('product_count', 0)} 款产品、"
            f"{metrics_summary.get('metrics_rows', 0)} 条指标。"
            " 建议定期运行分析向导抓取以建立时间轴。"
        )
        sections = [
            {
                "title": "数据概况",
                "content": f"数据来源：{metrics_summary.get('source', '—')}",
            },
            {
                "title": "下一步",
                "content": "1. 选定产品范围\n2. 生成周期报告并归档\n3. 积累两条以上快照后做 A/B 对比",
            },
        ]
        title = "数据复盘总结 · 当前周期"

    return {
        "title": title,
        "executive_summary": exec_summary,
        "sections": sections,
        "markdown": _to_markdown(title, exec_summary, sections),
        "html": _report_html(title, exec_summary, sections),
    }


async def generate_review_scenario_report(
    *,
    username: str,
    snapshot_a: Optional[str] = None,
    snapshot_b: Optional[str] = None,
    product_ids: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    metrics = get_user_metrics_data(username)
    if product_ids:
        pset = {str(p) for p in product_ids}
        metrics = [m for m in metrics if str(m.get("product")) in pset]

    products = sorted({str(m.get("product")) for m in metrics if m.get("product")})
    facts: Dict[str, Any] = {
        "source": resolve_user_data_source(username),
        "product_count": len(products),
        "metrics_rows": len(metrics),
    }
    deltas: List[Dict[str, Any]] = []
    snap_meta = None

    if snapshot_a and snapshot_b:
        cmp_result = compare_snapshots(snapshot_a, snapshot_b)
        if cmp_result.get("success"):
            deltas = cmp_result.get("deltas") or []
            snap_meta = {
                "a": cmp_result.get("snapshot_a", {}).get("captured_at", snapshot_a),
                "b": cmp_result.get("snapshot_b", {}).get("captured_at", snapshot_b),
            }
            facts["snapshot_compare"] = deltas[:10]

    analysis = get_mvp_analysis()
    if analysis:
        facts["mvp_summary"] = analysis.get("summary")

    base = _rule_review_report(
        deltas=deltas,
        metrics_summary={"source": facts["source"], "product_count": len(products), "metrics_rows": len(metrics)},
        snapshot_meta=snap_meta,
    )
    using_llm = False
    llm_error = None

    if llm_is_configured():
        prompt = (
            "你是游戏数据分析师。根据下列复盘事实 JSON，写数据复盘总结。\n"
            "必须只输出一个 JSON 对象，不要 Markdown 代码块，不要额外说明文字。\n"
            "格式：{\"executive_summary\":\"120-200字纯文本\",\"sections\":[{\"title\":\"标题\",\"content\":\"正文\"}]}\n"
            "需含：变化解读、可能归因、下一轮实验假设。\n\n"
            f"{json.dumps(facts, ensure_ascii=False)}"
        )
        try:
            raw = await complete_prompt_with_retry(prompt, max_tokens=1200, timeout=120, retries=1)
            base, using_llm, llm_error = _merge_llm_into_report(base, raw)
        except Exception as exc:
            llm_error = str(exc)

    base.update(
        {
            "success": True,
            "scenario": "review",
            "using_llm": using_llm,
            "llm_provider": _provider_label() if using_llm else None,
            "llm_model": LLM_CONFIG.get("model") if using_llm else None,
            "llm_error": llm_error,
            "llm_configured": llm_is_configured(),
            "facts": facts,
            "generated_at": datetime.now().isoformat(),
        }
    )
    return _finalize_scenario_report(base)


def _to_markdown(
    title: str,
    summary: str,
    sections: List[Dict[str, str]],
    action_items: Optional[List[Dict[str, Any]]] = None,
    dimension_scores: Optional[List[Dict[str, Any]]] = None,
    score_dimensions: Optional[List[Dict[str, Any]]] = None,
) -> str:
    lines = [f"# {title}", "", f"**摘要**：{summary}", ""]
    dim_md = _dimension_scores_markdown(dimension_scores, score_dimensions)
    if dim_md:
        lines.append(dim_md)
    for s in sections:
        lines.append(f"## {s.get('title', '')}")
        lines.append("")
        lines.append(s.get("content", ""))
        lines.append("")
    if action_items:
        lines.append("## 可执行行动清单")
        lines.append("")
        for a in action_items:
            lines.append(f"### [{a.get('priority', 'P1')}] {a.get('title', '')}")
            lines.append(f"- **负责人**：{a.get('owner_role', '制作人')}")
            lines.append(f"- **动作**：{a.get('action', '')}")
            lines.append(f"- **验证指标**：{a.get('verify_metric', '')}")
            if a.get("timeframe"):
                lines.append(f"- **建议周期**：{a['timeframe']}")
            lines.append("")
    return "\n".join(lines)


def archive_scenario_report(username: str, report: Dict[str, Any]) -> str:
    scenario = report.get("scenario") or "scenario"
    product_ids: List[str] = []
    game_ids: List[str] = []
    facts = report.get("facts") or {}
    for row in facts.get("dimension_scores") or []:
        gid = row.get("game_id")
        if gid and gid not in game_ids:
            game_ids.append(gid)
    for p in facts.get("products") or []:
        gid = p.get("game_id")
        if gid and gid not in game_ids:
            game_ids.append(gid)
        pid = p.get("product") or p.get("id")
        if pid:
            product_ids.append(str(pid))
    for item in facts.get("games") or []:
        if item.get("game_id") and item["game_id"] not in game_ids:
            game_ids.append(item["game_id"])
    snapshot = {
        "scenario": scenario,
        "platform": report.get("platform") or "steam",
        "using_llm": report.get("using_llm"),
        "generated_at": report.get("generated_at"),
        "executive_summary": report.get("executive_summary"),
        "sections": report.get("sections") or [],
        "dimension_scores": facts.get("dimension_scores"),
        "score_summary": facts.get("score_summary"),
        "score_dimensions": facts.get("score_dimensions"),
        "action_items": report.get("action_items") or [],
    }
    baseline: List[Dict[str, Any]] = []
    for p in facts.get("products") or []:
        pid = str(p.get("product") or p.get("id") or "")
        if not pid and p.get("game_id"):
            gid = str(p["game_id"])
            if gid.startswith("steam_"):
                pid = gid.replace("steam_", "", 1)
            elif gid.startswith("taptap_"):
                pid = gid.replace("taptap_", "", 1)
            elif gid.startswith("google_play_"):
                pid = gid.replace("google_play_", "", 1)
        if pid:
            baseline.append(
                {
                    "product": pid,
                    "name": p.get("name"),
                    "positive_rate": p.get("positive_rate"),
                }
            )
    if baseline:
        snapshot["baseline_products"] = baseline
    from src.data_resolution import resolve_user_data_source

    snapshot["data_source"] = (
        facts.get("data_source")
        or report.get("data_source")
        or resolve_user_data_source(username)
    )
    return AnalysisArchiveRepository.create(
        username=username,
        title=report.get("title") or f"AI {scenario}",
        report_type=f"ai_{scenario}",
        product_ids=product_ids,
        game_ids=game_ids,
        snapshot=snapshot,
        html_excerpt=report.get("html") or report.get("markdown") or "",
        body_markdown=report.get("markdown") or "",
        category={"competitor": "竞品分析", "breakdown": "玩法拆解", "review": "数据复盘"}.get(scenario, "其他"),
    )


def get_breakdowns_for_ids(ids: Sequence[str]) -> Dict[str, Any]:
    """Inline breakdown payload for compare page."""
    from src.services.competitor_workbench import resolve_compare_row

    rows = []
    for raw_id in ids:
        game_id, product_id = resolve_compare_row(str(raw_id))
        if not game_id:
            continue
        game = GameLibraryRepository.get(game_id) or {}
        bd = GameplayBreakdownRepository.get(game_id) or {}
        if not game and not bd and product_id.isdigit():
            alt = "taptap_" if game_id.startswith("steam_") else "steam_"
            game = GameLibraryRepository.get(f"{alt}{product_id}") or {}
            bd = GameplayBreakdownRepository.get(f"{alt}{product_id}") or {}
        if not game and not bd:
            continue
        name = game.get("name") or product_id
        rows.append(
            {
                "game_id": game_id,
                "name": name,
                "genre": game.get("genre"),
                "breakdown": {k: bd.get(k, "") for k, _, _ in BREAKDOWN_SECTIONS},
                "sections": [{"key": k, "title": t, "hint": h} for k, t, h in BREAKDOWN_SECTIONS],
            }
        )
    return {"success": True, "items": rows, "count": len(rows)}
