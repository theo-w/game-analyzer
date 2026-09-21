"""Database dialect resolution (SQLite default, PostgreSQL via DATABASE_URL)."""

from __future__ import annotations

import os
from typing import Any, Optional, Tuple
from urllib.parse import urlparse, unquote


def _truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def parse_database_url(url: str) -> Optional[dict]:
    """Parse postgres:// or postgresql:// URL into connection kwargs."""
    raw = (url or "").strip()
    if not raw:
        return None
    if raw.startswith("postgres://"):
        raw = "postgresql://" + raw[len("postgres://") :]
    if not raw.startswith("postgresql://"):
        return None
    parsed = urlparse(raw)
    dbname = (parsed.path or "/").lstrip("/") or "game_analyzer"
    return {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
        "database": dbname,
        "username": unquote(parsed.username or "postgres"),
        "password": unquote(parsed.password or ""),
    }


def resolve_database_backend(config_manager) -> Tuple[str, dict]:
    """
    Returns (db_type, db_config).
    DATABASE_URL wins over config.json when set.
    """
    url = os.getenv("DATABASE_URL", "").strip()
    forced = os.getenv("DATABASE_TYPE", "").strip().lower()

    if url:
        pg = parse_database_url(url)
        if pg:
            return "postgresql", {**config_manager.get_database_config(), **pg, "url": url}

    db_config = dict(config_manager.get_database_config())
    db_type = forced or db_config.get("type", "sqlite")
    if db_type not in ("sqlite", "postgresql", "mysql"):
        db_type = "sqlite"
    return db_type, db_config


def adapt_sql(sql: str, db_type: str) -> str:
    """SQLite ? placeholders → PostgreSQL %s."""
    if db_type != "postgresql":
        return sql
    out = []
    in_single = False
    in_double = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        if ch == "'" and not in_double:
            in_single = not in_single
            out.append(ch)
        elif ch == '"' and not in_single:
            in_double = not in_double
            out.append(ch)
        elif ch == "?" and not in_single and not in_double:
            out.append("%s")
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def serial_primary_key(db_type: str) -> str:
    if db_type == "postgresql":
        return "SERIAL PRIMARY KEY"
    return "INTEGER PRIMARY KEY AUTOINCREMENT"


class CompatCursor:
    """Cursor wrapper: unified ? placeholders and row access."""

    def __init__(self, cursor: Any, db_type: str):
        self._cursor = cursor
        self._db_type = db_type

    def execute(self, sql: str, params: Optional[tuple] = None):
        sql = adapt_sql(sql, self._db_type)
        if params is None:
            return self._cursor.execute(sql)
        return self._cursor.execute(sql, params)

    def executemany(self, sql: str, params_list):
        return self._cursor.executemany(adapt_sql(sql, self._db_type), params_list)

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    @property
    def description(self):
        return self._cursor.description

    @property
    def lastrowid(self):
        return self._cursor.lastrowid

    def __getattr__(self, name: str):
        return getattr(self._cursor, name)


class CompatConnection:
    """Wrap DB-API connection for dialect-aware cursors."""

    def __init__(self, conn: Any, db_type: str):
        self._conn = conn
        self._db_type = db_type

    def cursor(self) -> CompatCursor:
        return CompatCursor(self._conn.cursor(), self._db_type)

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return self._conn.close()

    def __enter__(self):
        if hasattr(self._conn, "__enter__"):
            self._conn.__enter__()
        return self

    def __exit__(self, *args):
        if hasattr(self._conn, "__exit__"):
            return self._conn.__exit__(*args)
        return False


def connect_postgresql(db_config: dict) -> Any:
    import psycopg2

    url = db_config.get("url") or os.getenv("DATABASE_URL", "").strip()
    if url:
        return psycopg2.connect(url)
    return psycopg2.connect(
        host=db_config.get("host", "localhost"),
        port=int(db_config.get("port", 5432)),
        dbname=db_config.get("database", "game_analyzer"),
        user=db_config.get("username", "postgres"),
        password=db_config.get("password", ""),
        connect_timeout=int(db_config.get("connect_timeout", 30)),
    )


def postgres_schema_statements() -> list:
    """DDL for PostgreSQL (idempotent). Loaded by init_database."""
    from src.db_schema_postgres import POSTGRES_SCHEMA_STATEMENTS

    return POSTGRES_SCHEMA_STATEMENTS
