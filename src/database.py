"""
数据库配置模块
支持 SQLite、PostgreSQL、MySQL 多数据库切换
提供连接池管理和配置管理功能
"""
import os
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

# 数据库类型枚举
DB_TYPES = ['sqlite', 'postgresql', 'mysql']

# 默认配置
DEFAULT_CONFIG = {
    'database': {
        'type': 'sqlite',
        'host': 'localhost',
        'port': 5432,
        'database': 'game_analyzer',
        'username': 'admin',
        'password': '',
        'path': 'data/game_analyzer.db',
        'pool_size': 10,
        'max_overflow': 20,
        'connect_timeout': 30
    },
    'redis': {
        'host': 'localhost',
        'port': 6379,
        'password': '',
        'db': 0,
        'socket_timeout': 5,
        'socket_connect_timeout': 5
    },
    'security': {
        'secret_key': 'your-secret-key-change-in-production',
        'algorithm': 'HS256',
        'access_token_expire_minutes': 30,
        'https_only': False,
        'cors_allowed_origins': ['*'],
        'rate_limit': {
            'enabled': True,
            'requests_per_minute': 60
        }
    },
    'app': {
        'debug': True,
        'host': '0.0.0.0',
        'port': 8080,
        'workers': 1
    }
}


class ConfigManager:
    """配置管理器"""
    
    _instance = None
    _config = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._config = cls._load_config()
        return cls._instance
    
    @classmethod
    def _load_config(cls) -> Dict:
        """加载配置文件"""
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'config.json')
        
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    return {**DEFAULT_CONFIG, **json.load(f)}
            except Exception as e:
                print(f"Warning: Failed to load config file: {e}")
        
        # 如果配置文件不存在，创建默认配置
        cls._create_default_config(config_path)
        return DEFAULT_CONFIG
    
    @classmethod
    def _create_default_config(cls, config_path: str):
        """创建默认配置文件"""
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        keys = key.split('.')
        value = self._config
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default
    
    def set(self, key: str, value: Any):
        """设置配置值"""
        keys = key.split('.')
        config = self._config
        for i, k in enumerate(keys[:-1]):
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value
        
        # 保存配置
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'config.json')
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(self._config, f, indent=2, ensure_ascii=False)
    
    def get_database_config(self) -> Dict:
        """获取数据库配置"""
        cfg = dict(self.get('database', DEFAULT_CONFIG['database']))
        # 环境变量覆盖 sqlite 路径（tests/conftest.py 用它把测试写入隔离到临时目录）
        env_path = os.environ.get('GA_SQLITE_PATH')
        if env_path and cfg.get('type', 'sqlite') == 'sqlite':
            cfg['path'] = env_path
        return cfg
    
    def get_redis_config(self) -> Dict:
        """获取Redis配置"""
        return self.get('redis', DEFAULT_CONFIG['redis'])
    
    def get_security_config(self) -> Dict:
        """获取安全配置"""
        return self.get('security', DEFAULT_CONFIG['security'])
    
    def get_app_config(self) -> Dict:
        """获取应用配置"""
        return self.get('app', DEFAULT_CONFIG['app'])


