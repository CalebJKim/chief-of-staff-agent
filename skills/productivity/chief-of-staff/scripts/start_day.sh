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

"$PYTHON" "$COS_HOME/skills/productivity/ingest/scripts/ingest.py" --max-messages 20 \
  && "$PYTHON" "$COS_HOME/skills/productivity/chief-of-staff/scripts/brief.py" --max-meetings 6 --max-mail 8 --max-files 4 --max-chars 14000
