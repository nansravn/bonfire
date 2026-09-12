#!/usr/bin/env bash
# Stage the Function deployment: function/ files, a copy of the bonfire package (spec 4.2),
# and vendored third-party dependencies. Flex Consumption's zip_deploy_file publishes the
# zip as-is (no remote build), so the packages must already be in the zip, under
# .python_packages/lib/site-packages, where the Python worker adds them to sys.path.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT="$ROOT/dist/function"
rm -rf "$OUT"
mkdir -p "$OUT"
cp "$ROOT/function/function_app.py" "$ROOT/function/host.json" "$ROOT/function/requirements.txt" "$OUT/"
cp -R "$ROOT/bonfire" "$OUT/bonfire"

PACKAGES="$OUT/.python_packages/lib/site-packages"
mkdir -p "$PACKAGES"
if command -v uv >/dev/null 2>&1; then
  uv pip install --quiet \
    --target "$PACKAGES" \
    --python-platform x86_64-manylinux2014 --python-version 3.12 --only-binary :all: \
    -r "$ROOT/function/requirements.txt"
else
  PIP="${PIP:-python3 -m pip}"
  $PIP install --quiet --disable-pip-version-check \
    --target "$PACKAGES" \
    --platform manylinux2014_x86_64 --python-version 3.12 --implementation cp --only-binary=:all: \
    -r "$ROOT/function/requirements.txt"
fi

find "$OUT" -name __pycache__ -type d -prune -exec rm -rf {} +
echo "$OUT"
