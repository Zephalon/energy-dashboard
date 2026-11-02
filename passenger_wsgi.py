import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


# Netcup Webhosting stellt keinen eigenen Python-Interpreter/venv bereit.
# Deshalb werden lokal installierte Pakete ueber einen hochgeladenen
# "packages"-Ordner in den Modul-Suchpfad eingehaengt statt ein venv zu
# aktivieren (os.execl auf ein venv-Python funktioniert hier NICHT, da der
# venv-Interpreter nur ein Symlink auf den lokalen Rechner ist).
PACKAGES = ROOT / "packages"
if PACKAGES.exists():
    sys.path.insert(0, str(PACKAGES))


sys.path.insert(0, str(ROOT))


from app import create_app  # noqa: E402


application = create_app()

