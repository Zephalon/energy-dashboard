# Energy Dashboard: Solar (SAX Power) + Wärmepumpe (Vaillant)

Kleine, passwortgeschützte Flask-App für das eigene Zuhause. Sie holt Tageswerte einer SAX-Power-Speicheranlage und einer Vaillant-Wärmepumpe (myVAILLANT), speichert sie in SQLite und zeigt sie nach Monaten gruppiert mit Kennzahlen und Diagrammen an.

> **Hinweis:** Beide Schnittstellen sind inoffiziell und nicht von SAX Power oder Vaillant unterstützt. Sie können sich jederzeit ändern. Das Projekt steht in keiner Verbindung zu den Herstellern.

## Features

- Monatsübersicht pro Jahr mit Kennzahlen (Hausverbrauch, Arbeitszahl, Autarkie, Eigenverbrauch …)
- Diagramme (Chart.js) pro Jahr
- Synchronisation per HTTP-Endpoint oder CLI, mit Max-Alter pro Quelle und Datei-Lock
- Ein Benutzer, PBKDF2-Passwort-Hash, CSRF-Schutz, Login-Sperre, strikte Security-Header
- Läuft ohne venv auf Shared Hosting mit Phusion Passenger (z. B. Plesk)

## Projektstruktur

```
passenger_wsgi.py      Einstieg für Phusion Passenger (bindet optional packages/ ein)
manage.py              CLI: sync, backfill, hash-password
build.sh               Baut ein Upload-Bundle mit Linux-Wheels nach build/
requirements.txt
.env.example           Vorlage für die Konfiguration
app/
  __init__.py          App-Factory, Security-Header
  settings.py          Konfiguration aus .env
  auth.py              Login, Logout, CSRF, Login-Sperre
  db.py                SQLite: daily(day, source, metric, kwh), sync_state, login_failures
  sync.py              Sync mit Max-Alter pro Quelle + Datei-Lock
  metrics.py           Monatsaggregation, abgeleitete Kennzahlen, Spalten- und Chartdefinition
  views.py             Übersicht (/) und Sync-Endpoint (/sync)
  sources/sax.py       SAX-Power-API
  sources/vaillant.py  myVAILLANT über myPyllant
  templates/           Jinja + Tailwind (CDN)
  static/charts.js     Diagramme (Chart.js, CDN)
```

Laufzeitdaten (`data/`, `.env`) und Build-Artefakte (`build/`) sind nicht im Repository.

## Voraussetzungen

