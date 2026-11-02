"""Vaillant aroTHERM über die inoffizielle myVAILLANT-API (Bibliothek myPyllant).

Strenges, undokumentiertes Rate-Limit: höchstens ein regulärer Lauf pro Tag.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import date, datetime, time, timedelta, tzinfo
from typing import Iterator
from zoneinfo import ZoneInfo

from ..db import Row
from ..settings import Settings

ENERGY_TYPES = {
    "CONSUMED_ELECTRICAL_ENERGY": "el",
    "HEAT_GENERATED": "heat",
    "EARNED_ENVIRONMENT_ENERGY": "env",
}
MAX_DAYS_PER_REQUEST = 60  # API antwortet sonst mit HTTP 416

MODES = {
    "HEATING": "heating",
    "DOMESTIC_HOT_WATER": "dhw",
    "COOLING": "cooling",
}


def fetch(settings: Settings, start: date, end: date) -> list[Row]:
    return asyncio.run(_fetch(settings, start, end))


async def _fetch(settings: Settings, start: date, end: date) -> list[Row]:
    from myPyllant.api import MyPyllantAPI
    from myPyllant.enums import DeviceDataBucketResolution

    tz = ZoneInfo(settings.timezone)
    totals: dict[tuple[str, str], float] = defaultdict(float)

    async with MyPyllantAPI(
        settings.vaillant_user,
        settings.vaillant_password,
        settings.vaillant_brand,
        settings.vaillant_country,
    ) as api:
        async for system in api.get_systems():
            for device in system.devices:
                first = device.first_data.astimezone(tz).date() if device.first_data else start
                chunks = list(_chunks(max(start, first), end, MAX_DAYS_PER_REQUEST))
                for i, (chunk_start, chunk_end) in enumerate(chunks):
                    if i:
                        await asyncio.sleep(settings.vaillant_chunk_pause)
                    async for series in api.get_data_by_device(
                        device,
                        DeviceDataBucketResolution.DAY,
                        _midnight(chunk_start, tz),
                        _midnight(chunk_end + timedelta(days=1), tz),
                    ):
                        metric = _metric(series)
                        if not metric:
                            continue
                        for bucket in series.data:
                            if bucket.value is None:
                                continue
                            day = bucket.start_date.astimezone(tz).date()
                            if chunk_start <= day <= chunk_end:
                                totals[(day.isoformat(), metric)] += bucket.value / 1000

    return [(day, metric, round(kwh, 3)) for (day, metric), kwh in sorted(totals.items())]


def _metric(series) -> str | None:
    energy = ENERGY_TYPES.get(series.energy_type or series.value_type or "")
    mode = MODES.get(series.operation_mode)
    return f"{energy}_{mode}" if energy and mode else None


def _midnight(day: date, tz: tzinfo) -> datetime:
    return datetime.combine(day, time.min, tzinfo=tz)


def _chunks(start: date, end: date, size: int) -> Iterator[tuple[date, date]]:
    while start <= end:
        stop = min(start + timedelta(days=size - 1), end)
        yield start, stop
        start = stop + timedelta(days=1)
