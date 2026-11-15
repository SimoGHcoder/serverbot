"""Small SQLite audit/state store; never stores credentials or full log payloads."""
from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from functools import lru_cache

_DEFAULT_DB_PATH = "/opt/server-bot/logs/bot.db"


def _db_path() -> str:
    return os.getenv("SERVER_BOT_DB_PATH", os.getenv("DB_PATH", _DEFAULT_DB_PATH))


def _connect() -> sqlite3.Connection:
    path = _db_path()
    _ensure_dir(path)
    conn = sqlite3.connect(path, timeout=5)
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


@lru_cache(maxsize=1)
def _ensure_dir(path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)


def init_db() -> None:
    with closing(_connect()) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS container_states (
            name TEXT PRIMARY KEY, status TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_id INTEGER NOT NULL, action TEXT NOT NULL,
            target TEXT NOT NULL DEFAULT '', result TEXT NOT NULL,
            timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS omniroute_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL, message TEXT NOT NULL,
            timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS metrics_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            uptime_sec REAL NOT NULL DEFAULT 0,
            mem_used_pct REAL NOT NULL DEFAULT 0,
            root_disk_pct REAL NOT NULL DEFAULT 0,
            storage_disk_pct REAL NOT NULL DEFAULT 0,
            load_1m REAL NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON metrics_history(timestamp);
        """)
        # Migrate the original audit_logs schema without removing its history.
        columns = {row[1] for row in conn.execute("PRAGMA table_info(audit_logs)")}
        for column, declaration in (
            ("actor_id", "INTEGER NOT NULL DEFAULT 0"),
            ("target", "TEXT NOT NULL DEFAULT ''"),
            ("result", "TEXT NOT NULL DEFAULT 'legacy'"),
        ):
            if column not in columns:
                conn.execute(f"ALTER TABLE audit_logs ADD COLUMN {column} {declaration}")
        conn.commit()


def get_container_states() -> dict[str, str]:
    with closing(_connect()) as conn:
        return dict(conn.execute("SELECT name, status FROM container_states"))


def save_container_states(states: dict[str, str]) -> None:
    with closing(_connect()) as conn:
        conn.executemany(
            "INSERT INTO container_states(name,status,updated_at) VALUES(?,?,CURRENT_TIMESTAMP) "
            "ON CONFLICT(name) DO UPDATE SET status=excluded.status,updated_at=CURRENT_TIMESTAMP",
            [(name[:255], status[:120]) for name, status in states.items()],
        )
        conn.commit()


def log_action(actor_id: int, action: str, target: str, result: str) -> None:
    with closing(_connect()) as conn:
        conn.execute(
            "INSERT INTO audit_logs(actor_id,action,target,result) VALUES(?,?,?,?)",
            (int(actor_id), action[:80], target[:255], result[:100]),
        )
        conn.commit()


def log_omniroute_event(event_type: str, message: str) -> None:
    with closing(_connect()) as conn:
        conn.execute(
            "INSERT INTO omniroute_logs(event_type,message) VALUES(?,?)",
            (event_type[:120], message[:1000]),
        )
        conn.commit()


def save_metrics_sample(metrics: dict[str, float]) -> None:
    """Insert one metrics sample into metrics_history."""
    with closing(_connect()) as conn:
        conn.execute(
            "INSERT INTO metrics_history(uptime_sec,mem_used_pct,root_disk_pct,storage_disk_pct,load_1m) "
            "VALUES(?,?,?,?,?)",
            (
                metrics.get("uptime_sec", 0.0),
                metrics.get("mem_used_pct", 0.0),
                metrics.get("root_disk_pct", 0.0),
                metrics.get("storage_disk_pct", 0.0),
                metrics.get("load_1m", 0.0),
            ),
        )
        conn.commit()


def get_metrics_history(minutes: int = 60) -> list[dict[str, float]]:
    """Return metrics samples from the last N minutes, oldest first."""
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT uptime_sec, mem_used_pct, root_disk_pct, storage_disk_pct, load_1m "
            "FROM metrics_history WHERE timestamp >= datetime('now', ?) ORDER BY timestamp ASC",
            (f"-{minutes} minutes",),
        ).fetchall()
    return [
        {
            "uptime_sec": row[0],
            "mem_used_pct": row[1],
            "root_disk_pct": row[2],
            "storage_disk_pct": row[3],
            "load_1m": row[4],
        }
        for row in rows
    ]


def prune_metrics_history(days: int = 30) -> None:
    """Delete metrics samples older than N days."""
    with closing(_connect()) as conn:
        conn.execute("DELETE FROM metrics_history WHERE timestamp < datetime('now', ?)", (f"-{days} days",))
        conn.commit()
