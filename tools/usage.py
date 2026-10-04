"""Persistent request budget ledger for provider quotas."""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

_LOCK = threading.Lock()


def reserve_request(db_path: str, provider: str, limit: int,
                    database_url: str | None = None) -> tuple[bool, int]:
    """Atomically reserve one provider request in the current UTC calendar month."""
    period = datetime.now(timezone.utc).strftime("%Y-%m")
    if database_url:
        import psycopg
        with psycopg.connect(database_url, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute("CREATE TABLE IF NOT EXISTS request_usage (provider TEXT NOT NULL, period TEXT NOT NULL, calls INTEGER NOT NULL, PRIMARY KEY(provider, period))")
                cursor.execute("INSERT INTO request_usage(provider, period, calls) VALUES (%s, %s, 0) ON CONFLICT (provider, period) DO NOTHING", (provider, period))
                cursor.execute("UPDATE request_usage SET calls = calls + 1 WHERE provider = %s AND period = %s AND calls < %s RETURNING calls", (provider, period, limit))
                row = cursor.fetchone()
                if row:
                    return True, max(0, limit - int(row[0]))
                cursor.execute("SELECT calls FROM request_usage WHERE provider = %s AND period = %s", (provider, period))
                used = int(cursor.fetchone()[0])
                return False, max(0, limit - used)
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with _LOCK, sqlite3.connect(db_path, timeout=10) as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS request_usage (provider TEXT NOT NULL, period TEXT NOT NULL, calls INTEGER NOT NULL, PRIMARY KEY(provider, period))")
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT calls FROM request_usage WHERE provider=? AND period=?", (provider, period)).fetchone()
        used = int(row[0]) if row else 0
        if used >= limit:
            connection.commit()
            return False, max(0, limit - used)
        connection.execute("INSERT INTO request_usage(provider, period, calls) VALUES(?,?,1) ON CONFLICT(provider,period) DO UPDATE SET calls=calls+1", (provider, period))
        connection.commit()
        return True, max(0, limit - used - 1)


def request_usage(db_path: str, provider: str, database_url: str | None = None) -> int:
    """Return requests used this month by one provider."""
    period = datetime.now(timezone.utc).strftime("%Y-%m")
    if database_url:
        import psycopg
        with psycopg.connect(database_url, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute("CREATE TABLE IF NOT EXISTS request_usage (provider TEXT NOT NULL, period TEXT NOT NULL, calls INTEGER NOT NULL, PRIMARY KEY(provider, period))")
                cursor.execute("SELECT calls FROM request_usage WHERE provider = %s AND period = %s", (provider, period))
                row = cursor.fetchone()
                return int(row[0]) if row else 0
    if db_path != ":memory:" and not Path(db_path).exists():
        return 0
    with _LOCK, sqlite3.connect(db_path, timeout=10) as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS request_usage (provider TEXT NOT NULL, period TEXT NOT NULL, calls INTEGER NOT NULL, PRIMARY KEY(provider, period))")
        row = connection.execute("SELECT calls FROM request_usage WHERE provider=? AND period=?", (provider, period)).fetchone()
        return int(row[0]) if row else 0


def request_budget(db_path: str, provider: str, limit: int,
                   database_url: str | None = None) -> dict[str, int]:
    """Return the current month counter without reserving/consuming a call."""
    used = request_usage(db_path, provider, database_url)
    return {"used": used, "limit": limit, "remaining": max(limit - used, 0)}
