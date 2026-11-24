from __future__ import annotations

import hmac
from datetime import date, datetime
from zoneinfo import ZoneInfo

from flask import Blueprint, abort, jsonify, render_template, request

from . import forecast, metrics, sync
from .db import current_store
from .settings import current_settings

bp = Blueprint("views", __name__)


def _sync_info(settings, store) -> list[dict]:
    tz = ZoneInfo(settings.timezone)
    states = store.states()
    return [
        {
            "label": sync.LABELS[source],
            "success": metrics.format_local(states[source]["last_success"] if source in states else None, tz),
            "error": states[source]["last_error"] if source in states else None,
        }
        for source in settings.sources
    ]


@bp.get("/")
def index():
    settings, store = current_settings(), current_store()
    tz = ZoneInfo(settings.timezone)
    context = {
        "pv_factor": settings.pv_correction_factor,
        "groups": metrics.GROUPS,
        "kpis": [metrics.COLUMNS[k] for k in metrics.KPI_KEYS],
        "sync_info": _sync_info(settings, store),
    }
    months = metrics.build_months(*store.monthly(), sync.LABELS, settings.pv_correction_factor)
    if not months:
        return render_template("months.html", selection=None, **context)

    keys = [m.key for m in months]
    default = metrics.default_range(keys, current=datetime.now(tz).strftime("%Y-%m"))
    start, end = metrics.resolve_range(keys, request.args.get("from"), request.args.get("to"), default)
    selection = metrics.select(months, start, end, settings.pv_correction_factor)
    stats, stats_basis = metrics.range_stats(selection, settings.house_area_m2, settings.electricity_price)
    return render_template(
        "months.html",
        selection=selection,
        months=months,
        range_from=start,
        range_to=end,
        is_default=(start, end) == default,
        default_months=metrics.DEFAULT_MONTHS,
        chart=metrics.chart_data(selection),
        stats=stats,
        stats_basis=stats_basis,
        **context,
    )


@bp.get("/prognosen")
def forecast_page():
    settings, store = current_settings(), current_store()
    context = {"sync_info": _sync_info(settings, store), "has_location": "dwd" in settings.sources}
    # All months are selectable here, earlier periods may contain the coldest days
    months = metrics.build_months(*store.monthly(), sync.LABELS, display_from="")
    if not months:
        return render_template("prognosen.html", model=None, **context)

    keys = [m.key for m in months]
    today = sync.local_today(settings).isoformat()
    default = metrics.default_range(keys, current=today[:7])
    start, end = metrics.resolve_range(keys, request.args.get("from"), request.args.get("to"), default)
    points = forecast.points(store.daily(f"{start}-01", f"{end}-31"), today)
    model = forecast.fit(points)
    context.update(
        months=months,
        range_from=start,
        range_to=end,
        is_default=(start, end) == default,
        points=points,
        model=model,
        min_days=forecast.MIN_HEATING_DAYS,
        span=metrics.span_label(start, end),
    )
    if model:
        rows = forecast.curve(model)
        context.update(
            stats=forecast.stats(model),
            table=forecast.table(rows, settings.electricity_price),
            chart=forecast.chart_data(points, rows),
        )
    return render_template("prognosen.html", **context)


@bp.get("/sync")
def sync_endpoint():
    """Für externe Scheduler (z. B. cron-job.org). Optional ?from=YYYY-MM für Backfill."""
    settings = current_settings()
    supplied = request.headers.get("X-Sync-Token") or request.args.get("token", "")
    if not settings.sync_token or not hmac.compare_digest(supplied, settings.sync_token):
        abort(404)

    start = None
    if request.args.get("from"):
        try:
            start = date.fromisoformat(f"{request.args['from']}-01")
        except ValueError:
            abort(400)
    sources = request.args.getlist("source") or None
    return jsonify(sync.run(settings, current_store(), sources=sources, start=start))
