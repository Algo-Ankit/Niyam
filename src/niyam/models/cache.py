"""Local response cache: every model response is stored once and replayed on identical input.

The key is a SHA-256 over (provider, model id, cache version, canonical JSON of the input),
so any change to a prompt, question or passage misses the cache, and bumping the cache
version invalidates old entries deliberately. This is our own cache; no provider-side
context caching is used.
"""

import hashlib
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

JsonValue = Any  # anything json.dumps accepts


def cache_key(provider: str, model_id: str, version: str, payload: JsonValue) -> str:
    canonical = json.dumps(
        {"provider": provider, "model": model_id, "version": version, "input": payload},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ResponseCache:
    """A thread-safe key/value store of JSON responses in a single SQLite file."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS responses ("
            " key TEXT PRIMARY KEY,"
            " value TEXT NOT NULL,"
            " created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )

    def get(self, key: str) -> JsonValue | None:
        with self._lock:
            row = self._conn.execute("SELECT value FROM responses WHERE key = ?", (key,)).fetchone()
        return None if row is None else json.loads(row[0])

    def put(self, key: str, value: JsonValue) -> None:
        encoded = json.dumps(value, ensure_ascii=False)
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO responses (key, value) VALUES (?, ?)", (key, encoded)
            )

    def close(self) -> None:
        with self._lock:
            self._conn.close()
