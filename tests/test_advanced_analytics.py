import pytest
import os

from src.advanced_analytics import (
    FunnelAnalyzer,
    CohortAnalyzer,
    UserJourneyAnalyzer,
    PredictiveAnalyzer,
    AnomalyDetector,
    RealTimeDataStream,
    _derive_scale_metric,
    _derive_arppu,
)

class TestAdvancedAnalytics:
    
    def test_funnel_analyzer(self):
        analyzer = FunnelAnalyzer()
        result = analyzer.create_funnel(products=['game_a'])
        assert isinstance(result, dict)
        assert 'steps' in result
        assert 'health_improvements' in result
        assert isinstance(result['health_improvements'], list)
        assert len(result['health_improvements']) >= 1

    def test_cohort_analyzer_improvements(self):
        analyzer = CohortAnalyzer()
        result = analyzer.create_cohort(products=['game_b'])
        assert 'summary' in result
        assert 'improvements' in result['summary']
        assert isinstance(result['summary']['improvements'], list)
        assert len(result['summary']['improvements']) >= 1
        assert all('suggestion' in item for item in result['summary']['improvements'])
    
    def test_real_time_data_stream(self):
        stream = RealTimeDataStream()
        metrics_data = []
        result = stream.calculate_real_time_metrics(metrics_data)
        assert isinstance(result, dict)
        assert 'online_users' in result
        assert result['online_users'] > 0

    def test_mvp_steam_metric_mapping(self):
        mvp_rows = [
            {"product": "730", "metric": "抓取评论数", "值": 42},
            {"product": "730", "metric": "Steam汇总好评率", "值": "78.5%"},
        ]
        assert _derive_scale_metric(mvp_rows) == 42
        stream = RealTimeDataStream()
        result = stream.calculate_real_time_metrics(mvp_rows)
        assert result["total_downloads"] == 42
        assert result.get("steam_positive_rate") == pytest.approx(78.5)

    def test_mock_arppu_parsing(self):
        rows = [{"product": "game_a", "metric": "付费付费占比 (ARPPU)", "值": "¥ 18.5"}]
        assert _derive_arppu(rows) == pytest.approx(18.5)