"""
告警调度器模块
实现自动告警检测和通知功能
"""
import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import os

from src.database import AlertRepository, get_db_connection
from src.analytics_engine import load_data

class AlertScheduler:
    """告警调度器"""
    
    def __init__(self, check_interval: int = 60):
        """
        初始化告警调度器
        
        Args:
            check_interval: 检查间隔（秒）
        """
        self.check_interval = check_interval
        self.last_check_time = {}
    
    async def check_all_alerts(self):
        """检查所有告警规则"""
        try:
            # 从数据库获取所有启用的告警规则
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT * FROM alert_rules 
                    WHERE enabled = 1 
                    AND (last_triggered IS NULL OR last_triggered < ?)
                ''', ((datetime.now() - timedelta(hours=1)).isoformat(),))
                
                alerts = [dict(row) for row in cursor.fetchall()]
            
            # 并行检查所有告警
            tasks = [self.check_single_alert(alert) for alert in alerts]
            await asyncio.gather(*tasks, return_exceptions=True)
            
        except Exception as e:
            print(f"[AlertScheduler] Error checking alerts: {e}")
    
    async def check_single_alert(self, alert: Dict):
        """检查单个告警规则"""
        try:
            # 获取当前指标值
            current_value = await self.get_metric_value(alert['metric'], alert['product'])
            
            if current_value is None:
                return
            
            # 检查是否触发告警
            if self.evaluate_condition(current_value, alert['operator'], alert['threshold']):
                # 触发告警
                await self.trigger_alert(alert, current_value)
                
                # 更新最后触发时间
                AlertRepository.update_last_triggered(alert['id'])
                
                print(f"[AlertScheduler] Alert triggered: {alert['name']} - {alert['metric']} {alert['operator']} {alert['threshold']}")
        
        except Exception as e:
            print(f"[AlertScheduler] Error checking alert {alert['id']}: {e}")
    
    async def get_metric_value(self, metric: str, product: Optional[str]) -> Optional[float]:
        """
        获取指标当前值
        
        Args:
            metric: 指标名称
            product: 产品ID
        
        Returns:
            指标值，如果获取失败返回None
        """
        try:
            # 从metrics.json加载数据
            metrics_file = os.path.join(os.path.dirname(__file__), '..', 'mock_data', 'metrics.json')
            data = load_data(metrics_file)
            
            if not data:
                return None
            
            # 根据指标名称查找对应的值
            for item in data:
                if product and item.get('product') != product:
                    continue
                
                if item.get('metric') == metric:
                    value = item.get('value') or item.get('值')
                    if value:
                        try:
                            return float(value)
                        except (ValueError, TypeError):
                            pass
            
            return None
        
        except Exception as e:
            print(f"[AlertScheduler] Error getting metric value: {e}")
            return None
    
    def evaluate_condition(self, value: float, operator: str, threshold: float) -> bool:
        """
        评估告警条件
        
        Args:
            value: 当前值
            operator: 操作符
            threshold: 阈值
        
        Returns:
            是否满足告警条件
        """
        operators = {
            'gt': lambda v, t: v > t,
            'lt': lambda v, t: v < t,
            'gte': lambda v, t: v >= t,
            'lte': lambda v, t: v <= t,
            'eq': lambda v, t: abs(v - t) < 0.001,
            'change_gt': lambda v, t: False,  # 需要历史数据
            'change_lt': lambda v, t: False,  # 需要历史数据
        }
        
        func = operators.get(operator)
        if func:
            return func(value, threshold)
        
        return False
    
    async def trigger_alert(self, alert: Dict, current_value: float):
        """
        触发告警通知
        
        Args:
            alert: 告警规则
            current_value: 当前指标值
        """
        # 发送邮件通知
        if alert.get('email'):
            await self.send_email_notification(alert, current_value)
        
        # 发送Webhook通知
        webhook_url = alert.get('webhook_url')
        if webhook_url:
            await self.send_webhook_notification(alert, current_value, webhook_url)
    
    async def send_email_notification(self, alert: Dict, current_value: float):
        """
        发送邮件通知
        
        Args:
            alert: 告警规则
            current_value: 当前指标值
        """
        # 这里可以集成真实的邮件服务
        # 目前只是打印日志
        print(f"[AlertScheduler] Email notification to {alert['email']}: "
              f"Alert '{alert['name']}' triggered - {alert['metric']} = {current_value}")
    
    async def send_webhook_notification(self, alert: Dict, current_value: float, webhook_url: str):
        """
        发送Webhook通知
        
        Args:
            alert: 告警规则
            current_value: 当前指标值
            webhook_url: Webhook URL
        """
        try:
            payload = {
                'alert_name': alert['name'],
                'metric': alert['metric'],
                'operator': alert['operator'],
                'threshold': alert['threshold'],
                'current_value': current_value,
                'product': alert.get('product', 'all'),
                'timestamp': datetime.now().isoformat(),
                'alert_id': alert['id']
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        print(f"[AlertScheduler] Webhook notification sent successfully to {webhook_url}")
                    else:
                        print(f"[AlertScheduler] Webhook notification failed: {response.status}")
        
        except Exception as e:
            print(f"[AlertScheduler] Error sending webhook notification: {e}")
    
    async def run(self):
        """运行告警调度器"""
        print(f"[AlertScheduler] Starting alert scheduler (interval: {self.check_interval}s)")
        
        while True:
            try:
                await self.check_all_alerts()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                print(f"[AlertScheduler] Error in scheduler loop: {e}")
                await asyncio.sleep(self.check_interval)

async def main():
    """主函数"""
    scheduler = AlertScheduler(check_interval=60)  # 每分钟检查一次
    await scheduler.run()

if __name__ == "__main__":
    asyncio.run(main())
