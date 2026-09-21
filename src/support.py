"""
客户支持模块
提供帮助中心、工单系统和在线客服功能
"""
import os
import json
from datetime import datetime
from typing import Optional, Dict, Any, List
from src.database import db_manager

class AIChatbot:
    """AI智能客服"""
    
    def __init__(self):
        self.knowledge_base = None
    
    def load_knowledge_base(self):
        """加载知识库用于AI回复"""
        global knowledge_base
        self.knowledge_base = knowledge_base
    
    def generate_response(self, message: str, chat_history: List[Dict] = None) -> str:
        """
        生成AI回复
        
        Args:
            message: 用户消息
            chat_history: 聊天历史记录
        
        Returns:
            AI回复内容
        """
        # 简单的关键词匹配回复
        message_lower = message.lower()
        
        # 问候语
        greetings = ['你好', '您好', 'hello', 'hi', '您好！', '你好！', '有人么', '有人吗', '在吗', '在么', '有人']
        if any(g in message_lower for g in greetings):
            return '您好！我是游戏数据分析引擎的智能客服。请问有什么可以帮助您的？'
        
        # 询问功能
        capability_words = ['功能', '能做什么', '可以做什么', '你能做什么', '你可以做什么', '做什么', '有什么用', '介绍']
        if any(w in message_lower for w in capability_words):
            return '我可以帮助您进行游戏数据分析，包括：\n\n📊 数据看板 - 查看KPI指标和产品对比\n💬 评论分析 - 分析玩家评论情感\n📈 指标详情 - 查看详细的指标趋势\n⚡ 高级分析 - 进行漏斗分析、留存分析等\n\n您想了解哪个功能？'
        
        # 数据导入相关
        if any(w in message_lower for w in ['导入', '上传', '数据导入']):
            return '关于数据导入，您可以参考帮助中心的"如何导入数据"文档。导入步骤：\n\n1. 登录系统后，进入数据导入页面\n2. 选择要导入的文件（支持CSV、JSON格式）\n3. 匹配字段映射\n4. 点击导入按钮\n\n如有问题，请提交工单获取进一步帮助。'
        
        # 订阅相关
        if any(w in message_lower for w in ['订阅', '套餐', '价格', '付费', '收费']):
            return '我们提供三种订阅套餐：\n\n🆓 免费版：1个游戏，每月1000次API调用\n💎 专业版（¥2999/年）：10个游戏，每月50000次API调用\n🏢 企业版：定制报价，无限游戏和API调用\n\n您可以在定价页面查看详细信息并升级您的套餐。'
        
        # 数据更新相关
        if any(w in message_lower for w in ['更新', '刷新', '数据更新']):
            return '数据默认每小时自动更新一次。您也可以在数据看板页面点击刷新按钮手动更新数据。'
        
        # 问题反馈
        if any(w in message_lower for w in ['问题', '错误', 'bug', '报错', '异常']):
            return '如果您遇到了问题，请通过工单系统提交详细信息，我们的技术团队会在24小时内回复您。'

        # 转人工 / 工单
        if any(w in message_lower for w in ['人工', '转人工', '客服', '工单', '投诉']):
            return '__ESCALATE_TO_HUMAN__'
        
        # 搜索知识库
        if self.knowledge_base:
            articles = self.knowledge_base.search_articles(message)
            if articles:
                article = articles[0]
                return f'我在知识库中找到了相关信息：\n\n📚 {article["title"]}\n\n{article["content"][:200]}...\n\n如需更详细的信息，请查看帮助中心。'
        
        # 默认回复
        return '感谢您的提问！我已经记录了您的问题。如果您需要进一步的帮助，请通过工单系统提交详细信息，我们的客服团队会尽快回复您。'
    
    def _finalize_response(self, chat_id: str, username: str, message: str, response: str) -> str:
        if '__ESCALATE_TO_HUMAN__' in response:
            response = response.replace('__ESCALATE_TO_HUMAN__', '').strip()
            ticket = ticket_system.create_ticket_from_chat(
                chat_id,
                username,
                subject=f'在线客服转接：{message[:40]}',
                message=message,
                priority='high',
            )
            suffix = (
                f'\n\n已为您转接人工客服，并创建工单 {ticket["ticket_id"]}。'
                ' 您可在「工单系统」查看进度。'
            )
            response = (response + suffix).strip() if response else (
                f'已为您转接人工客服，并创建工单 {ticket["ticket_id"]}。'
                ' 您可在「工单系统」查看进度，客服也会在控制台同步处理该会话。'
            )
        LiveChat.add_message(chat_id, 'ai_assistant', response, False)
        return response

    def process_message(self, chat_id: str, username: str, message: str):
        """处理用户消息并生成回复（关键词回退，供同步调用）"""
        if not self.knowledge_base:
            self.load_knowledge_base()

        history = LiveChat.get_messages(chat_id)
        response = self.generate_response(message, history)
        if response == '__ESCALATE_TO_HUMAN__':
            return self._finalize_response(chat_id, username, message, response)
        return self._finalize_response(chat_id, username, message, response)

    async def process_message_async(self, chat_id: str, username: str, message: str) -> Dict[str, Any]:
        """优先使用已配置的 LLM，失败时回退到关键词回复。人工接待中的会话不再自动回复。"""
        if not self.knowledge_base:
            self.load_knowledge_base()

        chat = LiveChat.get_chat(chat_id)
        if chat and chat.get("status") != "active":
            return {
                "reply": None,
                "ai_replied": False,
                "reason": "human_handling",
                "status": chat.get("status"),
            }

        history = LiveChat.get_messages(chat_id)
        response = None
        try:
            from src.services.support_ai import generate_support_reply
            from src.services.llm_client import llm_is_configured

            if llm_is_configured():
                response = await generate_support_reply(message, history)
        except Exception as exc:
            print(f"Support LLM fallback to keywords: {exc}")

        if not response:
            response = self.generate_response(message, history)
            if response == '__ESCALATE_TO_HUMAN__':
                text = self._finalize_response(chat_id, username, message, response)
                return {"reply": text, "ai_replied": True, "reason": "escalated"}

        text = self._finalize_response(chat_id, username, message, response)
        return {"reply": text, "ai_replied": True, "reason": "auto"}

