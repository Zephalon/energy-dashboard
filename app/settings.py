from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from flask import current_app

ROOT = Path(__file__).resolve().parent.parent


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or default


def _bool(name: str, default: bool) -> bool:
    value = _env(name)
    return default if value is None else value.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    secret_key: str | None
    password_hash: str | None
    sync_token: str | None
    data_dir: Path
    timezone: str
    cookie_secure: bool

    sax_email: str | None
    sax_password: str | None
    sax_serial: str | None
    sax_max_age_hours: float
    pv_correction_factor: float

    vaillant_user: str | None
    vaillant_password: str | None
    vaillant_brand: str
    vaillant_country: str
    vaillant_max_age_hours: float
    vaillant_days_back: int
    vaillant_chunk_pause: float

    @property
    def db_path(self) -> Path:
        return self.data_dir / "energy.sqlite"

    @property
    def sources(self) -> list[str]:
        enabled = []
        if self.sax_email and self.sax_password and self.sax_serial:
            enabled.append("sax")
        if self.vaillant_user and self.vaillant_password:
            enabled.append("vaillant")
        return enabled

    def require_web(self) -> None:
        missing = [
            name
            for name, value in (
                ("SECRET_KEY", self.secret_key),
                ("APP_PASSWORD_HASH", self.password_hash),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(f"Fehlende Umgebungsvariablen: {', '.join(missing)}")


def load_settings() -> Settings:
    load_dotenv(_env("ENV_FILE", str(ROOT / ".env")))
    return Settings(
        secret_key=_env("SECRET_KEY"),
        password_hash=_env("APP_PASSWORD_HASH"),
        sync_token=_env("SYNC_TOKEN"),
        data_dir=Path(_env("DATA_DIR", str(ROOT / "data"))),
        timezone=_env("TIMEZONE", "Europe/Berlin"),
        cookie_secure=_bool("COOKIE_SECURE", True),
        sax_email=_env("SAX_EMAIL"),
        sax_password=_env("SAX_PASSWORD"),
        sax_serial=_env("SAX_SERIAL"),
        sax_max_age_hours=float(_env("SAX_MAX_AGE_HOURS", "1")),
        pv_correction_factor=float(_env("PV_CORRECTION_FACTOR", "1.2")),
        vaillant_user=_env("VAILLANT_USER"),
        vaillant_password=_env("VAILLANT_PASSWORD"),
        vaillant_brand=_env("VAILLANT_BRAND", "vaillant"),
        vaillant_country=_env("VAILLANT_COUNTRY", "germany"),
        vaillant_max_age_hours=float(_env("VAILLANT_MAX_AGE_HOURS", "1")),
        vaillant_days_back=int(_env("VAILLANT_DAYS_BACK", "45")),
        vaillant_chunk_pause=float(_env("VAILLANT_CHUNK_PAUSE", "5")),
    )


def current_settings() -> Settings:
    return current_app.extensions["settings"]
