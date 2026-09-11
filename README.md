# Hermes Chief of Staff Agent

A portable Hermes Agent configuration for a lightweight Google Workspace chief of staff. It reads bounded Gmail, Calendar, Drive, Docs, Sheets, and Slides evidence; highlights meaningful daily outcomes; accounts for calendar constraints; prepares meeting work; drafts email; and proposes guarded tracker/document updates.

## Included

- `SOUL.md` routes natural-language chief-of-staff requests.
- `skills/productivity/chief-of-staff/` contains decision policy, packet builder, and tests.
- `skills/productivity/ingest/` contains bounded ingestion, focused actions, verification, and tests.
- `setup/google-workspace/` contains the portable OAuth helper.
- `config.example.yaml` documents the minimal recommended tool surface.
- [`DEMO_SCRIPT.md`](DEMO_SCRIPT.md) contains the presentation script and staged demo flow.

No sessions, OAuth credentials, email/calendar fixtures, account IDs, document IDs, or model files are included.

For the shortest installation path, see [QUICKSTART.md](QUICKSTART.md). Every user must create OAuth credentials and connect their own Google account. The optional reference workspace seeder is documented in [demo/DEMO_SPEC.md](demo/DEMO_SPEC.md).

## Requirements

- Hermes Agent (tested on v0.20.1; use a recent release).
- Python 3.11+.
- A tool-calling model that meets Hermes context requirements.
- A Google Cloud Desktop OAuth client with Gmail, Calendar, Drive, Docs, Sheets, and Slides APIs enabled.
- Enable the [Google Tasks API](https://console.cloud.google.com/apis/library/tasks.googleapis.com) and grant the Tasks scope to include the optional sample checklist.

Install dependencies:

```bash
PYTHON="$(command -v python3 || command -v python)"
"$PYTHON" -m pip install -r requirements.txt
```

## Install into a Hermes profile

```bash
"$PYTHON" install.py
hermes -p chief-of-staff tools list --platform cli
```

The installer creates `profiles/chief-of-staff` under the normal Hermes root
(or the root selected by `HERMES_HOME`). On first creation it copies the default
profile's model/settings, `.env`, `SOUL.md`, installed skills, user memories,
local authentication, and demo workspace-state file. The default profile remains
unchanged; session history and caches are not copied. An existing shared Hermes
Python runtime is linked into the new profile, not duplicated.

Rerunning the installer refreshes the two demo skills but preserves the profile's
existing credentials, workspace state, model settings, and customized Soul. It
adds chief-of-staff routing if missing and enables only `chief-of-staff` and
`ingest`. Other installed skills stay installed but disabled. An explicit
`--hermes-home PATH` still installs directly into that exact target.
The installer also
disables `desktop_ui` and sets `HERMES_TUI_TOOLSETS=skills,terminal` in the
profile's `.env` so Desktop auto-discovery cannot add preview tools back.
Restart Hermes Desktop after installation. Links remain available inline;
the agent uses the saved API connection instead of opening embedded web previews.

Select **chief-of-staff** in Hermes Desktop and start a new chat. Before running
OAuth or seed/reset scripts from a separate terminal, select the same profile:

```powershell
# Windows PowerShell
$env:HERMES_HOME = Join-Path $env:LOCALAPPDATA 'hermes\profiles\chief-of-staff'
```

```bash
# Windows Git Bash
export HERMES_HOME="$LOCALAPPDATA/hermes/profiles/chief-of-staff"
# Linux/macOS
# export HERMES_HOME="$HOME/.hermes/profiles/chief-of-staff"
```

Copied credentials still point at the same Google account and existing demo data.
Use the new profile for future resets; do not run two profiles against that shared
workspace at the same time. No Google data is reset or changed by installation.

## Connect Google Workspace

Never commit OAuth files. Create a Desktop OAuth client, then run:

```bash
"$PYTHON" setup/google-workspace/setup.py --install-deps
"$PYTHON" setup/google-workspace/setup.py --client-secret /path/to/client-secret.json
"$PYTHON" setup/google-workspace/setup.py --auth-url
```

Open the returned URL and approve access. The `http://localhost:1` redirect may
show a connection error; this is expected. Copy the full URL from the browser
address bar, then run:

```bash
"$PYTHON" setup/google-workspace/setup.py --auth-code "FULL_REDIRECT_URL"
"$PYTHON" setup/google-workspace/setup.py --check-live
"$PYTHON" skills/productivity/ingest/scripts/verify.py
```

The resulting google_token.json and google_client_secret.json live under HERMES_HOME and are ignored by git.

Normal demo commands refresh the saved token silently and do not open a sign-in
window. Reconnection is a setup step when access expires or is revoked. To add
Google Tasks to an existing connection, enable its API in the same OAuth project
and repeat `--auth-url` / `--auth-code` once to approve the additional Tasks scope.
The existing Workspace connection remains usable before this extra consent.

## Use

Start a new Hermes Desktop chat in **chief-of-staff** (or run
`hermes -p chief-of-staff chat`) and say:

> Good morning chief of staff, what should we work on today?

Typical follow-ups:

- Help me prepare for the exec review.
- What slides should I prepare?
- Update the campaign tracker using the latest email evidence.
- Prepare follow-up drafts for the unresolved items.

The daily brief presents material context, distinct work outcomes, and tasks the
agent can take off your plate, with descriptive source links. Meeting preparation
covers context, work needed before the meeting, and the meeting's intended goals.
Use [Google Tasks](https://tasks.google.com/) to check off the seeded tasks. Chat
lists in this Hermes Desktop version do not save checkbox progress or sync it to
Google Tasks.

## Safety behavior

- Broad ingestion is bounded and metadata/snippet-first.
- Gmail drafts are created but never sent by these scripts.
- A direct instruction to update a tracker is treated as approval for evidence-backed row changes; ambiguous requests and comparisons remain read-only.
- Other Docs, Sheets, Slides, and Calendar writes require approval and `--confirm`.
- Tracker updates preserve Lane/PIC, reject duplicate lanes, and validate statuses.
- One-time codes are redacted before model context.

## Tests

```bash
"$PYTHON" -m unittest discover -s tests -v
"$PYTHON" -m unittest discover -s skills/productivity/ingest/tests -v
"$PYTHON" -m unittest discover -s skills/productivity/chief-of-staff/tests -v
```

Live smoke test after OAuth:

```bash
"$PYTHON" skills/productivity/ingest/scripts/ingest.py
"$PYTHON" skills/productivity/chief-of-staff/scripts/brief.py --max-chars 14000
```

## Portability and demo data

The agent does not require seeded workspace data for ordinary use. The included reference-workspace seeder recreates the Gmail, Calendar, Drive, Sheet, Doc, and Slides environment used to exercise the complete workflow. On another account, the agent reasons over the Workspace data that actually exists.

The tracker-specific path currently expects a tab named `Campaign Lanes` with columns A:J matching the demonstrated schema. General Gmail, Calendar, and Drive planning works without that sheet. Supporting arbitrary tracker schemas requires a small schema adapter rather than another hard-coded workbook.
