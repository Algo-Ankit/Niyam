"""Persistent record of every billable model call: tokens, USD cost, and daily request counts.

Daily counts follow the provider's quota day. Gemini API daily limits reset at midnight
Pacific time, so calls are bucketed by the Pacific calendar date.
"""

import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from niyam.models.types import Usage

QUOTA_TIMEZONE = ZoneInfo("America/Los_Angeles")


def quota_day(moment: datetime) -> date:
    return moment.astimezone(QUOTA_TIMEZONE).date()


@dataclass(frozen=True, slots=True)
class LedgerRow:
    quota_day: str
    provider: str
    model_id: str
    requests: int
    input_tokens: int
    output_tokens: int
    thought_tokens: int
    cost_usd: float


class CostLedger:
    def __init__(self, path: Path, clock: Callable[[], datetime] = lambda: datetime.now(UTC)):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS calls ("
            " at_utc TEXT NOT NULL,"
            " quota_day TEXT NOT NULL,"
            " provider TEXT NOT NULL,"
            " model_id TEXT NOT NULL,"
            " input_tokens INTEGER NOT NULL,"
            " output_tokens INTEGER NOT NULL,"
            " thought_tokens INTEGER NOT NULL,"
            " cost_usd REAL NOT NULL)"
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS calls_by_day ON calls (model_id, quota_day)")

    def record(self, provider: str, model_id: str, usage: Usage, cost_usd: float) -> None:
        now = self._clock()
        with self._lock:
            self._conn.execute(
                "INSERT INTO calls VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    now.isoformat(),
                    quota_day(now).isoformat(),
                    provider,
                    model_id,
                    usage.input_tokens,
                    usage.output_tokens,
                    usage.thought_tokens,
                    cost_usd,
                ),
            )

    def requests_today(self, model_id: str) -> int:
        today = quota_day(self._clock()).isoformat()
        with self._lock:
            (count,) = self._conn.execute(
                "SELECT COUNT(*) FROM calls WHERE model_id = ? AND quota_day = ?",
                (model_id, today),
            ).fetchone()
        return int(count)

    def spend_usd(self, provider: str) -> float:
        with self._lock:
            (total,) = self._conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) FROM calls WHERE provider = ?", (provider,)
            ).fetchone()
        return float(total)

    def summary(self) -> list[LedgerRow]:
        """Per day, per model totals, oldest first."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT quota_day, provider, model_id, COUNT(*), SUM(input_tokens),"
                " SUM(output_tokens), SUM(thought_tokens), SUM(cost_usd)"
                " FROM calls GROUP BY quota_day, provider, model_id"
                " ORDER BY quota_day, provider, model_id"
            ).fetchall()
        return [LedgerRow(*row) for row in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
