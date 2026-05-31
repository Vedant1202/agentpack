"""
Content-addressed cache backed by SQLite.

Keys carry version components so changing parser/chunker/model versions
automatically invalidates the relevant cache entries (no manual flush needed).

Schema (single table):
    cache_entries(key TEXT PK, value BLOB, created_at TEXT)
"""
import hashlib
import json
import pickle
import sqlite3
from pathlib import Path
from typing import Any, Optional


def _db_path(cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "cache.db"


def _connect(cache_dir: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path(cache_dir)))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS cache_entries "
        "(key TEXT PRIMARY KEY, value BLOB, created_at TEXT DEFAULT (datetime('now')))"
    )
    conn.commit()
    return conn


def make_key(*parts: str) -> str:
    """Stable cache key from an arbitrary number of string parts."""
    combined = "|".join(parts)
    return hashlib.sha256(combined.encode()).hexdigest()


def cache_get(cache_dir: Path, key: str) -> Optional[Any]:
    """Return the cached value, or None on miss."""
    try:
        conn = _connect(cache_dir)
        row = conn.execute(
            "SELECT value FROM cache_entries WHERE key = ?", (key,)
        ).fetchone()
        conn.close()
        if row is None:
            return None
        return pickle.loads(row[0])
    except Exception:
        return None


def cache_set(cache_dir: Path, key: str, value: Any) -> None:
    """Store value under key (upsert)."""
    try:
        blob = pickle.dumps(value)
        conn = _connect(cache_dir)
        conn.execute(
            "INSERT OR REPLACE INTO cache_entries (key, value) VALUES (?, ?)",
            (key, blob),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass  # cache writes must never crash the main pipeline
