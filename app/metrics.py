from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, tzinfo

MONTH_KEY = re.compile(r"\d{4}-(0[1-9]|1[0-2])")  # YYYY-MM
DEFAULT_MONTHS = 12  # default range: the latest n complete months with data
SAX_KEYS = ("pv", "grid_import", "grid_export", "bat_charge", "bat_discharge")
HEAT_MODES = ("heating", "dhw")  # modes that produce heat; cooling is excluded from heat and COP
DISPLAY_FROM = "2026-05"  # YYYY-MM, earlier months are hidden


@dataclass(frozen=True)
class Column:
    key: str
    label: str
    kind: str = "kwh"  # kwh | pct | ratio
    kpi_label: str = ""

    @property
    def title(self) -> str:
        return self.kpi_label or self.label

    @property
    def unit(self) -> str:
        return {"kwh": "kWh", "pct": "%", "ratio": ""}[self.kind]


@dataclass(frozen=True)
class Group:
    label: str
    columns: tuple[Column, ...]


GROUPS = (
    Group("Solar & Netz", (
        Column("pv", "PV-Erzeugung"),
        Column("grid_import", "Netzbezug"),
        Column("grid_export", "Einspeisung"),
    )),
    Group("Haus", (
        Column("house", "Verbrauch gesamt", kpi_label="Hausverbrauch"),
        Column("house_without_hp", "ohne WP"),
    )),
    Group("Wärmepumpe", (
        Column("el_heating", "Strom Heizen"),
        Column("el_dhw", "Strom Warmwasser"),
        Column("el_cooling", "Strom Kühlung"),
        Column("hp_el", "Strom gesamt", kpi_label="WP-Strom"),
        Column("hp_heat", "Wärme erzeugt"),
        Column("cop", "Arbeitszahl", "ratio", kpi_label="WP-Arbeitszahl"),
    )),
    Group("Quoten", (
        Column("hp_share", "WP-Anteil", "pct"),
        Column("autarky", "Autarkie", "pct"),
        Column("self_use", "Eigenverbrauch", "pct"),
    )),
)
CHART_COLUMNS = (  # chart-only series, not shown in the table
    Column("heat_heating", "Heizen"),
    Column("heat_dhw", "Warmwasser"),
    Column("heat_cooling", "Kühlung"),
)
COLUMNS = {c.key: c for c in (*(c for g in GROUPS for c in g.columns), *CHART_COLUMNS)}
HP_MODES = (("Heizen", "el_heating"), ("Warmwasser", "el_dhw"), ("Kühlung", "el_cooling"))
KPI_KEYS = ("pv", "house", "hp_el", "cop", "autarky")


@dataclass(frozen=True)
class Chart:
    title: str
    keys: tuple[str, ...]  # all keys must share one kind
    stacked: bool = False  # stacked bars instead of lines


CHARTS = (
    Chart("Energie", ("pv", "grid_import", "house", "hp_el")),
    Chart("WP erzeugte Energie nach Nutzung", ("heat_heating", "heat_dhw", "heat_cooling"), stacked=True),
    Chart("Quoten", ("hp_share", "autarky", "self_use")),
    Chart("WP-Arbeitszahl", ("cop",)),
)


@dataclass
class Period:
    key: str  # YYYY-MM
    values: dict[str, float | None]
    raw: dict[str, float]  # source values incl. heat fallback, summed for ranges
    days: dict[str, int] = field(default_factory=dict)  # source -> days with data
    coverage: str = ""

    @property
    def label(self) -> str:
        return month_label(self.key)


@dataclass
class Selection:
    total: dict[str, float | None]
    months: list[Period]  # newest first
    days: dict[str, int] = field(default_factory=dict)  # source -> days with data

    @property
    def span(self) -> str:
        return span_label(self.months[-1].key, self.months[0].key)


@dataclass(frozen=True)
class Stat:
    label: str
    value: float | None
    kind: str  # fmt kind
    unit: str
    share: float | None = None  # optional fraction shown next to the value


@dataclass(frozen=True)
class StatCard:
    title: str
    stats: tuple[Stat, ...]
    note: str = ""


def _sum(values) -> float | None:
    values = [v for v in values if v is not None]
    return sum(values) if values else None


def _sum_prefix(raw: dict[str, float], prefix: str) -> float | None:
    return _sum(v for k, v in raw.items() if k.startswith(prefix))


