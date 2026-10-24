#!/bin/sh
set -eu
cd "$(dirname "$0")/../../.."
root="$PWD"
triple="$(rustc --print host-tuple)"
PYINSTALLER_CONFIG_DIR="$root/local-data/fabparts-tech01/pyinstaller-cache" .venv/bin/python -m PyInstaller --noconfirm --clean --onefile \
  --name "fabparts-engine-$triple" \
  --paths "$root/src" --exclude-module PySide6 --exclude-module shiboken6 \
  --exclude-module alembic --exclude-module tkinter \
  --distpath "$root/prototypes/fabparts-tech-01/src-tauri/binaries" \
  --workpath "$root/local-data/fabparts-tech01/pyinstaller" \
  --specpath "$root/local-data/fabparts-tech01" \
  prototypes/fabparts-tech-01/scripts/sidecar_entry.py
