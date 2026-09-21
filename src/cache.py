"""
Redis缓存模块
提供热点数据缓存、会话管理和速率限制功能
"""
import json
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import os

from src.database import config_manager

class RedisCache:
    """Redis缓存管理器"""
    
    _instance = None
    _redis = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RedisCache, cls).__new__(cls)
            cls._redis = cls._connect()
        return cls._instance
    
    @classmethod
    def _connect(cls):
        """连接到Redis"""
        redis_config = config_manager.get_redis_config()
        
        try:
            import redis
            return redis.Redis(
                host=redis_config['host'],
                port=redis_config['port'],
                password=redis_config['password'],
                db=redis_config['db'],
                socket_timeout=redis_config['socket_timeout'],
                socket_connect_timeout=redis_config['socket_connect_timeout']
            )
        except ImportError:
            print("Warning: redis package not installed, using in-memory cache")
            return None
        except Exception as e:
            print(f"Warning: Failed to connect to Redis: {e}, using in-memory cache")
            return None
    
    def _use_redis(self) -> bool:
        """检查是否可以使用Redis"""
        if self._redis is None:
            return False
        
        try:
            self._redis.ping()
            return True
        except Exception:
            return False
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        if self._use_redis():
            try:
                value = self._redis.get(key)
                if value:
                    try:
                        return json.loads(value)
                    except json.JSONDecodeError:
                        return value.decode('utf-8')
                return None
            except Exception:
                return None
        else:
            # 降级到内存缓存
            return getattr(self, '_memory_cache', {}).get(key)
    
    def set(self, key: str, value: Any, expire_seconds: int = None):
        """设置缓存值"""
        if self._use_redis():
            try:
                if isinstance(value, (dict, list)):
                    value_str = json.dumps(value)
                else:
                    value_str = str(value)
                
                if expire_seconds:
                    self._redis.setex(key, expire_seconds, value_str)
                else:
                    self._redis.set(key, value_str)
            except Exception as e:
                print(f"Redis set error: {e}")
        else:
            # 降级到内存缓存
            if not hasattr(self, '_memory_cache'):
                self._memory_cache = {}
            self._memory_cache[key] = value
            
            if expire_seconds:
                # 简单的过期机制
                if not hasattr(self, '_cache_expire'):
                    self._cache_expire = {}
                self._cache_expire[key] = datetime.now() + timedelta(seconds=expire_seconds)
    
    def delete(self, key: str):
        """删除缓存"""
        if self._use_redis():
            try:
                self._redis.delete(key)
            except Exception as e:
                print(f"Redis delete error: {e}")
        else:
            if hasattr(self, '_memory_cache') and key in self._memory_cache:
                del self._memory_cache[key]
            if hasattr(self, '_cache_expire') and key in self._cache_expire:
                del self._cache_expire[key]
    
    def exists(self, key: str) -> bool:
        """检查键是否存在"""
        if self._use_redis():
            try:
                return self._redis.exists(key) > 0
            except Exception as e:
                print(f"Redis exists error: {e}")
                return False
        else:
            if hasattr(self, '_memory_cache'):
                # 检查过期
                if hasattr(self, '_cache_expire') and key in self._cache_expire:
                    if datetime.now() > self._cache_expire[key]:
                        del self._memory_cache[key]
                        del self._cache_expire[key]
                        return False
                return key in self._memory_cache
            return False
    
    def flush(self):
        """清空所有缓存"""
        if self._use_redis():
            try:
                self._redis.flushdb()
            except Exception as e:
                print(f"Redis flush error: {e}")
        else:
            if hasattr(self, '_memory_cache'):
                self._memory_cache = {}
            if hasattr(self, '_cache_expire'):
                self._cache_expire = {}

class RateLimiter:
    """速率限制器"""
    
    def __init__(self):
        self.cache = RedisCache()
        self.config = config_manager.get_security_config()
    
    def is_allowed(self, key: str, requests_per_minute: int = None) -> bool:
        """检查是否允许请求"""
        if not self.config.get('rate_limit.enabled', True):
            return True
        
        limit = requests_per_minute or self.config.get('rate_limit.requests_per_minute', 60)
        
        # 使用分钟级别的key
        minute_key = f"rate_limit:{key}:{datetime.now().strftime('%Y%m%d%H%M')}"
        
        count = self.cache.get(minute_key) or 0
        
        if count >= limit:
            return False
        
        self.cache.set(minute_key, count + 1, 60)
        return True
    
    def get_remaining(self, key: str, requests_per_minute: int = None) -> int:
        """获取剩余请求次数"""
        limit = requests_per_minute or self.config.get('rate_limit.requests_per_minute', 60)
        minute_key = f"rate_limit:{key}:{datetime.now().strftime('%Y%m%d%H%M')}"
        count = self.cache.get(minute_key) or 0
        return max(0, limit - count)

