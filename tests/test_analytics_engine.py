import pytest
import os

from src.analytics_engine import load_data, run_business_intelligence_report

class TestAnalyticsEngine:
    
    def test_load_data(self):
        result = load_data(os.path.join(os.path.dirname(__file__), '..', 'mock_data', 'metrics.json'))
        assert isinstance(result, list)
        assert len(result) > 0
    
    def test_load_data_file_not_found(self):
        result = load_data('/non/existent/path.json')
        assert result is None
    
    def test_run_business_intelligence_report(self):
        comments_data = [
            {'内容': '游戏很好玩', '情绪': 'positive'},
            {'内容': '付费太贵了', '情绪': 'negative'}
        ]
        metrics_data = [
            {'metric': 'revenue', 'value': 10000}
        ]
        result = run_business_intelligence_report(comments_data, metrics_data)
        assert isinstance(result, dict)