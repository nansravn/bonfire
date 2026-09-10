#!/usr/bin/env bash
# Stage the Function deployment: function/ files plus a copy of the bonfire package (spec 4.2).
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT="$ROOT/dist/function"
rm -rf "$OUT"
mkdir -p "$OUT"
cp "$ROOT/function/function_app.py" "$ROOT/function/host.json" "$ROOT/function/requirements.txt" "$OUT/"
cp -R "$ROOT/bonfire" "$OUT/bonfire"
find "$OUT" -name __pycache__ -type d -prune -exec rm -rf {} +
echo "$OUT"
