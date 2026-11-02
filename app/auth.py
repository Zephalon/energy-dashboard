from __future__ import annotations

import hmac
import secrets
import time

from flask import Blueprint, abort, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from .db import current_store
from .settings import current_settings

bp = Blueprint("auth", __name__)

MAX_FAILURES = 5
FAILURE_WINDOW_SECONDS = 15 * 60
PUBLIC_ENDPOINTS = {"auth.login", "views.sync_endpoint", "static"}


def csrf_token() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def check_csrf() -> None:
    sent, expected = request.form.get("csrf", ""), session.get("csrf", "")
    if not expected or not hmac.compare_digest(sent, expected):
        abort(400)


def require_login():
    if request.endpoint in PUBLIC_ENDPOINTS or session.get("auth"):
        return None
    return redirect(url_for("auth.login"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("auth"):
        return redirect(url_for("views.index"))

    error, status = None, 200
    if request.method == "POST":
        check_csrf()
        store = current_store()
        ip = request.remote_addr or "unknown"
        if store.login_failures(ip, FAILURE_WINDOW_SECONDS) >= MAX_FAILURES:
            error, status = "Zu viele Fehlversuche. Bitte in 15 Minuten erneut versuchen.", 429
        elif check_password_hash(current_settings().password_hash, request.form.get("password", "")):
            session.clear()
            session.permanent = True
            session["auth"] = True
            return redirect(url_for("views.index"))
        else:
            store.add_login_failure(ip)
            time.sleep(1)
            error, status = "Falsches Passwort.", 401
    return render_template("login.html", error=error), status


@bp.post("/logout")
def logout():
    check_csrf()
    session.clear()
    return redirect(url_for("auth.login"))