class DatabaseManager:
    """数据库管理器"""
    
    def __init__(self):
        from src.db_dialect import resolve_database_backend

        self.config = ConfigManager()
        # DATABASE_URL / DATABASE_TYPE 在此真正生效, 与健康页展示同源
        self.db_type, self._db_config = resolve_database_backend(self.config)

    def _create_connection(self):
        """创建数据库连接"""
        db_config = self._db_config
        
        if self.db_type == 'sqlite':
            import sqlite3
            db_path = db_config['path']
            if not os.path.isabs(db_path):
                project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
                db_path = os.path.join(project_root, db_path)
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            return sqlite3.connect(db_path)
        
        elif self.db_type == 'postgresql':
            import psycopg2
            return psycopg2.connect(
                host=db_config['host'],
                port=db_config['port'],
                dbname=db_config['database'],
                user=db_config['username'],
                password=db_config['password'],
                connect_timeout=db_config['connect_timeout']
            )

        elif self.db_type == 'mysql':
            import pymysql
            return pymysql.connect(
                host=db_config['host'],
                port=db_config['port'],
                database=db_config['database'],
                user=db_config['username'],
                password=db_config['password'],
                connect_timeout=db_config['connect_timeout']
            )
        
        else:
            import sqlite3
            return sqlite3.connect(db_config['path'])
    
    @contextmanager
    def get_connection(self):
        """获取数据库连接（上下文管理器）"""
        conn = None
        try:
            conn = self._create_connection()
            yield conn
        finally:
            if conn:
                conn.close()
    
    def execute(self, query: str, params: tuple = None) -> List[Dict]:
        """执行查询并返回结果"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            # 获取列名
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            
            # 处理结果
            if query.strip().upper().startswith('SELECT'):
                results = cursor.fetchall()
                return [dict(zip(columns, row)) for row in results]
            else:
                conn.commit()
                return []
    
    def execute_one(self, query: str, params: tuple = None) -> Optional[Dict]:
        """执行查询并返回单个结果"""
        results = self.execute(query, params)
        return results[0] if results else None
    
    def insert(self, table: str, data: Dict) -> int:
        """插入数据并返回ID"""
        columns = ', '.join(data.keys())
        placeholders = ', '.join(['?' for _ in data])
        values = tuple(data.values())
        
        query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, values)
            conn.commit()
            
            # 返回插入的ID
            if self.db_type == 'sqlite':
                return cursor.lastrowid
            elif self.db_type == 'postgresql':
                cursor.execute("SELECT LASTVAL()")
                return cursor.fetchone()[0]
            elif self.db_type == 'mysql':
                return cursor.lastrowid
            
            return 0


# 全局实例
config_manager = ConfigManager()
db_manager = DatabaseManager()


def get_db_connection():
    """获取数据库连接（兼容旧代码）"""
    return db_manager.get_connection()


def _hash_password(password: str) -> str:
    """哈希密码（内部函数，避免循环导入）"""
    import hashlib
    return hashlib.sha256(password.encode()).hexdigest()


def _seed_support_agent_users(cursor) -> None:
    """Ensure default human-agent accounts exist (idempotent)."""
    now = datetime.now().isoformat()
    for agent_username, agent_name, agent_password in (
        ("agent1", "坐席小王", "agent123"),
        ("agent2", "坐席小李", "agent123"),
    ):
        cursor.execute("SELECT COUNT(*) FROM users WHERE username = ?", (agent_username,))
        if cursor.fetchone()[0] == 0:
            cursor.execute(
                """
                INSERT INTO users (username, email, full_name, hashed_password, role, plan_id, games_limit, api_quota, is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    agent_username,
                    f"{agent_username}@example.com",
                    agent_name,
                    _hash_password(agent_password),
                    "agent",
                    "pro",
                    1,
                    1000,
                    1,
                    now,
                    now,
                ),
            )


def ensure_support_agents() -> None:
    """Create missing default agent users on every app startup."""
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        _seed_support_agent_users(cursor)
        conn.commit()


def _ensure_sqlite_columns(cursor, table: str, columns: Dict[str, str]) -> None:
    """Add missing columns on existing SQLite databases."""
    cursor.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in cursor.fetchall()}
    for name, column_type in columns.items():
        if name not in existing:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {name} {column_type}")