def _sum_modes(raw: dict[str, float], energy: str, modes=HEAT_MODES) -> float | None:
    return _sum(raw.get(f"{energy}_{m}") for m in modes)


def _ratio(a: float | None, b: float | None) -> float | None:
    return a / b if a is not None and b else None


def with_heat_fallback(raw: dict[str, float]) -> dict[str, float]:
    """Fill missing heat_<mode> with el_<mode> + env_<mode>, before summing, so totals match months."""
    filled = dict(raw)
    for m in HEAT_MODES:
        el, env = raw.get(f"el_{m}"), raw.get(f"env_{m}")
        if f"heat_{m}" not in raw and el is not None and env is not None:
            filled[f"heat_{m}"] = el + env
    return filled


def derive(raw: dict[str, float], pv_factor: float = 1.0) -> dict[str, float | None]:
    values: dict[str, float | None] = dict(raw)
    if values.get("pv") is not None:
        values["pv"] *= pv_factor
    pv, grid_import, grid_export, bat_charge, bat_discharge = (values.get(k) for k in SAX_KEYS)

    house = None
    if all(values.get(k) is not None for k in SAX_KEYS):
        house = pv + grid_import - grid_export + bat_discharge - bat_charge

    hp_el = _sum_prefix(raw, "el_")  # all modes, incl. cooling
    hp_el_heat = _sum_modes(raw, "el")  # heating + hot water only
    hp_heat = _sum_modes(raw, "heat")

    import_share = _ratio(grid_import, house)
    values.update(
        house=house,
        house_without_hp=house - hp_el if house is not None and hp_el is not None else None,
        hp_el=hp_el,
        hp_el_heat=hp_el_heat,
        hp_heat=hp_heat,
        cop=_ratio(hp_heat, hp_el_heat),
        hp_share=_ratio(hp_el, house),
        autarky=1 - import_share if import_share is not None else None,
        self_use=_ratio(pv - grid_export, pv) if pv is not None and grid_export is not None else None,
    )
    return values


def _coverage(days: dict[str, int], labels: dict[str, str]) -> str:
    return " · ".join(f"{labels.get(s, s)}: {n} Tage" for s, n in sorted(days.items()))


def span_label(start: str, end: str) -> str:
    """YYYY-MM keys -> MM.YYYY or MM.YYYY–MM.YYYY"""
    first, last = month_label(start), month_label(end)
    return first if first == last else f"{first}–{last}"


def day_label(key: str) -> str:
    """YYYY-MM-DD -> DD.MM.YYYY"""
    y, m, d = key.split("-")
    return f"{d}.{m}.{y}"


def month_label(key: str) -> str:
    """YYYY-MM -> MM.YYYY"""
    y, m = key.split("-")
    return f"{m}.{y}"


def _add(target: dict, source: dict) -> None:
    for key, value in source.items():
        target[key] = target.get(key, 0) + value


def build_months(
    totals: dict[str, dict[str, float]],
    coverage: dict[str, dict[str, int]],
    labels: dict[str, str],
    pv_factor: float = 1.0,
    display_from: str = DISPLAY_FROM,
) -> list[Period]:
    """All months from display_from on, newest first."""
    months = []
    for key in sorted(totals, reverse=True):
        if key < display_from:
            continue
        raw = with_heat_fallback(totals[key])
        days = coverage.get(key, {})
        months.append(Period(key, derive(raw, pv_factor), raw, days, _coverage(days, labels)))
    return months


def default_range(keys: list[str], current: str) -> tuple[str, str]:
    """Latest DEFAULT_MONTHS complete months (before the running month `current`, YYYY-MM).

    Falls back to all months if none is complete yet. keys: newest first.
    """
    complete = [k for k in keys if k < current] or keys
    return complete[min(DEFAULT_MONTHS, len(complete)) - 1], complete[0]


def resolve_range(keys: list[str], start: str | None, end: str | None, default: tuple[str, str]) -> tuple[str, str]:
    """Validate a requested range: invalid bounds fall back to the default, others are clamped and ordered."""
    oldest, newest = keys[-1], keys[0]

    def clamp(value: str | None, fallback: str) -> str:
        return min(max(value, oldest), newest) if value and MONTH_KEY.fullmatch(value) else fallback

    start, end = clamp(start, default[0]), clamp(end, default[1])
    return (end, start) if start > end else (start, end)


