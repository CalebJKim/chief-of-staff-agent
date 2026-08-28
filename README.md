# Hermes Chief of Staff Agent

A portable Hermes Agent configuration for a lightweight Google Workspace chief of staff. It reads bounded Gmail, Calendar, Drive, Docs, Sheets, and Slides evidence; ranks the day; resolves calendar conflicts; prepares meeting work; drafts email; and proposes guarded tracker/document updates.

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

Install dependencies:

```bash
PYTHON="$(command -v python3 || command -v python)"
"$PYTHON" -m pip install -r requirements.txt
```

## Install into a Hermes profile

```bash
"$PYTHON" install.py
hermes tools enable skills terminal --platform cli
hermes tools list --platform cli
```

The installer uses `HERMES_HOME` when set and otherwise detects the normal
Hermes profile. It preserves an existing `SOUL.md`, adds only the chief-of-staff
routing instructions, and keeps only `chief-of-staff` and `ingest` enabled in
the target profile's skill catalog. Configure the user name in the Soul if
desired. Keep the `skills` and `terminal` toolsets enabled.

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

## Use

Start a new Hermes session and say:

> Good morning chief of staff, what should we work on today?

Typical follow-ups:

- Help me prepare for the exec review.
- What slides should I prepare?
- Compare the latest email updates with the campaign tracker.
- Apply the approved tracker updates.
- Draft a follow-up to the owner of this blocked lane.

## Safety behavior

- Broad ingestion is bounded and metadata/snippet-first.
- Gmail drafts are created but never sent by these scripts.
- Docs, Sheets, Slides, and Calendar writes require approval and `--confirm`.
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
"$PYTHON" skills/productivity/chief-of-staff/scripts/brief.py --max-chars 9000
```

## Portability and demo data

The agent does not require seeded workspace data for ordinary use. The included reference-workspace seeder recreates the Gmail, Calendar, Drive, Sheet, Doc, and Slides environment used to exercise the complete workflow. On another account, the agent reasons over the Workspace data that actually exists.

The tracker-specific path currently expects a tab named `Campaign Lanes` with columns A:J matching the demonstrated schema. General Gmail, Calendar, and Drive planning works without that sheet. Supporting arbitrary tracker schemas requires a small schema adapter rather than another hard-coded workbook.
