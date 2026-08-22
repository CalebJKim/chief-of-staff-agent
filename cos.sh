#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ] || [[ ! "$1" =~ ^[1-3]$ ]]; then
  printf '%s\n' 'Usage: cos.sh 1|2|3' >&2
  exit 2
fi

exec bash "$HERMES_HOME/skills/productivity/chief-of-staff/scripts/action.sh" workstream "$1" --confirm
