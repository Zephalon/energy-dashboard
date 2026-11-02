from __future__ import annotations

import hmac
from datetime import date
from zoneinfo import ZoneInfo

from flask import Blueprint, abort, jsonify, render_template, request

from . import metrics, sync
from .db import current_store
from .settings import current_settings

bp = Blueprint("views", __name__)


@bp.get("/")
def index():
    settings, store = current_settings(), current_store()
    tz = ZoneInfo(settings.timezone)
    states = store.states()
    sync_info = [
        {
            "label": sync.LABELS[source],
            "success": metrics.format_local(states[source]["last_success"] if source in states else None, tz),
            "error": states[source]["last_error"] if source in states else None,
        }
        for source in settings.sources
    ]
    years = metrics.build_years(*store.monthly(), sync.LABELS, settings.pv_correction_factor)
    selected = next((y for y in years if y.label == request.args.get("year")), years[0] if years else None)
    return render_template(
        "months.html",
        years=years,
        year=selected,
        pv_factor=settings.pv_correction_factor,
        groups=metrics.GROUPS,
        kpis=[metrics.COLUMNS[k] for k in metrics.KPI_KEYS],
        chart=metrics.chart_data(selected) if selected else None,
        sync_info=sync_info,
    )


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
