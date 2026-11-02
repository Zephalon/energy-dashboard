from __future__ import annotations

import sqlite3
import time
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

from flask import current_app

SCHEMA = """
CREATE TABLE IF NOT EXISTS daily (
    day TEXT NOT NULL,
    source TEXT NOT NULL,
    metric TEXT NOT NULL,
    kwh REAL NOT NULL,
    PRIMARY KEY (day, source, metric)
);
CREATE TABLE IF NOT EXISTS sync_state (
    source TEXT PRIMARY KEY,
    last_attempt TEXT,
    last_success TEXT,
    last_error TEXT
);
CREATE TABLE IF NOT EXISTS login_failures (
    ip TEXT NOT NULL,
    ts REAL NOT NULL
);
"""

Row = tuple[str, str, float]  # (day, metric, kwh)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def upsert(self, source: str, rows: Iterable[Row]) -> int:
        params = [(day, source, metric, kwh) for day, metric, kwh in rows]
        with self._conn() as conn:
            conn.executemany(
                """
                INSERT INTO daily (day, source, metric, kwh) VALUES (?, ?, ?, ?)
                ON CONFLICT (day, source, metric) DO UPDATE SET kwh = excluded.kwh
                """,
                params,
            )
        return len(params)

    def monthly(self) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, int]]]:
        """Returns ({month: {metric: kwh}}, {month: {source: day_count}})."""
        totals: dict[str, dict[str, float]] = defaultdict(dict)
        coverage: dict[str, dict[str, int]] = defaultdict(dict)
        with self._conn() as conn:
            for r in conn.execute(
                "SELECT substr(day, 1, 7) AS month, metric, SUM(kwh) AS kwh "
                "FROM daily GROUP BY month, metric"
            ):
                totals[r["month"]][r["metric"]] = r["kwh"]
            for r in conn.execute(
                "SELECT substr(day, 1, 7) AS month, source, COUNT(DISTINCT day) AS days "
                "FROM daily GROUP BY month, source"
            ):
                coverage[r["month"]][r["source"]] = r["days"]
        return totals, coverage

    def states(self) -> dict[str, sqlite3.Row]:
        with self._conn() as conn:
            return {r["source"]: r for r in conn.execute("SELECT * FROM sync_state")}

    def begin_sync(self, source: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO sync_state (source, last_attempt) VALUES (?, ?)
                ON CONFLICT (source) DO UPDATE SET last_attempt = excluded.last_attempt
                """,
                (source, utcnow()),
            )

    def finish_sync(self, source: str, error: str | None = None) -> None:
        with self._conn() as conn:
            if error is None:
                conn.execute(
                    "UPDATE sync_state SET last_success = ?, last_error = NULL WHERE source = ?",
                    (utcnow(), source),
                )
            else:
                conn.execute(
                    "UPDATE sync_state SET last_error = ? WHERE source = ?",
                    (error, source),
                )

    def login_failures(self, ip: str, window_seconds: int) -> int:
        with self._conn() as conn:
            conn.execute("DELETE FROM login_failures WHERE ts < ?", (time.time() - window_seconds,))
            return conn.execute(
                "SELECT COUNT(*) FROM login_failures WHERE ip = ?", (ip,)
            ).fetchone()[0]

    def add_login_failure(self, ip: str) -> None:
        with self._conn() as conn:
            conn.execute("INSERT INTO login_failures (ip, ts) VALUES (?, ?)", (ip, time.time()))


def current_store() -> Store:
    return current_app.extensions["store"]
