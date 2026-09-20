"""
支付模块
支持 Stripe、支付宝、微信支付
"""
import json
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
import os
from src.database import db_manager
from src.billing import subscription_manager, plan_manager, billing_manager

class PaymentManager:
    """支付管理器"""
    
    def __init__(self):
        self.stripe_enabled = False
        self.alipay_enabled = False
        self.wechat_enabled = False
        
        # 尝试初始化支付网关
        self._init_stripe()
        self._init_alipay()
        self._init_wechat()
    
    def _init_stripe(self):
        """初始化Stripe"""
        try:
            import stripe
            from src.database import config_manager
            api_key = config_manager.get('payment.stripe.api_key')
            
            if api_key:
                stripe.api_key = api_key
                self.stripe_enabled = True
                self.stripe_client = stripe
            else:
                print("Warning: Stripe API key not configured")
        except ImportError:
            print("Warning: stripe package not installed")
    
    def _init_alipay(self):
        """初始化支付宝"""
        try:
            from alipay import AliPay
            from src.database import config_manager
            
            app_id = config_manager.get('payment.alipay.app_id')
            private_key_path = config_manager.get('payment.alipay.private_key_path')
            public_key_path = config_manager.get('payment.alipay.public_key_path')
            
            if app_id and private_key_path and public_key_path:
                self.alipay_client = AliPay(
                    appid=app_id,
                    app_notify_url=None,
                    app_private_key_string=self._load_key(private_key_path),
                    alipay_public_key_string=self._load_key(public_key_path),
                    sign_type='RSA2'
                )
                self.alipay_enabled = True
            else:
                print("Warning: Alipay configuration incomplete")
        except ImportError:
            print("Warning: alipay-sdk-python package not installed")
    
    def _init_wechat(self):
        """初始化微信支付"""
        try:
            import wechatpayv3
            from src.database import config_manager
            
            mchid = config_manager.get('payment.wechat.mchid')
            serial_no = config_manager.get('payment.wechat.serial_no')
            private_key_path = config_manager.get('payment.wechat.private_key_path')
            apiv3_key = config_manager.get('payment.wechat.apiv3_key')
            appid = config_manager.get('payment.wechat.appid')
            
            if mchid and serial_no and private_key_path and apiv3_key and appid:
                self.wechat_client = wechatpayv3.Client(
                    mchid=mchid,
                    serial_no=serial_no,
                    private_key=self._load_key(private_key_path),
                    apiv3_key=apiv3_key,
                    appid=appid
                )
                self.wechat_enabled = True
            else:
                print("Warning: WeChat Pay configuration incomplete")
        except ImportError:
            print("Warning: wechatpayv3 package not installed")
    
    def _load_key(self, path: str) -> str:
        """加载密钥文件"""
        try:
            with open(path, 'r') as f:
                return f.read()
        except Exception as e:
            print(f"Error loading key file: {e}")
            return ""
    
    def create_payment_intent(self, user_id: str, plan_id: str, payment_method: str) -> Dict:
        """创建支付意图"""
        plan = plan_manager.get_plan(plan_id)
        if not plan:
            raise ValueError("Invalid plan ID")
        
        amount = plan['price']
        currency = plan['currency'].lower()
        
        payment_id = str(uuid.uuid4())
        
        # 创建支付记录
        db_manager.execute('''
            INSERT INTO payments 
            (payment_id, user_id, plan_id, amount, currency, method, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (payment_id, user_id, plan_id, amount, currency, payment_method, 'pending', datetime.now().isoformat()))
        
        if payment_method == 'stripe' and self.stripe_enabled:
            return self._create_stripe_payment(payment_id, amount, currency, user_id)
        
        elif payment_method == 'alipay' and self.alipay_enabled:
            return self._create_alipay_payment(payment_id, amount, user_id)
        
        elif payment_method == 'wechat' and self.wechat_enabled:
            return self._create_wechat_payment(payment_id, amount, user_id)
        
        else:
            # 模拟支付（用于测试）
            return {
                'payment_id': payment_id,
                'status': 'pending',
                'amount': amount,
                'currency': currency,
                'method': payment_method,
                'message': 'Payment method not fully configured, using mock payment'
            }
    
    def _create_stripe_payment(self, payment_id: str, amount: float, currency: str, user_id: str) -> Dict:
        """创建Stripe支付"""
        try:
            intent = self.stripe_client.PaymentIntent.create(
                amount=int(amount * 100),
                currency=currency,
                metadata={
                    'payment_id': payment_id,
                    'user_id': user_id
                }
            )
            
            return {
                'payment_id': payment_id,
                'status': 'pending',
                'client_secret': intent.client_secret,
                'stripe_id': intent.id,
                'amount': amount,
                'currency': currency,
                'method': 'stripe'
            }
        except Exception as e:
            print(f"Stripe payment error: {e}")
            return {
                'payment_id': payment_id,
                'status': 'error',
                'error': str(e),
                'method': 'stripe'
            }
    
    def _create_alipay_payment(self, payment_id: str, amount: float, user_id: str) -> Dict:
        """创建支付宝支付"""
        try:
            order_string = self.alipay_client.api_alipay_trade_page_pay(
                out_trade_no=payment_id,
                total_amount=str(amount),
                subject=f'Subscription - {plan_manager.get_plan("pro")["name"]}',
                return_url='http://localhost:8080/payment/callback/alipay',
                notify_url='http://localhost:8080/payment/webhook/alipay'
            )
            
            return {
                'payment_id': payment_id,
                'status': 'pending',
                'alipay_url': f'https://openapi.alipaydev.com/gateway.do?{order_string}',
                'amount': amount,
                'method': 'alipay'
            }
        except Exception as e:
            print(f"Alipay payment error: {e}")
            return {
                'payment_id': payment_id,
                'status': 'error',
                'error': str(e),
                'method': 'alipay'
            }
    
    def _create_wechat_payment(self, payment_id: str, amount: float, user_id: str) -> Dict:
        """创建微信支付"""
        try:
            result = self.wechat_client.post(
                '/pay/transactions/jsapi',
                json={
                    'mchid': self.wechat_client.mchid,
                    'out_trade_no': payment_id,
                    'appid': self.wechat_client.appid,
                    'description': f'Subscription',
                    'notify_url': 'http://localhost:8080/payment/webhook/wechat',
                    'amount': {
                        'total': int(amount * 100),
                        'currency': 'CNY'
                    },
                    'payer': {
                        'openid': 'test_openid'  # 需要用户的openid
                    }
                }
            )
            
            return {
                'payment_id': payment_id,
                'status': 'pending',
                'prepay_id': result.get('prepay_id'),
                'amount': amount,
                'method': 'wechat'
            }
        except Exception as e:
            print(f"WeChat payment error: {e}")
            return {
                'payment_id': payment_id,
                'status': 'error',
                'error': str(e),
                'method': 'wechat'
            }
    
    def verify_payment(self, payment_id: str, data: Dict) -> bool:
        """验证支付结果"""
        payment = db_manager.execute_one('''
            SELECT * FROM payments WHERE payment_id = ?
        ''', (payment_id,))
        
        if not payment:
            return False
        
        if payment['method'] == 'stripe':
            return self._verify_stripe_payment(payment_id, data)
        
        elif payment['method'] == 'alipay':
            return self._verify_alipay_payment(payment_id, data)
        
        elif payment['method'] == 'wechat':
            return self._verify_wechat_payment(payment_id, data)
        
        else:
            # 模拟支付验证
            return self._verify_mock_payment(payment_id, data)
    
    def _verify_stripe_payment(self, payment_id: str, data: Dict) -> bool:
        """验证Stripe支付"""
        try:
            intent = self.stripe_client.PaymentIntent.retrieve(data.get('payment_intent'))
            if intent.status == 'succeeded':
                self._complete_payment(payment_id)
                return True
            return False
        except Exception as e:
            print(f"Stripe verification error: {e}")
            return False
    
    def _verify_alipay_payment(self, payment_id: str, data: Dict) -> bool:
        """验证支付宝支付"""
        try:
            if self.alipay_client.verify(data):
                self._complete_payment(payment_id)
                return True
            return False
        except Exception as e:
            print(f"Alipay verification error: {e}")
            return False
    
    def _verify_wechat_payment(self, payment_id: str, data: Dict) -> bool:
        """验证微信支付"""
        try:
            # 验证签名等
            self._complete_payment(payment_id)
            return True
        except Exception as e:
            print(f"WeChat verification error: {e}")
            return False
    
    def _verify_mock_payment(self, payment_id: str, data: Dict) -> bool:
        """模拟支付验证"""
        if data.get('success') == 'true':
            self._complete_payment(payment_id)
            return True
        return False
    
    def simulate_payment(self, payment_id: str, success: bool = True) -> bool:
        """模拟支付（用于测试）"""
        payment = db_manager.execute_one('''
            SELECT * FROM payments WHERE payment_id = ?
        ''', (payment_id,))
        
        if not payment:
            return False
        
        if payment['status'] != 'pending':
            return False
        
        if success:
            self._complete_payment(payment_id)
            return True
        else:
            db_manager.execute('''
                UPDATE payments SET status = 'failed', completed_at = ? WHERE payment_id = ?
            ''', (datetime.now().isoformat(), payment_id))
            return False
    
    def _complete_payment(self, payment_id: str):
        """完成支付"""
        payment = db_manager.execute_one('''
            SELECT * FROM payments WHERE payment_id = ?
        ''', (payment_id,))
        
        if payment and payment['status'] == 'pending':
            # 更新支付状态
            db_manager.execute('''
                UPDATE payments SET status = 'completed', completed_at = ? WHERE payment_id = ?
            ''', (datetime.now().isoformat(), payment_id))
            
            # 创建订阅
            subscription_manager.create_subscription(
                payment['user_id'],
                payment['plan_id'],
                payment['method']
            )
            
            # 生成账单
            billing_manager.generate_invoice(
                payment['user_id'],
                datetime.now().isoformat(),
                (datetime.now() + timedelta(days=30)).isoformat()
            )
    
    def get_payment_methods(self) -> List[Dict]:
        """获取可用的支付方式"""
        methods = []
        
        if self.stripe_enabled:
            methods.append({
                'id': 'stripe',
                'name': 'Stripe',
                'description': '支持信用卡支付',
                'icon': '💳'
            })
        
        if self.alipay_enabled:
            methods.append({
                'id': 'alipay',
                'name': '支付宝',
                'description': '扫码支付',
                'icon': '📱'
            })
        
        if self.wechat_enabled:
            methods.append({
                'id': 'wechat',
                'name': '微信支付',
                'description': '扫码支付',
                'icon': '💬'
            })
        
        # 如果没有配置真实支付方式，添加模拟支付
        if not methods:
            methods.append({
                'id': 'mock',
                'name': '模拟支付',
                'description': '测试用支付方式',
                'icon': '🔧'
            })
        
        return methods
    
    def get_payment(self, payment_id: str) -> Optional[Dict]:
        """获取支付记录"""
        return db_manager.execute_one('''
            SELECT * FROM payments WHERE payment_id = ?
        ''', (payment_id,))
    
    def get_user_payments(self, user_id: str) -> List[Dict]:
        """获取用户支付记录"""
        return db_manager.execute('''
            SELECT * FROM payments WHERE user_id = ? ORDER BY created_at DESC
        ''', (user_id,))

def init_payment_tables():
    """初始化支付相关表"""
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payment_id TEXT UNIQUE NOT NULL,
                user_id TEXT NOT NULL,
                plan_id TEXT NOT NULL,
                amount REAL NOT NULL,
                currency TEXT DEFAULT 'CNY',
                method TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                external_id TEXT,
                created_at TEXT,
                completed_at TEXT
            )
        ''')
        
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_payments_user ON payments(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status)')
        
        conn.commit()

# 初始化表
init_payment_tables()

# 全局实例
payment_manager = PaymentManager()

def get_payment_manager() -> PaymentManager:
    """获取支付管理器"""
    return payment_manager
