"""
Onboarding引导模块
提供首次登录引导和功能教程
"""
import json
from datetime import datetime
from typing import Optional, Dict, Any, List
import os
from src.database import db_manager

# 引导步骤配置
ONBOARDING_STEPS = [
    {
        'id': 'step-1',
        'title': '欢迎使用',
        'description': '欢迎来到游戏数据分析引擎！让我们一起了解如何使用这个强大的工具。',
        'icon': '🎉',
        'type': 'welcome',
        'next_step': 'step-2',
        'show_skip': True
    },
    {
        'id': 'step-2',
        'title': '仪表盘概览',
        'description': '仪表盘是您的数据分析中心，包含关键指标卡片和实时数据图表。',
        'icon': '📊',
        'type': 'highlight',
        'target_selector': '.dashboard-container',
        'highlight_color': '#0071e3',
        'next_step': 'step-3',
        'show_skip': True
    },
    {
        'id': 'step-3',
        'title': '数据筛选',
        'description': '使用顶部筛选器可以切换产品、时间周期和数据源，查看不同维度的数据。',
        'icon': '🔍',
        'type': 'highlight',
        'target_selector': '.filters-bar',
        'highlight_color': '#34c759',
        'next_step': 'step-4',
        'show_skip': True
    },
    {
        'id': 'step-4',
        'title': '高级分析',
        'description': '点击高级分析按钮，进入专业分析模块，包含漏斗分析、群组分析等高级功能。',
        'icon': '📈',
        'type': 'highlight',
        'target_selector': '.analytics-btn',
        'highlight_color': '#ff9500',
        'next_step': 'step-5',
        'show_skip': True
    },
    {
        'id': 'step-5',
        'title': '告警设置',
        'description': '设置智能告警，当关键指标异常时会及时通知您。',
        'icon': '🔔',
        'type': 'highlight',
        'target_selector': '.alerts-btn',
        'highlight_color': '#ff3b30',
        'next_step': 'step-6',
        'show_skip': True
    },
    {
        'id': 'step-6',
        'title': '完成引导',
        'description': '恭喜！您已经完成了入门引导。现在开始探索数据分析的强大功能吧！',
        'icon': '🎊',
        'type': 'complete',
        'next_step': None,
        'show_skip': False
    }
]

# 功能教程
FEATURE_TUTORIALS = [
    {
        'id': 'tutorial-dashboard',
        'name': '仪表盘使用指南',
        'description': '学习如何创建和自定义仪表盘',
        'icon': '📊',
        'category': 'dashboard',
        'steps': [
            {'title': '创建仪表盘', 'description': '点击右上角「新建仪表盘」按钮'},
            {'title': '添加组件', 'description': '从组件库中选择需要的图表类型'},
            {'title': '配置数据', 'description': '选择数据源和指标字段'},
            {'title': '保存布局', 'description': '拖拽调整布局后保存'}
        ],
        'duration': '3分钟'
    },
    {
        'id': 'tutorial-funnel',
        'name': '漏斗分析教程',
        'description': '深入了解用户转化漏斗',
        'icon': '🔻',
        'category': 'analytics',
        'steps': [
            {'title': '选择漏斗', 'description': '选择要分析的转化漏斗'},
            {'title': '查看转化', 'description': '分析各步骤的转化率'},
            {'title': '对比分析', 'description': '对比不同产品的转化情况'},
            {'title': '获取建议', 'description': '查看智能优化建议'}
        ],
        'duration': '5分钟'
    },
    {
        'id': 'tutorial-cohort',
        'name': '群组分析教程',
        'description': '分析用户留存和生命周期',
        'icon': '👥',
        'category': 'analytics',
        'steps': [
            {'title': '选择群组', 'description': '选择时间范围和分组方式'},
            {'title': '查看留存', 'description': '分析不同群组的留存曲线'},
            {'title': '对比群组', 'description': '对比多个群组的表现'},
            {'title': '健康评分', 'description': '查看群组健康度评分'}
        ],
        'duration': '4分钟'
    },
    {
        'id': 'tutorial-abtest',
        'name': 'AB测试教程',
        'description': '设计和分析实验',
        'icon': '🧪',
        'category': 'ab-test',
        'steps': [
            {'title': '创建实验', 'description': '设置实验名称和目标'},
            {'title': '添加变体', 'description': '定义不同的实验变体'},
            {'title': '配置受众', 'description': '设置目标用户群体'},
            {'title': '查看结果', 'description': '分析实验数据和统计显著性'}
        ],
        'duration': '6分钟'
    },
    {
        'id': 'tutorial-alerts',
        'name': '告警设置教程',
        'description': '配置智能告警规则',
        'icon': '🔔',
        'category': 'alerts',
        'steps': [
            {'title': '创建规则', 'description': '点击「新建告警规则」'},
            {'title': '设置条件', 'description': '配置监控指标和阈值'},
            {'title': '配置通知', 'description': '设置邮件或Webhook通知'},
            {'title': '测试规则', 'description': '验证告警是否正常工作'}
        ],
        'duration': '3分钟'
    }
]

