#!/usr/bin/env bash
set -euo pipefail

if [ -n "${LOCALAPPDATA:-}" ]; then
  COS_HOME="${HERMES_HOME:-$LOCALAPPDATA/hermes}"
  COS_HOME="${COS_HOME//\\//}"
  PYTHON="${LOCALAPPDATA//\\//}/hermes/hermes-agent/venv/Scripts/python.exe"
else
  COS_HOME="${HERMES_HOME:-$HOME/.hermes}"
  PYTHON="$(command -v python3 || command -v python)"
fi

ACTION="$COS_HOME/skills/productivity/ingest/scripts/actions.py"

if [ "${1:-}" = "gmail" ] && { [ "${2:-}" = "draft" ] || [ "${2:-}" = "reply-draft" ]; }; then
  HAS_TRACKING=false
  HAS_CLOSING=false
  for argument in "$@"; do
    if [ "$argument" = "--track-demo-state" ]; then
      HAS_TRACKING=true
    fi
    if [ "$argument" = "--closing" ]; then
      HAS_CLOSING=true
    fi
  done
  if [ "$HAS_TRACKING" = false ] && [ -f "$COS_HOME/chief-of-staff-workspace-state.json" ]; then
    set -- "$@" --track-demo-state
  fi
  if [ "$HAS_CLOSING" = false ]; then
    set -- "$@" --closing "Thanks"
  fi
fi

exec "$PYTHON" "$ACTION" "$@"
