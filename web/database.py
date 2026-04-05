"""SQLite database initialization and helpers."""

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

from . import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    encrypted_credentials BLOB NOT NULL,
    administrations TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_active TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    admin_id TEXT NOT NULL,
    admin_name TEXT NOT NULL,
    job_type TEXT NOT NULL DEFAULT 'data',
    status TEXT NOT NULL DEFAULT 'pending',
    endpoints TEXT NOT NULL DEFAULT '[]',
    completed_steps TEXT NOT NULL DEFAULT '[]',
    current_step TEXT,
    items_exported INTEGER NOT NULL DEFAULT 0,
    items_total INTEGER,
    error_message TEXT,
    error_traceback TEXT,
    data_dir TEXT,
    years TEXT NOT NULL DEFAULT '[]',
    encrypted_credentials BLOB NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    started_at TEXT,
    completed_at TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_jobs_session ON jobs(session_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);

CREATE TABLE IF NOT EXISTS job_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    step_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    items_count INTEGER DEFAULT 0,
    items_total INTEGER,
    started_at TEXT,
    completed_at TEXT,
    error_message TEXT,
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);

CREATE INDEX IF NOT EXISTS idx_steps_job ON job_steps(job_id);
"""


def init_db():
    """Create database and tables if they don't exist."""
    db_path = config.DATABASE_PATH
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    with get_db() as db:
        db.executescript(_SCHEMA)


@contextmanager
def get_db():
    """Context manager that yields a SQLite connection with row_factory."""
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """Convert a sqlite3.Row to a plain dict, parsing JSON fields."""
    d = dict(row)
    for key in ("endpoints", "completed_steps", "administrations", "years"):
        if key in d and isinstance(d[key], str):
            try:
                d[key] = json.loads(d[key])
            except (json.JSONDecodeError, TypeError):
                pass
    # Remove encrypted credentials from API responses
    d.pop("encrypted_credentials", None)
    return d
