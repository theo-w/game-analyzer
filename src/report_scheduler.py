import asyncio
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import os
import json
from src.report_utils import generate_report_summary, generate_product_details, analyze_trends, generate_recommendations, DATA_DIR

class ReportScheduler:
    """自动化报告推送服务"""
    
    def __init__(self):
        self.scheduled_tasks = {}
        self.smtp_config = {
            'host': os.getenv('SMTP_HOST', 'smtp.gmail.com'),
            'port': int(os.getenv('SMTP_PORT', '587')),
            'username': os.getenv('SMTP_USERNAME', ''),
            'password': os.getenv('SMTP_PASSWORD', ''),
            'use_tls': os.getenv('SMTP_USE_TLS', 'true').lower() == 'true'
        }
    
    async def send_report_email(
        self,
        to_email: str,
        report_type: str,
        product_ids: List[str] = None,
        time_period: str = None
    ) -> bool:
        """发送报告邮件"""
        try:
            if not self.smtp_config['username'] or not self.smtp_config['password']:
                print("SMTP配置未完成，跳过邮件发送")
                return False
            
            product_ids = product_ids or ["game_a", "game_b", "game_c"]
            
            metrics_file = os.path.join(DATA_DIR, "metrics.json")
            comments_file = os.path.join(DATA_DIR, "comments.json")
            
            with open(metrics_file, "r", encoding="utf-8") as f:
                metrics_data = json.load(f)
            
            with open(comments_file, "r", encoding="utf-8") as f:
                comments_data = json.load(f)
            
            if time_period:
                metrics_data = [m for m in metrics_data if m.get("cycle") == time_period]
                comments_data = [c for c in comments_data if c.get("cycle") == time_period]
            
            metrics_data = [m for m in metrics_data if m.get("product") in product_ids]
            comments_data = [c for c in comments_data if c.get("product") in product_ids]
            
            summary = generate_report_summary(metrics_data, comments_data, report_type)
            product_details = generate_product_details(metrics_data)
            trends = analyze_trends(metrics_data)
            recommendations = generate_recommendations(metrics_data, comments_data)
            
            html_content = self._generate_email_html(summary, product_details, trends, recommendations)

            # 该报告基于 mock_data 演示数据, 显式标注避免被误认为真实业务数据
            subject = (
                f"[Demo 演示数据] 游戏数据分析报告 - {report_type} - "
                f"{datetime.now().strftime('%Y年%m月%d日')}"
            )
            
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.smtp_config['username']
            msg['To'] = to_email
            
            msg.attach(MIMEText(summary, 'plain', 'utf-8'))
            msg.attach(MIMEText(html_content, 'html', 'utf-8'))
            
            with smtplib.SMTP(self.smtp_config['host'], self.smtp_config['port']) as server:
                if self.smtp_config['use_tls']:
                    server.starttls()
                server.login(self.smtp_config['username'], self.smtp_config['password'])
                server.send_message(msg)
            
            print(f"报告邮件已发送到 {to_email}")
            return True
        except Exception as e:
            print(f"发送邮件失败: {e}")
            return False
    
    def _generate_email_html(
        self,
        summary: str,
        product_details: List[Dict],
        trends: List[Dict],
        recommendations: List[Dict]
    ) -> str:
        """生成邮件HTML内容"""
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>游戏数据分析报告</title>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
                .container {{ max-width: 800px; margin: 0 auto; background: white; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); padding: 30px; }}
                h1 {{ color: #1a73e8; font-size: 24px; margin-top: 0; }}
                h2 {{ color: #202124; font-size: 18px; border-bottom: 2px solid #e0e0e0; padding-bottom: 10px; }}
                .summary {{ background: #e8f0fe; padding: 15px; border-radius: 8px; margin-bottom: 20px; }}
                .product-card {{ border: 1px solid #e0e0e0; border-radius: 8px; padding: 15px; margin-bottom: 15px; }}
                .product-name {{ font-weight: bold; color: #1a73e8; }}
                .metric {{ display: inline-block; margin-right: 20px; color: #5f6368; }}
                .trend-up {{ color: #137333; }}
                .trend-down {{ color: #d93026; }}
                .recommendation {{ background: #fff3cd; border-left: 4px solid #ffc107; padding: 12px; margin-bottom: 10px; border-radius: 0 8px 8px 0; }}
                .recommendation.critical {{ background: #ffebee; border-color: #f44336; }}
                .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #e0e0e0; color: #80868b; font-size: 14px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🎮 游戏数据分析报告</h1>
                <p style="background:#fff3cd;border-left:4px solid #ffc107;padding:10px;border-radius:0 8px 8px 0;color:#7a5b00;">
                    ⚠️ 本报告基于 <strong>mock_data 演示数据</strong> 生成，仅用于展示报告能力，不代表真实业务指标。
                </p>
                <div class="summary"><pre style="white-space: pre-wrap; margin: 0; font-family: inherit;">{summary}</pre></div>
                
                <h2>📱 产品详情</h2>
                {''.join([self._product_card_html(pd) for pd in product_details])}
                
                <h2>📈 趋势分析</h2>
                {self._trends_html(trends)}
                
                <h2>💡 优化建议</h2>
                {self._recommendations_html(recommendations)}
                
                <div class="footer">
                    此报告由游戏数据分析引擎自动生成 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                </div>
            </div>
        </body>
        </html>
        """
        return html
    
    def _product_card_html(self, product: Dict) -> str:
        """生成产品卡片HTML"""
        return f"""
        <div class="product-card">
            <div class="product-name">{product['product']}</div>
            <div class="metric">下载量: {product['downloads']:,}</div>
            <div class="metric">ARPPU: {product['arppu']}</div>
            <div class="metric">留存率: {product['retention']}</div>
        </div>
        """
    
    def _trends_html(self, trends: List[Dict]) -> str:
        """生成趋势分析HTML"""
        if not trends:
            return "<p>暂无趋势数据</p>"
        
        trend_items = []
        for trend in trends:
            trend_class = "trend-up" if trend.get('trend') == 'up' else "trend-down"
            trend_items.append(f"<li><strong>{trend['product']}</strong>: {trend['metric']} {trend['change']}</li>")
        
        return f"<ul>{''.join(trend_items)}</ul>"
    
    def _recommendations_html(self, recommendations: List[Dict]) -> str:
        """生成建议HTML"""
        if not recommendations:
            return "<p>暂无优化建议</p>"
        
        html = []
        for rec in recommendations:
            rec_class = "critical" if rec.get('type') == 'critical' else ""
            html.append(f"""
            <div class="recommendation {rec_class}">
                <strong>{rec['title']}</strong>
                <p>{rec['suggestion']}</p>
            </div>
            """)
        
        return ''.join(html)
    
    async def schedule_daily_report(self, to_email: str, product_ids: List[str] = None, hour: int = 9):
        """定时发送日报（每天早上9点）"""
        task_name = f"daily_{to_email}"
        
        if task_name in self.scheduled_tasks:
            self.scheduled_tasks[task_name].cancel()
        
        async def daily_task():
            while True:
                now = datetime.now()
                target_time = now.replace(hour=hour, minute=0, second=0, microsecond=0)
                
                if now > target_time:
                    target_time += timedelta(days=1)
                
                wait_seconds = (target_time - now).total_seconds()
                await asyncio.sleep(wait_seconds)
                
                await self.send_report_email(to_email, 'daily', product_ids)
        
        task = asyncio.create_task(daily_task())
        self.scheduled_tasks[task_name] = task
        return task
    
    async def schedule_weekly_report(self, to_email: str, product_ids: List[str] = None, weekday: int = 0, hour: int = 9):
        """定时发送周报（每周一早上9点）"""
        task_name = f"weekly_{to_email}"
        
        if task_name in self.scheduled_tasks:
            self.scheduled_tasks[task_name].cancel()
        
        async def weekly_task():
            while True:
                now = datetime.now()
                days_until_target = (weekday - now.weekday() + 7) % 7
                if days_until_target == 0 and now.hour >= hour:
                    days_until_target = 7
                
                target_time = now.replace(hour=hour, minute=0, second=0, microsecond=0) + timedelta(days=days_until_target)
                wait_seconds = (target_time - now).total_seconds()
                await asyncio.sleep(wait_seconds)
                
                await self.send_report_email(to_email, 'weekly', product_ids)
        
        task = asyncio.create_task(weekly_task())
        self.scheduled_tasks[task_name] = task
        return task
    
    async def schedule_monthly_report(self, to_email: str, product_ids: List[str] = None, day: int = 1, hour: int = 9):
        """定时发送月报（每月1号早上9点）"""
        task_name = f"monthly_{to_email}"
        
        if task_name in self.scheduled_tasks:
            self.scheduled_tasks[task_name].cancel()
        
        async def monthly_task():
            while True:
                now = datetime.now()
                next_month = now.replace(day=1) + timedelta(days=32)
                target_time = next_month.replace(day=day, hour=hour, minute=0, second=0, microsecond=0)
                
                wait_seconds = (target_time - now).total_seconds()
                await asyncio.sleep(wait_seconds)
                
                await self.send_report_email(to_email, 'monthly', product_ids)
        
        task = asyncio.create_task(monthly_task())
        self.scheduled_tasks[task_name] = task
        return task
    
    def cancel_scheduled_task(self, task_name: str):
        """取消定时任务"""
        if task_name in self.scheduled_tasks:
            self.scheduled_tasks[task_name].cancel()
            del self.scheduled_tasks[task_name]
            return True
        return False
    
    def get_scheduled_tasks(self) -> List[Dict]:
        """获取所有定时任务"""
        return [{"name": name, "active": not task.done()} for name, task in self.scheduled_tasks.items()]

report_scheduler = ReportScheduler()