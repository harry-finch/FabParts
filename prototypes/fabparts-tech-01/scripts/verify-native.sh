#!/bin/sh
set -eu
cd "$(dirname "$0")/../../.."
root="$PWD"
mkdir -p local-data/fabparts-tech01b
report="local-data/fabparts-tech01b/packaged-smoke-$(date -u +%Y%m%dT%H%M%SZ)-$$.json"
.venv/bin/python prototypes/fabparts-tech-01/scripts/smoke-packaged.py \
  --binary "$root/prototypes/fabparts-tech-01/src-tauri/target/release/bundle/macos/FabParts TECH-01.app/Contents/MacOS/fabparts-engine" \
  --data-dir "$root/local-data/fabparts-tech01/catalogue-copy" > "$report"
cat "$report"
exec .venv/bin/python prototypes/fabparts-tech-01/scripts/check-native-lifecycle.py "$@"
