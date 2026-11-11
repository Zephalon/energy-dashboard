from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, tzinfo

MONTH_NAMES = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]
SAX_KEYS = ("pv", "grid_import", "grid_export", "bat_charge", "bat_discharge")
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
COLUMNS = {c.key: c for g in GROUPS for c in g.columns}
KPI_KEYS = ("pv", "house", "hp_el", "cop", "autarky")
CHARTS = (  # title, keys; all keys of a chart must share one kind
    ("Energie", ("pv", "grid_import", "house", "hp_el")),
    ("Quoten", ("hp_share", "autarky", "self_use")),
    ("WP-Arbeitszahl", ("cop",)),
)


@dataclass
class Period:
    label: str
    values: dict[str, float | None]
    coverage: str = ""


@dataclass
class Year:
    label: str
    total: dict[str, float | None]
    months: list[Period] = field(default_factory=list)
    days: dict[str, int] = field(default_factory=dict)  # source -> days with data

    @property
    def span(self) -> str:
        first, last = self.months[-1].label, self.months[0].label
        return first if first == last else f"{first}–{last}"


@dataclass(frozen=True)
class Stat:
    label: str
    value: float | None
    kind: str  # fmt kind
    unit: str


@dataclass(frozen=True)
class StatCard:
    title: str
    stats: tuple[Stat, ...]
    note: str = ""


def _sum_prefix(raw: dict[str, float], prefix: str) -> float | None:
    values = [v for k, v in raw.items() if k.startswith(prefix)]
    return sum(values) if values else None


def _ratio(a: float | None, b: float | None) -> float | None:
    return a / b if a is not None and b else None


def derive(raw: dict[str, float], pv_factor: float = 1.0) -> dict[str, float | None]:
    values: dict[str, float | None] = dict(raw)
    if values.get("pv") is not None:
        values["pv"] *= pv_factor
    pv, grid_import, grid_export, bat_charge, bat_discharge = (values.get(k) for k in SAX_KEYS)

    house = None
    if all(values.get(k) is not None for k in SAX_KEYS):
        house = pv + grid_import - grid_export + bat_discharge - bat_charge

    hp_el = _sum_prefix(raw, "el_")
    hp_heat = _sum_prefix(raw, "heat_")
    hp_env = _sum_prefix(raw, "env_")
    if hp_heat is None and hp_el is not None and hp_env is not None:
        hp_heat = hp_el + hp_env

    import_share = _ratio(grid_import, house)
    values.update(
        house=house,
        house_without_hp=house - hp_el if house is not None and hp_el is not None else None,
        hp_el=hp_el,
        hp_heat=hp_heat,
        cop=_ratio(hp_heat, hp_el),
        hp_share=_ratio(hp_el, house),
        autarky=1 - import_share if import_share is not None else None,
        self_use=_ratio(pv - grid_export, pv) if pv is not None and grid_export is not None else None,
    )
    return values


def _coverage(days: dict[str, int], labels: dict[str, str]) -> str:
    return " · ".join(f"{labels.get(s, s)}: {n} Tage" for s, n in sorted(days.items()))


def build_years(
    totals: dict[str, dict[str, float]],
    coverage: dict[str, dict[str, int]],
    labels: dict[str, str],
    pv_factor: float = 1.0,
) -> list[Year]:
    years: dict[str, Year] = {}
    year_raw: dict[str, dict[str, float]] = {}
    for month in sorted(totals, reverse=True):
        if month < DISPLAY_FROM:
            continue
        y, m = month.split("-")
        raw = totals[month]
        sums = year_raw.setdefault(y, {})
        for key, value in raw.items():
            sums[key] = sums.get(key, 0.0) + value
        year = years.setdefault(y, Year(label=y, total={}))
        for source, n in coverage.get(month, {}).items():
            year.days[source] = year.days.get(source, 0) + n
        year.months.append(
            Period(
                label=MONTH_NAMES[int(m) - 1],
                values=derive(raw, pv_factor),
                coverage=_coverage(coverage.get(month, {}), labels),
            )
        )
    for y, year in years.items():
        year.total = derive(year_raw[y], pv_factor)
    return list(years.values())


def chart_data(year: Year) -> dict:
    months = year.months[::-1]
    return {
        "labels": [m.label for m in months],
        "charts": [
            {
                "title": title,
                "kind": COLUMNS[keys[0]].kind,
                "unit": COLUMNS[keys[0]].unit,
                "series": [
                    {"key": k, "label": COLUMNS[k].title, "values": [m.values.get(k) for m in months]}
                    for k in keys
                ],
            }
            for title, keys in CHARTS
        ],
    }


def _scale(value: float | None, factor: float) -> float | None:
    return value * factor if value is not None else None


def year_stats(year: Year, area_m2: float | None, price: float | None) -> tuple[list[StatCard], str]:
    """Averages use days with data, so partial years are not diluted."""
    t = year.total
    days, hp_days = year.days.get("sax"), year.days.get("vaillant")
    month_factor = 365.25 / 12

    def per_day(key: str, n: int | None) -> float | None:
        return _ratio(t.get(key), n)

    cards = [StatCard("Ø Stromverbrauch pro Tag", (
        Stat("mit Wärmepumpe", per_day("house", days), "dec", "kWh"),
        Stat("ohne Wärmepumpe", per_day("house_without_hp", days), "dec", "kWh"),
        Stat("Wärmepumpe", per_day("hp_el", hp_days), "dec", "kWh"),
    ))]
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
            Stat("WP-Strom", _scale(t.get("hp_el"), 1 / area_m2), "dec", "kWh/m²"),
            Stat("Wärme erzeugt", _scale(t.get("hp_heat"), 1 / area_m2), "dec", "kWh/m²"),
        ), "Summe im Zeitraum, inkl. Warmwasser"))

    basis = [f"{days or 0} Tage", year.span]
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
    return _de(value, 0)


def format_local(iso: str | None, tz: tzinfo) -> str:
    if not iso:
        return "nie"
    return datetime.fromisoformat(iso).astimezone(tz).strftime("%d.%m.%Y %H:%M")
