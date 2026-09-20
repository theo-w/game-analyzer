"""
自定义报表构建器模块
支持拖拽式报表设计和可视化配置
"""
import json
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
import os
from src.database import db_manager

# 可用的组件类型
COMPONENT_TYPES = {
    'kpi_card': {
        'name': 'KPI卡片',
        'description': '显示关键指标',
        'icon': '📊',
        'default_config': {
            'title': '指标名称',
            'value': 0,
            'unit': '',
            'trend': 0,
            'color': '#0071e3'
        }
    },
    'line_chart': {
        'name': '折线图',
        'description': '显示趋势数据',
        'icon': '📈',
        'default_config': {
            'title': '趋势图',
            'x_label': '日期',
            'y_label': '数值',
            'data': [],
            'color': '#0071e3'
        }
    },
    'bar_chart': {
        'name': '柱状图',
        'description': '显示对比数据',
        'icon': '📊',
        'default_config': {
            'title': '对比图',
            'x_label': '类别',
            'y_label': '数值',
            'data': [],
            'colors': ['#0071e3', '#34c759', '#ff9500']
        }
    },
    'pie_chart': {
        'name': '饼图',
        'description': '显示占比数据',
        'icon': '🥧',
        'default_config': {
            'title': '占比图',
            'data': [],
            'colors': ['#0071e3', '#34c759', '#ff9500', '#ff3b30', '#af52de']
        }
    },
    'table': {
        'name': '数据表格',
        'description': '显示详细数据',
        'icon': '📋',
        'default_config': {
            'title': '数据表',
            'columns': [],
            'data': []
        }
    },
    'funnel': {
        'name': '漏斗图',
        'description': '显示转化漏斗',
        'icon': '🔻',
        'default_config': {
            'title': '转化漏斗',
            'steps': [],
            'colors': ['#0071e3', '#34c759']
        }
    },
    'text': {
        'name': '文本',
        'description': '显示说明文字',
        'icon': '📝',
        'default_config': {
            'content': '在此输入文本',
            'font_size': 14,
            'color': '#1d1d1f'
        }
    },
    'divider': {
        'name': '分隔线',
        'description': '分隔内容区域',
        'icon': '📏',
        'default_config': {
            'style': 'solid',
            'color': '#e5e5e7'
        }
    }
}

# 可用的数据源
DATA_SOURCES = {
    'revenue': {
        'name': '收入数据',
        'description': '游戏收入相关指标',
        'fields': ['daily_revenue', 'arpu', 'arppu', 'paying_users', 'avg_payment']
    },
    'user': {
        'name': '用户数据',
        'description': '用户相关指标',
        'fields': ['dau', 'wau', 'mau', 'new_users', 'retention_1d', 'retention_7d', 'retention_30d']
    },
    'engagement': {
        'name': '活跃度数据',
        'description': '用户活跃度指标',
        'fields': ['avg_session_time', 'sessions_per_user', 'daily_play_time', 'events_count']
    },
    'conversion': {
        'name': '转化数据',
        'description': '转化漏斗相关指标',
        'fields': ['downloads', 'registrations', 'tutorial_completion', 'first_purchase', 'conversion_rate']
    }
}

