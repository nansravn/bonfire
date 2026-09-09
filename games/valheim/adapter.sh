#!/usr/bin/env bash
# Bonfire adapter for Valheim. Implements docs/contracts/adapter-interface.md.
# Stdout carries only contract values; every diagnostic goes to stderr.
set -euo pipefail

: "${BONFIRE_GAME:?}" "${BONFIRE_ADAPTER_DIR:?}" "${BONFIRE_DATA_DIR:?}" \
  "${BONFIRE_BACKUP_DIR:?}" "${BONFIRE_STOP_GRACE_SECONDS:?}"
export BONFIRE_GAME_ENV_FILE="${BONFIRE_GAME_ENV_FILE:-/etc/bonfire/${BONFIRE_GAME}.env}"
PY="${BONFIRE_PYTHON:-/opt/bonfire/venv/bin/python}"
RUN_DIR="${BONFIRE_RUN_DIR:-/run/bonfire}"
RESTART_CACHE="$RUN_DIR/${BONFIRE_GAME}.restarts"
A2S_HOST=127.0.0.1
A2S_PORT=2457

cd "$BONFIRE_ADAPTER_DIR"

log() { echo "adapter[$BONFIRE_GAME]: $*" >&2; }
compose() { docker compose --project-directory "$BONFIRE_ADAPTER_DIR" "$@"; }
container_id() { compose ps -q valheim 2>/dev/null || true; }
container_status() {  # prints "<status> <restart_count>" or nothing
  local cid; cid=$(container_id)
  [ -n "$cid" ] && docker inspect -f '{{.State.Status}} {{.RestartCount}}' "$cid" 2>/dev/null || true
}
a2s() { "$PY" "$BONFIRE_ADAPTER_DIR/a2s_query.py" "$A2S_HOST" "$A2S_PORT"; }

cmd_install() {
  compose pull >&2
}

cmd_start() {
  mkdir -p "$BONFIRE_DATA_DIR/config" "$BONFIRE_DATA_DIR/server" "$RUN_DIR"
  compose up -d >&2
  echo 0 > "$RESTART_CACHE"
  local st; st=$(container_status)
  [ "${st%% *}" = "running" ] || { log "container is not running after start: $st"; return 1; }
}

cmd_stop() {
  compose stop --timeout "$BONFIRE_STOP_GRACE_SECONDS" >&2
  compose down >&2
}

cmd_is_ready() {
  local rc=0
  a2s >/dev/null 2>&1 || rc=$?
  return "$rc"
}

cmd_player_count() {
  local out
  if out=$(a2s 2>/dev/null); then
    echo "${out%% *}"
    return 0
  fi
  log "A2S did not answer; falling back to log parsing"
  local cid; cid=$(container_id)
  if [ -z "$cid" ] || [ "$(container_status | cut -d' ' -f1)" != "running" ]; then
    echo unknown
    return 0
  fi
  local logs joins leaves
  logs=$(docker logs --since 24h "$cid" 2>&1 || true)
  if ! grep -q 'Game server connected' <<<"$logs"; then
    echo unknown
    return 0
  fi
  joins=$(grep -c 'Got connection SteamID' <<<"$logs" || true)
  leaves=$(grep -c 'Closing socket' <<<"$logs" || true)
  local n=$((joins - leaves))
  [ "$n" -lt 0 ] && n=0
  echo "$n"
}

cmd_health() {
  local st; st=$(container_status)
  if [ -z "$st" ]; then
    echo crashed
    return 0
  fi
  local status restarts prev=0
  status=${st%% *}; restarts=${st##* }
  mkdir -p "$RUN_DIR"
  [ -f "$RESTART_CACHE" ] && prev=$(cat "$RESTART_CACHE")
  echo "$restarts" > "$RESTART_CACHE"
  case "$status" in
    running)    if [ "$restarts" -gt "$prev" ]; then echo degraded; else echo ok; fi ;;
    restarting) echo degraded ;;
    *)          echo crashed ;;
  esac
}

cmd_backup() {
  local world
  world=$(sed -n 's/^WORLD_NAME=//p' "$BONFIRE_GAME_ENV_FILE" | tr -d '"' | head -1)
  [ -n "$world" ] || { log "WORLD_NAME not set in $BONFIRE_GAME_ENV_FILE"; return 1; }
  local src="$BONFIRE_DATA_DIR/config/worlds_local"
  local dst; dst="$BONFIRE_BACKUP_DIR/$(date -u +%Y%m%dT%H%M%SZ)"
  [ -f "$src/$world.db" ] && [ -f "$src/$world.fwl" ] || { log "world files for $world missing in $src"; return 1; }
  mkdir -p "$dst"
  cp -p "$src/$world.db" "$src/$world.fwl" "$dst/"
  log "backed up $world to $dst"
}

case "${1:-}" in
  install|start|stop|is_ready|player_count|health|backup) "cmd_$1" ;;
  *) log "usage: adapter.sh {install|start|stop|is_ready|player_count|health|backup}"; exit 2 ;;
esac
