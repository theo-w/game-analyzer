"""
运维监控模块
提供系统健康监控、错误日志和用户行为分析功能
"""
import os
import psutil
import time
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from threading import Lock

from src.database import db_manager

class SystemHealthMonitor:
    """系统健康监控器"""
    
    def __init__(self):
        self.metrics = {
            'cpu_usage': 0.0,
            'memory_usage': 0.0,
            'disk_usage': 0.0,
            'network_io': {'bytes_sent': 0, 'bytes_recv': 0},
            'uptime': 0,
            'response_time': 0.0,
            'error_count': 0,
            'request_count': 0
        }
        self.start_time = datetime.now()
        self.lock = Lock()
        self.last_network_stats = psutil.net_io_counters()
    
    def get_cpu_usage(self) -> float:
        """获取CPU使用率"""
        return psutil.cpu_percent(interval=0.1)
    
    def get_memory_usage(self) -> float:
        """获取内存使用率"""
        memory = psutil.virtual_memory()
        return memory.percent
    
    def get_disk_usage(self) -> float:
        """获取磁盘使用率"""
        disk = psutil.disk_usage('/')
        return disk.percent
    
    def get_network_io(self) -> Dict:
        """获取网络IO统计"""
        current = psutil.net_io_counters()
        sent = current.bytes_sent - self.last_network_stats.bytes_sent
        recv = current.bytes_recv - self.last_network_stats.bytes_recv
        self.last_network_stats = current
        return {'bytes_sent': sent, 'bytes_recv': recv}
    
    def get_uptime(self) -> int:
        """获取系统运行时间（秒）"""
        return int((datetime.now() - self.start_time).total_seconds())
    
    def update_metrics(self):
        """更新所有指标"""
        with self.lock:
            self.metrics['cpu_usage'] = self.get_cpu_usage()
            self.metrics['memory_usage'] = self.get_memory_usage()
            self.metrics['disk_usage'] = self.get_disk_usage()
            self.metrics['network_io'] = self.get_network_io()
            self.metrics['uptime'] = self.get_uptime()
    
    def get_health_status(self) -> Dict:
        """获取健康状态"""
        self.update_metrics()
        
        status = 'healthy'
        warnings = []
        
        if self.metrics['cpu_usage'] > 80:
            status = 'warning'
            warnings.append(f"CPU使用率过高: {self.metrics['cpu_usage']}%")
        
        if self.metrics['memory_usage'] > 85:
            status = 'warning'
            warnings.append(f"内存使用率过高: {self.metrics['memory_usage']}%")
        
        if self.metrics['disk_usage'] > 90:
            status = 'critical'
            warnings.append(f"磁盘空间不足: {self.metrics['disk_usage']}%")
        
        return {
            'status': status,
            'timestamp': datetime.now().isoformat(),
            'metrics': self.metrics,
            'warnings': warnings
        }
    
    def record_health_check(self):
        """记录健康检查日志"""
        status = self.get_health_status()
        db_manager.execute('''
            INSERT INTO health_logs (status, metrics, recorded_at)
            VALUES (?, ?, ?)
        ''', (status['status'], json.dumps(status['metrics']), status['timestamp']))

class ErrorLogger:
    """错误日志记录器"""
    
    ERROR_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
    
    @staticmethod
    def log(level: str, message: str, module: str = 'unknown', traceback: str = ''):
        """记录错误日志"""
        if level not in ErrorLogger.ERROR_LEVELS:
            level = 'INFO'
        
        log_entry = {
            'level': level,
            'message': message,
            'module': module,
            'traceback': traceback,
            'timestamp': datetime.now().isoformat()
        }
        
        db_manager.execute('''
            INSERT INTO error_logs (level, message, module, traceback, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (level, message, module, traceback, log_entry['timestamp']))
        
        print(f"[{level}] [{module}] {message}")
        
        # 如果是严重错误，发送告警
        if level in ['ERROR', 'CRITICAL']:
            ErrorLogger.send_alert(log_entry)
    
    @staticmethod
    def send_alert(log_entry: Dict):
        """发送错误告警"""
        print(f"🚨 ALERT [{log_entry['level']}]: {log_entry['message']}")
        # 这里可以集成邮件、钉钉、企业微信等告警方式
    
    @staticmethod
    def get_recent_errors(limit: int = 50) -> List[Dict]:
        """获取最近的错误日志"""
        return db_manager.execute('''
            SELECT * FROM error_logs 
            ORDER BY created_at DESC 
            LIMIT ?
        ''', (limit,))
    
    @staticmethod
    def get_error_stats(hours: int = 24) -> Dict:
        """获取错误统计"""
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        
        result = db_manager.execute_one('''
            SELECT level, COUNT(*) as count 
            FROM error_logs 
            WHERE created_at >= ? 
            GROUP BY level
        ''', (cutoff,))
        
        stats = {level: 0 for level in ErrorLogger.ERROR_LEVELS}
        if result:
            for row in result:
                stats[row['level']] = row['count']
        
        return stats

class UserBehaviorTracker:
    """用户行为追踪器"""
    
    @staticmethod
    def track_event(username: str, event_type: str, details: Dict = None):
        """追踪用户行为事件"""
        if details is None:
            details = {}
        
        db_manager.execute('''
            INSERT INTO user_events (username, event_type, details, created_at)
            VALUES (?, ?, ?, ?)
        ''', (username, event_type, json.dumps(details), datetime.now().isoformat()))
    
    @staticmethod
    def get_user_activity(username: str, days: int = 7) -> List[Dict]:
        """获取用户活动记录"""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        return db_manager.execute('''
            SELECT * FROM user_events 
            WHERE username = ? AND created_at >= ?
            ORDER BY created_at DESC
        ''', (username, cutoff))
    
    @staticmethod
    def get_aggregated_stats(days: int = 7) -> Dict:
        """获取聚合统计数据"""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        
        # 活跃用户数
        active_users = db_manager.execute_one('''
            SELECT COUNT(DISTINCT username) as count FROM user_events WHERE created_at >= ?
        ''', (cutoff,))
        
        # 事件类型统计
        event_stats = db_manager.execute('''
            SELECT event_type, COUNT(*) as count 
            FROM user_events 
            WHERE created_at >= ? 
            GROUP BY event_type
        ''', (cutoff,))
        
        # 每日活跃用户
        daily_stats = db_manager.execute('''
            SELECT DATE(created_at) as date, COUNT(DISTINCT username) as count 
            FROM user_events 
            WHERE created_at >= ? 
            GROUP BY DATE(created_at)
        ''', (cutoff,))
        
        return {
            'active_users': active_users['count'] if active_users else 0,
            'event_stats': {row['event_type']: row['count'] for row in event_stats},
            'daily_stats': [{'date': row['date'], 'count': row['count']} for row in daily_stats]
        }
    
    @staticmethod
    def get_popular_features(days: int = 7, limit: int = 10) -> List[Dict]:
        """获取最受欢迎的功能"""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        
        result = db_manager.execute('''
            SELECT event_type, COUNT(*) as count 
            FROM user_events 
            WHERE created_at >= ? 
            GROUP BY event_type 
            ORDER BY count DESC 
            LIMIT ?
        ''', (cutoff, limit))
        
        return result

# 全局实例
health_monitor = SystemHealthMonitor()
error_logger = ErrorLogger()
behavior_tracker = UserBehaviorTracker()