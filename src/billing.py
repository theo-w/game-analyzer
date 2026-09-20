"""
计费系统模块
提供订阅模型、定价配置和计费管理功能
"""
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import uuid
import os
from src.database import db_manager

# 定价方案配置
PRICING_PLANS = {
    'free': {
        'id': 'free',
        'name': '免费版',
        'description': '适合个人开发者和小型项目',
        'price': 0,
        'currency': 'CNY',
        'interval': 'month',
        'features': {
            'max_games': 1,
            'max_team_members': 1,
            'api_quota_daily': 100,
            'data_retention_days': 30,
            'alert_rules': 3,
            'custom_dashboards': 3,
            'ab_tests': 5,
            'priority_support': False,
            'custom_domain': False,
            'white_label': False
        }
    },
    'pro': {
        'id': 'pro',
        'name': '专业版',
        'description': '适合中型团队和成长中的项目',
        'price': 299,
        'currency': 'CNY',
        'interval': 'month',
        'features': {
            'max_games': 10,
            'max_team_members': 10,
            'api_quota_daily': 1000,
            'data_retention_days': 90,
            'alert_rules': 20,
            'custom_dashboards': 20,
            'ab_tests': 50,
            'priority_support': True,
            'custom_domain': True,
            'white_label': False
        }
    },
    'enterprise': {
        'id': 'enterprise',
        'name': '企业版',
        'description': '适合大型企业和定制需求',
        'price': 1999,
        'currency': 'CNY',
        'interval': 'month',
        'features': {
            'max_games': None,  # 无限制
            'max_team_members': None,  # 无限制
            'api_quota_daily': None,  # 无限制
            'data_retention_days': 365,
            'alert_rules': None,  # 无限制
            'custom_dashboards': None,  # 无限制
            'ab_tests': None,  # 无限制
            'priority_support': True,
            'custom_domain': True,
            'white_label': True,
            'on_premise_deployment': True,
            'custom_integrations': True,
            'dedicated_account_manager': True
        }
    }
}

def _align_pricing_with_auth():
    try:
        from src.plans_catalog import sync_billing_pricing_plans

        sync_billing_pricing_plans(PRICING_PLANS)
    except Exception:
        pass

_align_pricing_with_auth()

class PlanManager:
    """套餐管理器"""
    
    def get_plan(self, plan_id: str) -> Optional[Dict]:
        """获取套餐信息"""
        return PRICING_PLANS.get(plan_id)
    
    def get_all_plans(self) -> List[Dict]:
        """获取所有套餐"""
        return list(PRICING_PLANS.values())
    
    def get_plan_features(self, plan_id: str) -> Dict:
        """获取套餐功能限制"""
        plan = self.get_plan(plan_id)
        return plan['features'] if plan else PRICING_PLANS['free']['features']
    
    def is_feature_allowed(self, plan_id: str, feature: str, current_usage: int = 0) -> bool:
        """检查功能是否可用"""
        features = self.get_plan_features(plan_id)
        limit = features.get(feature)
        
        if limit is None:
            return True  # 无限制
        
        return current_usage < limit
    
    def get_feature_limit(self, plan_id: str, feature: str) -> Optional[int]:
        """获取功能限制"""
        features = self.get_plan_features(plan_id)
        return features.get(feature)

