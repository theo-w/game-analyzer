"""
团队协作管理模块
支持多角色权限、团队成员管理和共享功能
"""
from datetime import datetime
from typing import List, Dict, Optional
import os

from src.database import get_db_connection

def _fetchone_dict(cursor) -> Optional[Dict]:
    row = cursor.fetchone()
    if row is None:
        return None
    columns = [col[0] for col in cursor.description]
    return dict(zip(columns, row))

def _fetchall_dicts(cursor) -> List[Dict]:
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]

class TeamRepository:
    """团队仓库类"""
    
    @staticmethod
    def create_team(team_data: Dict) -> Optional[int]:
        """创建团队"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO teams (name, description, owner_id, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    team_data['name'],
                    team_data.get('description', ''),
                    team_data['owner_id'],
                    datetime.now().isoformat(),
                    datetime.now().isoformat()
                ))
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            print(f"Error creating team: {e}")
            return None
    
    @staticmethod
    def get_team(team_id: int) -> Optional[Dict]:
        """获取团队信息"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM teams WHERE id = ?', (team_id,))
            return _fetchone_dict(cursor)
    
    @staticmethod
    def get_user_teams(username: str) -> List[Dict]:
        """获取用户所在的所有团队"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT t.*, tm.role 
                FROM teams t
                JOIN team_members tm ON t.id = tm.team_id
                WHERE tm.username = ?
                ORDER BY tm.joined_at DESC
            ''', (username,))
            return _fetchall_dicts(cursor)
    
    @staticmethod
    def add_member(team_id: int, username: str, role: str = 'viewer') -> bool:
        """添加团队成员"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO team_members (team_id, username, role, joined_at)
                    VALUES (?, ?, ?, ?)
                ''', (team_id, username, role, datetime.now().isoformat()))
                conn.commit()
                return True
        except Exception as e:
            print(f"Error adding team member: {e}")
            return False
    
    @staticmethod
    def remove_member(team_id: int, username: str) -> bool:
        """移除团队成员"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    DELETE FROM team_members 
                    WHERE team_id = ? AND username = ?
                ''', (team_id, username))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            print(f"Error removing team member: {e}")
            return False
    
    @staticmethod
    def get_team_members(team_id: int) -> List[Dict]:
        """获取团队成员列表"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT tm.*, u.email, u.full_name, u.role as user_role
                FROM team_members tm
                JOIN users u ON tm.username = u.username
                WHERE tm.team_id = ?
                ORDER BY tm.joined_at ASC
            ''', (team_id,))
            return _fetchall_dicts(cursor)
    
    @staticmethod
    def update_member_role(team_id: int, username: str, role: str) -> bool:
        """更新成员角色"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE team_members 
                    SET role = ?, updated_at = ?
                    WHERE team_id = ? AND username = ?
                ''', (role, datetime.now().isoformat(), team_id, username))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            print(f"Error updating member role: {e}")
            return False
    
    @staticmethod
    def is_team_member(team_id: int, username: str) -> bool:
        """检查用户是否是团队成员"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 1 FROM team_members 
                WHERE team_id = ? AND username = ?
            ''', (team_id, username))
            return cursor.fetchone() is not None
    
    @staticmethod
    def get_member_role(team_id: int, username: str) -> Optional[str]:
        """获取成员角色"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT role FROM team_members 
                WHERE team_id = ? AND username = ?
            ''', (team_id, username))
            row = _fetchone_dict(cursor)
            return row.get('role') if row else None

class DashboardShareRepository:
    """仪表盘共享仓库类"""
    
    @staticmethod
    def create_share(share_data: Dict) -> Optional[str]:
        """创建仪表盘共享"""
        try:
            import secrets
            share_token = secrets.token_urlsafe(32)
            
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO dashboard_shares 
                    (dashboard_id, share_token, shared_by, permissions, expires_at, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    share_data['dashboard_id'],
                    share_token,
                    share_data['shared_by'],
                    share_data.get('permissions', 'view'),
                    share_data.get('expires_at'),
                    datetime.now().isoformat()
                ))
                conn.commit()
                return share_token
        except Exception as e:
            print(f"Error creating dashboard share: {e}")
            return None
    
    @staticmethod
    def get_share(share_token: str) -> Optional[Dict]:
        """获取共享信息"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM dashboard_shares WHERE share_token = ?', (share_token,))
            return _fetchone_dict(cursor)
    
    @staticmethod
    def get_dashboard_shares(dashboard_id: int) -> List[Dict]:
        """获取仪表盘的所有共享记录"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT ds.*, u.full_name as shared_by_name
                FROM dashboard_shares ds
                JOIN users u ON ds.shared_by = u.username
                WHERE ds.dashboard_id = ?
                ORDER BY ds.created_at DESC
            ''', (dashboard_id,))
            return _fetchall_dicts(cursor)
    
    @staticmethod
    def delete_share(share_token: str) -> bool:
        """删除共享"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM dashboard_shares WHERE share_token = ?', (share_token,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            print(f"Error deleting dashboard share: {e}")
            return False
    
    @staticmethod
    def get_user_shared_dashboards(username: str) -> List[Dict]:
        """获取用户共享给我的仪表盘"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT ds.*, dc.name as dashboard_name, u.full_name as shared_by_name
                FROM dashboard_shares ds
                JOIN dashboard_configs dc ON ds.dashboard_id = dc.id
                JOIN users u ON ds.shared_by = u.username
                JOIN team_members tm ON ds.shared_by = tm.username
                WHERE tm.username = ?
                ORDER BY ds.created_at DESC
            ''', (username,))
            return _fetchall_dicts(cursor)

def check_permission(user_role: str, required_role: str) -> bool:
    """
    检查权限
    
    权限等级：admin > editor > viewer
    """
    role_levels = {
        'admin': 3,
        'editor': 2,
        'viewer': 1
    }
    
    user_level = role_levels.get(user_role, 0)
    required_level = role_levels.get(required_role, 0)
    
    return user_level >= required_level

def init_team_tables():
    """初始化团队协作相关的数据库表"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # 团队表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                owner_id TEXT NOT NULL,
                created_at TEXT,
                updated_at TEXT
            )
        ''')
        
        # 团队成员表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS team_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                role TEXT DEFAULT 'viewer',
                joined_at TEXT,
                updated_at TEXT,
                FOREIGN KEY (team_id) REFERENCES teams(id),
                FOREIGN KEY (username) REFERENCES users(username)
            )
        ''')
        
        # 仪表盘共享表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS dashboard_shares (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dashboard_id INTEGER NOT NULL,
                share_token TEXT UNIQUE NOT NULL,
                shared_by TEXT NOT NULL,
                permissions TEXT DEFAULT 'view',
                expires_at TEXT,
                created_at TEXT,
                FOREIGN KEY (dashboard_id) REFERENCES dashboard_configs(id),
                FOREIGN KEY (shared_by) REFERENCES users(username)
            )
        ''')
        
        conn.commit()