def init_database():
    """初始化数据库（兼容旧代码）"""
    if db_manager.db_type != 'sqlite':
        # init_database 的 DDL 与 _ensure_sqlite_columns 均为 sqlite 方言,
        # PostgreSQL schema 尚未完成迁移; 宁可启动报错也不静默写错库
        raise RuntimeError(
            f"数据库类型 {db_manager.db_type} 的建表初始化尚未支持, "
            "当前版本请使用 sqlite (移除 DATABASE_URL / DATABASE_TYPE 配置)"
        )
    db_config = config_manager.get_database_config()
    
    # 确保数据目录存在
    if db_config['type'] == 'sqlite':
        db_path = db_config['path']
        if not os.path.isabs(db_path):
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
            db_path = os.path.join(project_root, db_path)
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                email TEXT,
                full_name TEXT,
                hashed_password TEXT,
                role TEXT DEFAULT 'user',
                plan_id TEXT DEFAULT 'free',
                games_limit INTEGER DEFAULT 1,
                api_quota INTEGER DEFAULT 100,
                is_active INTEGER DEFAULT 1,
                trial_start_date TEXT,
                trial_end_date TEXT,
                is_trial INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT
            )
        ''')

        _ensure_sqlite_columns(
            cursor,
            "users",
            {
                "trial_start_date": "TEXT",
                "trial_end_date": "TEXT",
                "is_trial": "INTEGER DEFAULT 0",
            },
        )
        conn.commit()
        
        # 添加默认管理员用户
        cursor.execute('SELECT COUNT(*) FROM users WHERE username = ?', ('admin',))
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT INTO users (username, email, full_name, hashed_password, role, plan_id, games_limit, api_quota, is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', ('admin', 'admin@example.com', '管理员', _hash_password('admin123'), 'admin', 'enterprise', 10, 10000, 1, datetime.now().isoformat(), datetime.now().isoformat()))
        
        # 添加默认演示用户
        cursor.execute('SELECT COUNT(*) FROM users WHERE username = ?', ('demo',))
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT INTO users (username, email, full_name, hashed_password, role, plan_id, games_limit, api_quota, is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', ('demo', 'demo@example.com', '演示用户', _hash_password('demo123'), 'user', 'pro', 5, 5000, 1, datetime.now().isoformat(), datetime.now().isoformat()))

        _seed_support_agent_users(cursor)
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS llm_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                provider TEXT DEFAULT 'openai',
                model TEXT DEFAULT 'gpt-4o-mini',
                api_key TEXT,
                endpoint TEXT,
                temperature REAL DEFAULT 0.7,
                max_tokens INTEGER DEFAULT 2000,
                updated_at TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS operation_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                action TEXT NOT NULL,
                target TEXT,
                detail TEXT,
                created_at TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS dashboard_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                name TEXT,
                layout TEXT,
                filters TEXT,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY (username) REFERENCES users(username)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS alert_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                product TEXT,
                metric TEXT NOT NULL,
                operator TEXT NOT NULL,
                threshold REAL NOT NULL,
                email TEXT,
                webhook_url TEXT,
                enabled INTEGER DEFAULT 1,
                last_triggered TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        ''')
        
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
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS shared_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                share_token TEXT UNIQUE NOT NULL,
                username TEXT NOT NULL,
                report_type TEXT NOT NULL,
                report_data TEXT NOT NULL,
                expires_at TEXT,
                created_at TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT UNIQUE NOT NULL,
                username TEXT NOT NULL,
                plan_id TEXT NOT NULL,
                amount INTEGER NOT NULL,
                payment_method TEXT,
                payment_status TEXT DEFAULT 'pending',
                transaction_id TEXT,
                paid_at TEXT,
                expires_at TEXT,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY (username) REFERENCES users(username)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                steam_app_id TEXT,
                google_play_id TEXT,
                app_store_id TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT,
                updated_at TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS data_source_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT UNIQUE NOT NULL,
                api_key TEXT,
                api_secret TEXT,
                access_token TEXT,
                refresh_token TEXT,
                expires_at TEXT,
                config TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS imported_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                product TEXT,
                channel TEXT,
                cycle TEXT,
                metric TEXT,
                值 REAL,
                date TEXT,
                platform TEXT,
                installs INTEGER DEFAULT 0,
                revenue REAL DEFAULT 0,
                active_users INTEGER DEFAULT 0,
                sessions INTEGER DEFAULT 0,
                avg_session_duration REAL DEFAULT 0,
                retention_1d REAL DEFAULT 0,
                retention_7d REAL DEFAULT 0,
                retention_30d REAL DEFAULT 0,
                created_at TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS imported_comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                product TEXT,
                platform TEXT,
                review_id TEXT,
                rating INTEGER,
                title TEXT,
                content TEXT,
                内容 TEXT,
                author TEXT,
                date TEXT,
                日期 TEXT,
                用户角色 TEXT,
                情绪 TEXT,
                helpful_count INTEGER DEFAULT 0,
                sentiment REAL DEFAULT 0,
                created_at TEXT
            )
        ''')
        
        # 缓存的采集数据表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cached_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product TEXT NOT NULL,
                platform TEXT NOT NULL,
                channel TEXT,
                cycle TEXT,
                metric TEXT,
                值 REAL,
                date TEXT,
                installs INTEGER DEFAULT 0,
                revenue REAL DEFAULT 0,
                active_users INTEGER DEFAULT 0,
                sessions INTEGER DEFAULT 0,
                avg_session_duration REAL DEFAULT 0,
                retention_1d REAL DEFAULT 0,
                retention_7d REAL DEFAULT 0,
                retention_30d REAL DEFAULT 0,
                cached_at TEXT NOT NULL,
                UNIQUE(product, platform, date, metric)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cached_comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product TEXT NOT NULL,
                platform TEXT NOT NULL,
                review_id TEXT,
                rating INTEGER,
                title TEXT,
                content TEXT,
                内容 TEXT,
                author TEXT,
                date TEXT,
                日期 TEXT,
                用户角色 TEXT,
                情绪 TEXT,
                helpful_count INTEGER DEFAULT 0,
                sentiment REAL DEFAULT 0,
                cached_at TEXT NOT NULL,
                UNIQUE(product, platform, review_id)
            )
        ''')
        
        # GDPR同意日志表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS consent_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                consent_type TEXT NOT NULL,
                consented_at TEXT NOT NULL,
                FOREIGN KEY (username) REFERENCES users(username)
            )
        ''')
        
        # 订阅到期提醒日志表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reminder_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subscription_id TEXT NOT NULL,
                days_remaining INTEGER NOT NULL,
                sent_at TEXT NOT NULL
            )
        ''')
        
        # 系统健康日志表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS health_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                status TEXT NOT NULL,
                metrics TEXT,
                recorded_at TEXT NOT NULL
            )
        ''')
        
        # 错误日志表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS error_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level TEXT NOT NULL,
                message TEXT NOT NULL,
                module TEXT,
                traceback TEXT,
                created_at TEXT NOT NULL
            )
        ''')
        
        # 用户行为事件表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                event_type TEXT NOT NULL,
                details TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (username) REFERENCES users(username)
            )
        ''')
        
        # 工单系统表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS support_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id TEXT UNIQUE NOT NULL,
                username TEXT NOT NULL,
                subject TEXT NOT NULL,
                message TEXT NOT NULL,
                priority TEXT DEFAULT 'medium',
                status TEXT DEFAULT 'open',
                agent_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                FOREIGN KEY (username) REFERENCES users(username)
            )
        ''')
        
        # 工单回复表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ticket_replies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id TEXT NOT NULL,
                username TEXT NOT NULL,
                message TEXT NOT NULL,
                is_agent INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (ticket_id) REFERENCES support_tickets(ticket_id),
                FOREIGN KEY (username) REFERENCES users(username)
            )
        ''')
        
        # 在线聊天表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS live_chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT UNIQUE NOT NULL,
                username TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                created_at TEXT NOT NULL,
                ended_at TEXT,
                FOREIGN KEY (username) REFERENCES users(username)
            )
        ''')
        
        # 聊天消息表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT NOT NULL,
                username TEXT NOT NULL,
                message TEXT NOT NULL,
                is_system INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (chat_id) REFERENCES live_chats(chat_id),
                FOREIGN KEY (username) REFERENCES users(username)
            )
        ''')
        
        # 创建索引
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_team_members_team ON team_members(team_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_team_members_user ON team_members(username)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_alert_rules_enabled ON alert_rules(enabled)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_orders_order_id ON orders(order_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_orders_username ON orders(username)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_products_product_id ON products(product_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_data_source_configs_platform ON data_source_configs(platform)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cached_metrics_product ON cached_metrics(product)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cached_metrics_platform ON cached_metrics(platform)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cached_metrics_date ON cached_metrics(date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cached_comments_product ON cached_comments(product)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cached_comments_platform ON cached_comments(platform)')

        _ensure_sqlite_columns(
            cursor,
            "support_tickets",
            {
                "chat_id": "TEXT",
            },
        )
        _ensure_sqlite_columns(
            cursor,
            "live_chats",
            {
                "ticket_id": "TEXT",
                "assigned_agent": "TEXT",
                "updated_at": "TEXT",
                "last_agent_reply": "TEXT",
            },
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS registration_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                email TEXT NOT NULL,
                ip_address TEXT NOT NULL,
                device_id TEXT,
                trial_granted INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS login_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                ip_address TEXT NOT NULL,
                device_id TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS device_accounts (
                device_id TEXT NOT NULL,
                username TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                PRIMARY KEY (device_id, username)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS device_trial_claims (
                device_id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                claimed_at TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_registration_events_ip ON registration_events(ip_address, created_at)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_registration_events_device ON registration_events(device_id, created_at)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_login_events_ip ON login_events(ip_address, created_at)"
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS game_library (
                game_id TEXT PRIMARY KEY,
                username TEXT,
                name TEXT NOT NULL,
                name_en TEXT,
                genre TEXT,
                sub_genre TEXT,
                platforms TEXT,
                developer TEXT,
                publisher TEXT,
                release_date TEXT,
                business_model TEXT,
                steam_app_id TEXT,
                store_urls TEXT,
                tags TEXT,
                summary TEXT,
                cover_emoji TEXT DEFAULT '🎮',
                competitor_ids TEXT,
                source TEXT DEFAULT 'manual',
                is_active INTEGER DEFAULT 1,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS gameplay_breakdowns (
                game_id TEXT PRIMARY KEY,
                core_loop TEXT,
                progression TEXT,
                monetization TEXT,
                social_features TEXT,
                session_design TEXT,
                differentiation TEXT,
                benchmarks TEXT,
                analysis_notes TEXT,
                pillars TEXT,
                auto_generated INTEGER DEFAULT 0,
                updated_at TEXT
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_game_library_genre ON game_library(genre)"
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_archives (
                archive_id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                title TEXT NOT NULL,
                report_type TEXT NOT NULL,
                product_ids TEXT,
                game_ids TEXT,
                snapshot_json TEXT,
                share_token TEXT,
                html_excerpt TEXT,
                created_at TEXT
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_analysis_archives_user ON analysis_archives(username, created_at)"
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS game_version_history (
                version_id TEXT PRIMARY KEY,
                game_id TEXT NOT NULL,
                version_label TEXT NOT NULL,
                released_at TEXT,
                change_summary TEXT,
                change_type TEXT DEFAULT 'update',
                source TEXT DEFAULT 'manual',
                created_at TEXT
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_game_version_game ON game_version_history(game_id, released_at)"
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS competitor_dimension_scores (
                username TEXT NOT NULL,
                game_id TEXT NOT NULL,
                scores_json TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT,
                PRIMARY KEY (username, game_id)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS hotspot_custom_topics (
                topic_id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                product_id TEXT NOT NULL,
                title TEXT NOT NULL,
                brief TEXT NOT NULL DEFAULT '',
                hook TEXT DEFAULT '',
                angle TEXT DEFAULT 'custom',
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_hotspot_custom_user ON hotspot_custom_topics(username, created_at)"
        )
        _ensure_sqlite_columns(
            cursor,
            "analysis_archives",
            {
                "category": "TEXT DEFAULT ''",
                "tags": "TEXT DEFAULT '[]'",
                "body_markdown": "TEXT DEFAULT ''",
                "updated_at": "TEXT",
                "parent_archive_id": "TEXT DEFAULT ''",
            },
        )
        _ensure_sqlite_columns(
            cursor,
            "gameplay_breakdowns",
            {"level_design": "TEXT DEFAULT ''"},
        )
        
        conn.commit()


def get_config() -> Dict:
    """获取配置（兼容旧代码）"""
    return config_manager._config


def set_config(key: str, value: Any):
    """设置配置（兼容旧代码）"""
    config_manager.set(key, value)


class UserRepository:
    """用户数据仓库"""
    
    @staticmethod
    def get_by_username(username: str) -> Optional[Dict]:
        """根据用户名获取用户"""
        return db_manager.execute_one('SELECT * FROM users WHERE username = ?', (username,))

    @staticmethod
    def get_by_email(email: str) -> Optional[Dict]:
        """根据邮箱获取用户（不区分大小写）"""
        if not email:
            return None
        return db_manager.execute_one(
            'SELECT * FROM users WHERE LOWER(email) = LOWER(?) LIMIT 1',
            (email.strip(),),
        )
    
    @staticmethod
    def create(user_data: Dict) -> bool:
        """创建用户"""
        user_data['created_at'] = datetime.now().isoformat()
        user_data['updated_at'] = datetime.now().isoformat()
        try:
            db_manager.insert('users', user_data)
            return True
        except Exception:
            return False
    
    @staticmethod
    def update(username: str, user_data: Dict) -> bool:
        """更新用户"""
        user_data['updated_at'] = datetime.now().isoformat()
        updates = [f"{k} = ?" for k in user_data.keys()]
        params = list(user_data.values()) + [username]
        query = f"UPDATE users SET {', '.join(updates)} WHERE username = ?"
        db_manager.execute(query, tuple(params))
        return True
    
    @staticmethod
    def delete(username: str) -> bool:
        """删除用户"""
        db_manager.execute('DELETE FROM users WHERE username = ?', (username,))
        return True
    
    @staticmethod
    def get_all() -> List[Dict]:
        """获取所有用户"""
        return db_manager.execute('SELECT username, email, role, plan_id, is_active, created_at FROM users ORDER BY created_at DESC')
    
    @staticmethod
    def update_plan(username: str, plan_id: str):
        """更新用户套餐"""
        db_manager.execute('UPDATE users SET plan_id = ?, updated_at = ? WHERE username = ?', 
                          (plan_id, datetime.now().isoformat(), username))
    
    @staticmethod
    def update_limits(username: str, games_limit: int, api_quota: int):
        """更新用户限制"""
        db_manager.execute('UPDATE users SET games_limit = ?, api_quota = ?, updated_at = ? WHERE username = ?',
                          (games_limit, api_quota, datetime.now().isoformat(), username))


class OperationLogRepository:
    """操作日志仓库"""
    
    @staticmethod
    def log(username: str, action: str, detail: str = None, target: str = None):
        """记录操作日志"""
        db_manager.execute('''
            INSERT INTO operation_logs (username, action, target, detail, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (username, action, target, detail, datetime.now().isoformat()))
    
    @staticmethod
    def get_all(limit: int = 100) -> List[Dict]:
        """获取所有日志"""
        return db_manager.execute('SELECT * FROM operation_logs ORDER BY created_at DESC LIMIT ?', (limit,))
    
    @staticmethod
    def get_by_username(username: str, limit: int = 50) -> List[Dict]:
        """根据用户名获取日志"""
        return db_manager.execute('SELECT * FROM operation_logs WHERE username = ? ORDER BY created_at DESC LIMIT ?',
                                  (username, limit))


