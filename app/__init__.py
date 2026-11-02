from __future__ import annotations

import logging
from datetime import timedelta

from flask import Flask

from . import auth, metrics, views
from .db import Store
from .settings import Settings, load_settings

CSP = (
    "default-src 'self'; "
    "script-src 'self' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "form-action 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'none'"
)


def _security_headers(response):
    response.headers.setdefault("Content-Security-Policy", CSP)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Cache-Control", "no-store")
    return response


def create_app(settings: Settings | None = None) -> Flask:
    settings = settings or load_settings()
    settings.require_web()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=settings.secret_key,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=settings.cookie_secure,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    )
    app.extensions["settings"] = settings
    app.extensions["store"] = Store(settings.db_path)

    app.register_blueprint(auth.bp)
    app.register_blueprint(views.bp)
    app.before_request(auth.require_login)
    app.after_request(_security_headers)
    app.jinja_env.globals["csrf_token"] = auth.csrf_token
    app.jinja_env.filters["fmt"] = metrics.fmt
    return app
