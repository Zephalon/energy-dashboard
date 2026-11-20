"""Outdoor temperature from DWD data via Bright Sky (https://brightsky.dev, no API key)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from statistics import fmean
from zoneinfo import ZoneInfo

import requests

from ..db import Row
from ..settings import Settings

URL = "https://api.brightsky.dev/weather"
TIMEOUT = 30
MAX_DAYS_PER_REQUEST = 31
MIN_HOURS = 20  # hourly values needed for a valid daily mean
METRIC = "temp_mean"


class DwdError(RuntimeError):
    pass


def fetch(settings: Settings, start: date, end: date) -> list[Row]:
    """Daily mean temperatures for [start, end]; today is skipped because it is partly forecast."""
    end = min(end, datetime.now(ZoneInfo(settings.timezone)).date() - timedelta(days=1))
    session = requests.Session()
    rows: list[Row] = []
    chunk_start = start
    while chunk_start <= end:
        chunk_end = min(chunk_start + timedelta(days=MAX_DAYS_PER_REQUEST - 1), end)
        rows += _daily_means(session, settings, chunk_start, chunk_end)
        chunk_start = chunk_end + timedelta(days=1)
    return rows


def _daily_means(session: requests.Session, settings: Settings, start: date, end: date) -> list[Row]:
    resp = session.get(
        URL,
        params={
            "lat": settings.latitude,
            "lon": settings.longitude,
            "date": start.isoformat(),
            "last_date": (end + timedelta(days=1)).isoformat(),
            "tz": settings.timezone,
        },
        timeout=TIMEOUT,
    )
    if not resp.ok:
        raise DwdError(f"Bright Sky HTTP {resp.status_code}")

    hourly: dict[str, list[float]] = defaultdict(list)
    for record in resp.json().get("weather", []):
        if record.get("temperature") is not None:
            hourly[record["timestamp"][:10]].append(record["temperature"])  # local date thanks to tz

    first, last = start.isoformat(), end.isoformat()
    return [
        (day, METRIC, round(fmean(values), 2))
        for day, values in sorted(hourly.items())
        if first <= day <= last and len(values) >= MIN_HOURS
    ]