- Python >= 3.10 (wegen [myPyllant](https://github.com/signalkraft/myPyllant))
- Zugangsdaten für SAX Power (inkl. Seriennummer) und/oder myVAILLANT. Eine Quelle ist nur aktiv, wenn ihre Zugangsdaten gesetzt sind.

## Lokal starten

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env             # ausfüllen
.venv/bin/python manage.py hash-password
.venv/bin/python manage.py backfill --from 2026-01
COOKIE_SECURE=false .venv/bin/flask --app passenger_wsgi:application run
```

## Konfiguration

Alle Einstellungen kommen aus `.env` (siehe [`.env.example`](.env.example)). Pflicht für die Web-App sind `SECRET_KEY` und `APP_PASSWORD_HASH`, für `/sync` zusätzlich `SYNC_TOKEN`.

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # SECRET_KEY / SYNC_TOKEN
python manage.py hash-password                                  # APP_PASSWORD_HASH
```

## CLI

```bash
python manage.py sync [--source sax|vaillant] [--force]
python manage.py backfill --from YYYY-MM [--to YYYY-MM] [--source sax|vaillant]
python manage.py hash-password
```

## Aktualisierung ohne Cron

- Seitenaufrufe synchronisieren nie, aktualisiert wird nur über `/sync` (oder `manage.py sync`).
- Ein externer Scheduler (z. B. [cron-job.org](https://cron-job.org)) ruft regelmäßig `GET /sync?token=<SYNC_TOKEN>` auf, alternativ mit Header `X-Sync-Token`.
- Jede Quelle wird höchstens einmal pro Stunde abgefragt (`SAX_MAX_AGE_HOURS`, `VAILLANT_MAX_AGE_HOURS`). Das Max-Alter zählt ab dem letzten Versuch, auch Fehlschläge hämmern also nicht.
- Backfill per HTTP: `/sync?token=…&from=2025-01&source=sax`. Für Vaillant lieber per CLI, da es wegen der Pausen zwischen den Blöcken lange dauert.

## Deployment (Passenger, z. B. Plesk)

Auf vielen Shared-Hostern gibt es kein venv. `passenger_wsgi.py` hängt stattdessen einen hochgeladenen `packages/`-Ordner in den Modul-Suchpfad.

1. **Python-Version prüfen.** Per SSH `python3 --version`. Der Build zielt standardmäßig auf 3.11, für eine andere Version `TARGET_PYTHON=3.12 ./build.sh`.
2. **Bauen.** Lokal `./build.sh` ausführen. Ergebnis ist `build/` mit `app/`, `packages/` (Linux-x86_64-Wheels), leerem `public/` und `tmp/restart.txt`. `.env` und `data/` sind bewusst nicht enthalten.
3. **Hochladen.** Den Inhalt von `build/` in einen Ordner außerhalb des Webroots legen, z. B. `~/energie/`. Beim ersten Mal `.env` (aus `.env.example`) dort anlegen und `chmod 600 .env` setzen. `data/` entsteht von selbst.
4. **Passenger-App** anlegen: Anwendungsstamm `~/energie`, Startdatei `passenger_wsgi.py`, Dokumentenstamm `~/energie/public`.
5. **HTTPS** aktivieren und auf HTTPS umleiten. Das Session-Cookie ist `Secure`, ohne HTTPS klappt der Login nicht.
6. **Historie laden:** `python3 manage.py backfill --from 2026-01`.
7. **Scheduler** einrichten (Cron, falls verfügbar, sonst cron-job.org, siehe oben).

Nach Code-Änderungen startet Passenger die App neu, wenn `tmp/restart.txt` im App-Root angefasst wird (`mkdir -p tmp && touch tmp/restart.txt`).

## Kennzahlen

| Kennzahl | Formel |
| --- | --- |
| Hausverbrauch | PV + Netzbezug − Einspeisung + Akku entladen − Akku laden |
| ohne WP | Hausverbrauch − WP-Strom |
| Arbeitszahl | erzeugte Wärme / WP-Strom (Fallback: (Strom + Umweltenergie) / Strom) |
| WP-Anteil | WP-Strom / Hausverbrauch |
| Autarkie | 1 − Netzbezug / Hausverbrauch |
| Eigenverbrauch | (PV − Einspeisung) / PV |
| Ø pro Tag | Jahressumme / Tage mit Daten (SAX, für WP-Strom Vaillant) |
| Ø Stromkosten pro Monat | Ø pro Tag × 365,25 / 12 × `ELECTRICITY_PRICE` (ohne Grundgebühr) |
| Heizenergie pro m² | WP-Strom bzw. erzeugte Wärme im Zeitraum / `HOUSE_AREA_M2` (inkl. Warmwasser) |

Die Jahresstatistik bezieht sich auf die angezeigten Monate des gewählten Jahres. Ohne `ELECTRICITY_PRICE` bzw. `HOUSE_AREA_M2` entfällt die jeweilige Karte.

PV ist der SAX-Wert × `PV_CORRECTION_FACTOR` (Default 1,2). Der Faktor greift nur in der Anzeige, in SQLite stehen die Rohwerte. Angezeigt werden Monate ab `DISPLAY_FROM` in `app/metrics.py`, das Jahr wählt man über den Umschalter im Header (`/?year=2026`).

## SAX-Felder

Werte kommen in Wh/Tag. Positiv bedeutet Fluss ins Haus, negativ aus dem Haus.

| Key | Bedeutung |
| --- | --- |
| `m2` | Netzbezug |
| `m2N` | Netzeinspeisung |
| `m4` | PV-Erzeugung |
| `m5` | Akku entladen |
| `m5N` | Akku laden |

`m5`/`m5N` wurden per Plausibilität zugeordnet (andersherum wäre über Monate mehr entladen als geladen worden).

## Sicherheit

- Ein Benutzer, das Passwort steht als PBKDF2-Hash in `.env`. Session-Cookie mit `HttpOnly`, `Secure` und `SameSite=Lax`, Gültigkeit 30 Tage.
- CSRF-Token auf Login und Logout, Sperre nach 5 Fehlversuchen in 15 Minuten pro IP.
- CSP, `X-Frame-Options: DENY`, `noindex`, `Cache-Control: no-store`.
- `/sync` ohne gültiges Token liefert 404.