class SubscriptionManager:
    """订阅管理器"""
    
    def __init__(self):
        self.plan_manager = PlanManager()
    
    def create_subscription(self, user_id: str, plan_id: str, payment_method: str = None) -> Dict:
        """创建订阅"""
        subscription_id = str(uuid.uuid4())
        plan = self.plan_manager.get_plan(plan_id)
        
        if not plan:
            raise ValueError("Invalid plan ID")
        
        start_date = datetime.now().isoformat()
        end_date = (datetime.now() + timedelta(days=30)).isoformat()
        
        data = {
            'subscription_id': subscription_id,
            'user_id': user_id,
            'plan_id': plan_id,
            'status': 'active',
            'start_date': start_date,
            'end_date': end_date,
            'auto_renew': True,
            'payment_method': payment_method,
            'created_at': datetime.now().isoformat()
        }
        
        db_manager.execute('''
            INSERT INTO subscriptions 
            (subscription_id, user_id, plan_id, status, start_date, end_date, auto_renew, payment_method, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            subscription_id, user_id, plan_id, 'active', start_date, end_date, True, payment_method, datetime.now().isoformat()
        ))
        
        # 更新用户套餐
        db_manager.execute('''
            UPDATE users SET plan_id = ?, updated_at = ? WHERE username = ?
        ''', (plan_id, datetime.now().isoformat(), user_id))
        
        return data
    
    def get_subscription(self, user_id: str) -> Optional[Dict]:
        """获取用户订阅"""
        result = db_manager.execute_one('''
            SELECT * FROM subscriptions WHERE user_id = ? AND status = 'active'
            ORDER BY created_at DESC LIMIT 1
        ''', (user_id,))
        
        return result
    
    def update_subscription(self, user_id: str, plan_id: str) -> bool:
        """更新订阅套餐"""
        subscription = self.get_subscription(user_id)
        
        if not subscription:
            return False
        
        plan = self.plan_manager.get_plan(plan_id)
        if not plan:
            return False
        
        db_manager.execute('''
            UPDATE subscriptions 
            SET plan_id = ?, end_date = ?, updated_at = ?
            WHERE subscription_id = ?
        ''', (
            plan_id,
            (datetime.now() + timedelta(days=30)).isoformat(),
            datetime.now().isoformat(),
            subscription['subscription_id']
        ))
        
        # 更新用户套餐
        db_manager.execute('''
            UPDATE users SET plan_id = ?, updated_at = ? WHERE username = ?
        ''', (plan_id, datetime.now().isoformat(), user_id))
        
        return True
    
    def cancel_subscription(self, user_id: str) -> bool:
        """取消订阅"""
        subscription = self.get_subscription(user_id)
        
        if not subscription:
            return False
        
        db_manager.execute('''
            UPDATE subscriptions 
            SET status = 'cancelled', updated_at = ?
            WHERE subscription_id = ?
        ''', (datetime.now().isoformat(), subscription['subscription_id']))
        
        return True
    
    def check_subscription_status(self, user_id: str) -> str:
        """检查订阅状态"""
        subscription = self.get_subscription(user_id)
        
        if not subscription:
            return 'free'
        
        # 检查是否过期
        if subscription['end_date'] and datetime.fromisoformat(subscription['end_date']) < datetime.now():
            return 'expired'
        
        return subscription['status']
    
    def is_subscription_active(self, user_id: str) -> bool:
        """检查订阅是否活跃"""
        status = self.check_subscription_status(user_id)
        return status == 'active'
    
    def check_and_downgrade_expired(self, user_id: str) -> bool:
        """检查并降级过期订阅"""
        subscription = self.get_subscription(user_id)
        
        if not subscription:
            return False
        
        if not subscription['end_date']:
            return False
        
        try:
            end_date = datetime.fromisoformat(subscription['end_date'])
            if end_date < datetime.now() and subscription['status'] == 'active':
                self.downgrade_to_free(user_id, subscription)
                return True
        except Exception as e:
            print(f"Error checking subscription expiration: {e}")
        
        return False
    
    def downgrade_to_free(self, user_id: str, subscription: Dict = None):
        """将用户降级到免费版"""
        if not subscription:
            subscription = self.get_subscription(user_id)
        
        if subscription:
            db_manager.execute('''
                UPDATE subscriptions 
                SET status = 'expired', updated_at = ?
                WHERE subscription_id = ?
            ''', (datetime.now().isoformat(), subscription['subscription_id']))
        
        db_manager.execute('''
            UPDATE users 
            SET plan_id = 'free', games_limit = 1, api_quota = 100, updated_at = ?
            WHERE username = ?
        ''', (datetime.now().isoformat(), user_id))
        
        print(f"User {user_id} downgraded to free plan due to subscription expiration")
    
    def downgrade_all_expired(self):
        """降级所有过期订阅"""
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT s.user_id, s.subscription_id 
                    FROM subscriptions s
                    WHERE s.status = 'active'
                    AND s.end_date IS NOT NULL
                    AND datetime(s.end_date) < datetime('now')
                ''')
                
                expired = cursor.fetchall()
                for row in expired:
                    user_id = row[0]
                    subscription_id = row[1]
                    print(f"Downgrading expired subscription: {subscription_id} for user: {user_id}")
                    self.downgrade_to_free(user_id, {'subscription_id': subscription_id})
            
            return len(expired)
        except Exception as e:
            print(f"Error downgrading expired subscriptions: {e}")
            return 0

