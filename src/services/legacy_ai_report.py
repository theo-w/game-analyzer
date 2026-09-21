"""Template-based AI analysis for mock game_a/b/c datasets."""

from __future__ import annotations

from typing import Dict, List


def _neutral_trend_for_product(pid: str, name: str) -> Dict[str, object]:
    """Template trend row for real catalog products (non mock game_a/b/c)."""
    bucket = abs(hash(pid)) % 3
    rating = ("良好", "中等", "优秀")[bucket]
    trend = ("稳定", "上升", "波动")[bucket]
    change = ("+3%", "+8%", "-2%")[bucket]
    return {
        "product": name,
        "rating": rating,
        "trend": trend,
        "change": change,
        "strengths": ["核心玩法反馈积极", "社区讨论活跃", "版本更新受关注"],
    }


def generate_product_trends(product_ids: List[str], product_names: Dict[str, str]):
    trends = []
    has_valid_products = False
    explicit_ids = [pid for pid in product_ids if pid and pid != "all"]

    for pid in explicit_ids:
        name = product_names.get(pid)
        if not name:
            continue
        has_valid_products = True
        if pid in MOCK_PRODUCT_NAMES:
            trends.append(
                {
                    "product": name,
                    "rating": "优秀" if pid == "game_c" else "良好" if pid == "game_b" else "中等",
                    "trend": "上升" if pid == "game_c" else "稳定" if pid == "game_b" else "下降",
                    "change": "+12%" if pid == "game_c" else "+3%" if pid == "game_b" else "-8%",
                    "strengths": ["留存率高", "用户粘性强"]
                    if pid == "game_c"
                    else ["玩法新颖", "画面精美"]
                    if pid == "game_b"
                    else ["战斗系统优秀"],
                }
            )
        else:
            trends.append(_neutral_trend_for_product(pid, name))

    if not has_valid_products and not explicit_ids:
        trends = [
            {
                "product": "游戏C - 魔法大陆",
                "rating": "优秀",
                "trend": "上升",
                "change": "+12%",
                "strengths": ["留存率高", "用户粘性强"],
            },
            {
                "product": "游戏B - 星际争霸",
                "rating": "良好",
                "trend": "稳定",
                "change": "+3%",
                "strengths": ["玩法新颖", "画面精美"],
            },
            {
                "product": "游戏A - 战神传说",
                "rating": "中等",
                "trend": "下降",
                "change": "-8%",
                "strengths": ["战斗系统优秀"],
            },
        ]
    return trends


def generate_new_product_trends():
    return {
        "top_categories": ["RPG", "动作", "策略"],
        "hot_features": ["开放世界", "多人联机", "虚拟形象"],
        "recommendations": [
            "🔥 RPG类型持续火爆，建议加大投入",
            "🎮 多人联机需求增长，优化网络体验",
            "📱 移动端用户增长，适配触摸屏操作",
            "💬 社区活跃，UGC功能需求强烈",
        ],
        "upcoming_products": [
            {"name": "游戏G - 永恒之塔", "forecast": "爆款潜力", "reason": "优秀的画面表现+独特玩法"},
            {"name": "游戏H - 机甲风暴", "forecast": "稳定增长", "reason": "核心粉丝群体稳定"},
            {"name": "游戏J - 星际前线", "forecast": "市场竞争激烈", "reason": "同类型产品较多"},
        ],
    }


def generate_issues_diagnosis(product_ids, product_names):
    issues = []
    explicit_ids = [p for p in product_ids if p and p != "all"]
    mock_hits = [p for p in explicit_ids if p in MOCK_PRODUCT_NAMES]
    all_products = "all" in product_ids or (not mock_hits and not explicit_ids)

    if all_products or "game_a" in product_ids:
        issues.append(
            {
                "product": "游戏A - 战神传说",
                "severity": "high",
                "issues": ["付费限制过严导致用户流失", "新手引导流程过长", "资源获取难度过高"],
                "impact": "用户流失率上升15%",
            }
        )
    if all_products or "game_b" in product_ids:
        issues.append(
            {
                "product": "游戏B - 星际争霸",
                "severity": "medium",
                "issues": ["付费深度不足", "社交功能薄弱"],
                "impact": "ARPPU低于预期",
            }
        )
    if all_products or "game_c" in product_ids:
        issues.append(
            {
                "product": "游戏C - 魔法大陆",
                "severity": "low",
                "issues": ["内容消耗过快", "新手难度略高"],
                "impact": "长期留存需关注",
            }
        )
    for pid in explicit_ids:
        if pid in MOCK_PRODUCT_NAMES:
            continue
        name = product_names.get(pid, pid)
        issues.append(
            {
                "product": name,
                "severity": "medium",
                "issues": ["付费与留存需结合评论样本持续观察", "新手引导与版本节奏可进一步优化"],
                "impact": "建议结合抓取评论做定向验证",
            }
        )
    return issues


def generate_optimization_suggestions(product_ids, product_names):
    return [
        {
            "category": "🎯 付费设计",
            "priority": "high",
            "suggestions": [
                "将核心机制改为限时免费体验",
                "优化首充奖励设计",
                "增加月卡类型的付费选项",
                "调整付费点节奏",
            ],
        },
        {
            "category": "🎮 游戏体验",
            "priority": "high",
            "suggestions": [
                "简化新手引导流程",
                "优化资源获取反馈",
                "增加用户激励机制",
                "改进新手体验",
            ],
        },
        {
            "category": "📈 运营策略",
            "priority": "medium",
            "suggestions": ["增加限时活动频率", "优化社区互动", "推出UGC功能", "举办线上赛事"],
        },
    ]


def generate_action_plan():
    return {
        "short_term": ["7天内: 上线新手优化版本", "14天内: 调整付费设计", "30天内: 增加限时活动"],
        "medium_term": ["45天内: 推出社交功能", "60天内: 上线UGC系统", "90天内: 举办首次赛事"],
        "long_term": ["6个月: 建立电竞生态", "12个月: 全球化布局", "18个月: IP衍生开发"],
    }


MOCK_PRODUCT_NAMES = {
    "game_a": "游戏A - 战神传说",
    "game_b": "游戏B - 星际争霸",
    "game_c": "游戏C - 魔法大陆",
}
