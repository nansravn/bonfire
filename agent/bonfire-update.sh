#!/usr/bin/env bash
# Runs at every boot before the game and agent units: pull the configured ref, reinstall the
# agent package, refresh the units (spec 4.1). A failure here leaves the previous checkout in place.
# Stage 1 updates the checkout, then re-executes the NEW copy of this script for stage 2, because
# bash keeps executing the old file otherwise.
set -euo pipefail
cd /opt/bonfire
if [ "${BONFIRE_UPDATE_STAGE:-}" != "post" ]; then
  REF="${BONFIRE_GIT_REF:-main}"
  git fetch --quiet origin
  git checkout --quiet "$REF"
  if git show-ref --verify --quiet "refs/remotes/origin/$REF"; then
    git merge --ff-only --quiet "origin/$REF"
  fi
  # shellcheck disable=SC2093
  BONFIRE_UPDATE_STAGE=post exec "$0" "$@"
fi
# Stage 2: runs from the freshly checked-out script.
INTERVAL="${BONFIRE_IDLE_CHECK_INTERVAL:-1}"
/opt/bonfire/venv/bin/pip install --quiet "/opt/bonfire[agent]"
install -m 0644 agent/systemd/bonfire-update.service agent/systemd/bonfire-agent.service \
  agent/systemd/bonfire-agent.timer /etc/systemd/system/
mkdir -p /etc/systemd/system/bonfire-agent.timer.d
# An empty OnUnitActiveSec= clears every monotonic timer, so OnBootSec is restated.
printf '[Timer]\nOnUnitActiveSec=\nOnBootSec=30s\nOnUnitActiveSec=%smin\n' "$INTERVAL" > /etc/systemd/system/bonfire-agent.timer.d/interval.conf
systemctl daemon-reload
echo "bonfire-update: checked out $(git rev-parse --short HEAD) ($(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo detached))"