class AgentConsole:
    """人工客服控制台"""
    
    @staticmethod
    def get_all_chats(status: str = None, agent_username: str = None, admin_view: bool = False) -> List[Dict]:
        """获取对话列表；坐席仅见未分配或分配给自己的会话。"""
        if admin_view:
            if status:
                return db_manager.execute(
                    '''
                    SELECT * FROM live_chats
                    WHERE status = ?
                    ORDER BY datetime(COALESCE(updated_at, created_at)) DESC
                    ''',
                    (status,),
                )
            return db_manager.execute(
                '''
                SELECT * FROM live_chats
                ORDER BY datetime(COALESCE(updated_at, created_at)) DESC
                '''
            )

        base = '''
            SELECT * FROM live_chats
            WHERE (assigned_agent IS NULL OR assigned_agent = '' OR assigned_agent = ?)
        '''
        params: List[Any] = [agent_username or ""]
        if status:
            base += ' AND status = ?'
            params.append(status)
        base += ' ORDER BY datetime(COALESCE(updated_at, created_at)) DESC'
        return db_manager.execute(base, tuple(params))
    
    @staticmethod
    def enrich_chat_summaries(chats: List[Dict]) -> List[Dict]:
        """为会话列表附加最近一条消息摘要，便于坐席实时收件箱展示。"""
        enriched: List[Dict] = []
        for chat in chats or []:
            row = dict(chat)
            last = db_manager.execute_one(
                """
                SELECT message, created_at FROM chat_messages
                WHERE chat_id = ?
                ORDER BY datetime(created_at) DESC
                LIMIT 1
                """,
                (row.get("chat_id"),),
            )
            if last:
                text = (last.get("message") or "").strip()
                row["last_message"] = text[:120] if len(text) > 120 else text
                row["last_message_at"] = last.get("created_at")
            else:
                row["last_message"] = ""
                row["last_message_at"] = row.get("created_at")
            enriched.append(row)
        return enriched
    
    @staticmethod
    def get_chat_detail(chat_id: str) -> Dict:
        """获取对话详情"""
        chat = db_manager.execute_one('SELECT * FROM live_chats WHERE chat_id = ?', (chat_id,))
        if chat:
            chat["messages"] = LiveChat.get_messages(chat_id, for_display=True)
        return chat
    
    @staticmethod
    def reply_to_chat(chat_id: str, agent_username: str, message: str):
        """人工客服回复消息"""
        LiveChat.add_message(chat_id, agent_username, message, False)
        
        # 更新对话状态为有人工回复
        db_manager.execute('''
            UPDATE live_chats 
            SET last_agent_reply = ? 
            WHERE chat_id = ?
        ''', (datetime.now().isoformat(), chat_id))
    
    @staticmethod
    def transfer_to_human(chat_id: str, agent_username: str = None):
        """将对话转交给人工客服"""
        db_manager.execute('''
            UPDATE live_chats 
            SET status = 'pending_human', assigned_agent = ?, updated_at = ? 
            WHERE chat_id = ?
        ''', (agent_username, datetime.now().isoformat(), chat_id))
    
    @staticmethod
    def get_waiting_chats() -> List[Dict]:
        """获取等待人工回复的对话"""
        return db_manager.execute('''
            SELECT * FROM live_chats 
            WHERE status = 'pending_human' 
            ORDER BY created_at ASC
        ''')
    
    @staticmethod
    def get_ticket_assignments(agent_username: str) -> List[Dict]:
        """获取客服人员分配的工单"""
        return db_manager.execute('''
            SELECT * FROM support_tickets 
            WHERE agent_id = ? 
            ORDER BY created_at DESC
        ''', (agent_username,))
    
    @staticmethod
    def get_unified_inbox(agent_username: str = None, admin_view: bool = False) -> List[Dict]:
        """合并在线会话与工单，供客服控制台统一查看"""
        if admin_view:
            chats = db_manager.execute('''
                SELECT chat_id, username, status, created_at, ticket_id, assigned_agent, 'chat' AS item_type
                FROM live_chats
                ORDER BY created_at DESC
                LIMIT 100
            ''')
            tickets = db_manager.execute('''
                SELECT ticket_id, username, subject, status, priority, created_at, chat_id, agent_id, 'ticket' AS item_type
                FROM support_tickets
                ORDER BY created_at DESC
                LIMIT 100
            ''')
        else:
            chats = db_manager.execute('''
                SELECT chat_id, username, status, created_at, ticket_id, assigned_agent, 'chat' AS item_type
                FROM live_chats
                WHERE assigned_agent IS NULL OR assigned_agent = '' OR assigned_agent = ?
                ORDER BY created_at DESC
                LIMIT 100
            ''', (agent_username or "",))
            tickets = db_manager.execute('''
                SELECT ticket_id, username, subject, status, priority, created_at, chat_id, agent_id, 'ticket' AS item_type
                FROM support_tickets
                WHERE agent_id IS NULL OR agent_id = '' OR agent_id = ?
                ORDER BY created_at DESC
                LIMIT 100
            ''', (agent_username or "",))
        items = []
        for row in chats or []:
            items.append({
                'type': 'chat',
                'id': row['chat_id'],
                'username': row['username'],
                'status': row['status'],
                'created_at': row['created_at'],
                'ticket_id': row.get('ticket_id'),
                'assigned_agent': row.get('assigned_agent'),
                'title': f"在线会话 {row['chat_id']}",
            })
        for row in tickets or []:
            items.append({
                'type': 'ticket',
                'id': row['ticket_id'],
                'username': row['username'],
                'status': row['status'],
                'priority': row.get('priority'),
                'created_at': row['created_at'],
                'chat_id': row.get('chat_id'),
                'agent_id': row.get('agent_id'),
                'title': row.get('subject') or row['ticket_id'],
            })
        items.sort(key=lambda item: item.get('created_at') or '', reverse=True)
        return items

    @staticmethod
    def get_dashboard_stats() -> Dict:
        """获取客服仪表盘统计"""
        # 获取活跃对话数
        active_count = db_manager.execute_one('''
            SELECT COUNT(*) as count 
            FROM live_chats 
            WHERE status = 'active'
        ''')
        
        # 获取等待处理对话数
        waiting_count = db_manager.execute_one('''
            SELECT COUNT(*) as count 
            FROM live_chats 
            WHERE status = 'pending_human'
        ''')
        
        # 获取今日工单数
        today = datetime.now().strftime('%Y-%m-%d')
        today_tickets = db_manager.execute_one('''
            SELECT COUNT(*) as count 
            FROM support_tickets 
            WHERE DATE(created_at) = ?
        ''', (today,))
        
        # 获取未处理工单数
        open_tickets = db_manager.execute_one('''
            SELECT COUNT(*) as count 
            FROM support_tickets 
            WHERE status IN ('open', 'processing')
        ''')
        
        return {
            'active_chats': active_count['count'] if active_count else 0,
            'waiting_chats': waiting_count['count'] if waiting_count else 0,
            'today_tickets': today_tickets['count'] if today_tickets else 0,
            'open_tickets': open_tickets['count'] if open_tickets else 0
        }

    @staticmethod
    def claim_chat(chat_id: str, agent_username: str) -> bool:
        """坐席接手：停止该会话的 AI 自动回复。"""
        db_manager.execute(
            """
            UPDATE live_chats
            SET assigned_agent = ?, status = 'pending_human', updated_at = ?
            WHERE chat_id = ?
            """,
            (agent_username, datetime.now().isoformat(), chat_id),
        )
        LiveChat.add_message(
            chat_id,
            "system",
            f"人工客服 {agent_username} 已接手，后续由人工回复。",
            True,
        )
        return True

    @staticmethod
    def assign_chat(chat_id: str, agent_username: str) -> bool:
        """管理员分配坐席（不停止 AI，坐席需点击「接手」才转人工）。"""
        db_manager.execute(
            """
            UPDATE live_chats
            SET assigned_agent = ?, updated_at = ?
            WHERE chat_id = ?
            """,
            (agent_username, datetime.now().isoformat(), chat_id),
        )
        return True

    @staticmethod
    def release_to_ai(chat_id: str) -> bool:
        """恢复 AI 自动回复（清除人工接待状态）。"""
        db_manager.execute(
            """
            UPDATE live_chats
            SET assigned_agent = NULL, status = 'active', updated_at = ?
            WHERE chat_id = ?
            """,
            (datetime.now().isoformat(), chat_id),
        )
        LiveChat.add_message(
            chat_id,
            "system",
            "已恢复 AI 智能客服自动回复。",
            True,
        )
        return True

    @staticmethod
    def assign_ticket(ticket_id: str, agent_username: str) -> bool:
        db_manager.execute(
            '''
            UPDATE support_tickets
            SET agent_id = ?, status = 'processing', updated_at = ?
            WHERE ticket_id = ?
            ''',
            (agent_username, datetime.now().isoformat(), ticket_id),
        )
        return True

    @staticmethod
    def get_all_tickets_for_staff(agent_username: str = None, admin_view: bool = False) -> List[Dict]:
        if admin_view:
            return db_manager.execute(
                '''
                SELECT * FROM support_tickets
                ORDER BY created_at DESC
                '''
            )
        return db_manager.execute(
            '''
            SELECT * FROM support_tickets
            WHERE agent_id IS NULL OR agent_id = '' OR agent_id = ?
            ORDER BY created_at DESC
            ''',
            (agent_username or "",),
        )

