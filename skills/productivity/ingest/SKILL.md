---
name: ingest
description: Pull bounded Gmail, Calendar, and Drive evidence.
version: 0.1.0
author: NVIDIA, Hermes Agent
license: MIT
platforms: [linux, macos, windows]
created_by: agent
metadata:
  hermes:
    tags: [Google, Gmail, Calendar, Drive, Productivity]
---

# Ingest Skill

Pull a bounded, metadata-first Workspace snapshot for planning. It deliberately avoids full email bodies and document contents; retrieve those only after relevance is established.

## When to Use

- Refresh the chief-of-staff brief.
- Pull recent Gmail, Calendar, and Drive changes.
- Diagnose data coverage before making a plan.
- Don't use for sending mail or editing files.

## Prerequisites

- OAuth token at the active Hermes profile's `google_token.json`.
- Gmail, Calendar, Drive, Docs, Sheets, and Slides APIs enabled.
- Google Python dependencies installed by the bundled Google Workspace setup.

## How to Run

Use `terminal` with the active profile root:

```bash
if [ -n "${HERMES_HOME:-}" ]; then
  COS_HOME="$HERMES_HOME"
elif [ -n "${LOCALAPPDATA:-}" ]; then
  COS_HOME="$LOCALAPPDATA/hermes"
else
  COS_HOME="$HOME/.hermes"
fi
if [ -n "${LOCALAPPDATA:-}" ] && [ -f "$LOCALAPPDATA/hermes/hermes-agent/venv/Scripts/python.exe" ]; then PYTHON="$LOCALAPPDATA/hermes/hermes-agent/venv/Scripts/python.exe"; elif [ -x "$HOME/.hermes/hermes-agent/venv/bin/python" ]; then PYTHON="$HOME/.hermes/hermes-agent/venv/bin/python"; else PYTHON="$(command -v python3 || command -v python)"; fi
"$PYTHON" "$COS_HOME/skills/productivity/ingest/scripts/ingest.py"
```

The snapshot is written to `$COS_HOME/chief-of-staff/snapshot.json`. The command prints only counts and connector errors.

## Quick Reference

```bash
if [ -n "${HERMES_HOME:-}" ]; then COS_HOME="$HERMES_HOME"; elif [ -n "${LOCALAPPDATA:-}" ]; then COS_HOME="$LOCALAPPDATA/hermes"; else COS_HOME="$HOME/.hermes"; fi
if [ -n "${LOCALAPPDATA:-}" ] && [ -f "$LOCALAPPDATA/hermes/hermes-agent/venv/Scripts/python.exe" ]; then PYTHON="$LOCALAPPDATA/hermes/hermes-agent/venv/Scripts/python.exe"; elif [ -x "$HOME/.hermes/hermes-agent/venv/bin/python" ]; then PYTHON="$HOME/.hermes/hermes-agent/venv/bin/python"; else PYTHON="$(command -v python3 || command -v python)"; fi

# Today plus tomorrow; active inbox and recent Drive files
"$PYTHON" "$COS_HOME/skills/productivity/ingest/scripts/ingest.py"

# Explicit local day and tighter bounds
"$PYTHON" "$COS_HOME/skills/productivity/ingest/scripts/ingest.py" --days-ahead 1 --days-back 30 --max-messages 35

# Use a focused Gmail query
"$PYTHON" "$COS_HOME/skills/productivity/ingest/scripts/ingest.py" --gmail-query 'in:inbox (is:unread OR label:important) -category:promotions'
```

## Procedure

1. Run ingestion once. Continue only when output says `"ok":true`.
2. Inspect `coverage.errors`. Name any failed connector instead of treating missing data as an empty inbox or calendar.
3. Pass the saved snapshot to the chief-of-staff packet builder. Do not print the full snapshot into model context.
4. Fetch a full Gmail thread or document only when the packet identifies it as relevant.

## Pitfalls

- Snapshot snippets are leads, not complete email evidence.
- Calendar events come from selected calendars and exclude declined/cancelled events.
- Fuzzy mail/file links are suggestions, not facts.
- Keep bounds small for local models; increase one source at a time.

## Verification

- `coverage` has nonzero expected sources and no unexplained errors.
- `generated_at` is current and `timezone` matches the Google account.
- The snapshot contains IDs and links needed for targeted follow-up reads.
