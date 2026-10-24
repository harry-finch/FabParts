#!/bin/sh
set -eu
cd "$(dirname "$0")/../../.."
.venv/bin/python -m pip install 'pyinstaller==6.16.0'
cd prototypes/fabparts-tech-01
npm ci
rustup toolchain install 1.90.0 --profile minimal
cargo +1.90.0 fetch --locked --manifest-path src-tauri/Cargo.toml
