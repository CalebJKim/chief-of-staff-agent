#!/usr/bin/env bash
# Run native action commands, initializing once per invocation/batch.
set -euo pipefail

if [[ $# -eq 0 ]]; then
  printf '%s\n' 'Supply SERVICE COMMAND [arguments], or --batch with action commands on standard input.' >&2
  exit 2
fi
source "$(dirname -- "${BASH_SOURCE[0]}")/runtime.sh"

action() {
  if [[ $# -eq 0 ]]; then
    printf '%s\n' 'action needs SERVICE COMMAND [arguments].' >&2
    exit 2
  fi
  "$COS_EXECUTABLE" "$@" || exit "$?"
}
if [[ "$1" == '--batch' ]]; then
  if [[ $# -ne 1 ]]; then
    printf '%s\n' '--batch takes its command block from standard input, not extra arguments.' >&2
    exit 2
  fi
  # Read the complete caller-authored shell block first so helpers cannot
  # accidentally consume subsequent commands as their input.
  COS_ACTION_BATCH="$(cat)"
  if [[ -z "${COS_ACTION_BATCH//[[:space:]]/}" ]]; then
    printf '%s\n' 'The batch needs action commands.' >&2
    exit 2
  fi
  export COS_EXECUTABLE
  export -f action
  "$BASH" -euo pipefail -c "$COS_ACTION_BATCH"
else
  exec "$COS_EXECUTABLE" "$@"
fi