class LLMConfigRepository:
    """LLM配置仓库"""
    
    @staticmethod
    def get_config() -> Optional[Dict]:
        """获取配置"""
        return db_manager.execute_one('SELECT * FROM llm_config WHERE id = 1')
    
    @staticmethod
    def update_config(config_data: Dict):
        """更新配置"""
        config_data['updated_at'] = datetime.now().isoformat()
        
        existing = db_manager.execute_one('SELECT * FROM llm_config WHERE id = 1')
        if existing:
            updates = [f"{k} = ?" for k in config_data.keys()]
            params = list(config_data.values()) + [1]
            query = f"UPDATE llm_config SET {', '.join(updates)} WHERE id = ?"
            db_manager.execute(query, tuple(params))
        else:
            config_data['id'] = 1
            db_manager.insert('llm_config', config_data)
    
    @staticmethod
    def get() -> Optional[Dict]:
        """获取配置（兼容web_app）"""
        return db_manager.execute_one('SELECT * FROM llm_config WHERE id = 1')
    
    @staticmethod
    def save(config_data: Dict):
        """保存配置（合并已有字段，避免部分更新丢失 provider/model）。"""
        existing = db_manager.execute_one('SELECT * FROM llm_config WHERE id = 1') or {}
        merged = {
            k: v
            for k, v in existing.items()
            if k not in ('id', 'updated_at')
        }
        merged.update(config_data)
        merged['updated_at'] = datetime.now().isoformat()
        
        if db_manager.execute_one('SELECT * FROM llm_config WHERE id = 1'):
            updates = [f"{k} = ?" for k in merged.keys()]
            params = list(merged.values()) + [1]
            query = f"UPDATE llm_config SET {', '.join(updates)} WHERE id = ?"
            db_manager.execute(query, tuple(params))
        else:
            merged['id'] = 1
            db_manager.insert('llm_config', merged)