class KnowledgeBase:
    """知识库管理器"""
    
    def __init__(self):
        self.articles = self._load_default_articles()
    
    def _load_default_articles(self) -> List[Dict]:
        """加载默认知识库文章"""
        return [
            {
                'id': '1',
                'title': '如何导入数据',
                'category': '数据管理',
                'content': '''
                    ## 数据导入指南

                    1. 登录系统后，进入数据导入页面
                    2. 选择要导入的文件（支持CSV、JSON格式）
                    3. 匹配字段映射
                    4. 点击导入按钮
                    
                    ### 支持的文件格式
                    - CSV文件（逗号分隔）
                    - JSON文件
                    - Excel文件（.xlsx）
                    
                    ### 字段要求
                    - 必须包含产品ID字段
                    - 建议包含时间戳字段
                    - 数值字段应为数字格式
                ''',
                'created_at': '2024-01-01',
                'views': 120
            },
            {
                'id': '2',
                'title': '如何创建告警规则',
                'category': '告警管理',
                'content': '''
                    ## 告警规则创建指南

                    1. 进入告警规则页面
                    2. 点击"新建规则"按钮
                    3. 配置规则参数：
                       - 选择监控指标
                       - 设置阈值
                       - 选择触发条件
                       - 配置通知方式
                    4. 保存规则
                    
                    ### 支持的通知方式
                    - 邮件通知
                    - Webhook通知
                    
                    ### 触发条件
                    - 大于(gt)
                    - 小于(lt)
                    - 大于等于(gte)
                    - 小于等于(lte)
                    - 等于(eq)
                ''',
                'created_at': '2024-01-02',
                'views': 85
            },
            {
                'id': '3',
                'title': 'API使用指南',
                'category': 'API',
                'content': '''
                    ## API使用指南

                    ### 认证方式
                    使用Bearer Token认证，在请求头中添加：
                    ```
                    Authorization: Bearer <your_token>
                    ```
                    
                    ### 主要接口
                    - GET /api/report - 获取报告数据
                    - GET /api/metrics - 获取指标数据
                    - GET /api/comments - 获取评论数据
                    - POST /api/import - 导入数据
                    
                    ### 响应格式
                    ```json
                    {
                        "success": true,
                        "data": [...],
                        "message": "success"
                    }
                    ```
                    
                    ### 错误处理
                    ```json
                    {
                        "success": false,
                        "detail": "错误描述"
                    }
                    ```
                ''',
                'created_at': '2024-01-03',
                'views': 156
            },
            {
                'id': '4',
                'title': '订阅套餐说明',
                'category': '订阅',
                'content': '''
                    ## 订阅套餐说明

                    ### 免费版
                    - 最多1个游戏
                    - 每日API调用100次
                    - 30天数据保留
                    - 基础功能访问
                    
                    ### 专业版 (¥299/月)
                    - 最多10个游戏
                    - 每日API调用1000次
                    - 90天数据保留
                    - 高级分析功能
                    - 优先技术支持
                    
                    ### 企业版 (定制报价)
                    - 无限游戏数量
                    - 无限API调用
                    - 365天数据保留
                    - 所有高级功能
                    - 专属客户经理
                    - 定制集成服务
                    - 私有化部署选项
                ''',
                'created_at': '2024-01-04',
                'views': 234
            },
            {
                'id': '5',
                'title': '常见问题解答',
                'category': 'FAQ',
                'content': '''
                    ## 常见问题

                    ### Q: 数据多久更新一次？
                    A: 默认每小时自动更新一次，也可以手动点击刷新。

                    ### Q: 支持哪些数据源？
                    A: 目前支持Steam、Google Play、App Store等主流平台。

                    ### Q: 如何取消订阅？
                    A: 在账户设置中可以随时取消订阅，取消后服务将在当前周期结束时停止。

                    ### Q: 数据会被共享吗？
                    A: 不会，您的数据仅用于为您提供服务，不会出售或共享给第三方。

                    ### Q: 遇到问题如何联系支持？
                    A: 可以通过工单系统提交问题，我们会在24小时内回复。
                ''',
                'created_at': '2024-01-05',
                'views': 312
            }
        ]
    
    def search_articles(self, query: str, category: str = None) -> List[Dict]:
        """搜索知识库文章"""
        results = []
        
        for article in self.articles:
            matches = False
            
            if query:
                query_lower = query.lower()
                if query_lower in article['title'].lower() or query_lower in article['content'].lower():
                    matches = True
            else:
                matches = True
            
            if category and category != 'all':
                matches = matches and article['category'] == category
            
            if matches:
                results.append(article)
        
        return sorted(results, key=lambda x: x['views'], reverse=True)
    
    def get_categories(self) -> List[str]:
        """获取所有分类"""
        categories = set()
        for article in self.articles:
            categories.add(article['category'])
        return sorted(list(categories))
    
    def get_article(self, article_id: str) -> Optional[Dict]:
        """获取单篇文章"""
        for article in self.articles:
            if article['id'] == article_id:
                article['views'] += 1
                return article
        return None
    
    def add_article(self, title: str, category: str, content: str) -> Dict:
        """添加新文章"""
        new_id = str(len(self.articles) + 1)
        article = {
            'id': new_id,
            'title': title,
            'category': category,
            'content': content,
            'created_at': datetime.now().strftime('%Y-%m-%d'),
            'views': 0
        }
        self.articles.append(article)
        return article
    
    def get_popular_articles(self, limit: int = 5) -> List[Dict]:
        """获取热门文章"""
        return sorted(self.articles, key=lambda x: x['views'], reverse=True)[:limit]

