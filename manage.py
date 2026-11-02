#!/usr/bin/env python3
"""Kommandozeile für Sync, Backfill und Passwort-Hash.

  python manage.py sync [--source sax|vaillant] [--force]
  python manage.py backfill --from 2025-01 [--to 2026-10] [--source vaillant]
  python manage.py hash-password
"""

from __future__ import annotations

import argparse
import getpass
import json
import logging
import sys
from datetime import date, timedelta


def _month(value: str) -> date:
    return date.fromisoformat(f"{value}-01")


def _month_end(value: str) -> date:
    first = _month(value)
    return (first + timedelta(days=32)).replace(day=1) - timedelta(days=1)


def cmd_hash_password(_args) -> None:
    from werkzeug.security import generate_password_hash

    password = getpass.getpass("Neues Passwort: ")
    if password != getpass.getpass("Wiederholen: "):
        sys.exit("Passwörter stimmen nicht überein.")
    if len(password) < 12:
        sys.exit("Mindestens 12 Zeichen.")
    print(f"APP_PASSWORD_HASH='{generate_password_hash(password, method='pbkdf2:sha256:600000')}'")


def cmd_sync(args) -> None:
    from app import sync
    from app.db import Store
    from app.settings import load_settings

    settings = load_settings()
    sources = [args.source] if args.source else None
    start = _month(args.from_month) if getattr(args, "from_month", None) else None
    end = _month_end(args.to_month) if getattr(args, "to_month", None) else None
    if end:
        end = min(end, sync.local_today(settings))
    result = sync.run(settings, Store(settings.db_path), sources=sources, start=start, end=end, force=args.force)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    p_sync = sub.add_parser("sync", help="Fällige Quellen synchronisieren")
    p_sync.add_argument("--source", choices=["sax", "vaillant"])
    p_sync.add_argument("--force", action="store_true", help="Max-Alter ignorieren")
    p_sync.set_defaults(func=cmd_sync)

    p_back = sub.add_parser("backfill", help="Historie ab Monat nachladen")
    p_back.add_argument("--from", dest="from_month", required=True, metavar="YYYY-MM")
    p_back.add_argument("--to", dest="to_month", metavar="YYYY-MM")
    p_back.add_argument("--source", choices=["sax", "vaillant"])
    p_back.set_defaults(func=cmd_sync, force=True)

    p_hash = sub.add_parser("hash-password", help="Hash für APP_PASSWORD_HASH erzeugen")
    p_hash.set_defaults(func=cmd_hash_password)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
