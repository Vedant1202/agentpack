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
import sys
from pathlib import Path
from typing import Any, Optional

_CREATE_TABLE_SQL = (
    "CREATE TABLE IF NOT EXISTS cache_entries "
    "(key TEXT PRIMARY KEY, value BLOB, created_at TEXT DEFAULT (datetime('now')))"
)

# Module-level flag: warn about a corrupt cache.db at most once per process, even if
# multiple cache_get/cache_set calls hit it before the caller stops retrying.
_warned_corrupt = False


def _connect(cache_dir: Path, create: bool = True) -> Optional[sqlite3.Connection]:
    """Connect to cache.db. When create=False (read paths), never create the cache.db
    file (or its parent directory) -- if it doesn't exist yet, return None (a clean miss)
    instead of side-effect-creating it for e.g. a typo'd pack path, or a cache dir that
    exists (created by other tooling) but has never been written to. If the db FILE
    already exists (read or write), a corrupt cache.db still self-heals as usual --
    deleting/recreating a file that's already there isn't the side effect read paths
    must avoid.
    """
    global _warned_corrupt
    db_path = cache_dir / "cache.db"
    if not create and not db_path.exists():
        return None
    if create:
        cache_dir.mkdir(parents=True, exist_ok=True)
    try:
        conn = sqlite3.connect(str(db_path))
        conn.execute(_CREATE_TABLE_SQL)
        conn.commit()
        return conn
    except sqlite3.DatabaseError:
        if not _warned_corrupt:
            print(
                f"[agentpack] Warning: corrupt cache database at {db_path}, rebuilding.",
                file=sys.stderr,
            )
            _warned_corrupt = True
        db_path.unlink(missing_ok=True)
        conn = sqlite3.connect(str(db_path))
        conn.execute(_CREATE_TABLE_SQL)
        conn.commit()
        return conn


def make_key(*parts: str) -> str:
    """Stable cache key from an arbitrary number of string parts."""
    combined = "|".join(parts)
    return hashlib.sha256(combined.encode()).hexdigest()


def cache_get(cache_dir: Path, key: str) -> Optional[Any]:
    """Return the cached value, or None on miss. Never creates the cache directory -- a
    query against a path that doesn't exist yet (e.g. a typo'd pack dir) is just a miss,
    not a side effect."""
    conn = None
    try:
        conn = _connect(cache_dir, create=False)
        if conn is None:
            return None
        row = conn.execute(
            "SELECT value FROM cache_entries WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        return pickle.loads(row[0])
    except Exception:
        return None
    finally:
        if conn is not None:
            conn.close()


def cache_set(cache_dir: Path, key: str, value: Any) -> None:
    """Store value under key (upsert). Creates the cache directory if needed."""
    conn = None
    try:
        blob = pickle.dumps(value)
        conn = _connect(cache_dir, create=True)
        conn.execute(
            "INSERT OR REPLACE INTO cache_entries (key, value) VALUES (?, ?)",
            (key, blob),
        )
        conn.commit()
    except Exception:
        pass  # cache writes must never crash the main pipeline
    finally:
        if conn is not None:
            conn.close()
