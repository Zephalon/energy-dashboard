from __future__ import annotations

import fcntl
import logging
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Iterator
from zoneinfo import ZoneInfo

from .db import Row, Store
from .settings import Settings
from .sources import sax, vaillant

log = logging.getLogger(__name__)

Fetcher = Callable[[Settings, date, date], list[Row]]

FETCHERS: dict[str, Fetcher] = {"sax": sax.fetch, "vaillant": vaillant.fetch}
LABELS = {"sax": "Solar (SAX)", "vaillant": "Wärmepumpe (Vaillant)"}


def local_today(settings: Settings) -> date:
    return datetime.now(ZoneInfo(settings.timezone)).date()


def _max_age(settings: Settings, source: str) -> timedelta:
    hours = settings.sax_max_age_hours if source == "sax" else settings.vaillant_max_age_hours
    return timedelta(hours=hours)


def _default_start(settings: Settings, source: str, today: date) -> date:
    # SAX liefert ganze Monate: drei Tage Rückblick ziehen am Monatsanfang den Vormonat mit.
    days = 3 if source == "sax" else settings.vaillant_days_back
    return today - timedelta(days=days)


def _is_due(state, max_age: timedelta) -> bool:
    if state is None or not state["last_attempt"]:
        return True
    return datetime.now(timezone.utc) - datetime.fromisoformat(state["last_attempt"]) >= max_age


@contextmanager
def _lock(path) -> Iterator[bool]:
    with open(path, "w") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def run(
    settings: Settings,
    store: Store,
    *,
    sources: list[str] | None = None,
    start: date | None = None,
    end: date | None = None,
    force: bool = False,
) -> dict[str, str]:
    """Syncs due sources. An explicit start (backfill) always counts as forced."""
    results: dict[str, str] = {}
    with _lock(settings.data_dir / "sync.lock") as acquired:
        if not acquired:
            return {"status": "busy"}
        states = store.states()
        end = end or local_today(settings)
        for source in sources or settings.sources:
            if source not in settings.sources:
                results[source] = "not configured"
                continue
            if not (force or start) and not _is_due(states.get(source), _max_age(settings, source)):
                results[source] = "fresh"
                continue
            store.begin_sync(source)
            try:
                rows = FETCHERS[source](settings, start or _default_start(settings, source, end), end)
                count = store.upsert(source, rows)
            except Exception as exc:  # APIs sind inoffiziell, alles kann brechen
                message = f"{type(exc).__name__}: {exc}"[:300]
                log.warning("Sync %s fehlgeschlagen: %s", source, message)
                store.finish_sync(source, error=message)
                results[source] = f"error: {message}"
            else:
                store.finish_sync(source)
                results[source] = f"ok ({count} Werte)"
    return results
