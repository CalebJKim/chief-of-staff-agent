#!/usr/bin/env bash
# Common setup for the native helper; no Python or persistent shell state needed.
set -euo pipefail
COS_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
COS_EXECUTABLE="$COS_SCRIPT_DIR/cos-actions.exe"
if [[ ! -f "$COS_EXECUTABLE" ]]; then
  printf '%s\n' "Missing native runtime: $COS_EXECUTABLE (this bundle targets Windows ARM64)." >&2
  return 2
fi
if [[ -z "${COS_STATE_DIR:-}" ]]; then
  if [[ -n "${HERMES_HOME:-}" ]]; then
    COS_STATE_DIR="$HERMES_HOME"
  elif [[ -n "${LOCALAPPDATA:-}" ]]; then
    COS_STATE_DIR="$LOCALAPPDATA/hermes/profiles/chief-of-staff"
  else
    COS_STATE_DIR="$HOME/.hermes/profiles/chief-of-staff"
  fi
fi
if [[ ! -d "$COS_STATE_DIR" ]]; then
  printf '%s\n' "Hermes profile not found: $COS_STATE_DIR. Set HERMES_HOME to the active profile." >&2
  return 2
fi
COS_STATE_DIR="$(cd -- "$COS_STATE_DIR" && pwd)"
case "$(uname -s)" in
  MINGW*|MSYS*) COS_STATE_DIR="$(cygpath -m "$COS_STATE_DIR")" ;;
esac
export COS_STATE_DIR COS_EXECUTABLE
export MSYS2_ARG_CONV_EXCL='*' MSYS_NO_PATHCONV=1