class OnboardingManager:
    """Onboarding引导管理器"""
    
    def __init__(self):
        self.onboarding_steps = ONBOARDING_STEPS
        self.feature_tutorials = FEATURE_TUTORIALS
    
    def get_onboarding_steps(self) -> List[Dict]:
        """获取所有引导步骤"""
        return self.onboarding_steps
    
    def get_step(self, step_id: str) -> Optional[Dict]:
        """获取单个步骤"""
        return next((step for step in self.onboarding_steps if step['id'] == step_id), None)
    
    def get_next_step(self, current_step_id: str) -> Optional[Dict]:
        """获取下一步骤"""
        current_step = self.get_step(current_step_id)
        if current_step and current_step['next_step']:
            return self.get_step(current_step['next_step'])
        return None
    
    def has_completed_onboarding(self, user_id: str) -> bool:
        """检查用户是否完成引导"""
        result = db_manager.execute_one('''
            SELECT * FROM user_onboarding WHERE user_id = ? AND completed = 1
        ''', (user_id,))
        return result is not None
    
    def set_onboarding_completed(self, user_id: str):
        """标记引导完成"""
        existing = db_manager.execute_one('SELECT * FROM user_onboarding WHERE user_id = ?', (user_id,))
        
        if existing:
            db_manager.execute('''
                UPDATE user_onboarding SET completed = 1, completed_at = ? WHERE user_id = ?
            ''', (datetime.now().isoformat(), user_id))
        else:
            db_manager.execute('''
                INSERT INTO user_onboarding (user_id, completed, completed_at)
                VALUES (?, 1, ?)
            ''', (user_id, datetime.now().isoformat()))
    
    def get_user_progress(self, user_id: str) -> Optional[str]:
        """获取用户引导进度"""
        result = db_manager.execute_one('SELECT current_step FROM user_onboarding WHERE user_id = ?', (user_id,))
        return result['current_step'] if result else None
    
    def set_user_progress(self, user_id: str, step_id: str):
        """设置用户引导进度"""
        existing = db_manager.execute_one('SELECT * FROM user_onboarding WHERE user_id = ?', (user_id,))
        
        if existing:
            db_manager.execute('''
                UPDATE user_onboarding SET current_step = ?, updated_at = ? WHERE user_id = ?
            ''', (step_id, datetime.now().isoformat(), user_id))
        else:
            db_manager.execute('''
                INSERT INTO user_onboarding (user_id, current_step, created_at)
                VALUES (?, ?, ?)
            ''', (user_id, step_id, datetime.now().isoformat()))
    
    def reset_onboarding(self, user_id: str):
        """重置用户引导进度"""
        db_manager.execute('DELETE FROM user_onboarding WHERE user_id = ?', (user_id,))
    
    def get_feature_tutorials(self, category: str = None) -> List[Dict]:
        """获取功能教程列表"""
        if category:
            return [t for t in self.feature_tutorials if t['category'] == category]
        return self.feature_tutorials
    
    def get_feature_tutorial(self, tutorial_id: str) -> Optional[Dict]:
        """获取单个功能教程"""
        return next((t for t in self.feature_tutorials if t['id'] == tutorial_id), None)
    
    def mark_tutorial_completed(self, user_id: str, tutorial_id: str):
        """标记教程完成"""
        existing = db_manager.execute_one('''
            SELECT * FROM user_tutorials WHERE user_id = ? AND tutorial_id = ?
        ''', (user_id, tutorial_id))
        
        if existing:
            db_manager.execute('''
                UPDATE user_tutorials SET completed = 1, completed_at = ? 
                WHERE user_id = ? AND tutorial_id = ?
            ''', (datetime.now().isoformat(), user_id, tutorial_id))
        else:
            db_manager.execute('''
                INSERT INTO user_tutorials (user_id, tutorial_id, completed, completed_at)
                VALUES (?, ?, 1, ?)
            ''', (user_id, tutorial_id, datetime.now().isoformat()))
    
    def has_completed_tutorial(self, user_id: str, tutorial_id: str) -> bool:
        """检查用户是否完成教程"""
        result = db_manager.execute_one('''
            SELECT * FROM user_tutorials WHERE user_id = ? AND tutorial_id = ? AND completed = 1
        ''', (user_id, tutorial_id))
        return result is not None
    
    def get_user_completed_tutorials(self, user_id: str) -> List[str]:
        """获取用户已完成的教程列表"""
        results = db_manager.execute('''
            SELECT tutorial_id FROM user_tutorials WHERE user_id = ? AND completed = 1
        ''', (user_id,))
        return [r['tutorial_id'] for r in results]

def init_onboarding_tables():
    """初始化引导相关表"""
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_onboarding (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT UNIQUE NOT NULL,
                current_step TEXT,
                completed INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT,
                completed_at TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_tutorials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                tutorial_id TEXT NOT NULL,
                completed INTEGER DEFAULT 0,
                created_at TEXT,
                completed_at TEXT,
                UNIQUE(user_id, tutorial_id)
            )
        ''')
        
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_onboarding_user ON user_onboarding(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tutorials_user ON user_tutorials(user_id)')
        
        conn.commit()

# 初始化表
init_onboarding_tables()

# 全局实例
onboarding_manager = OnboardingManager()

def get_onboarding_manager() -> OnboardingManager:
    """获取Onboarding引导管理器"""
    return onboarding_manager
