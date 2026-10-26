#!/bin/sh
set -eu
cd "$(dirname "$0")/../../.."
root="$PWD"
triple="$(rustc --print host-tuple)"
build_python="${FABPARTS_BUILD_PYTHON:-$root/.venv/bin/python}"
PYINSTALLER_CONFIG_DIR="$root/local-data/fabparts-tech01/pyinstaller-cache" "$build_python" -m PyInstaller --noconfirm --clean --onefile \
  --name "fabparts-engine-$triple" \
  --paths "$root/src" --exclude-module PySide6 --exclude-module shiboken6 \
  --collect-data alembic --add-data "$root/src/kipartmanager/infrastructure/migrations:kipartmanager/infrastructure/migrations" --exclude-module tkinter \
  --distpath "$root/prototypes/fabparts-tech-01/src-tauri/binaries" \
  --workpath "$root/local-data/fabparts-tech01/pyinstaller" \
  --specpath "$root/local-data/fabparts-tech01" \
  prototypes/fabparts-tech-01/scripts/sidecar_entry.py
