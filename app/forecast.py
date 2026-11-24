"""Heating forecast: daily space-heating energy (without hot water) as a function of outdoor temperature."""

from __future__ import annotations

from dataclasses import dataclass

from .metrics import Stat, StatCard, day_label, with_heat_fallback

TEMP_METRIC = "temp_mean"
TEMPS = range(20, -16, -1)  # °C, warm to cold; also the chart's x range
TABLE_TEMPS = range(15, -16, -3)  # °C, table rows
MIN_HEATING_DAYS = 10
MIN_HEAT_KWH = 2.0  # days with less heat are too noisy for the COP fit
BALANCE_CANDIDATES = [t / 10 for t in range(80, 221)]  # 8.0 … 22.0 °C
COP_REFERENCE_TEMPS = (7, 2, -7)  # common rating points (A7/A2/A-7)


@dataclass(frozen=True)
class Point:
    day: str  # YYYY-MM-DD
    temp: float
    heat: float
    el: float


@dataclass(frozen=True)
class Model:
    balance: float  # heating limit: no heating at or above this mean temperature
    slope: float  # kWh heat per K below the balance point and day
    r2: float
    cop_slope: float
    cop_intercept: float
    cop_max: float
    temp_min: float  # observed range
    temp_max: float
    days: int
    heating_days: int

    def heat(self, temp: float) -> float:
        return self.slope * max(0.0, self.balance - temp)

    def cop(self, temp: float) -> float:
        return min(max(self.cop_intercept + self.cop_slope * temp, 1.0), self.cop_max)

    def el(self, temp: float) -> float:
        return self.heat(temp) / self.cop(temp)

    def extrapolated(self, temp: float) -> bool:
        return not self.temp_min <= temp <= self.temp_max


def points(daily: dict[str, dict[str, float]], today: str) -> list[Point]:
    """Complete days with temperature and heat pump data. A missing heating value counts as 0 on days with other heat pump data."""
    result = []
    for day, raw in sorted(daily.items()):
        temp = raw.get(TEMP_METRIC)
        if day >= today or temp is None or not any(k.startswith("el_") for k in raw):
            continue
        raw = with_heat_fallback(raw)
        result.append(Point(day, temp, raw.get("heat_heating", 0.0), raw.get("el_heating", 0.0)))
    return result


def _linreg(xs: list[float], ys: list[float], ws: list[float] | None = None) -> tuple[float, float]:
    """Weighted least squares y = intercept + slope * x. Returns (slope, intercept)."""
    ws = ws or [1.0] * len(xs)
    total = sum(ws)
    mx = sum(w * x for w, x in zip(ws, xs)) / total
    my = sum(w * y for w, y in zip(ws, ys)) / total
    sxx = sum(w * (x - mx) ** 2 for w, x in zip(ws, xs))
    slope = sum(w * (x - mx) * (y - my) for w, x, y in zip(ws, xs, ys)) / sxx if sxx else 0.0
    return slope, my - slope * mx


def _fit_signature(pts: list[Point]) -> tuple[float, float, float]:
    """Grid search over the balance point; per candidate a least-squares slope through the origin. Returns (balance, slope, sse)."""
    best = (0.0, 0.0, float("inf"))
    for balance in BALANCE_CANDIDATES:
        xs = [max(0.0, balance - p.temp) for p in pts]
        sxx = sum(x * x for x in xs)
        if not sxx:
            continue
        slope = sum(x * p.heat for x, p in zip(xs, pts)) / sxx
        sse = sum((p.heat - slope * x) ** 2 for x, p in zip(xs, pts))
        if sse < best[2]:
            best = (balance, slope, sse)
    return best


def fit(pts: list[Point]) -> Model | None:
    heating = [p for p in pts if p.heat >= MIN_HEAT_KWH and p.el > 0]
    if len(heating) < MIN_HEATING_DAYS:
        return None

    balance, slope, sse = _fit_signature(pts)
    mean_heat = sum(p.heat for p in pts) / len(pts)
    sst = sum((p.heat - mean_heat) ** 2 for p in pts)

    # COP falls with outdoor temperature; weight by heat so small, noisy days count less
    cops = [p.heat / p.el for p in heating]
    weights = [p.heat for p in heating]
    cop_slope, cop_intercept = _linreg([p.temp for p in heating], cops, weights)
    if cop_slope < 0:  # implausible, fall back to a constant mean COP
        cop_slope, cop_intercept = 0.0, sum(c * w for c, w in zip(cops, weights)) / sum(weights)

    temps = [p.temp for p in pts]
    return Model(
        balance=balance,
        slope=slope,
        r2=1 - sse / sst if sst else 0.0,
        cop_slope=cop_slope,
        cop_intercept=cop_intercept,
        cop_max=max(cops),
        temp_min=min(temps),
        temp_max=max(temps),
        days=len(pts),
        heating_days=len(heating),
    )


def curve(model: Model) -> list[dict]:
    return [
        {
            "temp": t,
            "heat": model.heat(t),
            "el": model.el(t),
            "cop": model.cop(t) if model.heat(t) else None,
            "extrapolated": model.extrapolated(t),
        }
        for t in TEMPS
    ]


def table(rows: list[dict], price: float | None) -> list[dict]:
    return [
        {**r, "cost": r["el"] * price if price else None}
        for r in rows
        if r["temp"] in TABLE_TEMPS
    ]


def stats(model: Model) -> list[StatCard]:
    return [
        StatCard("Kennlinie Heizwärme", (
            Stat("Heizgrenze", model.balance, "dec", "°C"),
            Stat("Wärme je Kelvin", model.slope, "dec", "kWh/K·Tag"),
            Stat("Bestimmtheitsmaß R²", model.r2, "pct", "%"),
        ), "Heizwärme = Steigung × (Heizgrenze − Tagesmitteltemperatur)"),
        StatCard("Arbeitszahl Heizen", tuple(
            Stat(f"bei {t:+d} °C".replace("-", "−"), model.cop(t), "ratio", "")
            for t in COP_REFERENCE_TEMPS
        ), "Lineare Regression über die Heiztage, gewichtet nach Wärmemenge"),
        StatCard("Datenbasis", (
            Stat("Tage mit Temperatur", model.days, "kwh", ""),
            Stat("davon Heiztage", model.heating_days, "kwh", ""),
            Stat("kältester Tag", model.temp_min, "dec", "°C"),
            Stat("wärmster Tag", model.temp_max, "dec", "°C"),
        ), f"Heiztag: mindestens {MIN_HEAT_KWH:.0f} kWh Heizwärme"),
    ]


def chart_data(pts: list[Point], rows: list[dict]) -> dict:
    x_max, x_min = TEMPS[0], TEMPS[-1]  # warmer days need no heating and would only stretch the axis

    def series(key: str, label: str, attr: str) -> dict:
        return {
            "key": key,
            "label": label,
            "points": [{"x": p.temp, "y": getattr(p, attr), "day": day_label(p.day)} for p in pts if x_min <= p.temp <= x_max],
            "curve": [{"x": r["temp"], "y": r[attr], "ext": r["extrapolated"]} for r in rows],
        }

    return {"unit": "kWh", "xMin": x_min, "xMax": x_max, "series": [series("heat_heating", "Wärme", "heat"), series("el_heating", "Strom", "el")]}