class ReportBuilder:
    """报表构建器"""
    
    def __init__(self):
        self.component_types = COMPONENT_TYPES
        self.data_sources = DATA_SOURCES
    
    def create_report(self, user_id: str, name: str, description: str = '') -> Dict:
        """创建新报表"""
        report_id = str(uuid.uuid4())
        
        db_manager.execute('''
            INSERT INTO custom_reports 
            (report_id, user_id, name, description, layout, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (report_id, user_id, name, description, '{}', datetime.now().isoformat()))
        
        return self.get_report(report_id)
    
    def get_report(self, report_id: str) -> Optional[Dict]:
        """获取报表"""
        result = db_manager.execute_one('''
            SELECT * FROM custom_reports WHERE report_id = ?
        ''', (report_id,))
        
        if result:
            result['layout'] = json.loads(result['layout']) if result['layout'] else {}
        return result
    
    def update_report(self, report_id: str, data: Dict) -> bool:
        """更新报表"""
        updates = []
        params = []
        
        if 'name' in data:
            updates.append('name = ?')
            params.append(data['name'])
        
        if 'description' in data:
            updates.append('description = ?')
            params.append(data['description'])
        
        if 'layout' in data:
            updates.append('layout = ?')
            params.append(json.dumps(data['layout']))
        
        if 'filters' in data:
            updates.append('filters = ?')
            params.append(json.dumps(data['filters']))
        
        if not updates:
            return False
        
        params.append(report_id)
        query = f"UPDATE custom_reports SET {', '.join(updates)}, updated_at = ? WHERE report_id = ?"
        params.insert(len(updates), datetime.now().isoformat())
        
        db_manager.execute(query, tuple(params))
        return True
    
    def delete_report(self, report_id: str) -> bool:
        """删除报表"""
        db_manager.execute('DELETE FROM custom_reports WHERE report_id = ?', (report_id,))
        return True
    
    def get_user_reports(self, user_id: str) -> List[Dict]:
        """获取用户报表列表"""
        results = db_manager.execute('''
            SELECT * FROM custom_reports WHERE user_id = ? ORDER BY created_at DESC
        ''', (user_id,))
        
        for result in results:
            result['layout'] = json.loads(result['layout']) if result['layout'] else {}
            result['filters'] = json.loads(result['filters']) if result.get('filters') else {}
        
        return results
    
    def add_component(self, report_id: str, component_type: str, position: Dict) -> Dict:
        """添加组件"""
        if component_type not in self.component_types:
            raise ValueError("Invalid component type")
        
        report = self.get_report(report_id)
        if not report:
            raise ValueError("Report not found")
        
        component_id = str(uuid.uuid4())
        config = self.component_types[component_type]['default_config'].copy()
        
        component = {
            'id': component_id,
            'type': component_type,
            'config': config,
            'position': position
        }
        
        layout = report.get('layout', {})
        if 'components' not in layout:
            layout['components'] = []
        
        layout['components'].append(component)
        self.update_report(report_id, {'layout': layout})
        
        return component
    
    def update_component(self, report_id: str, component_id: str, updates: Dict) -> bool:
        """更新组件"""
        report = self.get_report(report_id)
        if not report:
            return False
        
        layout = report.get('layout', {})
        components = layout.get('components', [])
        
        for comp in components:
            if comp['id'] == component_id:
                if 'config' in updates:
                    comp['config'] = {**comp['config'], **updates['config']}
                if 'position' in updates:
                    comp['position'] = updates['position']
                if 'type' in updates:
                    comp['type'] = updates['type']
                
                self.update_report(report_id, {'layout': layout})
                return True
        
        return False
    
    def delete_component(self, report_id: str, component_id: str) -> bool:
        """删除组件"""
        report = self.get_report(report_id)
        if not report:
            return False
        
        layout = report.get('layout', {})
        components = layout.get('components', [])
        
        new_components = [c for c in components if c['id'] != component_id]
        layout['components'] = new_components
        
        self.update_report(report_id, {'layout': layout})
        return True
    
    def get_component_types(self) -> Dict:
        """获取可用组件类型"""
        return self.component_types
    
    def get_data_sources(self) -> Dict:
        """获取可用数据源"""
        return self.data_sources
    
    def generate_report_html(self, report_id: str) -> str:
        """生成报表HTML"""
        report = self.get_report(report_id)
        if not report:
            return "<div>报表不存在</div>"
        
        layout = report.get('layout', {})
        components = layout.get('components', [])
        
        html = f"<h2>{report['name']}</h2>"
        if report.get('description'):
            html += f"<p>{report['description']}</p>"
        
        for component in components:
            html += self._render_component(component)
        
        return html
    
    def _render_component(self, component: Dict) -> str:
        """渲染组件为HTML"""
        comp_type = component['type']
        config = component.get('config', {})
        
        if comp_type == 'kpi_card':
            trend_icon = '📈' if config.get('trend', 0) >= 0 else '📉'
            trend_color = '#34c759' if config.get('trend', 0) >= 0 else '#ff3b30'
            return f'''
                <div style="background: #f5f5f7; padding: 20px; border-radius: 12px; text-align: center;">
                    <div style="color: #86868b; font-size: 14px;">{config.get('title', '')}</div>
                    <div style="font-size: 32px; font-weight: 700; color: #1d1d1f; margin: 8px 0;">
                        {config.get('value', 0)}{config.get('unit', '')}
                    </div>
                    <div style="color: {trend_color}; font-size: 14px;">{trend_icon} {config.get('trend', 0)}%</div>
                </div>
            '''
        
        elif comp_type == 'text':
            return f'''
                <div style="padding: 16px; color: {config.get('color', '#1d1d1f')}; font-size: {config.get('font_size', 14)}px;">
                    {config.get('content', '')}
                </div>
            '''
        
        elif comp_type == 'divider':
            return f'''
                <hr style="border: none; border-top: 1px {config.get('style', 'solid')} {config.get('color', '#e5e5e7')}; margin: 20px 0;" />
            '''
        
        else:
            return f'''
                <div style="background: #f5f5f7; padding: 20px; border-radius: 12px; min-height: 200px;">
                    <div style="color: #1d1d1f; font-weight: 600; margin-bottom: 12px;">{config.get('title', '')}</div>
                    <div style="color: #86868b; text-align: center; padding: 40px;">
                        {self.component_types[comp_type]['icon']} 图表组件
                    </div>
                </div>
            '''

class ReportRenderer:
    """报表渲染器"""
    
    def __init__(self):
        self.builder = ReportBuilder()
    
    def render_report(self, report_id: str) -> Dict:
        """渲染报表数据"""
        report = self.builder.get_report(report_id)
        if not report:
            return {'error': 'Report not found'}
        
        layout = report.get('layout', {})
        components = layout.get('components', [])
        
        rendered_components = []
        for component in components:
            rendered = self._render_component_data(component)
            rendered_components.append(rendered)
        
        return {
            'report_id': report['report_id'],
            'name': report['name'],
            'description': report.get('description'),
            'components': rendered_components,
            'created_at': report['created_at']
        }
    
    def _render_component_data(self, component: Dict) -> Dict:
        """渲染组件数据"""
        comp_type = component['type']
        config = component.get('config', {})
        
        if comp_type == 'kpi_card':
            return {
                'id': component['id'],
                'type': comp_type,
                'title': config.get('title'),
                'value': config.get('value'),
                'unit': config.get('unit'),
                'trend': config.get('trend'),
                'color': config.get('color')
            }
        
        elif comp_type in ['line_chart', 'bar_chart', 'pie_chart']:
            return {
                'id': component['id'],
                'type': comp_type,
                'title': config.get('title'),
                'data': config.get('data', []),
                'config': config
            }
        
        else:
            return {
                'id': component['id'],
                'type': comp_type,
                'config': config
            }

def init_report_tables():
    """初始化报表相关表"""
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS custom_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id TEXT UNIQUE NOT NULL,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                layout TEXT DEFAULT '{}',
                filters TEXT DEFAULT '{}',
                created_at TEXT,
                updated_at TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS report_schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                schedule_type TEXT DEFAULT 'daily',
                time TEXT,
                recipients TEXT,
                enabled INTEGER DEFAULT 1,
                last_run TEXT,
                created_at TEXT
            )
        ''')
        
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_reports_user ON custom_reports(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_schedules_report ON report_schedules(report_id)')
        
        conn.commit()

# 初始化表
init_report_tables()

# 全局实例
report_builder = ReportBuilder()
report_renderer = ReportRenderer()

def get_report_builder() -> ReportBuilder:
    """获取报表构建器"""
    return report_builder

def get_report_renderer() -> ReportRenderer:
    """获取报表渲染器"""
    return report_renderer
