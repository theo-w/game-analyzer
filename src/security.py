"""
安全模块
提供HTTPS强制、数据加密和安全中间件功能
"""
import os
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import Request, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from cryptography.fernet import Fernet
import base64
import json

# 密码上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT配置
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# 数据加密密钥（用于敏感数据存储）
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", Fernet.generate_key().decode())


class SecurityMiddleware:
    """安全中间件"""
    
    @staticmethod
    def force_https(request: Request) -> bool:
        """
        检查是否需要强制HTTPS
        
        Args:
            request: 请求对象
        
        Returns:
            是否应该重定向到HTTPS
        """
        if os.getenv("APP_ENV", "development").lower() == "production":
            if request.url.scheme != "https":
                return True
        return False
    
    @staticmethod
    def get_redirect_url(request: Request) -> str:
        """获取HTTPS重定向URL"""
        return f"https://{request.url.hostname}{request.url.path}"
    
    @staticmethod
    def validate_token(credentials: HTTPAuthorizationCredentials) -> Optional[Dict]:
        """验证JWT令牌"""
        try:
            payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
            username: str = payload.get("sub")
            if username is None:
                raise HTTPException(status_code=401, detail="Invalid token")
            return payload
        except JWTError:
            raise HTTPException(status_code=401, detail="Invalid token")


class DataEncryptor:
    """数据加密器"""
    
    def __init__(self):
        self.cipher = Fernet(self._get_key())
    
    def _get_key(self) -> bytes:
        """获取加密密钥"""
        key = ENCRYPTION_KEY.encode()
        if len(key) != 32:
            key = hashlib.sha256(ENCRYPTION_KEY.encode()).digest()
        return base64.urlsafe_b64encode(key)
    
    def encrypt(self, data: str) -> str:
        """加密字符串"""
        return self.cipher.encrypt(data.encode()).decode()
    
    def decrypt(self, encrypted_data: str) -> str:
        """解密字符串"""
        try:
            return self.cipher.decrypt(encrypted_data.encode()).decode()
        except Exception:
            return encrypted_data
    
    def encrypt_dict(self, data: Dict) -> Dict:
        """加密字典中的敏感字段"""
        sensitive_fields = ['email', 'password', 'token', 'api_key', 'secret']
        result = {}
        for key, value in data.items():
            if key.lower() in sensitive_fields and value:
                result[key] = self.encrypt(str(value))
            else:
                result[key] = value
        return result
    
    def decrypt_dict(self, data: Dict) -> Dict:
        """解密字典中的敏感字段"""
        sensitive_fields = ['email', 'password', 'token', 'api_key', 'secret']
        result = {}
        for key, value in data.items():
            if key.lower() in sensitive_fields and value:
                result[key] = self.decrypt(str(value))
            else:
                result[key] = value
        return result


class GDPRCompliance:
    """GDPR合规管理器"""
    
    @staticmethod
    def has_consent(username: str) -> bool:
        """检查用户是否同意隐私政策"""
        from src.database import db_manager
        
        result = db_manager.execute_one('''
            SELECT consent_given FROM users WHERE username = ?
        ''', (username,))
        
        return result and result.get('consent_given') == 1
    
    @staticmethod
    def record_consent(username: str, consent_type: str = 'privacy_policy'):
        """记录用户同意"""
        from src.database import db_manager
        
        db_manager.execute('''
            UPDATE users SET consent_given = 1, consent_date = ? WHERE username = ?
        ''', (datetime.now().isoformat(), username))
        
        # 记录同意日志
        db_manager.execute('''
            INSERT INTO consent_logs (username, consent_type, consented_at)
            VALUES (?, ?, ?)
        ''', (username, consent_type, datetime.now().isoformat()))
    
    @staticmethod
    def export_user_data(username: str) -> Dict:
        """导出用户所有数据（GDPR第15条）"""
        from src.database import db_manager
        
        user = db_manager.execute_one('SELECT * FROM users WHERE username = ?', (username,))
        if not user:
            return {}
        
        # 获取用户相关的所有数据
        data = {
            'user': user,
            'subscriptions': [],
            'imported_data': [],
            'alerts': [],
            'logs': []
        }
        
        subscriptions = db_manager.execute('SELECT * FROM subscriptions WHERE user_id = ?', (username,))
        data['subscriptions'] = subscriptions
        
        imported_data = db_manager.execute('SELECT * FROM imported_data WHERE username = ?', (username,))
        data['imported_data'] = imported_data
        
        alerts = db_manager.execute('SELECT * FROM alert_rules WHERE username = ?', (username,))
        data['alerts'] = alerts
        
        logs = db_manager.execute('SELECT * FROM operation_logs WHERE username = ?', (username,))
        data['logs'] = logs
        
        return data
    
    @staticmethod
    def delete_user_data(username: str) -> bool:
        """删除用户所有数据（GDPR第17条 - 被遗忘权）"""
        from src.database import db_manager
        
        try:
            db_manager.execute('DELETE FROM subscriptions WHERE user_id = ?', (username,))
            db_manager.execute('DELETE FROM imported_data WHERE username = ?', (username,))
            db_manager.execute('DELETE FROM alert_rules WHERE username = ?', (username,))
            db_manager.execute('DELETE FROM operation_logs WHERE username = ?', (username,))
            db_manager.execute('DELETE FROM consent_logs WHERE username = ?', (username,))
            db_manager.execute('DELETE FROM users WHERE username = ?', (username,))
            
            return True
        except Exception as e:
            print(f"Error deleting user data: {e}")
            return False
    
    @staticmethod
    def get_privacy_policy() -> Dict:
        """获取隐私政策内容"""
        return {
            'title': '隐私政策',
            'version': '1.0',
            'last_updated': '2024-01-01',
            'content': {
                'introduction': '我们重视您的隐私，致力于保护您的个人信息安全。',
                'data_collection': '我们收集您的用户名、邮箱地址、使用数据等信息以提供服务。',
                'data_usage': '您的数据仅用于提供和改进我们的服务，不会出售给第三方。',
                'user_rights': '您有权访问、更正、删除您的个人数据，或撤回同意。',
                'contact': '如有疑问，请联系 privacy@gameanalyzer.com'
            }
        }


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """生成密码哈希"""
    return pwd_context.hash(password)


def create_access_token(data: Dict, expires_delta: Optional[timedelta] = None) -> str:
    """创建访问令牌"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now() + expires_delta
    else:
        expire = datetime.now() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def generate_encryption_key() -> str:
    """生成新的加密密钥"""
    return Fernet.generate_key().decode()