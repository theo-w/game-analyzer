"""Database dialect helpers (no live Postgres required)."""

from __future__ import annotations

import os

import pytest


def test_parse_database_url():
    from src.db_dialect import parse_database_url

    cfg = parse_database_url("postgresql://user:pass@db.example.com:5433/mydb")
    assert cfg["host"] == "db.example.com"
    assert cfg["port"] == 5433
    assert cfg["database"] == "mydb"
    assert cfg["username"] == "user"
    assert cfg["password"] == "pass"


def test_adapt_sql_placeholders():
    from src.db_dialect import adapt_sql

    sql = "SELECT * FROM users WHERE username = ? AND role = ?"
    assert adapt_sql(sql, "sqlite") == sql
    assert adapt_sql(sql, "postgresql") == (
        "SELECT * FROM users WHERE username = %s AND role = %s"
    )


def test_adapt_sql_ignores_question_marks_in_strings():
    from src.db_dialect import adapt_sql

    sql = "SELECT 'a?b' AS x WHERE id = ?"
    assert adapt_sql(sql, "postgresql") == "SELECT 'a?b' AS x WHERE id = %s"


def test_resolve_database_backend_prefers_url(monkeypatch):
    from src.db_dialect import resolve_database_backend
    from src.database import ConfigManager

    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://game:secret@localhost:5432/game_analyzer",
    )
    db_type, cfg = resolve_database_backend(ConfigManager())
    assert db_type == "postgresql"
    assert cfg["database"] == "game_analyzer"


def test_postgres_schema_statement_count():
    from src.db_schema_postgres import POSTGRES_SCHEMA_STATEMENTS

    assert len(POSTGRES_SCHEMA_STATEMENTS) >= 30
    assert any("CREATE TABLE IF NOT EXISTS users" in s for s in POSTGRES_SCHEMA_STATEMENTS)


def test_health_reports_database_type():
    from fastapi.testclient import TestClient
    from src.web_app import app

    client = TestClient(app)
    res = client.get("/api/health")
    body = res.json()
    assert body["database_type"] in ("sqlite", "postgresql", "mysql")
