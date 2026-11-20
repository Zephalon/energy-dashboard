from __future__ import annotations

import fcntl
import logging
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Iterator
from zoneinfo import ZoneInfo

from .db import Row, Store
from .settings import Settings
from .sources import dwd, sax, vaillant

log = logging.getLogger(__name__)

Fetcher = Callable[[Settings, date, date], list[Row]]



@dataclass(frozen=True)
class Source:
    label: str
    fetch: Fetcher
    max_age_hours: Callable[[Settings], float]
    days_back: Callable[[Settings], int]  # default look-back of a regular sync


SOURCES: dict[str, Source] = {
    # SAX liefert ganze Monate: drei Tage Rückblick ziehen am Monatsanfang den Vormonat mit.
    "sax": Source("Solar (SAX)", sax.fetch, lambda s: s.sax_max_age_hours, lambda s: 3),
    "vaillant": Source(
        "Wärmepumpe (Vaillant)", vaillant.fetch, lambda s: s.vaillant_max_age_hours, lambda s: s.vaillant_days_back
    ),
    "dwd": Source("Wetter (DWD)", dwd.fetch, lambda s: s.dwd_max_age_hours, lambda s: s.dwd_days_back),
}
LABELS = {key: source.label for key, source in SOURCES.items()}


def local_today(settings: Settings) -> date:
    return datetime.now(ZoneInfo(settings.timezone)).date()


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
            config = SOURCES[source]
            if not (force or start) and not _is_due(
                states.get(source), timedelta(hours=config.max_age_hours(settings))
            ):
                results[source] = "fresh"
                continue
            store.begin_sync(source)
            try:
                rows = config.fetch(settings, start or end - timedelta(days=config.days_back(settings)), end)
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
