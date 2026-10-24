#!/bin/sh
set -eu
cd "$(dirname "$0")/../../.."
./prototypes/fabparts-tech-01/scripts/build-sidecar.sh
cd prototypes/fabparts-tech-01
npm run check
npm test
npm run tauri -- build --bundles app -- --locked "$@"