class SessionManager:
    """会话管理器"""
    
    SESSION_EXPIRE_HOURS = 24
    
    def __init__(self):
        self.cache = RedisCache()
    
    def create_session(self, user_id: str, data: Dict = None) -> str:
        """创建会话"""
        session_id = hashlib.sha256(f"{user_id}{datetime.now()}".encode()).hexdigest()
        session_data = {
            'user_id': user_id,
            'created_at': datetime.now().isoformat(),
            'data': data or {}
        }
        self.cache.set(
            f"session:{session_id}", 
            session_data, 
            expire_seconds=self.SESSION_EXPIRE_HOURS * 3600
        )
        return session_id
    
    def get_session(self, session_id: str) -> Optional[Dict]:
        """获取会话"""
        session_data = self.cache.get(f"session:{session_id}")
        return session_data
    
    def update_session(self, session_id: str, data: Dict):
        """更新会话数据"""
        session_data = self.cache.get(f"session:{session_id}")
        if session_data:
            session_data['data'] = {**session_data.get('data', {}), **data}
            self.cache.set(
                f"session:{session_id}", 
                session_data, 
                expire_seconds=self.SESSION_EXPIRE_HOURS * 3600
            )
    
    def invalidate_session(self, session_id: str):
        """使会话失效"""
        self.cache.delete(f"session:{session_id}")
    
    def is_valid(self, session_id: str) -> bool:
        """检查会话是否有效"""
        return self.cache.exists(f"session:{session_id}")

class DataCache:
    """数据缓存管理器"""
    
    def __init__(self):
        self.cache = RedisCache()
    
    def cache_metrics(self, key: str, data: Any, expire_minutes: int = 5):
        """缓存指标数据"""
        self.cache.set(f"metrics:{key}", data, expire_seconds=expire_minutes * 60)
    
    def get_metrics(self, key: str) -> Optional[Any]:
        """获取缓存的指标数据"""
        return self.cache.get(f"metrics:{key}")
    
    def cache_dashboard(self, user_id: str, dashboard_id: str, data: Any, expire_minutes: int = 10):
        """缓存仪表盘数据"""
        self.cache.set(f"dashboard:{user_id}:{dashboard_id}", data, expire_seconds=expire_minutes * 60)
    
    def get_dashboard(self, user_id: str, dashboard_id: str) -> Optional[Any]:
        """获取缓存的仪表盘数据"""
        return self.cache.get(f"dashboard:{user_id}:{dashboard_id}")
    
    def cache_analytics(self, key: str, data: Any, expire_minutes: int = 5):
        """缓存分析数据"""
        self.cache.set(f"analytics:{key}", data, expire_seconds=expire_minutes * 60)
    
    def get_analytics(self, key: str) -> Optional[Any]:
        """获取缓存的分析数据"""
        return self.cache.get(f"analytics:{key}")
    
    def invalidate_dashboard(self, user_id: str, dashboard_id: str = None):
        """使仪表盘缓存失效"""
        if dashboard_id:
            self.cache.delete(f"dashboard:{user_id}:{dashboard_id}")
        else:
            # 删除用户所有仪表盘缓存
            # 在内存模式下无法批量删除，这里简化处理
            pass

# 全局实例
redis_cache = RedisCache()
rate_limiter = RateLimiter()
session_manager = SessionManager()
data_cache = DataCache()

def get_cache() -> RedisCache:
    """获取缓存实例（兼容旧代码）"""
    return redis_cache

def get_rate_limiter() -> RateLimiter:
    """获取速率限制器实例"""
    return rate_limiter

def get_session_manager() -> SessionManager:
    """获取会话管理器实例"""
    return session_manager

def get_data_cache() -> DataCache:
    """获取数据缓存管理器实例"""
    return data_cache