class TicketSystem:
    """工单系统"""
    
    STATUS_CHOICES = ['open', 'processing', 'pending', 'resolved', 'closed']
    PRIORITY_CHOICES = ['low', 'medium', 'high', 'urgent']
    
    @staticmethod
    def create_ticket(
        username: str,
        subject: str,
        message: str,
        priority: str = 'medium',
        chat_id: Optional[str] = None,
    ) -> Dict:
        """创建工单"""
        ticket_id = 'TKT-' + datetime.now().strftime('%Y%m%d') + '-' + str(hash(username + subject) % 1000).zfill(3)
        
        db_manager.execute('''
            INSERT INTO support_tickets 
            (ticket_id, username, subject, message, priority, status, chat_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (ticket_id, username, subject, message, priority, 'open', chat_id, datetime.now().isoformat()))

        if chat_id:
            db_manager.execute(
                'UPDATE live_chats SET ticket_id = ?, updated_at = ? WHERE chat_id = ?',
                (ticket_id, datetime.now().isoformat(), chat_id),
            )
        
        return {'ticket_id': ticket_id, 'status': 'open', 'chat_id': chat_id}

    @staticmethod
    def create_ticket_from_chat(
        chat_id: str,
        username: str,
        subject: str,
        message: str,
        priority: str = 'high',
    ) -> Dict:
        """从在线会话创建关联工单并转人工"""
        ticket = TicketSystem.create_ticket(username, subject, message, priority, chat_id=chat_id)
        agent_console.transfer_to_human(chat_id)
        LiveChat.add_message(
            chat_id,
            'system',
            f'会话已关联工单 {ticket["ticket_id"]}，等待人工客服处理。',
            True,
        )
        return ticket
    
    @staticmethod
    def get_ticket(ticket_id: str) -> Optional[Dict]:
        """获取工单详情"""
        ticket = db_manager.execute_one('SELECT * FROM support_tickets WHERE ticket_id = ?', (ticket_id,))
        if ticket:
            ticket['replies'] = TicketSystem.get_replies(ticket_id)
        return ticket
    
    @staticmethod
    def get_user_tickets(username: str) -> List[Dict]:
        """获取用户的工单"""
        return db_manager.execute('''
            SELECT * FROM support_tickets 
            WHERE username = ? 
            ORDER BY created_at DESC
        ''', (username,))
    
    @staticmethod
    def get_all_tickets() -> List[Dict]:
        """获取所有工单（管理员使用）"""
        return db_manager.execute('''
            SELECT * FROM support_tickets 
            ORDER BY created_at DESC
        ''')
    
    @staticmethod
    def update_ticket(ticket_id: str, updates: Dict) -> bool:
        """更新工单"""
        allowed_fields = ['status', 'priority', 'message', 'agent_id']
        
        set_clause = []
        params = []
        
        for key, value in updates.items():
            if key in allowed_fields:
                set_clause.append(f"{key} = ?")
                params.append(value)
        
        if not set_clause:
            return False
        
        params.append(ticket_id)
        
        db_manager.execute(f'''
            UPDATE support_tickets 
            SET {', '.join(set_clause)}, updated_at = ? 
            WHERE ticket_id = ?
        ''', tuple(params + [datetime.now().isoformat(), ticket_id]))
        
        return True
    
    @staticmethod
    def add_reply(ticket_id: str, username: str, message: str, is_agent: bool = False):
        """添加回复"""
        db_manager.execute('''
            INSERT INTO ticket_replies 
            (ticket_id, username, message, is_agent, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (ticket_id, username, message, 1 if is_agent else 0, datetime.now().isoformat()))
        ticket = TicketSystem.get_ticket(ticket_id)
        if ticket and ticket.get('chat_id'):
            sender = username if not is_agent else 'admin'
            LiveChat.add_message(
                ticket['chat_id'],
                sender,
                f'[工单回复] {message}',
                False,
            )
    
    @staticmethod
    def get_replies(ticket_id: str) -> List[Dict]:
        """获取工单回复"""
        return db_manager.execute('''
            SELECT * FROM ticket_replies 
            WHERE ticket_id = ? 
            ORDER BY created_at ASC
        ''', (ticket_id,))
    
    @staticmethod
    def get_ticket_stats() -> Dict:
        """获取工单统计"""
        # 获取各状态工单数量
        status_stats = db_manager.execute('''
            SELECT status, COUNT(*) as count 
            FROM support_tickets 
            GROUP BY status
        ''')
        
        # 获取优先级分布
        priority_stats = db_manager.execute('''
            SELECT priority, COUNT(*) as count 
            FROM support_tickets 
            GROUP BY priority
        ''')
        
        # 获取未处理工单数量
        open_count = db_manager.execute_one('''
            SELECT COUNT(*) as count 
            FROM support_tickets 
            WHERE status IN ('open', 'processing', 'pending')
        ''')
        
        return {
            'status_stats': {row['status']: row['count'] for row in status_stats},
            'priority_stats': {row['priority']: row['count'] for row in priority_stats},
            'open_count': open_count['count'] if open_count else 0
        }

class LiveChat:
    """在线客服系统"""
    
    @staticmethod
    def get_active_chat_for_user(username: str) -> Optional[Dict]:
        """Return the newest open session for this customer account."""
        return db_manager.execute_one(
            """
            SELECT * FROM live_chats
            WHERE username = ?
              AND status IN ('active', 'pending_human')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (username,),
        )

    @staticmethod
    def start_chat(username: str) -> Dict:
        """开始对话（同一客户账号复用未结束的会话，避免串会话）"""
        existing = LiveChat.get_active_chat_for_user(username)
        if existing:
            return {"chat_id": existing["chat_id"], "resumed": True}

        chat_id = "CHT-" + datetime.now().strftime("%Y%m%d%H%M%S")
        db_manager.execute(
            """
            INSERT INTO live_chats
            (chat_id, username, status, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (chat_id, username, "active", datetime.now().isoformat()),
        )
        LiveChat.add_message(
            chat_id,
            "system",
            "欢迎咨询！我是您的专属客服，请问有什么可以帮助您的？",
            True,
        )
        return {"chat_id": chat_id, "resumed": False}

    @staticmethod
    def assert_customer_can_access_chat(chat_id: str, username: str) -> Dict:
        chat = LiveChat.get_chat(chat_id)
        if not chat:
            raise ValueError("会话不存在")
        if chat.get("username") != username:
            raise PermissionError("无权访问该会话")
        return chat
    
    @staticmethod
    def add_message(chat_id: str, username: str, message: str, is_system: bool = False):
        """添加消息"""
        now = datetime.now().isoformat()
        db_manager.execute('''
            INSERT INTO chat_messages 
            (chat_id, username, message, is_system, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (chat_id, username, message, 1 if is_system else 0, now))
        db_manager.execute(
            'UPDATE live_chats SET updated_at = ? WHERE chat_id = ?',
            (now, chat_id),
        )
    
    @staticmethod
    def enrich_messages(messages: List[Dict], chat_owner: str) -> List[Dict]:
        """Attach sender_kind: customer | staff | ai | system (based on session owner, not viewer)."""
        owner = (chat_owner or "").strip()
        enriched: List[Dict] = []
        for msg in messages or []:
            row = dict(msg)
            uname = (row.get("username") or "").strip()
            if row.get("is_system") or uname == "system":
                row["sender_kind"] = "system"
            elif uname == "ai_assistant":
                row["sender_kind"] = "ai"
            elif owner and uname == owner:
                row["sender_kind"] = "customer"
            else:
                row["sender_kind"] = "staff"
            enriched.append(row)
        return enriched

    @staticmethod
    def get_messages(chat_id: str, *, for_display: bool = False) -> List[Dict]:
        """获取聊天消息；for_display 时附带 sender_kind。"""
        rows = db_manager.execute(
            """
            SELECT * FROM chat_messages
            WHERE chat_id = ?
            ORDER BY created_at ASC
            """,
            (chat_id,),
        )
        if not for_display:
            return rows
        chat = LiveChat.get_chat(chat_id)
        owner = (chat or {}).get("username") or ""
        return LiveChat.enrich_messages(rows, owner)
    
    @staticmethod
    def get_chat(chat_id: str) -> Optional[Dict]:
        return db_manager.execute_one('SELECT * FROM live_chats WHERE chat_id = ?', (chat_id,))

    @staticmethod
    def end_chat(chat_id: str):
        """结束对话"""
        db_manager.execute('''
            UPDATE live_chats 
            SET status = 'ended', ended_at = ? 
            WHERE chat_id = ?
        ''', (datetime.now().isoformat(), chat_id))
    
    @staticmethod
    def get_active_chats() -> List[Dict]:
        """获取活跃对话"""
        return db_manager.execute('''
            SELECT * FROM live_chats 
            WHERE status = 'active' 
            ORDER BY created_at ASC
        ''')

# 全局实例
knowledge_base = KnowledgeBase()
ticket_system = TicketSystem()
live_chat = LiveChat()
ai_chatbot = AIChatbot()
agent_console = AgentConsole()