class ProductRepository:
    """产品数据仓库"""
    
    @staticmethod
    def get_all() -> List[Dict]:
        """获取所有产品（仅来自数据库；看板产品由抓取/导入数据动态生成）。"""
        try:
            rows = db_manager.execute('SELECT * FROM products ORDER BY name')
            return rows or []
        except Exception:
            return []
    
    @staticmethod
    def create(product_data: Dict) -> bool:
        """创建产品"""
        product_data['created_at'] = datetime.now().isoformat()
        product_data['updated_at'] = datetime.now().isoformat()
        try:
            db_manager.insert('products', product_data)
            return True
        except Exception:
            return False


class DataSourceConfigRepository:
    """数据源配置仓库"""
    
    @staticmethod
    def get_all() -> List[Dict]:
        """获取所有数据源配置"""
        return db_manager.execute('SELECT * FROM data_source_configs ORDER BY platform')
    
    @staticmethod
    def create_or_update(platform: str, config_data: Dict) -> bool:
        """创建或更新数据源配置"""
        config_data['platform'] = platform
        config_data['updated_at'] = datetime.now().isoformat()
        
        existing = db_manager.execute_one('SELECT * FROM data_source_configs WHERE platform = ?', (platform,))
        if existing:
            updates = [f"{k} = ?" for k in config_data.keys()]
            params = list(config_data.values()) + [platform]
            query = f"UPDATE data_source_configs SET {', '.join(updates)} WHERE platform = ?"
            db_manager.execute(query, tuple(params))
        else:
            config_data['created_at'] = datetime.now().isoformat()
            db_manager.insert('data_source_configs', config_data)
        
        return True
    
    @staticmethod
    def delete(platform: str) -> bool:
        """删除数据源配置"""
        db_manager.execute('DELETE FROM data_source_configs WHERE platform = ?', (platform,))
        return True


