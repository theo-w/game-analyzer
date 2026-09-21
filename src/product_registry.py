"""Canonical crawl products: platform IDs, aliases, and user-added custom games."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Sequence

# Built-in catalog — extend via data/custom_products.json.
PRODUCT_ENTRIES: List[Dict[str, Any]] = [
    {
        "key": "last_war",
        "display_name": "Last War: Survival",
        "genre": "SLG",
        "aliases": [
            "last war",
            "last war survival",
            "last war: survival",
            "last war生存",
            "last war 生存",
        ],
        "platforms": {
            "google_play": "com.fun.lastwar.gp",
            "taptap": "33569155",
        },
    },
    {
        "key": "dark_war",
        "display_name": "Dark War: Survival",
        "genre": "SLG",
        "aliases": [
            "dark war",
            "dark war survival",
            "dark war: survival",
            "dark war生存",
            "暗黑战争",
        ],
        "platforms": {
            "google_play": "com.readygo.dark.gp",
        },
    },
    {
        "key": "last_beacon",
        "display_name": "Last Beacon: Survival",
        "genre": "SLG",
        "aliases": [
            "last beacon",
            "last beacon survival",
            "last beacon: survival",
            "last beacon生存",
        ],
        "platforms": {
            "google_play": "com.hnhs.endlesssea.gp",
        },
    },
    {
        "key": "honor_of_kings",
        "display_name": "王者荣耀",
        "genre": "MOBA",
        "aliases": ["王者荣耀", "honor of kings"],
        "platforms": {
            "taptap": "23167",
            "google_play": "com.levelinfinite.sgameGlobal",
        },
        "platform_display_names": {
            "google_play": "王者荣耀国际服",
        },
    },
    {
        "key": "genshin",
        "display_name": "原神",
        "genre": "RPG",
        "aliases": ["原神", "genshin", "genshin impact"],
        "platforms": {
            "taptap": "168332",
            "google_play": "com.miHoYo.GenshinImpact",
        },
    },
]

_PLATFORM_KEYS = {
    "steam": "steam",
    "taptap": "taptap",
    "google_play": "google_play",
    "google play": "google_play",
}


def _norm_platform(platform: str) -> str:
    return _PLATFORM_KEYS.get((platform or "").strip().lower(), (platform or "").strip().lower())


def custom_products_path() -> str:
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "data", "custom_products.json")


def load_custom_products() -> List[Dict[str, Any]]:
    path = custom_products_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
    except Exception:
        pass
    return []


def save_custom_products(entries: List[Dict[str, Any]]) -> None:
    path = custom_products_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(entries, handle, ensure_ascii=False, indent=2)


def get_all_product_entries() -> List[Dict[str, Any]]:
    return list(PRODUCT_ENTRIES) + load_custom_products()


def _slugify(name: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower()).strip("_")
    return token or "custom_game"


def _build_indexes(entries: Sequence[Dict[str, Any]]) -> tuple[
    Dict[str, str],
    Dict[str, str],
    Dict[str, Dict[str, str]],
    Dict[str, str],
    Dict[str, str],
    Dict[str, str],
    Dict[str, str],
]:
    display_by_id: Dict[str, str] = {}
    genre_by_id: Dict[str, str] = {}
    platform_display: Dict[str, Dict[str, str]] = {}
    taptap_aliases: Dict[str, str] = {}
    taptap_demo: Dict[str, str] = {}
    gplay_aliases: Dict[str, str] = {}
    gplay_demo: Dict[str, str] = {}

    for entry in entries:
        base_name = str(entry.get("display_name") or entry.get("key") or "").strip()
        genre = str(entry.get("genre") or "").strip()
        per_platform_names = entry.get("platform_display_names") or {}
        platforms = entry.get("platforms") or {}

        for plat, product_id in platforms.items():
            pid = str(product_id).strip()
            if not pid:
                continue
            name = str(per_platform_names.get(plat) or base_name).strip() or pid
            display_by_id[pid] = name
            if genre:
                genre_by_id[pid] = genre
            platform_display.setdefault(pid, {})[plat] = name

            if plat == "taptap":
                taptap_demo[pid] = name
            elif plat == "google_play":
                gplay_demo[pid] = name

        alias_tokens = list(entry.get("aliases") or [])
        if base_name:
            alias_tokens.append(base_name)
        for alias in alias_tokens:
            token = str(alias).strip().lower()
            if not token:
                continue
            for plat, product_id in platforms.items():
                pid = str(product_id).strip()
                if not pid:
                    continue
                if plat == "taptap":
                    taptap_aliases[token] = pid
                elif plat == "google_play":
                    gplay_aliases[token] = pid

    return display_by_id, genre_by_id, platform_display, taptap_aliases, taptap_demo, gplay_aliases, gplay_demo


def _indexes() -> tuple[
    Dict[str, str],
    Dict[str, str],
    Dict[str, Dict[str, str]],
    Dict[str, str],
    Dict[str, str],
    Dict[str, str],
    Dict[str, str],
]:
    return _build_indexes(get_all_product_entries())


def taptap_alias_map() -> Dict[str, str]:
    return dict(_indexes()[3])


def taptap_demo_map() -> Dict[str, str]:
    return dict(_indexes()[4])


def google_play_alias_map() -> Dict[str, str]:
    return dict(_indexes()[5])


def google_play_demo_map() -> Dict[str, str]:
    return dict(_indexes()[6])


def lookup_display_name(
    product_id: str,
    *,
    platform: str = "",
    store_title: str = "",
    overrides: Optional[Dict[str, str]] = None,
) -> str:
    pid = str(product_id or "").strip()
    if not pid:
        return store_title or ""

    if overrides and pid in overrides:
        custom = str(overrides[pid]).strip()
        if custom:
            return custom

    display_by_id, _, platform_display, _, _, _, _ = _indexes()
    plat = _norm_platform(platform)
    if plat and platform_display.get(pid, {}).get(plat):
        return platform_display[pid][plat]
    if pid in display_by_id:
        return display_by_id[pid]

    store = str(store_title or "").strip()
    if store and store != pid:
        return store
    return pid


def lookup_product_genre(product_id: str) -> str:
    _, genre_by_id, _, _, _, _, _ = _indexes()
    return genre_by_id.get(str(product_id or "").strip(), "")


def get_mvp_presets() -> List[Dict[str, str]]:
    presets: List[Dict[str, str]] = []
    seen: set[str] = set()
    for entry in get_all_product_entries():
        genre = str(entry.get("genre") or "")
        platforms = entry.get("platforms") or {}
        per_platform_names = entry.get("platform_display_names") or {}
        base_name = str(entry.get("display_name") or "")
        for plat, product_id in platforms.items():
            if plat not in ("taptap", "google_play"):
                continue
            pid = str(product_id).strip()
            if not pid or pid in seen:
                continue
            name = str(per_platform_names.get(plat) or base_name or pid)
            presets.append(
                {
                    "id": pid,
                    "name": name,
                    "genre": genre,
                    "platform": plat,
                    "user_added": bool(entry.get("user_added")),
                }
            )
            seen.add(pid)
    return presets


def has_mapping_syntax(raw: str) -> bool:
    return bool(re.search(r"[:@|]", (raw or "").strip()))


def parse_product_name_overrides(raw: str) -> Dict[str, str]:
    text = (raw or "").strip()
    if not text:
        return {}

    overrides: Dict[str, str] = {}
    for segment in re.split(r"[\n,;]+", text):
        token = segment.strip()
        if not token:
            continue
        if ":" in token:
            pid, name = token.split(":", 1)
            pid, name = pid.strip(), name.strip()
            if pid and name:
                overrides[pid] = name
            continue
        for sep in ("@", "|"):
            if sep in token:
                left, right = token.split(sep, 1)
                left, right = left.strip(), right.strip()
                if not left or not right:
                    break
                if _looks_like_product_id(left):
                    overrides[left] = right
                else:
                    overrides[right] = left
                break
    return overrides


def _looks_like_product_id(token: str) -> bool:
    raw = (token or "").strip()
    if not raw:
        return False
    if raw.isdigit():
        return True
    return bool(re.match(r"^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$", raw))


def resolve_mvp_crawl_targets(
    platform: str,
    app_ids_raw: str,
    product_names_raw: str = "",
) -> tuple[List[str], Dict[str, str], List[str]]:
    from src.services.analysis_wizard import resolve_game_inputs
    from src.services.google_play_pipeline import resolve_google_play_inputs
    from src.services.taptap_pipeline import resolve_taptap_inputs

    plat = (platform or "steam").strip().lower()
    id_text = (app_ids_raw or "").strip()
    name_text = (product_names_raw or "").strip()
    errors: List[str] = []

    overrides = parse_product_name_overrides(name_text)
    crawl_input = id_text
    if not crawl_input:
        if overrides:
            crawl_input = ",".join(overrides.keys())
        elif name_text and not has_mapping_syntax(name_text):
            crawl_input = name_text

    if not crawl_input:
        return [], {}, ["请至少选择一款产品，或使用「新增游戏产品」添加"]

    if plat == "taptap":
        resolved = resolve_taptap_inputs(crawl_input)
    elif plat == "google_play":
        resolved = resolve_google_play_inputs(crawl_input)
    else:
        resolved = resolve_game_inputs(crawl_input)

    app_ids = list(resolved.get("app_ids") or [])
    errors.extend(resolved.get("errors") or [])
    if not app_ids:
        msg = resolved.get("message") or "未能解析游戏 ID"
        errors.append(str(msg))
        return [], overrides, errors

    return app_ids, overrides, errors


def add_custom_product(
    *,
    display_name: str,
    platform: str,
    product_id: str = "",
    genre: str = "",
) -> Dict[str, Any]:
    """Register a new game product (persists to data/custom_products.json)."""
    from src.services.game_genre import infer_product_genre

    name = (display_name or "").strip()
    if not name:
        raise ValueError("请填写游戏产品名称")

    plat = _norm_platform(platform)
    if plat not in ("steam", "taptap", "google_play"):
        raise ValueError(f"不支持的渠道：{platform}")

    pid = (product_id or "").strip()
    if not pid:
        app_ids, _, errors = resolve_mvp_crawl_targets(plat, "", name)
        if not app_ids:
            detail = errors[0] if errors else "未能解析平台 ID，请填写包名/AppID"
            raise ValueError(detail)
        pid = app_ids[0]

    entry = {
        "key": _slugify(name),
        "display_name": name,
        "genre": (genre or "").strip() or infer_product_genre(pid, name),
        "aliases": sorted({name.lower(), _slugify(name).replace("_", " ")}),
        "platforms": {plat: pid},
        "user_added": True,
    }

    custom = load_custom_products()
    replaced = False
    for idx, existing in enumerate(custom):
        existing_plat = (existing.get("platforms") or {}).get(plat)
        if str(existing_plat) == pid or str(existing.get("display_name") or "").lower() == name.lower():
            custom[idx] = entry
            replaced = True
            break
    if not replaced:
        custom.append(entry)
    save_custom_products(custom)

    return {
        "success": True,
        "entry": entry,
        "product": {
            "id": pid,
            "name": name,
            "genre": entry["genre"],
            "platform": plat,
            "user_added": True,
        },
    }


def apply_product_display_names(
    dataset: Dict[str, Any],
    overrides: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    merged_overrides = dict(overrides or {})

    def _name_for(pid: str, current: str = "", platform: str = "") -> str:
        return lookup_display_name(
            pid,
            platform=platform,
            store_title=current,
            overrides=merged_overrides,
        )

    for game in dataset.get("games") or []:
        if not isinstance(game, dict):
            continue
        pid = str(game.get("app_id") or game.get("package_id") or "").strip()
        platform = str(game.get("platform") or "")
        if pid:
            game["name"] = _name_for(pid, str(game.get("name") or ""), platform)

    for bucket in ("comments", "metrics"):
        for row in dataset.get(bucket) or []:
            if not isinstance(row, dict):
                continue
            pid = str(row.get("product") or "").strip()
            platform = str(row.get("platform") or "")
            if pid:
                row["product_name"] = _name_for(pid, str(row.get("product_name") or ""), platform)

    return dataset
