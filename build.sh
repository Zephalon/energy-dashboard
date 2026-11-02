#!/usr/bin/env bash
# Builds a self-contained upload bundle for Netcup (Passenger, no venv on server).
# Packages are fetched as Linux wheels matching the server's Python, not the local one.
set -euo pipefail

cd "$(dirname "$0")"

BUILD_DIR="build"
TARGET_PYTHON="${TARGET_PYTHON:-3.11}"
TARGET_ABI="cp${TARGET_PYTHON/./}"

if [[ -x .venv/bin/python ]]; then
  PYTHON="${PYTHON:-.venv/bin/python}"
else
  PYTHON="${PYTHON:-python3}"
fi

echo "==> Cleaning $BUILD_DIR/"
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR/public" "$BUILD_DIR/tmp"

echo "==> Copying app code"
cp passenger_wsgi.py manage.py requirements.txt "$BUILD_DIR/"
rsync -a --exclude '__pycache__' --exclude '*.pyc' --exclude '.DS_Store' app "$BUILD_DIR/"

echo "==> Installing packages for CPython $TARGET_PYTHON (manylinux x86_64)"
"$PYTHON" -m pip install \
  --quiet \
  --disable-pip-version-check \
  --no-compile \
  --target "$BUILD_DIR/packages" \
  --platform manylinux2014_x86_64 \
  --platform manylinux_2_28_x86_64 \
  --implementation cp \
  --python-version "$TARGET_PYTHON" \
  --abi "$TARGET_ABI" \
  --only-binary=:all: \
  -r requirements.txt

# Console scripts carry shebangs pointing at the local machine.
rm -rf "$BUILD_DIR/packages/bin"

touch "$BUILD_DIR/public/.gitkeep" "$BUILD_DIR/tmp/restart.txt"

echo "==> Done: $BUILD_DIR/ ($(du -sh "$BUILD_DIR" | cut -f1))"
echo "    Upload the contents of $BUILD_DIR/ to the app root. Keep .env and data/ on the server."
