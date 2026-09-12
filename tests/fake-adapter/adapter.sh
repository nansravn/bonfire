#!/usr/bin/env bash
# Fake adapter for unit tests (docs/testing.md). Each subcommand's result is scripted by
# FAKE_* variables; every invocation is appended to $FAKE_LOG. Never touches Docker.
set -u
sub="${1:-}"
[ -n "${FAKE_LOG:-}" ] && echo "$sub" >> "$FAKE_LOG"
rc_var="FAKE_$(echo "$sub" | tr '[:lower:]' '[:upper:]')_RC"
rc="${!rc_var:-0}"
case "$sub" in
  install|start|stop|backup) exit "$rc" ;;
  is_ready) exit "${FAKE_IS_READY:-1}" ;;
  player_count) [ "$rc" = 0 ] && echo "${FAKE_PLAYER_COUNT:-0}"; exit "$rc" ;;
  health) [ "$rc" = 0 ] && echo "${FAKE_HEALTH:-ok}"; exit "$rc" ;;
  *) echo "fake adapter: unknown subcommand $sub" >&2; exit 2 ;;
esac
