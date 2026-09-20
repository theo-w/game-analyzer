"""
帮助中心模块
提供知识库、FAQ、视频教程和搜索功能
"""
import json
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
import os
from src.database import db_manager

# 帮助中心分类
HELP_CATEGORIES = [
    {'id': 'getting-started', 'name': '入门指南', 'icon': '🚀', 'description': '快速上手使用指南'},
    {'id': 'dashboard', 'name': '仪表盘', 'icon': '📊', 'description': '仪表盘功能详解'},
    {'id': 'analytics', 'name': '高级分析', 'icon': '📈', 'description': '数据分析功能使用'},
    {'id': 'ab-test', 'name': 'AB测试', 'icon': '🧪', 'description': '实验设计与分析'},
    {'id': 'alerts', 'name': '告警管理', 'icon': '🔔', 'description': '告警规则配置'},
    {'id': 'api', 'name': 'API文档', 'icon': '🔌', 'description': 'API使用文档'},
    {'id': 'troubleshooting', 'name': '故障排除', 'icon': '🔧', 'description': '常见问题解决'},
    {'id': 'billing', 'name': '计费与订阅', 'icon': '💰', 'description': '套餐与支付'}
]

# FAQ数据
FAQ_DATA = [
    {
        'id': 'faq-001',
        'category': 'getting-started',
        'question': '如何创建第一个仪表盘？',
        'answer': '1. 登录后点击顶部导航的「仪表盘」\n2. 点击「新建仪表盘」按钮\n3. 输入仪表盘名称和描述\n4. 从组件库中选择需要的图表组件\n5. 配置组件数据和样式\n6. 点击「保存」完成创建',
        'views': 1256,
        'is_featured': True
    },
    {
        'id': 'faq-002',
        'category': 'getting-started',
        'question': '如何接入游戏数据？',
        'answer': '目前支持以下数据接入方式：\n1. API接入：通过REST API推送数据\n2. SDK接入：集成我们的Unity/Unreal SDK\n3. CSV导入：上传CSV文件导入历史数据\n4. 数据库连接：直连游戏数据库',
        'views': 892,
        'is_featured': True
    },
    {
        'id': 'faq-003',
        'category': 'dashboard',
        'question': '仪表盘数据多久刷新一次？',
        'answer': '仪表盘数据默认每5分钟自动刷新一次。您可以在仪表盘设置中调整刷新间隔，支持的选项：\n- 1分钟（专业版及以上）\n- 5分钟（默认）\n- 15分钟\n- 1小时',
        'views': 654,
        'is_featured': False
    },
    {
        'id': 'faq-004',
        'category': 'analytics',
        'question': '如何解读群组分析数据？',
        'answer': '群组分析帮助您了解不同时期用户的留存情况：\n- 第1周留存：用户注册后7天内的留存率\n- 第2周留存：用户注册后14天内的留存率\n- 第30天留存：用户注册后30天内的留存率\n健康的游戏通常30天留存率在20%以上。',
        'views': 445,
        'is_featured': True
    },
    {
        'id': 'faq-005',
        'category': 'ab-test',
        'question': 'AB测试需要多少样本量？',
        'answer': '建议每个变体至少有1000个用户参与，才能获得统计显著的结果。我们的系统会自动计算统计显著性，并在结果页面显示置信区间。',
        'views': 328,
        'is_featured': False
    },
    {
        'id': 'faq-006',
        'category': 'billing',
        'question': '如何升级或降级套餐？',
        'answer': '1. 点击右上角用户头像，选择「账户设置」\n2. 进入「套餐」页面\n3. 选择目标套餐\n4. 完成支付后即时生效\n降级将在下一个计费周期生效。',
        'views': 567,
        'is_featured': False
    },
    {
        'id': 'faq-007',
        'category': 'troubleshooting',
        'question': '数据延迟怎么办？',
        'answer': '数据延迟通常由以下原因导致：\n1. 网络延迟：检查服务器连接\n2. 数据量大：高峰期可能有延迟\n3. 缓存问题：尝试刷新页面\n如果问题持续，请联系客服。',
        'views': 723,
        'is_featured': True
    },
    {
        'id': 'faq-008',
        'category': 'api',
        'question': 'API调用失败怎么办？',
        'answer': '请检查以下几点：\n1. API密钥是否正确\n2. 请求格式是否正确（JSON格式）\n3. 请求频率是否超限\n4. 权限是否足够\n详细错误信息请查看响应中的error字段。',
        'views': 298,
        'is_featured': False
    }
]

