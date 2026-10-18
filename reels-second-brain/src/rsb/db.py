"""PostgreSQL 연결과 마이그레이션."""

from __future__ import annotations

from pathlib import Path

import psycopg
from psycopg.rows import dict_row

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def connect(database_url: str) -> psycopg.Connection:
    return psycopg.connect(database_url, row_factory=dict_row)


def migrate(conn: psycopg.Connection) -> list[str]:
    """migrations/*.sql을 이름 순으로 한 번씩 적용한다."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ DEFAULT now())"
    )
    applied = {r["name"] for r in conn.execute("SELECT name FROM schema_migrations")}
    done = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if path.name in applied:
            continue
        with conn.transaction():
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (path.name,))
        done.append(path.name)
    conn.commit()
    return done
