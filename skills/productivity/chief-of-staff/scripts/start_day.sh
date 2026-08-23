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

TOP_N=3
if [ "${1:-}" = "--top" ]; then
  if [ "$#" -ne 2 ]; then
    echo '{"ok":false,"error":"Usage: start_day.sh [--top POSITIVE_INTEGER]"}' >&2
    exit 2
  fi
  TOP_N="$2"
  shift 2
fi
if [ "$#" -ne 0 ] || ! [[ "$TOP_N" =~ ^[1-9][0-9]*$ ]]; then
  echo '{"ok":false,"error":"Usage: start_day.sh [--top POSITIVE_INTEGER]"}' >&2
  exit 2
fi

"$PYTHON" "$COS_HOME/skills/productivity/ingest/scripts/ingest.py" --max-messages 20 >/dev/null \
  && "$PYTHON" "$COS_HOME/skills/productivity/chief-of-staff/scripts/brief.py" --max-meetings 6 --max-mail 8 --max-files 4 --max-chars 14000 --top "$TOP_N" --reply-only