# 视频教程数据
VIDEO_TUTORIALS = [
    {
        'id': 'video-001',
        'category': 'getting-started',
        'title': '快速入门：5分钟创建您的第一个仪表盘',
        'description': '从零开始，快速了解仪表盘的创建流程',
        'duration': '4:32',
        'thumbnail': 'https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=dashboard%20analytics%20tutorial%20thumbnail&image_size=landscape_16_9',
        'views': 2341,
        'url': '#',
        'is_featured': True
    },
    {
        'id': 'video-002',
        'category': 'analytics',
        'title': '高级分析：漏斗分析深度解析',
        'description': '深入了解漏斗分析的原理和应用场景',
        'duration': '8:15',
        'thumbnail': 'https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=funnel%20analytics%20chart%20visualization&image_size=landscape_16_9',
        'views': 1567,
        'url': '#',
        'is_featured': True
    },
    {
        'id': 'video-003',
        'category': 'ab-test',
        'title': 'AB测试实战：如何设计有效的实验',
        'description': '学习如何设计科学的AB测试实验',
        'duration': '10:45',
        'thumbnail': 'https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=AB%20testing%20experiment%20comparison&image_size=landscape_16_9',
        'views': 987,
        'url': '#',
        'is_featured': False
    },
    {
        'id': 'video-004',
        'category': 'api',
        'title': 'API接入指南：Unity SDK集成',
        'description': '手把手教您集成Unity SDK',
        'duration': '12:20',
        'thumbnail': 'https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=Unity%20game%20development%20coding&image_size=landscape_16_9',
        'views': 756,
        'url': '#',
        'is_featured': False
    }
]

