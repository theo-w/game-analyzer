"""SEO 内容页测试(游戏舆情 AI 分析平台)。"""

from __future__ import annotations

from fastapi.testclient import TestClient

EXPECTED = {
    "/game-public-opinion-ai-analysis": "游戏舆情 AI 分析平台",
    "/ai-game-opinion-monitoring-system": "AI 游戏舆情监测系统",
    "/game-negative-public-opinion-monitoring": "负面舆情风险识别",
    "/mobile-game-player-experience-analysis": "玩家体验舆情分析",
    "/game-hot-event-tracking": "热点事件追踪",
    "/game-monetization-controversy-monitoring": "商业化争议舆情监测",
    "/cross-platform-game-opinion-aggregation": "跨平台舆情聚合",
}


def _client() -> TestClient:
    from src.web_app import app

    return TestClient(app)


def test_seo_pages_serve_with_meta():
    c = _client()
    for path, title_kw in EXPECTED.items():
        res = c.get(path)
        assert res.status_code == 200, f"{path} -> {res.status_code}"
        assert "text/html" in res.headers["content-type"]
        assert title_kw in res.text
        assert '<meta name="description"' in res.text
        assert '<meta name="keywords"' in res.text
        assert 'rel="canonical"' in res.text


def test_seo_pages_cross_link_and_boundary():
    c = _client()
    res = c.get("/game-public-opinion-ai-analysis")
    # 站内互链
    assert "/ai-game-opinion-monitoring-system" in res.text
    assert "/game-negative-public-opinion-monitoring" in res.text
    # 数据边界标注
    assert "数据边界" in res.text
    assert "不编造内容" in res.text


def test_sitemap_includes_seo_pages(monkeypatch):
    monkeypatch.setenv("PUBLIC_DEMO_BASE_URL", "https://game-analyzer-eq8i.onrender.com")
    res = _client().get("/sitemap.xml")
    assert res.status_code == 200
    for path in EXPECTED:
        assert f"https://game-analyzer-eq8i.onrender.com{path}" in res.text


def test_unknown_seo_path_404():
    res = _client().get("/game-public-opinion-ai-analysis-unknown")
    assert res.status_code == 404


def test_no_nexus_branding():
    c = _client()
    for path in EXPECTED:
        html = c.get(path).text
        assert "NEXUS" not in html, f"{path} 仍含 NEXUS 标志"


def test_topbar_links_use_urls_not_labels():
    html = _client().get("/game-negative-public-opinion-monitoring").text
    # 顶栏已统一为共享 AppNav：静态 HTML 需含挂载容器与脚本引用，链接 href 必须是 URL
    assert 'id="app-nav-mount"' in html
    assert '/static/js/app-nav.js' in html
    assert 'href="平台首页"' not in html


def test_next_steps_causal_path_present():
    html = _client().get("/game-negative-public-opinion-monitoring").text
    assert "下一步 · 推荐路径" in html
    assert "了解 AI 监测系统" in html
    assert "回到平台总览" in html
    assert "查看负面预警" in html


def test_hub_page_lists_five_scenarios():
    html = _client().get("/game-public-opinion-ai-analysis").text
    assert "5 大能力场景" in html
    assert "/game-negative-public-opinion-monitoring" in html
    assert "/cross-platform-game-opinion-aggregation" in html


def test_two_system_positioning_clear():
    html = _client().get("/game-public-opinion-ai-analysis").text
    assert "两系统定位" in html
    assert "Game Analyzer 数据分析工具" in html
    assert "两系统关系（业务边界）" in html
    # CTA 明确进入数据工具(带登录回跳)
    assert "进入数据工具" in html
    assert "/login?redirect=" in html


def test_content_pages_show_positioning_note():
    html = _client().get("/game-negative-public-opinion-monitoring").text
    assert "两系统定位" in html
    assert "不含实时数据" in html


def test_about_page_documents_two_systems():
    res = _client().get("/about")
    assert res.status_code == 200
    assert "两系统定位说明" in res.text
    assert "系统 A" in res.text and "系统 B" in res.text
    assert "不含实时数据" in res.text


def test_sitemap_includes_about(monkeypatch):
    monkeypatch.setenv("PUBLIC_DEMO_BASE_URL", "https://game-analyzer-eq8i.onrender.com")
    res = _client().get("/sitemap.xml")
    assert "https://game-analyzer-eq8i.onrender.com/about" in res.text


def test_prototype_style_applied():
    html = _client().get("/game-public-opinion-ai-analysis").text
    assert "#f5f6f2" in html        # 原型纸感背景
    assert "#e85e2c" in html        # 原型橙色主色
    assert "#172337" in html        # 原型海军蓝
    assert "Georgia" in html        # 衬线标题
    assert "结构演示 · 待工具验证" in html  # 诚实标注
    assert "NEXUS" not in html


def test_landing_prototype_style():
    html = _client().get("/").text
    assert "#f5f6f2" in html
    assert "#e85e2c" in html
    assert "Georgia" in html
