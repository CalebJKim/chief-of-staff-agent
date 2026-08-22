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

if [ "${1:-}" = "workstream" ]; then
  shift
  exec "$PYTHON" "$COS_HOME/skills/productivity/chief-of-staff/scripts/workstream.py" "$@"
fi

if [ "${1:-}" = "gmail" ] && [ "${2:-}" = "draft" ] && [ -f "$COS_HOME/chief-of-staff-workspace-state.json" ]; then
  for argument in "$@"; do
    if [ "$argument" = "--track-demo-state" ]; then
      exec "$PYTHON" "$ACTION" "$@"
    fi
  done
  set -- "$@" --track-demo-state
fi

exec "$PYTHON" "$ACTION" "$@"
