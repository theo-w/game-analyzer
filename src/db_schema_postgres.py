"""PostgreSQL schema (idempotent). Keep in sync with init_database() in database.py."""

POSTGRES_SCHEMA_STATEMENTS = [
    """
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
    """,
    """
    CREATE TABLE IF NOT EXISTS llm_config (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        provider TEXT DEFAULT 'openai',
        model TEXT DEFAULT 'gpt-4o-mini',
        api_key TEXT,
        endpoint TEXT,
        temperature DOUBLE PRECISION DEFAULT 0.7,
        max_tokens INTEGER DEFAULT 2000,
        updated_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS operation_logs (
        id SERIAL PRIMARY KEY,
        username TEXT NOT NULL,
        action TEXT NOT NULL,
        target TEXT,
        detail TEXT,
        created_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dashboard_configs (
        id SERIAL PRIMARY KEY,
        username TEXT,
        name TEXT,
        layout TEXT,
        filters TEXT,
        created_at TEXT,
        updated_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS alert_rules (
        id SERIAL PRIMARY KEY,
        username TEXT,
        name TEXT NOT NULL,
        product TEXT,
        metric TEXT NOT NULL,
        operator TEXT NOT NULL,
        threshold DOUBLE PRECISION NOT NULL,
        email TEXT,
        webhook_url TEXT,
        enabled INTEGER DEFAULT 1,
        last_triggered TEXT,
        created_at TEXT,
        updated_at TEXT
    )
    """,
    # 存量库补列：早期建表缺 username，导致 /api/alerts 查询报列不存在
    "ALTER TABLE alert_rules ADD COLUMN IF NOT EXISTS username TEXT",
    """
    CREATE TABLE IF NOT EXISTS teams (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        owner_id TEXT NOT NULL,
        created_at TEXT,
        updated_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS team_members (
        id SERIAL PRIMARY KEY,
        team_id INTEGER NOT NULL,
        username TEXT NOT NULL,
        role TEXT DEFAULT 'viewer',
        joined_at TEXT,
        updated_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dashboard_shares (
        id SERIAL PRIMARY KEY,
        dashboard_id INTEGER NOT NULL,
        share_token TEXT UNIQUE NOT NULL,
        shared_by TEXT NOT NULL,
        permissions TEXT DEFAULT 'view',
        expires_at TEXT,
        created_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS shared_reports (
        id SERIAL PRIMARY KEY,
        share_token TEXT UNIQUE NOT NULL,
        username TEXT NOT NULL,
        report_type TEXT NOT NULL,
        report_data TEXT NOT NULL,
        expires_at TEXT,
        created_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS orders (
        id SERIAL PRIMARY KEY,
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
        updated_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS products (
        id SERIAL PRIMARY KEY,
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
    """,
    """
    CREATE TABLE IF NOT EXISTS data_source_configs (
        id SERIAL PRIMARY KEY,
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
    """,
    """
    CREATE TABLE IF NOT EXISTS imported_metrics (
        id SERIAL PRIMARY KEY,
        username TEXT NOT NULL,
        product TEXT,
        channel TEXT,
        cycle TEXT,
        metric TEXT,
        "值" DOUBLE PRECISION,
        date TEXT,
        platform TEXT,
        installs INTEGER DEFAULT 0,
        revenue DOUBLE PRECISION DEFAULT 0,
        active_users INTEGER DEFAULT 0,
        sessions INTEGER DEFAULT 0,
        avg_session_duration DOUBLE PRECISION DEFAULT 0,
        retention_1d DOUBLE PRECISION DEFAULT 0,
        retention_7d DOUBLE PRECISION DEFAULT 0,
        retention_30d DOUBLE PRECISION DEFAULT 0,
        created_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS imported_comments (
        id SERIAL PRIMARY KEY,
        username TEXT NOT NULL,
        product TEXT,
        platform TEXT,
        review_id TEXT,
        rating INTEGER,
        title TEXT,
        content TEXT,
        "内容" TEXT,
        author TEXT,
        date TEXT,
        "日期" TEXT,
        "用户角色" TEXT,
        "情绪" TEXT,
        helpful_count INTEGER DEFAULT 0,
        sentiment DOUBLE PRECISION DEFAULT 0,
        created_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS cached_metrics (
        id SERIAL PRIMARY KEY,
        product TEXT NOT NULL,
        platform TEXT NOT NULL,
        channel TEXT,
        cycle TEXT,
        metric TEXT,
        "值" DOUBLE PRECISION,
        date TEXT,
        installs INTEGER DEFAULT 0,
        revenue DOUBLE PRECISION DEFAULT 0,
        active_users INTEGER DEFAULT 0,
        sessions INTEGER DEFAULT 0,
        avg_session_duration DOUBLE PRECISION DEFAULT 0,
        retention_1d DOUBLE PRECISION DEFAULT 0,
        retention_7d DOUBLE PRECISION DEFAULT 0,
        retention_30d DOUBLE PRECISION DEFAULT 0,
        cached_at TEXT NOT NULL,
        UNIQUE(product, platform, date, metric)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS cached_comments (
        id SERIAL PRIMARY KEY,
        product TEXT NOT NULL,
        platform TEXT NOT NULL,
        review_id TEXT,
        rating INTEGER,
        title TEXT,
        content TEXT,
        "内容" TEXT,
        author TEXT,
        date TEXT,
        "日期" TEXT,
        "用户角色" TEXT,
        "情绪" TEXT,
        helpful_count INTEGER DEFAULT 0,
        sentiment DOUBLE PRECISION DEFAULT 0,
        cached_at TEXT NOT NULL,
        UNIQUE(product, platform, review_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS consent_logs (
        id SERIAL PRIMARY KEY,
        username TEXT NOT NULL,
        consent_type TEXT NOT NULL,
        consented_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS reminder_logs (
        id SERIAL PRIMARY KEY,
        subscription_id TEXT NOT NULL,
        days_remaining INTEGER NOT NULL,
        sent_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS health_logs (
        id SERIAL PRIMARY KEY,
        status TEXT NOT NULL,
        metrics TEXT,
        recorded_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS error_logs (
        id SERIAL PRIMARY KEY,
        level TEXT NOT NULL,
        message TEXT NOT NULL,
        module TEXT,
        traceback TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_events (
        id SERIAL PRIMARY KEY,
        username TEXT NOT NULL,
        event_type TEXT NOT NULL,
        details TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS support_tickets (
        id SERIAL PRIMARY KEY,
        ticket_id TEXT UNIQUE NOT NULL,
        username TEXT NOT NULL,
        subject TEXT NOT NULL,
        message TEXT NOT NULL,
        priority TEXT DEFAULT 'medium',
        status TEXT DEFAULT 'open',
        agent_id TEXT,
        chat_id TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ticket_replies (
        id SERIAL PRIMARY KEY,
        ticket_id TEXT NOT NULL,
        username TEXT NOT NULL,
        message TEXT NOT NULL,
        is_agent INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS live_chats (
        id SERIAL PRIMARY KEY,
        chat_id TEXT UNIQUE NOT NULL,
        username TEXT NOT NULL,
        status TEXT DEFAULT 'active',
        ticket_id TEXT,
        assigned_agent TEXT,
        updated_at TEXT,
        last_agent_reply TEXT,
        created_at TEXT NOT NULL,
        ended_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS chat_messages (
        id SERIAL PRIMARY KEY,
        chat_id TEXT NOT NULL,
        username TEXT NOT NULL,
        message TEXT NOT NULL,
        is_system INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS registration_events (
        id SERIAL PRIMARY KEY,
        username TEXT NOT NULL,
        email TEXT NOT NULL,
        ip_address TEXT NOT NULL,
        device_id TEXT,
        trial_granted INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS login_events (
        id SERIAL PRIMARY KEY,
        username TEXT NOT NULL,
        ip_address TEXT NOT NULL,
        device_id TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS device_accounts (
        device_id TEXT NOT NULL,
        username TEXT NOT NULL,
        first_seen_at TEXT NOT NULL,
        last_seen_at TEXT NOT NULL,
        PRIMARY KEY (device_id, username)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS device_trial_claims (
        device_id TEXT PRIMARY KEY,
        username TEXT NOT NULL,
        claimed_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS password_reset_tokens (
        id SERIAL PRIMARY KEY,
        username TEXT NOT NULL,
        token_hash TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        used_at TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_password_reset_hash ON password_reset_tokens(token_hash)
    """,
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
    """,
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
        level_design TEXT DEFAULT '',
        auto_generated INTEGER DEFAULT 0,
        updated_at TEXT
    )
    """,
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
        category TEXT DEFAULT '',
        tags TEXT DEFAULT '[]',
        body_markdown TEXT DEFAULT '',
        updated_at TEXT,
        parent_archive_id TEXT DEFAULT '',
        created_at TEXT
    )
    """,
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
    """,
    """
    CREATE TABLE IF NOT EXISTS competitor_dimension_scores (
        username TEXT NOT NULL,
        game_id TEXT NOT NULL,
        scores_json TEXT NOT NULL DEFAULT '{}',
        updated_at TEXT,
        PRIMARY KEY (username, game_id)
    )
    """,
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
    """,
    "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)",
    "CREATE INDEX IF NOT EXISTS idx_team_members_team ON team_members(team_id)",
    "CREATE INDEX IF NOT EXISTS idx_team_members_user ON team_members(username)",
    "CREATE INDEX IF NOT EXISTS idx_alert_rules_enabled ON alert_rules(enabled)",
    "CREATE INDEX IF NOT EXISTS idx_orders_order_id ON orders(order_id)",
    "CREATE INDEX IF NOT EXISTS idx_orders_username ON orders(username)",
    "CREATE INDEX IF NOT EXISTS idx_products_product_id ON products(product_id)",
    "CREATE INDEX IF NOT EXISTS idx_data_source_configs_platform ON data_source_configs(platform)",
    "CREATE INDEX IF NOT EXISTS idx_cached_metrics_product ON cached_metrics(product)",
    "CREATE INDEX IF NOT EXISTS idx_cached_metrics_platform ON cached_metrics(platform)",
    "CREATE INDEX IF NOT EXISTS idx_cached_metrics_date ON cached_metrics(date)",
    "CREATE INDEX IF NOT EXISTS idx_cached_comments_product ON cached_comments(product)",
    "CREATE INDEX IF NOT EXISTS idx_cached_comments_platform ON cached_comments(platform)",
    "CREATE INDEX IF NOT EXISTS idx_registration_events_ip ON registration_events(ip_address, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_registration_events_device ON registration_events(device_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_login_events_ip ON login_events(ip_address, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_game_library_genre ON game_library(genre)",
    "CREATE INDEX IF NOT EXISTS idx_analysis_archives_user ON analysis_archives(username, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_hotspot_custom_user ON hotspot_custom_topics(username, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_game_version_game ON game_version_history(game_id, released_at)",
]