class BillingManager:
    """计费管理器"""
    
    def __init__(self):
        self.subscription_manager = SubscriptionManager()
        self.plan_manager = PlanManager()
    
    def generate_invoice(self, user_id: str, period_start: str, period_end: str) -> Dict:
        """生成账单"""
        subscription = self.subscription_manager.get_subscription(user_id)
        
        if not subscription:
            plan = self.plan_manager.get_plan('free')
            amount = 0
        else:
            plan = self.plan_manager.get_plan(subscription['plan_id'])
            amount = plan['price']
        
        invoice_id = 'INV-' + str(uuid.uuid4())[:8].upper()
        
        invoice = {
            'invoice_id': invoice_id,
            'user_id': user_id,
            'subscription_id': subscription['subscription_id'] if subscription else None,
            'plan_id': plan['id'],
            'plan_name': plan['name'],
            'amount': amount,
            'currency': plan['currency'],
            'period_start': period_start,
            'period_end': period_end,
            'status': 'pending',
            'created_at': datetime.now().isoformat(),
            'due_date': (datetime.now() + timedelta(days=7)).isoformat()
        }
        
        db_manager.execute('''
            INSERT INTO invoices 
            (invoice_id, user_id, subscription_id, plan_id, plan_name, amount, currency, 
             period_start, period_end, status, created_at, due_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            invoice_id, user_id, invoice['subscription_id'], plan['id'], plan['name'],
            amount, plan['currency'], period_start, period_end, 'pending',
            datetime.now().isoformat(), invoice['due_date']
        ))
        
        return invoice
    
    def get_invoices(self, user_id: str) -> List[Dict]:
        """获取用户账单列表"""
        return db_manager.execute('''
            SELECT * FROM invoices WHERE user_id = ? ORDER BY created_at DESC
        ''', (user_id,))
    
    def get_invoice(self, invoice_id: str) -> Optional[Dict]:
        """获取单个账单"""
        return db_manager.execute_one('''
            SELECT * FROM invoices WHERE invoice_id = ?
        ''', (invoice_id,))
    
    def mark_invoice_paid(self, invoice_id: str) -> bool:
        """标记账单已支付"""
        result = db_manager.execute('''
            UPDATE invoices SET status = 'paid', paid_at = ? WHERE invoice_id = ?
        ''', (datetime.now().isoformat(), invoice_id))
        
        return len(result) > 0

class QuotaManager:
    """配额管理器"""
    
    def __init__(self):
        self.subscription_manager = SubscriptionManager()
        self.plan_manager = PlanManager()
    
    def get_daily_quota(self, user_id: str) -> int:
        """获取每日API配额"""
        subscription = self.subscription_manager.get_subscription(user_id)
        plan_id = subscription['plan_id'] if subscription else 'free'
        features = self.plan_manager.get_plan_features(plan_id)
        return features.get('api_quota_daily', 100)
    
    def get_used_quota(self, user_id: str, date: str = None) -> int:
        """获取已使用配额"""
        if not date:
            date = datetime.now().strftime('%Y-%m-%d')
        
        result = db_manager.execute_one('''
            SELECT SUM(request_count) as total FROM api_usage 
            WHERE user_id = ? AND date = ?
        ''', (user_id, date))
        
        return result['total'] if result and result['total'] else 0
    
    def record_api_usage(self, user_id: str, endpoint: str):
        """记录API使用"""
        date = datetime.now().strftime('%Y-%m-%d')
        
        # 检查是否已有记录
        existing = db_manager.execute_one('''
            SELECT * FROM api_usage WHERE user_id = ? AND date = ? AND endpoint = ?
        ''', (user_id, date, endpoint))
        
        if existing:
            db_manager.execute('''
                UPDATE api_usage SET request_count = request_count + 1, updated_at = ?
                WHERE user_id = ? AND date = ? AND endpoint = ?
            ''', (datetime.now().isoformat(), user_id, date, endpoint))
        else:
            db_manager.execute('''
                INSERT INTO api_usage (user_id, date, endpoint, request_count, created_at)
                VALUES (?, ?, ?, 1, ?)
            ''', (user_id, date, endpoint, datetime.now().isoformat()))
    
    def check_quota(self, user_id: str) -> bool:
        """检查配额是否充足"""
        quota = self.get_daily_quota(user_id)
        used = self.get_used_quota(user_id)
        return used < quota
    
    def get_quota_remaining(self, user_id: str) -> int:
        """获取剩余配额"""
        quota = self.get_daily_quota(user_id)
        used = self.get_used_quota(user_id)
        return max(0, quota - used)

# 全局实例
plan_manager = PlanManager()
subscription_manager = SubscriptionManager()
billing_manager = BillingManager()
quota_manager = QuotaManager()

def init_billing_tables():
    """初始化计费相关表"""
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subscription_id TEXT UNIQUE NOT NULL,
                user_id TEXT NOT NULL,
                plan_id TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                start_date TEXT NOT NULL,
                end_date TEXT,
                auto_renew INTEGER DEFAULT 1,
                payment_method TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_id TEXT UNIQUE NOT NULL,
                user_id TEXT NOT NULL,
                subscription_id TEXT,
                plan_id TEXT NOT NULL,
                plan_name TEXT NOT NULL,
                amount REAL NOT NULL,
                currency TEXT DEFAULT 'CNY',
                period_start TEXT NOT NULL,
                period_end TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                paid_at TEXT,
                created_at TEXT,
                due_date TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS api_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                date TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                request_count INTEGER DEFAULT 1,
                created_at TEXT,
                updated_at TEXT
            )
        ''')
        
        # 创建索引
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_subscriptions_user ON subscriptions(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_invoices_user ON invoices(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_api_usage_user_date ON api_usage(user_id, date)')
        
        conn.commit()

# 初始化表
init_billing_tables()