class HelpCenterManager:
    """帮助中心管理器"""
    
    def __init__(self):
        self._init_data()
    
    def _init_data(self):
        """初始化帮助中心数据"""
        # 初始化FAQ
        for faq in FAQ_DATA:
            existing = db_manager.execute_one('SELECT * FROM help_faq WHERE faq_id = ?', (faq['id'],))
            if not existing:
                db_manager.execute('''
                    INSERT INTO help_faq (faq_id, category, question, answer, views, is_featured, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (faq['id'], faq['category'], faq['question'], faq['answer'], faq['views'], faq['is_featured'], datetime.now().isoformat()))
        
        # 初始化视频教程
        for video in VIDEO_TUTORIALS:
            existing = db_manager.execute_one('SELECT * FROM help_videos WHERE video_id = ?', (video['id'],))
            if not existing:
                db_manager.execute('''
                    INSERT INTO help_videos (video_id, category, title, description, duration, thumbnail, views, url, is_featured, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (video['id'], video['category'], video['title'], video['description'], video['duration'], video['thumbnail'], video['views'], video['url'], video['is_featured'], datetime.now().isoformat()))
    
    def get_categories(self) -> List[Dict]:
        """获取所有分类"""
        return HELP_CATEGORIES
    
    def get_category(self, category_id: str) -> Optional[Dict]:
        """获取单个分类"""
        return next((cat for cat in HELP_CATEGORIES if cat['id'] == category_id), None)
    
    def get_faqs(self, category_id: str = None, featured_only: bool = False) -> List[Dict]:
        """获取FAQ列表"""
        query = 'SELECT * FROM help_faq WHERE 1=1'
        params = []
        
        if category_id:
            query += ' AND category = ?'
            params.append(category_id)
        
        if featured_only:
            query += ' AND is_featured = 1'
        
        query += ' ORDER BY views DESC'
        
        results = db_manager.execute(query, tuple(params))
        return results
    
    def get_faq(self, faq_id: str) -> Optional[Dict]:
        """获取单个FAQ"""
        result = db_manager.execute_one('SELECT * FROM help_faq WHERE faq_id = ?', (faq_id,))
        
        if result:
            # 增加浏览次数
            db_manager.execute('UPDATE help_faq SET views = views + 1 WHERE faq_id = ?', (faq_id,))
        
        return result
    
    def search_faqs(self, query: str) -> List[Dict]:
        """搜索FAQ"""
        query = f'%{query}%'
        results = db_manager.execute('''
            SELECT * FROM help_faq 
            WHERE question LIKE ? OR answer LIKE ?
            ORDER BY views DESC
        ''', (query, query))
        return results
    
    def get_videos(self, category_id: str = None, featured_only: bool = False) -> List[Dict]:
        """获取视频教程列表"""
        query = 'SELECT * FROM help_videos WHERE 1=1'
        params = []
        
        if category_id:
            query += ' AND category = ?'
            params.append(category_id)
        
        if featured_only:
            query += ' AND is_featured = 1'
        
        query += ' ORDER BY views DESC'
        
        results = db_manager.execute(query, tuple(params))
        return results
    
    def get_video(self, video_id: str) -> Optional[Dict]:
        """获取单个视频"""
        result = db_manager.execute_one('SELECT * FROM help_videos WHERE video_id = ?', (video_id,))
        
        if result:
            db_manager.execute('UPDATE help_videos SET views = views + 1 WHERE video_id = ?', (video_id,))
        
        return result
    
    def search_videos(self, query: str) -> List[Dict]:
        """搜索视频教程"""
        query = f'%{query}%'
        results = db_manager.execute('''
            SELECT * FROM help_videos 
            WHERE title LIKE ? OR description LIKE ?
            ORDER BY views DESC
        ''', (query, query))
        return results
    
    def search_all(self, query: str) -> Dict:
        """搜索所有内容"""
        return {
            'faqs': self.search_faqs(query),
            'videos': self.search_videos(query)
        }
    
    def create_feedback(self, user_id: str, type: str, content: str, page_url: str = None) -> Dict:
        """创建反馈"""
        feedback_id = str(uuid.uuid4())
        
        db_manager.execute('''
            INSERT INTO help_feedback (feedback_id, user_id, type, content, page_url, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (feedback_id, user_id, type, content, page_url, 'pending', datetime.now().isoformat()))
        
        return {'feedback_id': feedback_id, 'status': 'pending'}
    
    def get_feedback_list(self, user_id: str = None, status: str = None) -> List[Dict]:
        """获取反馈列表"""
        query = 'SELECT * FROM help_feedback WHERE 1=1'
        params = []
        
        if user_id:
            query += ' AND user_id = ?'
            params.append(user_id)
        
        if status:
            query += ' AND status = ?'
            params.append(status)
        
        query += ' ORDER BY created_at DESC'
        
        return db_manager.execute(query, tuple(params))
    
    def update_feedback_status(self, feedback_id: str, status: str, response: str = None) -> bool:
        """更新反馈状态"""
        updates = ['status = ?']
        params = [status]
        
        if response:
            updates.append('response = ?')
            params.append(response)
        
        updates.append('updated_at = ?')
        params.append(datetime.now().isoformat())
        params.append(feedback_id)
        
        query = f'UPDATE help_feedback SET {", ".join(updates)} WHERE feedback_id = ?'
        db_manager.execute(query, tuple(params))
        return True

def init_help_tables():
    """初始化帮助中心相关表"""
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS help_faq (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                faq_id TEXT UNIQUE NOT NULL,
                category TEXT NOT NULL,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                views INTEGER DEFAULT 0,
                is_featured INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS help_videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT UNIQUE NOT NULL,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                duration TEXT,
                thumbnail TEXT,
                views INTEGER DEFAULT 0,
                url TEXT,
                is_featured INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS help_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                feedback_id TEXT UNIQUE NOT NULL,
                user_id TEXT NOT NULL,
                type TEXT NOT NULL,
                content TEXT NOT NULL,
                page_url TEXT,
                status TEXT DEFAULT 'pending',
                response TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        ''')
        
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_faq_category ON help_faq(category)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_videos_category ON help_videos(category)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_feedback_user ON help_feedback(user_id)')
        
        conn.commit()

# 初始化表
init_help_tables()

# 全局实例
help_center_manager = HelpCenterManager()

def get_help_center_manager() -> HelpCenterManager:
    """获取帮助中心管理器"""
    return help_center_manager
