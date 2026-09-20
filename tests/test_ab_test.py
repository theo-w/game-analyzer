import pytest
import os

from src.ab_test_platform import ABTestPlatform, ABTestExperiment

class TestABTestPlatform:

    def test_create_experiment(self, tmp_path):
        # data_dir 必须指向临时目录, 否则 create_experiment 会写坏仓库 mock_data/ab_experiments.json
        self.ab_platform = ABTestPlatform(data_dir=str(tmp_path))
        experiment = self.ab_platform.create_experiment(
            name='Test Experiment',
            description='Test description',
            variants=[
                {"id": "control", "name": "对照组", "is_control": True},
                {"id": "variant_a", "name": "实验组A", "is_control": False}
            ],
            traffic_allocation=0.5
        )
        assert isinstance(experiment, ABTestExperiment)
        assert experiment.name == 'Test Experiment'
    
    def test_experiment_is_user_eligible(self):
        experiment = ABTestExperiment(
            experiment_id='test_exp',
            name='Test',
            variants=[
                {"id": "control", "name": "对照组", "is_control": True}
            ],
            filters={
                "regions": ["CN"],
                "platforms": ["ios"]
            }
        )
        user_info = {'user_id': 'user123', 'region': 'CN', 'platform': 'ios'}
        result = experiment.is_user_eligible(user_info)
        assert result is True
        
        user_info_ineligible = {'user_id': 'user456', 'region': 'US', 'platform': 'ios'}
        result = experiment.is_user_eligible(user_info_ineligible)
        assert result is False