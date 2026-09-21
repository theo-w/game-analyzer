"""Game library and gameplay breakdown (竞品资料库 / 玩法拆解)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.database import db_manager
from src.mvp_data import get_mvp_comments_and_metrics, mvp_validation_passed
from src.services.game_genre import assign_competitors_by_genre, infer_product_genre
from src.services.game_versions import GameVersionRepository

GENRE_PRESETS = [
    "MOBA",
    "FPS",
    "Battle Royale",
    "RPG",
    "SLG",
    "Casual",
    "Card",
    "Roguelike",
    "Open World",
    "Sports",
]

BUSINESS_MODELS = ["Free-to-Play", "Premium", "Hybrid", "Subscription", "Ad-supported"]

BREAKDOWN_SECTIONS = [
    ("core_loop", "核心循环", "玩家重复体验的最小闭环（目标→操作→反馈→奖励）"),
    ("progression", "成长路径", "等级、装备、段位、收集等中长期追求"),
    ("level_design", "关卡设计", "地图结构、难度曲线、关卡目标与节奏编排"),
    ("monetization", "商业化设计", "付费点、Battle Pass、皮肤、抽卡等"),
    ("social_features", "社交与竞技", "组队、公会、排位、观战、UGC"),
    ("session_design", "单局/session 设计", "时长、节奏、失败惩罚、回流钩子"),
    ("differentiation", "差异化卖点", "相对同品类竞品的核心差异"),
    ("benchmarks", "可借鉴点", "值得参考的机制或运营手法"),
]


def _now() -> str:
    return datetime.now().isoformat()


def _json_loads(value: Any, default: Any) -> Any:
    if value is None or value == "":
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


def _row_to_game(row: Dict[str, Any]) -> Dict[str, Any]:
    if not row:
        return {}
    return {
        **row,
        "platforms": _json_loads(row.get("platforms"), []),
        "tags": _json_loads(row.get("tags"), []),
        "competitor_ids": _json_loads(row.get("competitor_ids"), []),
        "store_urls": _json_loads(row.get("store_urls"), {}),
    }


def _row_to_breakdown(row: Dict[str, Any]) -> Dict[str, Any]:
    if not row:
        return {}
    return {
        **row,
        "pillars": _json_loads(row.get("pillars"), []),
    }


class GameLibraryRepository:
    @staticmethod
    def list_games(
        *,
        username: Optional[str] = None,
        genre: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM game_library WHERE is_active = 1"
        params: List[Any] = []
        if username:
            query += " AND (username IS NULL OR username = '' OR username = ?)"
            params.append(username)
        if genre and genre != "all":
            query += " AND (genre = ? OR sub_genre = ?)"
            params.extend([genre, genre])
        if search:
            query += " AND (name LIKE ? OR name_en LIKE ? OR summary LIKE ? OR tags LIKE ?)"
            like = f"%{search}%"
            params.extend([like, like, like, like])
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        rows = db_manager.execute(query, tuple(params)) or []
        return [_row_to_game(r) for r in rows]

    @staticmethod
    def get(game_id: str) -> Optional[Dict[str, Any]]:
        row = db_manager.execute_one(
            "SELECT * FROM game_library WHERE game_id = ? AND is_active = 1",
            (game_id,),
        )
        return _row_to_game(row) if row else None

    @staticmethod
    def create(data: Dict[str, Any]) -> str:
        game_id = data.get("game_id") or f"game_{uuid.uuid4().hex[:10]}"
        payload = {
            "game_id": game_id,
            "username": data.get("username") or "",
            "name": data["name"],
            "name_en": data.get("name_en", ""),
            "genre": data.get("genre", ""),
            "sub_genre": data.get("sub_genre", ""),
            "platforms": json.dumps(data.get("platforms") or [], ensure_ascii=False),
            "developer": data.get("developer", ""),
            "publisher": data.get("publisher", ""),
            "release_date": data.get("release_date", ""),
            "business_model": data.get("business_model", "Free-to-Play"),
            "steam_app_id": data.get("steam_app_id", ""),
            "store_urls": json.dumps(data.get("store_urls") or {}, ensure_ascii=False),
            "tags": json.dumps(data.get("tags") or [], ensure_ascii=False),
            "summary": data.get("summary", ""),
            "cover_emoji": data.get("cover_emoji", "🎮"),
            "competitor_ids": json.dumps(data.get("competitor_ids") or [], ensure_ascii=False),
            "source": data.get("source", "manual"),
            "is_active": 1,
            "created_at": _now(),
            "updated_at": _now(),
        }
        db_manager.insert("game_library", payload)
        return game_id

    @staticmethod
    def update(game_id: str, data: Dict[str, Any]) -> bool:
        allowed = {
            "name",
            "name_en",
            "genre",
            "sub_genre",
            "developer",
            "publisher",
            "release_date",
            "business_model",
            "steam_app_id",
            "summary",
            "cover_emoji",
            "source",
        }
        json_fields = {"platforms", "tags", "competitor_ids", "store_urls"}
        updates: Dict[str, Any] = {}
        for key in allowed:
            if key in data:
                updates[key] = data[key]
        for key in json_fields:
            if key in data:
                updates[key] = json.dumps(data[key], ensure_ascii=False)
        if not updates:
            return False
        updates["updated_at"] = _now()
        parts = [f"{k} = ?" for k in updates]
        params = list(updates.values()) + [game_id]
        db_manager.execute(
            f"UPDATE game_library SET {', '.join(parts)} WHERE game_id = ?",
            tuple(params),
        )
        return True

    @staticmethod
    def soft_delete(game_id: str) -> bool:
        db_manager.execute(
            "UPDATE game_library SET is_active = 0, updated_at = ? WHERE game_id = ?",
            (_now(), game_id),
        )
        return True


class GameplayBreakdownRepository:
    @staticmethod
    def get(game_id: str) -> Optional[Dict[str, Any]]:
        row = db_manager.execute_one(
            "SELECT * FROM gameplay_breakdowns WHERE game_id = ?",
            (game_id,),
        )
        return _row_to_breakdown(row) if row else None

    @staticmethod
    def upsert(game_id: str, data: Dict[str, Any]) -> bool:
        existing = GameplayBreakdownRepository.get(game_id)
        payload = {
            "core_loop": data.get("core_loop", ""),
            "progression": data.get("progression", ""),
            "level_design": data.get("level_design", ""),
            "monetization": data.get("monetization", ""),
            "social_features": data.get("social_features", ""),
            "session_design": data.get("session_design", ""),
            "differentiation": data.get("differentiation", ""),
            "benchmarks": data.get("benchmarks", ""),
            "analysis_notes": data.get("analysis_notes", ""),
            "pillars": json.dumps(data.get("pillars") or [], ensure_ascii=False),
            "auto_generated": 1 if data.get("auto_generated") else 0,
            "updated_at": _now(),
        }
        if existing:
            parts = [f"{k} = ?" for k in payload]
            params = list(payload.values()) + [game_id]
            db_manager.execute(
                f"UPDATE gameplay_breakdowns SET {', '.join(parts)} WHERE game_id = ?",
                tuple(params),
            )
        else:
            payload["game_id"] = game_id
            db_manager.insert("gameplay_breakdowns", payload)
        return True


def seed_default_library() -> None:
    """Seed reference titles when library is empty (GameRefinery / Sensor Tower style profiles)."""
    count = db_manager.execute_one("SELECT COUNT(*) AS c FROM game_library WHERE is_active = 1")
    if count and int(count["c"]) > 0:
        return

    samples = [
        {
            "game_id": "ref_moba_a",
            "name": "示例：5v5 MOBA（对标王者/LOL）",
            "genre": "MOBA",
            "sub_genre": "Team PvP",
            "platforms": ["Mobile", "PC"],
            "developer": "示例工作室",
            "business_model": "Free-to-Play",
            "tags": ["排位", "皮肤", "赛季", "战队"],
            "summary": "典型碎片化 MOBA：短局对战 + 英雄收集 + 赛季通行证。",
            "cover_emoji": "⚔️",
            "source": "seed",
        },
        {
            "game_id": "ref_fps_b",
            "name": "示例：战术 FPS（对标 CS2/Valorant）",
            "genre": "FPS",
            "sub_genre": "Tactical Shooter",
            "platforms": ["PC"],
            "developer": "示例工作室",
            "business_model": "Free-to-Play",
            "tags": ["排位", "皮肤", "电竞"],
            "summary": "强调枪法与团队配合，局内零成长，局外皮肤变现。",
            "cover_emoji": "🎯",
            "source": "seed",
        },
        {
            "game_id": "ref_roguelike_c",
            "name": "示例：Roguelike 卡牌（对标 Slay the Spire）",
            "genre": "Roguelike",
            "sub_genre": "Deckbuilder",
            "platforms": ["PC", "Mobile", "Switch"],
            "developer": "示例工作室",
            "business_model": "Premium",
            "tags": ["单局构建", "随机地图", "高重玩"],
            "summary": "单局构建循环清晰，付费一次买断，靠内容深度驱动口碑。",
            "cover_emoji": "🃏",
            "source": "seed",
        },
    ]
    for item in samples:
        gid = GameLibraryRepository.create(item)
        GameplayBreakdownRepository.upsert(
            gid,
            _template_breakdown_for_genre(item.get("genre", ""), item.get("name", "")),
        )


def _template_breakdown_for_genre(genre: str, name: str) -> Dict[str, Any]:
    templates = {
        "MOBA": {
            "core_loop": "选英雄 → 对线/打野 → 团战推塔 → 结算段位分",
            "progression": "英雄熟练度、皮肤收集、赛季段位与战令等级",
            "monetization": "英雄/皮肤售卖、Battle Pass、限时活动礼包",
            "social_features": "开黑组队、战队/公会、观战与赛事",
            "session_design": "单局 15–25 分钟，强回流：每日首胜、赛季重置",
            "differentiation": "需明确：英雄差异化、地图机制或节奏与头部产品的差异",
            "benchmarks": "参考王者荣耀的赛季运营节奏；参考 LOL 的赛事生态",
        },
        "FPS": {
            "core_loop": "匹配 → 回合制对抗 → 经济/技能轮 → 胜负结算",
            "progression": "排位段位、通行证、角色/武器皮肤（不影响数值）",
            "monetization": "皮肤捆绑包、通行证、电竞联动",
            "social_features": "五人排位、战队、自定义房间、回放",
            "session_design": "单局 30–45 分钟，强调公平竞技与反作弊",
            "differentiation": "枪感、地图设计、技能系统或经济规则的创新点",
            "benchmarks": "参考 CS2 的纯粹竞技；参考 Valorant 的技能射击融合",
        },
        "Roguelike": {
            "core_loop": "选路线 → 战斗/事件 → 拿牌/升级 → Boss → 死亡重来",
            "progression": "局外解锁卡牌/角色，局内构建流派",
            "monetization": "买断制 + DLC 角色/剧情；移动端可考虑去广告",
            "social_features": "排行榜、每日挑战、社区 Build 分享",
            "session_design": "单局 45–90 分钟，死亡惩罚适中，鼓励再来一局",
            "differentiation": "构建深度、随机事件质量、美术叙事风格",
            "benchmarks": "参考 Slay the Spire 的构建清晰度；参考 Hades 的叙事推进",
        },
    }
    base = templates.get(
        genre,
        {
            "core_loop": "描述玩家从进入到获得正反馈的最小闭环",
            "progression": "中长期目标与成长系统",
            "level_design": "关卡/地图结构、难度曲线与目标编排",
            "monetization": "主要变现方式与付费动机",
            "social_features": "社交、竞技或 UGC 设计",
            "session_design": "单局时长与回流机制",
            "differentiation": f"{name} 相对同类的独特价值",
            "benchmarks": "列出可对标的竞品与可借鉴机制",
        },
    )
    base["auto_generated"] = True
    base["analysis_notes"] = "系统根据品类模板生成的初始拆解，请结合实际调研补充。"
    return base


def sync_library_from_mvp(username: str = "", output_dir: Optional[str] = None) -> Dict[str, Any]:
    """Import Steam MVP crawled titles into the game library."""
    if not mvp_validation_passed(output_dir):
        return {"success": False, "message": "MVP Steam 数据未就绪，请先运行 /mvp 抓取"}

    comments, metrics, _ = get_mvp_comments_and_metrics(output_dir)
    if not metrics:
        return {"success": False, "message": "MVP 数据集为空"}

    products: Dict[str, Dict[str, Any]] = {}
    for row in metrics:
        pid = str(row.get("product") or "")
        if not pid:
            continue
        platform = str(row.get("platform") or row.get("平台") or "Steam")
        plat_lower = platform.lower()
        source = str(row.get("source") or "")
        is_taptap = plat_lower == "taptap" or source.startswith("taptap")
        is_gplay = plat_lower == "google play" or source.startswith("google_play")
        if is_gplay:
            plat_label = "Google Play"
            game_id_prefix = "google_play_"
            row_source = "google_play_public"
        elif is_taptap:
            plat_label = "TapTap"
            game_id_prefix = "taptap_"
            row_source = "taptap_public"
        else:
            plat_label = "Steam"
            game_id_prefix = "steam_"
            row_source = "mvp_steam"
        if pid not in products:
            products[pid] = {
                "name": row.get("product_name") or f"{plat_label} App {pid}",
                "steam_app_id": pid if not is_taptap and not is_gplay else "",
                "taptap_app_id": pid if is_taptap else "",
                "google_play_id": pid if is_gplay else "",
                "platforms": [plat_label],
                "genre": _infer_genre_from_metrics(metrics, pid),
                "business_model": "Free-to-Play",
                "tags": [plat_label, "真实数据"],
                "summary": f"从 MVP 同步的竞品：{row.get('product_name') or pid}",
                "source": row_source,
            }

    created, updated = 0, 0
    competitor_map = assign_competitors_by_genre(products)
    for pid, meta in products.items():
        platforms = meta.get("platforms") or ["Steam"]
        if "Google Play" in platforms:
            game_id = f"google_play_{pid}"
        elif "TapTap" in platforms:
            game_id = f"taptap_{pid}"
        else:
            game_id = f"steam_{pid}"
        meta["competitor_ids"] = competitor_map.get(game_id, [])
        existing = GameLibraryRepository.get(game_id)
        if existing:
            GameLibraryRepository.update(game_id, meta)
            updated += 1
        else:
            GameLibraryRepository.create({**meta, "game_id": game_id, "username": username})
            created += 1

        breakdown = generate_breakdown_from_comments(game_id, meta["name"], comments, pid)
        GameplayBreakdownRepository.upsert(game_id, breakdown)

    return {
        "success": True,
        "created": created,
        "updated": updated,
        "total": len(products),
        "competitors_linked": sum(1 for ids in competitor_map.values() if ids),
    }


def backfill_competitor_links(game_id: str) -> None:
    """Recompute competitor_ids when missing (e.g. after MVP sync before related-genre fallback)."""
    game = GameLibraryRepository.get(game_id)
    if not game or game.get("competitor_ids"):
        return
    if not str(game_id).startswith("steam_"):
        return

    products: Dict[str, Dict[str, Any]] = {}
    for row in GameLibraryRepository.list_games():
        gid = row.get("game_id") or ""
        if not gid.startswith("steam_"):
            continue
        pid = str(row.get("steam_app_id") or gid.replace("steam_", "", 1))
        products[pid] = {
            "name": row.get("name"),
            "genre": row.get("genre") or infer_product_genre(pid, row.get("name", "")),
        }
    if len(products) < 2:
        return

    mapping = assign_competitors_by_genre(products)
    peer_ids = mapping.get(game_id, [])
    if peer_ids:
        GameLibraryRepository.update(game_id, {"competitor_ids": peer_ids})


def _infer_genre_from_metrics(metrics: List[Dict], product_id: str) -> str:
    name = ""
    for row in metrics:
        if str(row.get("product")) == product_id:
            name = row.get("product_name") or ""
            break
    return infer_product_genre(product_id, name)


def generate_breakdown_from_comments(
    game_id: str,
    name: str,
    comments: List[Dict[str, Any]],
    product_id: str,
) -> Dict[str, Any]:
    """Heuristic gameplay breakdown from review themes (no LLM required)."""
    from collections import Counter

    product_comments = [
        c
        for c in comments
        if str(c.get("product") or c.get("产品") or "") == product_id
    ]
    texts = " ".join(
        (c.get("内容") or c.get("content") or "").lower() for c in product_comments
    )

    themes = Counter()
    theme_map = {
        "performance": ("性能/稳定性", ("卡", "lag", "crash", "闪退", "延迟", "fps")),
        "monetization": ("商业化", ("付费", "氪", "贵", "pay", "price", "dlc")),
        "matchmaking": ("匹配/竞技", ("匹配", "排位", "外挂", "rank", "cheat")),
        "content": ("内容量", ("内容", "无聊", "刷", "content", "grind")),
        "social": ("社交", ("好友", "组队", "friend", "team", "公会")),
        "gameplay": ("核心玩法", ("好玩", "fun", "玩法", "gameplay", "手感")),
    }
    for key, (_, kws) in theme_map.items():
        if any(kw in texts for kw in kws):
            themes[key] += 1

    top_themes = [theme_map[k][0] for k, _ in themes.most_common(4)]
    genre = _infer_genre_from_metrics([], product_id)

    base = _template_breakdown_for_genre(genre, name)
    if top_themes:
        base["analysis_notes"] = (
            f"基于 {len(product_comments)} 条 Steam 评论关键词归纳，玩家高频讨论："
            + "、".join(top_themes)
            + "。建议结合实机体验补充拆解。"
        )
        if themes.get("gameplay"):
            base["core_loop"] += "\n\n【评论信号】玩家认可核心玩法/手感相关讨论较多。"
        if themes.get("monetization"):
            base["monetization"] += "\n\n【评论信号】付费/定价是玩家主要吐槽或关注点之一。"
        if themes.get("matchmaking"):
            base["social_features"] += "\n\n【评论信号】匹配、排位或竞技公平性被频繁提及。"

    base["auto_generated"] = True
    return base


def get_game_detail(game_id: str) -> Optional[Dict[str, Any]]:
    backfill_competitor_links(game_id)
    game = GameLibraryRepository.get(game_id)
    if not game:
        return None
    breakdown = GameplayBreakdownRepository.get(game_id) or {}
    if not (breakdown.get("core_loop") or "").strip():
        breakdown = _template_breakdown_for_genre(
            game.get("genre", ""),
            game.get("name", ""),
        )
    competitors = []
    for cid in game.get("competitor_ids") or []:
        comp = GameLibraryRepository.get(cid)
        if comp:
            competitors.append(
                {
                    "game_id": comp["game_id"],
                    "name": comp["name"],
                    "genre": comp.get("genre"),
                    "cover_emoji": comp.get("cover_emoji", "🎮"),
                }
            )
    return {
        "game": game,
        "breakdown": breakdown,
        "competitors": competitors,
        "versions": GameVersionRepository.list_for_game(game_id),
        "sections": [
            {"key": k, "title": t, "hint": h} for k, t, h in BREAKDOWN_SECTIONS
        ],
    }
