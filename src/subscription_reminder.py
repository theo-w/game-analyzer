"""
订阅到期提醒模块
实现订阅到期检测和通知功能
"""
import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import os

from src.database import get_db_connection, db_manager
from src.billing import subscription_manager

class SubscriptionReminder:
    """订阅到期提醒管理器"""
    
    def __init__(self, check_interval: int = 3600):
        """
        初始化订阅到期提醒管理器
        
        Args:
            check_interval: 检查间隔（秒），默认为1小时
        """
        self.check_interval = check_interval
    
    async def check_all_subscriptions(self):
        """检查所有即将到期的订阅"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT s.*, u.email, u.username 
                    FROM subscriptions s
                    JOIN users u ON s.user_id = u.username
                    WHERE s.status = 'active'
                    AND s.end_date IS NOT NULL
                ''')
                
                subscriptions = [dict(row) for row in cursor.fetchall()]
            
            for subscription in subscriptions:
                await self.check_subscription(subscription)
            
        except Exception as e:
            print(f"[SubscriptionReminder] Error checking subscriptions: {e}")
    
    async def check_subscription(self, subscription: Dict):
        """
        检查单个订阅是否需要发送提醒
        
        Args:
            subscription: 订阅信息
        """
        try:
            end_date = datetime.fromisoformat(subscription['end_date'])
            now = datetime.now()
            days_until_expiry = (end_date - now).days
            
            if days_until_expiry <= 0:
                await self.send_expired_reminder(subscription)
            elif days_until_expiry == 7:
                await self.send_7day_reminder(subscription)
            elif days_until_expiry == 3:
                await self.send_3day_reminder(subscription)
            elif days_until_expiry == 1:
                await self.send_1day_reminder(subscription)
                
        except Exception as e:
            print(f"[SubscriptionReminder] Error checking subscription {subscription['subscription_id']}: {e}")
    
    async def send_7day_reminder(self, subscription: Dict):
        """发送7天到期提醒"""
        await self._send_reminder(subscription, 7)
    
    async def send_3day_reminder(self, subscription: Dict):
        """发送3天到期提醒"""
        await self._send_reminder(subscription, 3)
    
    async def send_1day_reminder(self, subscription: Dict):
        """发送1天到期提醒"""
        await self._send_reminder(subscription, 1)
    
    async def send_expired_reminder(self, subscription: Dict):
        """发送已过期提醒"""
        await self._send_reminder(subscription, 0)
    
    async def _send_reminder(self, subscription: Dict, days_remaining: int):
        """
        发送订阅到期提醒
        
        Args:
            subscription: 订阅信息
            days_remaining: 剩余天数（0表示已过期）
        """
        user_email = subscription.get('email')
        username = subscription.get('username')
        plan_id = subscription.get('plan_id')
        
        if not user_email:
            return
        
        if days_remaining == 0:
            subject = f"您的游戏数据分析引擎订阅已过期"
            message = f"""尊敬的{username}用户：

您的游戏数据分析引擎订阅（{plan_id}版）已过期。

为了不影响您的使用，请及时续费。

续费链接：http://localhost:8080/pricing

如有疑问，请联系我们的客服团队。

游戏数据分析引擎团队"""
        else:
            subject = f"您的订阅还有{days_remaining}天到期"
            message = f"""尊敬的{username}用户：

您好！您的游戏数据分析引擎订阅（{plan_id}版）将在{days_remaining}天后到期。

为了确保您的服务不中断，请及时续费。

续费链接：http://localhost:8080/pricing

如有任何问题，请随时联系我们。

游戏数据分析引擎团队"""
        
        await self.send_email(user_email, subject, message)
        self.save_reminder_log(subscription['subscription_id'], days_remaining)
        
        print(f"[SubscriptionReminder] Sent {days_remaining} day reminder to {user_email}")
    
    async def send_email(self, to_email: str, subject: str, message: str):
        """
        发送邮件通知
        
        Args:
            to_email: 收件人邮箱
            subject: 邮件主题
            message: 邮件内容
        """
        print(f"[SubscriptionReminder] Sending email to {to_email}")
        print(f"Subject: {subject}")
        print(f"Message:\n{message}")
        print("-" * 50)
    
    def save_reminder_log(self, subscription_id: str, days_remaining: int):
        """
        保存提醒日志
        
        Args:
            subscription_id: 订阅ID
            days_remaining: 剩余天数
        """
        try:
            db_manager.execute('''
                INSERT INTO reminder_logs 
                (subscription_id, days_remaining, sent_at)
                VALUES (?, ?, ?)
            ''', (subscription_id, days_remaining, datetime.now().isoformat()))
        except Exception as e:
            print(f"[SubscriptionReminder] Error saving reminder log: {e}")
    
    async def get_user_subscription_status(self, username: str) -> Dict:
        """
        获取用户订阅状态信息（用于前端显示）
        
        Args:
            username: 用户名
        
        Returns:
            订阅状态信息
        """
        subscription = subscription_manager.get_subscription(username)
        
        if not subscription:
            return {
                'has_subscription': False,
                'plan_id': 'free',
                'status': 'free',
                'days_remaining': None,
                'show_reminder': False,
                'reminder_message': ''
            }
        
        try:
            end_date = datetime.fromisoformat(subscription['end_date'])
            now = datetime.now()
            days_remaining = (end_date - now).days
            
            status = subscription['status']
            show_reminder = False
            reminder_message = ''
            
            if status == 'active':
                if days_remaining <= 0:
                    status = 'expired'
                    show_reminder = True
                    reminder_message = '您的订阅已过期，请及时续费'
                elif days_remaining <= 7:
                    show_reminder = True
                    reminder_message = f'您的订阅还有{days_remaining}天到期，请及时续费'
            
            return {
                'has_subscription': True,
                'plan_id': subscription['plan_id'],
                'status': status,
                'days_remaining': days_remaining,
                'end_date': subscription['end_date'],
                'show_reminder': show_reminder,
                'reminder_message': reminder_message
            }
        
        except Exception as e:
            print(f"[SubscriptionReminder] Error getting subscription status for {username}: {e}")
            return {
                'has_subscription': False,
                'plan_id': 'free',
                'status': 'free',
                'days_remaining': None,
                'show_reminder': False,
                'reminder_message': ''
            }
    
    async def run(self):
        """运行订阅到期提醒调度器"""
        print(f"[SubscriptionReminder] Starting subscription reminder scheduler (interval: {self.check_interval}s)")
        
        while True:
            try:
                await self.check_all_subscriptions()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                print(f"[SubscriptionReminder] Error in scheduler loop: {e}")
                await asyncio.sleep(self.check_interval)

async def main():
    """主函数"""
    reminder = SubscriptionReminder(check_interval=3600)  # 每小时检查一次
    await reminder.run()

if __name__ == "__main__":
    asyncio.run(main())