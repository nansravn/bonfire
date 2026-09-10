#!/usr/bin/env bash
# Runs at every boot before the game and agent units: pull the configured ref, reinstall the
# agent package, refresh the units (spec 4.1). A failure here leaves the previous checkout in place.
set -euo pipefail
REF="${BONFIRE_GIT_REF:-main}"
INTERVAL="${BONFIRE_IDLE_CHECK_INTERVAL:-1}"
cd /opt/bonfire
git fetch --quiet origin
git checkout --quiet "$REF"
if git show-ref --verify --quiet "refs/remotes/origin/$REF"; then
  git merge --ff-only --quiet "origin/$REF"
fi
/opt/bonfire/venv/bin/pip install --quiet "/opt/bonfire[agent]"
install -m 0644 agent/systemd/bonfire-update.service agent/systemd/bonfire-agent.service \
  agent/systemd/bonfire-agent.timer /etc/systemd/system/
mkdir -p /etc/systemd/system/bonfire-agent.timer.d
printf '[Timer]\nOnUnitActiveSec=\nOnUnitActiveSec=%smin\n' "$INTERVAL" > /etc/systemd/system/bonfire-agent.timer.d/interval.conf
systemctl daemon-reload
echo "bonfire-update: checked out $(git rev-parse --short HEAD) ($REF)"
