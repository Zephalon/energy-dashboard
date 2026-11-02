"""SAX Power, inoffizielle API von webserver.sax-power.net (Port von fetch-energy.mjs)."""

from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Iterator

import requests

from ..db import Row
from ..settings import Settings

BASE = "https://webserver.sax-power.net"
TIMEOUT = 30

# Werte in Wh/Tag. Positiv = Fluss ins Haus (Netzbezug, Akku entladen), negativ = aus dem Haus.
# m5/m5N so zugeordnet, weil sonst die Entladung über Monate die Ladung übersteigt.
FIELDS = {
    "m4": "pv",
    "m2": "grid_import",
    "m2N": "grid_export",
    "m5": "bat_discharge",
    "m5N": "bat_charge",
}


class SaxError(RuntimeError):
    pass


def fetch(settings: Settings, start: date, end: date) -> list[Row]:
    """Fetches whole months covering [start, end], skipping days after end."""
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {_login(session, settings)}"
    rows: list[Row] = []
    for i, month in enumerate(_months(start, end)):
        if i:
            time.sleep(1)
        rows += _month_rows(session, settings.sax_serial, month, end)
    return rows


def _login(session: requests.Session, settings: Settings) -> str:
    resp = session.post(
        f"{BASE}/api/auth/token/",
        json={"email": settings.sax_email, "password": settings.sax_password},
        timeout=TIMEOUT,
    )
    if not resp.ok:
        raise SaxError(f"Login fehlgeschlagen (HTTP {resp.status_code})")
    token = resp.json().get("access")
    if not token:
        raise SaxError("Login-Antwort enthält kein access-Token")
    return token


def _months(start: date, end: date) -> Iterator[date]:
    month = start.replace(day=1)
    while month <= end:
        yield month
        month = (month + timedelta(days=32)).replace(day=1)


def _month_rows(session: requests.Session, serial: str, month: date, end: date) -> list[Row]:
    resp = session.get(
        f"{BASE}/api/auth/energy_chart/",
        params={"sn": serial, "m2": "true", "m4": "true", "m5": "true", "days": f"month_{month.isoformat()}"},
        timeout=TIMEOUT,
    )
    if not resp.ok:
        raise SaxError(f"Chart-Abruf {month:%Y-%m} fehlgeschlagen (HTTP {resp.status_code})")
    series = resp.json().get(serial)
    if not isinstance(series, list):
        raise SaxError(f"Keine Daten für Seriennummer {serial}")

    rows: list[Row] = []
    for entry in series:
        day = str(entry.get("de_time") or "")[:10]
        if not day or day > end.isoformat():
            continue
        for key, metric in FIELDS.items():
            value = entry.get(key)
            if isinstance(value, (int, float)):
                rows.append((day, metric, round(abs(value) / 1000, 3)))
    return rows