class OrderRepository:
    """订单数据仓库"""
    
    @staticmethod
    def create(order_data: Dict) -> bool:
        """创建订单"""
        order_data['created_at'] = datetime.now().isoformat()
        try:
            db_manager.insert('orders', order_data)
            return True
        except Exception:
            return False
    
    @staticmethod
    def get_by_transaction_id(transaction_id: str) -> Optional[Dict]:
        """根据交易ID获取订单"""
        return db_manager.execute_one('SELECT * FROM orders WHERE transaction_id = ?', (transaction_id,))
    
    @staticmethod
    def update_status(order_id: str, status: str):
        """更新订单状态"""
        db_manager.execute('UPDATE orders SET status = ?, updated_at = ? WHERE order_id = ?',
                          (status, datetime.now().isoformat(), order_id))
    
    @staticmethod
    def create_order(username: str, plan_id: str, amount: int, payment_method: str) -> Optional[str]:
        """创建支付订单"""
        import uuid

        order_id = f"ORD{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:6]}"
        order_data = {
            'order_id': order_id,
            'username': username,
            'plan_id': plan_id,
            'amount': amount,
            'payment_method': payment_method,
            'payment_status': 'pending',
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        try:
            db_manager.insert('orders', order_data)
            return order_id
        except Exception:
            return None
    
    @staticmethod
    def get_order(order_id: str) -> Optional[Dict]:
        """根据订单ID获取订单"""
        return db_manager.execute_one('SELECT * FROM orders WHERE order_id = ?', (order_id,))
    
    @staticmethod
    def get_user_orders(username: str) -> List[Dict]:
        """获取用户订单列表"""
        return db_manager.execute('SELECT * FROM orders WHERE username = ? ORDER BY created_at DESC', (username,))


class AlertRepository:
    """告警规则仓库"""
    
    @staticmethod
    def get_all() -> List[Dict]:
        """获取所有告警规则"""
        return db_manager.execute('SELECT * FROM alert_rules ORDER BY created_at DESC')
    
    @staticmethod
    def get_by_id(rule_id: int) -> Optional[Dict]:
        """根据ID获取规则"""
        return db_manager.execute_one('SELECT * FROM alert_rules WHERE id = ?', (rule_id,))
    
    @staticmethod
    def create(rule_data: Dict) -> int:
        """创建告警规则"""
        rule_data['created_at'] = datetime.now().isoformat()
        rule_data['updated_at'] = datetime.now().isoformat()
        return db_manager.insert('alert_rules', rule_data)
    
    @staticmethod
    def update(rule_id: int, rule_data: Dict):
        """更新告警规则"""
        rule_data['updated_at'] = datetime.now().isoformat()
        updates = [f"{k} = ?" for k in rule_data.keys()]
        params = list(rule_data.values()) + [rule_id]
        query = f"UPDATE alert_rules SET {', '.join(updates)} WHERE id = ?"
        db_manager.execute(query, tuple(params))
    
    @staticmethod
    def delete(rule_id: int):
        """删除告警规则"""
        db_manager.execute('DELETE FROM alert_rules WHERE id = ?', (rule_id,))
    
    @staticmethod
    def get_by_username(username: str) -> List[Dict]:
        """根据用户名获取告警规则"""
        return db_manager.execute('SELECT * FROM alert_rules WHERE username = ? ORDER BY created_at DESC', (username,))


class DashboardConfigRepository:
    """仪表盘配置仓库"""
    
    @staticmethod
    def get_by_username(username: str) -> List[Dict]:
        """根据用户名获取仪表盘配置"""
        return db_manager.execute('SELECT * FROM dashboard_configs WHERE username = ? ORDER BY created_at DESC',
                                  (username,))
    
    @staticmethod
    def create(config_data: Dict) -> int:
        """创建仪表盘配置"""
        config_data['created_at'] = datetime.now().isoformat()
        config_data['updated_at'] = datetime.now().isoformat()
        return db_manager.insert('dashboard_configs', config_data)
    
    @staticmethod
    def update(config_id: int, config_data: Dict):
        """更新仪表盘配置"""
        config_data['updated_at'] = datetime.now().isoformat()
        updates = [f"{k} = ?" for k in config_data.keys()]
        params = list(config_data.values()) + [config_id]
        query = f"UPDATE dashboard_configs SET {', '.join(updates)} WHERE id = ?"
        db_manager.execute(query, tuple(params))
    
    @staticmethod
    def delete(config_id: int):
        """删除仪表盘配置"""
        db_manager.execute('DELETE FROM dashboard_configs WHERE id = ?', (config_id,))


class SharedReportRepository:
    """共享分析报告仓库（与 dashboard_shares 仪表盘分享分离）"""

    @staticmethod
    def create_share(
        username: str,
        report_type: str,
        report_data,
        expires_at: Optional[str] = None,
    ) -> str:
        import json
        import uuid

        share_token = uuid.uuid4().hex
        payload = {
            "share_token": share_token,
            "username": username,
            "report_type": report_type,
            "report_data": json.dumps(report_data, ensure_ascii=False)
            if not isinstance(report_data, str)
            else report_data,
            "expires_at": expires_at,
            "created_at": datetime.now().isoformat(),
        }
        db_manager.insert("shared_reports", payload)
        return share_token

    @staticmethod
    def create(share_data: Dict) -> int:
        """创建仪表盘共享（兼容 team_management）"""
        share_data["created_at"] = datetime.now().isoformat()
        return db_manager.insert("dashboard_shares", share_data)

    @staticmethod
    def get_by_token(token: str) -> Optional[Dict]:
        row = db_manager.execute_one(
            "SELECT * FROM shared_reports WHERE share_token = ?", (token,)
        )
        if not row:
            return None
        expires_at = row.get("expires_at")
        if expires_at:
            try:
                if datetime.fromisoformat(expires_at) < datetime.now():
                    return None
            except ValueError:
                pass
        return row

    @staticmethod
    def get_user_reports(username: str) -> List[Dict]:
        return db_manager.execute(
            """
            SELECT id, share_token, username, report_type, report_data,
                   expires_at, created_at
            FROM shared_reports
            WHERE username = ?
            ORDER BY created_at DESC
            """,
            (username,),
        )

    @staticmethod
    def delete(share_id: int):
        """删除共享"""
        db_manager.execute("DELETE FROM dashboard_shares WHERE id = ?", (share_id,))
        db_manager.execute("DELETE FROM shared_reports WHERE id = ?", (share_id,))


class ImportedDataRepository:
    """导入数据仓库"""
    
    @staticmethod
    def get_comments(username: str) -> Optional[List[Dict]]:
        """获取用户评论数据"""
        result = db_manager.execute('SELECT * FROM imported_comments WHERE username = ? ORDER BY created_at DESC', (username,))
        return result if result else None
    
    @staticmethod
    def get_metrics(username: str) -> Optional[List[Dict]]:
        """获取用户指标数据"""
        result = db_manager.execute('SELECT * FROM imported_metrics WHERE username = ? ORDER BY created_at DESC', (username,))
        return result if result else None
    
    @staticmethod
    def replace_for_user(username: str, metrics: List[Dict] = None, comments: List[Dict] = None) -> Dict[str, int]:
        """替换用户的导入数据"""
        counts = {"metrics": 0, "comments": 0}
        
        if metrics:
            db_manager.execute('DELETE FROM imported_metrics WHERE username = ?', (username,))
            for record in metrics:
                record['username'] = username
                record['created_at'] = datetime.now().isoformat()
                db_manager.insert('imported_metrics', record)
            counts["metrics"] = len(metrics)
        
        if comments:
            db_manager.execute('DELETE FROM imported_comments WHERE username = ?', (username,))
            for record in comments:
                record['username'] = username
                record['created_at'] = datetime.now().isoformat()
                db_manager.insert('imported_comments', record)
            counts["comments"] = len(comments)
        
        return counts
    
    @staticmethod
    def get_cached_metrics(product: str = None, platform: str = None, max_age_hours: int = 24) -> Optional[List[Dict]]:
        """获取缓存的指标数据"""
        from datetime import timedelta
        cutoff_time = (datetime.now() - timedelta(hours=max_age_hours)).isoformat()
        
        query = 'SELECT * FROM cached_metrics WHERE cached_at >= ?'
        params = [cutoff_time]
        
        if product:
            query += ' AND product = ?'
            params.append(product)
        if platform:
            query += ' AND platform = ?'
            params.append(platform)
        
        query += ' ORDER BY date DESC'
        result = db_manager.execute(query, tuple(params))
        return result if result else None
    
    @staticmethod
    def get_cached_comments(product: str = None, platform: str = None, max_age_hours: int = 24) -> Optional[List[Dict]]:
        """获取缓存的评论数据"""
        from datetime import timedelta
        cutoff_time = (datetime.now() - timedelta(hours=max_age_hours)).isoformat()
        
        query = 'SELECT * FROM cached_comments WHERE cached_at >= ?'
        params = [cutoff_time]
        
        if product:
            query += ' AND product = ?'
            params.append(product)
        if platform:
            query += ' AND platform = ?'
            params.append(platform)
        
        query += ' ORDER BY date DESC'
        result = db_manager.execute(query, tuple(params))
        return result if result else None
    
    @staticmethod
    def save_cached_metrics(metrics: List[Dict]) -> int:
        """保存缓存的指标数据（使用 INSERT OR REPLACE）"""
        count = 0
        cached_at = datetime.now().isoformat()
        
        for record in metrics:
            record['cached_at'] = cached_at
            try:
                db_manager.execute('''
                    INSERT OR REPLACE INTO cached_metrics 
                    (product, platform, channel, cycle, metric, 值, date, installs, revenue, active_users, sessions, avg_session_duration, retention_1d, retention_7d, retention_30d, cached_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    record.get('product'),
                    record.get('platform'),
                    record.get('channel'),
                    record.get('cycle'),
                    record.get('metric'),
                    record.get('值'),
                    record.get('date'),
                    record.get('installs', 0),
                    record.get('revenue', 0.0),
                    record.get('active_users', 0),
                    record.get('sessions', 0),
                    record.get('avg_session_duration', 0.0),
                    record.get('retention_1d', 0.0),
                    record.get('retention_7d', 0.0),
                    record.get('retention_30d', 0.0),
                    cached_at
                ))
                count += 1
            except Exception:
                continue
        
        return count
    
    @staticmethod
    def save_cached_comments(comments: List[Dict]) -> int:
        """保存缓存的评论数据（使用 INSERT OR REPLACE）"""
        count = 0
        cached_at = datetime.now().isoformat()
        
        for record in comments:
            record['cached_at'] = cached_at
            try:
                db_manager.execute('''
                    INSERT OR REPLACE INTO cached_comments 
                    (product, platform, review_id, rating, title, content, 内容, author, date, 日期, 用户角色, 情绪, helpful_count, sentiment, cached_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    record.get('product'),
                    record.get('platform'),
                    record.get('review_id'),
                    record.get('rating'),
                    record.get('title'),
                    record.get('content'),
                    record.get('内容'),
                    record.get('author'),
                    record.get('date'),
                    record.get('日期'),
                    record.get('用户角色'),
                    record.get('情绪'),
                    record.get('helpful_count', 0),
                    record.get('sentiment', 0.0),
                    cached_at
                ))
                count += 1
            except Exception:
                continue
        
        return count
    
    @staticmethod
    def clear_old_cache(max_age_hours: int = 168) -> int:
        """清理过期的缓存数据（默认168小时=7天）"""
        from datetime import timedelta
        cutoff_time = (datetime.now() - timedelta(hours=max_age_hours)).isoformat()
        
        db_manager.execute('DELETE FROM cached_metrics WHERE cached_at < ?', (cutoff_time,))
        db_manager.execute('DELETE FROM cached_comments WHERE cached_at < ?', (cutoff_time,))
        
        return 1


# 初始化数据库表
init_database()
