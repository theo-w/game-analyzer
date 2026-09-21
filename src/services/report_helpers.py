"""Helper functions for scheduled and generated reports."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

DOWNLOAD_METRIC_ALIASES = (
    "用户总下载量",
    "downloads",
    "installs",
    "抓取评论数",
    "Steam汇总评论数",
)
REVENUE_METRIC_ALIASES = ("充值金额", "revenue", "收入", "当前价格_美分")
RATING_METRIC_ALIASES = ("7日留存率", "rating", "评分", "样本好评率", "Steam汇总好评率")
ARPPU_METRIC_ALIASES = ("付费付费占比 (ARPPU)", "ARPPU", "arppu", "付费占比")


def product_label_map(metrics: List[dict]) -> Dict[str, str]:
    labels: Dict[str, str] = {}
    for row in metrics:
        pid = row.get("product")
        if not pid:
            continue
        pid = str(pid)
        labels[pid] = str(row.get("product_name") or labels.get(pid) or pid)
    return labels


def _metric_rows(metrics: List[dict], product: str) -> List[dict]:
    return [m for m in metrics if str(m.get("product") or "") == str(product)]


def _pick_metric_value(rows: List[dict], aliases: tuple) -> float:
    for row in rows:
        name = str(row.get("metric") or row.get("指标") or "")
        if any(alias in name or name == alias for alias in aliases):
            raw = row.get("值", row.get("value", 0))
            if isinstance(raw, (int, float)):
                return float(raw)
            text = str(raw).replace("%", "").replace("¥", "").strip()
            try:
                return float(text)
            except ValueError:
                continue
    return 0.0


def generate_report_summary(metrics, comments, report_type):
    labels = product_label_map(metrics)
    products = list(dict.fromkeys(m.get("product") for m in metrics if m.get("product")))
    total_downloads = sum(
        int(_pick_metric_value(_metric_rows(metrics, p), DOWNLOAD_METRIC_ALIASES))
        for p in products
    )
    type_labels = {"daily": "日报", "weekly": "周报", "monthly": "月报"}
    return (
        f"📊 {type_labels.get(report_type, '报表')} - {datetime.now().strftime('%Y年%m月%d日')}\n\n"
        f"📱 覆盖产品：{', '.join([labels.get(str(p), str(p)) for p in products])}\n"
        f"📥 总下载量：{total_downloads:,}\n"
        f"💬 评论数量：{len(comments)}条\n"
        f"📈 数据周期：{report_type}"
    )


def generate_product_details(metrics):
    labels = product_label_map(metrics)
    products = list(dict.fromkeys(m.get("product") for m in metrics if m.get("product")))
    details = []
    for product in products:
        rows = _metric_rows(metrics, product)
        details.append(
            {
                "product": labels.get(str(product), str(product)),
                "downloads": int(_pick_metric_value(rows, DOWNLOAD_METRIC_ALIASES)),
                "arppu": _pick_metric_value(rows, ARPPU_METRIC_ALIASES),
                "retention": _pick_metric_value(rows, RATING_METRIC_ALIASES),
                "channels": list(
                    dict.fromkeys(
                        m.get("channel") or m.get("platform") or m.get("平台")
                        for m in rows
                        if m.get("channel") or m.get("platform") or m.get("平台")
                    )
                ),
            }
        )
    return details


def analyze_trends(metrics):
    trends = []
    products = list(set(m.get("product") for m in metrics))
    for product in products:
        p_metrics = [m for m in metrics if m.get("product") == product]
        download_metric = next(
            (
                m for m in p_metrics
                if any(a in str(m.get("metric") or "") for a in DOWNLOAD_METRIC_ALIASES)
            ),
            None,
        )
        if download_metric and download_metric.get("环比变化"):
            change = download_metric["环比变化"]
            trend_type = "up" if change.startswith("+") else "down"
            trends.append(
                {"product": product, "metric": "下载量", "change": change, "trend": trend_type}
            )
    return trends


def generate_recommendations(metrics, comments):
    recommendations = []
    products = list(set(m.get("product") for m in metrics))
    for product in products:
        p_metrics = [m for m in metrics if m.get("product") == product]
        retention = next((m for m in p_metrics if "留存率" in m.get("metric", "")), None)
        if retention:
            retention_val = float(str(retention.get("值", "0")).replace("%", ""))
            if retention_val < 30:
                recommendations.append(
                    {
                        "product": product,
                        "type": "critical",
                        "title": "留存率偏低",
                        "suggestion": "建议优化新手引导流程，增加新手福利活动",
                    }
                )
    return recommendations


def generate_html_period_report(
    report_type: str,
    metrics: List[dict],
    product_ids: Optional[List[str]] = None,
) -> str:
    """Build daily/weekly/monthly HTML report from resolved user metrics."""
    rows = list(metrics or [])
    if product_ids:
        wanted = {str(p) for p in product_ids if p}
        rows = [m for m in rows if str(m.get("product") or "") in wanted]

    labels = product_label_map(rows)
    products = list(dict.fromkeys(m.get("product") for m in rows if m.get("product")))
    if product_ids:
        ordered = [p for p in product_ids if str(p) in {str(x) for x in products}]
        products = ordered or products

    total_downloads = int(
        sum(_pick_metric_value(_metric_rows(rows, p), DOWNLOAD_METRIC_ALIASES) for p in products)
    )
    total_revenue = int(
        sum(_pick_metric_value(_metric_rows(rows, p), REVENUE_METRIC_ALIASES) for p in products)
    )
    arppu_values = [
        _pick_metric_value(_metric_rows(rows, p), ARPPU_METRIC_ALIASES)
        for p in products
        if _pick_metric_value(_metric_rows(rows, p), ARPPU_METRIC_ALIASES) > 0
    ]
    avg_arppu = round(sum(arppu_values) / len(arppu_values), 2) if arppu_values else 0.0

    summary_cards = f"""
        <div class="card"><div class="card-title">总规模/评论样本</div><div class="card-value">{total_downloads:,}</div></div>
        <div class="card"><div class="card-title">产品数量</div><div class="card-value">{len(products)}</div></div>"""
    # 收入/ARPPU 仅在数据集中真实存在（如用户导入的经营 CSV）时输出
    if total_revenue > 0:
        summary_cards += f"""
        <div class="card"><div class="card-title">充值/收入</div><div class="card-value">¥{total_revenue:,}</div></div>"""
    if avg_arppu > 0:
        summary_cards += f"""
        <div class="card"><div class="card-title">平均ARPPU</div><div class="card-value">¥{avg_arppu}</div></div>"""

    type_labels = {"daily": "日报", "weekly": "周报", "monthly": "月报"}
    title = type_labels.get(report_type, "报告")
    now = datetime.now()
    subtitle = now.strftime("%Y-%m-%d")
    if report_type == "weekly":
        subtitle = f"周期: {subtitle}"
    elif report_type == "monthly":
        subtitle = f"月份: {now.strftime('%Y-%m')}"

    product_lines = "".join(
        f"""
        <div class="card">
            <div class="card-title">{labels.get(str(pid), str(pid))}</div>
            <div class="card-value" style="font-size:16px;">规模 {int(_pick_metric_value(_metric_rows(rows, pid), DOWNLOAD_METRIC_ALIASES)):,}</div>
            <div class="change">好评/评分 {_pick_metric_value(_metric_rows(rows, pid), RATING_METRIC_ALIASES):.1f}%</div>
        </div>"""
        for pid in products
    )

    scope = "、".join(labels.get(str(p), str(p)) for p in products) or "全部产品"
    generated_at = now.strftime("%Y-%m-%d %H:%M:%S")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>{title} - {subtitle}</title>
    <style>
        body {{font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px;}}
        .header {{text-align: center; margin-bottom: 30px;}}
        .title {{font-size: 24px; font-weight: bold; color: #1e293b;}}
        .subtitle {{color: #64748b; margin-top: 8px;}}
        .summary {{display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; margin: 20px 0;}}
        .card {{background: #f8fafc; padding: 16px; border-radius: 8px;}}
        .card-title {{font-size: 14px; color: #64748b;}}
        .card-value {{font-size: 24px; font-weight: bold; color: #1e293b;}}
        .change {{font-size: 12px; margin-top: 4px; color: #64748b;}}
        .footer {{text-align: center; margin-top: 40px; color: #94a3b8; font-size: 14px;}}
    </style>
</head>
<body>
    <div class="header">
        <div class="title">{title}</div>
        <div class="subtitle">{subtitle}</div>
    </div>
    <h3>📊 核心指标汇总</h3>
    <div class="summary">{summary_cards}</div>
    <h3>🎮 分产品概览</h3>
    <div class="summary">{product_lines}</div>
    <div class="footer">
        <div>产品范围: {scope}</div>
        <div>生成时间: {generated_at}</div>
    </div>
</body>
</html>"""