def select(months: list[Period], start: str, end: str, pv_factor: float = 1.0) -> Selection:
    picked = [m for m in months if start <= m.key <= end]
    raw: dict[str, float] = {}
    days: dict[str, int] = {}
    for m in picked:
        _add(raw, m.raw)
        _add(days, m.days)
    return Selection(derive(raw, pv_factor), picked, days)


def chart_data(selection: Selection) -> dict:
    months = selection.months[::-1]
    return {
        "labels": [m.label for m in months],
        "charts": [
            {
                "title": c.title,
                "kind": COLUMNS[c.keys[0]].kind,
                "unit": COLUMNS[c.keys[0]].unit,
                "stacked": c.stacked,
                "series": [
                    {"key": k, "label": COLUMNS[k].title, "values": [m.values.get(k) for m in months]}
                    for k in c.keys
                ],
            }
            for c in CHARTS
        ],
    }


def _scale(value: float | None, factor: float) -> float | None:
    return value * factor if value is not None else None


def range_stats(selection: Selection, area_m2: float | None, price: float | None) -> tuple[list[StatCard], str]:
    """Averages use days with data, so incomplete months are not diluted."""
    t = selection.total
    days, hp_days = selection.days.get("sax"), selection.days.get("vaillant")
    month_factor = 365.25 / 12

    def per_day(key: str, n: int | None) -> float | None:
        return _ratio(t.get(key), n)

    cards = [StatCard("Ø Stromverbrauch pro Tag", (
        Stat("mit Wärmepumpe", per_day("house", days), "dec", "kWh"),
        Stat("ohne Wärmepumpe", per_day("house_without_hp", days), "dec", "kWh"),
        Stat("Wärmepumpe", per_day("hp_el", hp_days), "dec", "kWh"),
    ))]
    hp_el = t.get("hp_el")
    if hp_el:
        cards.append(StatCard("WP-Strom nach Nutzung", tuple(
            Stat(label, t.get(key), "kwh", "kWh", _ratio(t.get(key), hp_el))
            for label, key in HP_MODES
        ), "Summe im Zeitraum, Anteil am WP-Strom"))
    if price:
        monthly = month_factor * price
        period = " · ".join(
            f"{label} {fmt(_scale(t.get(key), price), 'eur')} €"
            for label, key in (("Netzbezug", "grid_import"), ("Verbrauch", "house"))
            if t.get(key) is not None
        )
        cards.append(StatCard("Ø Stromkosten pro Monat", (
            Stat("Netzbezug", _scale(per_day("grid_import", days), monthly), "eur", "€"),
            Stat("Hausverbrauch", _scale(per_day("house", days), monthly), "eur", "€"),
            Stat("davon Wärmepumpe", _scale(per_day("hp_el", hp_days), monthly), "eur", "€"),
        ), f"Im Zeitraum: {period}" if period else ""))
    if area_m2:
        cards.append(StatCard("Heizenergie pro m²", (
            Stat("WP-Strom", _scale(t.get("hp_el_heat"), 1 / area_m2), "dec", "kWh/m²"),
            Stat("Wärme erzeugt", _scale(t.get("hp_heat"), 1 / area_m2), "dec", "kWh/m²"),
        ), "Summe im Zeitraum, Heizen + Warmwasser, ohne Kühlung"))

    basis = [f"{days or 0} Tage", selection.span]
    if hp_days is not None and hp_days != days:
        basis.append(f"Wärmepumpe: {hp_days} Tage")
    if area_m2:
        basis.append(f"{fmt(area_m2)} m²")
    if price:
        basis.append(f"{_de(price, 2)} €/kWh ohne Grundgebühr")
    return cards, " · ".join(basis)


def _de(value: float, digits: int) -> str:
    return f"{value:,.{digits}f}".translate(str.maketrans(",.", ".,"))


def fmt(value: float | None, kind: str = "kwh") -> str:
    if value is None:
        return "–"
    if kind == "pct":
        return f"{value * 100:.0f}"
    if kind in ("ratio", "dec"):
        return _de(value, 1)
    if kind == "money":
        return _de(value, 2)
    return _de(value, 0)


def format_local(iso: str | None, tz: tzinfo) -> str:
    if not iso:
        return "nie"
    return datetime.fromisoformat(iso).astimezone(tz).strftime("%d.%m.%Y %H:%M")
