# Hermes Chief of Staff Agent

A portable Hermes Agent configuration for a lightweight Google Workspace chief of staff. It reads bounded Gmail, Calendar, Drive, Docs, Sheets, and Slides evidence; ranks the day; resolves calendar conflicts; prepares meeting work; drafts email; and proposes guarded tracker/document updates.

## Included

- `SOUL.md` routes natural-language chief-of-staff requests.
- `skills/productivity/chief-of-staff/` contains decision policy, packet builder, and tests.
- `skills/productivity/ingest/` contains bounded ingestion, focused actions, verification, and tests.
- `setup/google-workspace/` contains the portable OAuth helper.
- `config.example.yaml` documents the minimal recommended tool surface.

No sessions, OAuth credentials, email/calendar fixtures, account IDs, document IDs, or model files are included.

For the shortest installation path, see [QUICKSTART.md](QUICKSTART.md). Every user must create OAuth credentials and connect their own Google account.

## Requirements

- Hermes Agent (tested on v0.20.1; use a recent release).
- Python 3.11+.
- A tool-calling model that meets Hermes context requirements.
- A Google Cloud Desktop OAuth client with Gmail, Calendar, Drive, Docs, Sheets, and Slides APIs enabled.

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

## Install into a Hermes profile

```bash
# Windows Git Bash
export HERMES_HOME="$LOCALAPPDATA/hermes"

# Linux/macOS default profile
# export HERMES_HOME="$HOME/.hermes"

mkdir -p "$HERMES_HOME/skills/productivity"
cp -R skills/productivity/ingest "$HERMES_HOME/skills/productivity/"
cp -R skills/productivity/chief-of-staff "$HERMES_HOME/skills/productivity/"
cp SOUL.md "$HERMES_HOME/SOUL.md"
hermes tools enable skills terminal --platform cli
```

If the target has a customized SOUL.md, merge only the routing paragraph instead of overwriting it. Configure the user name in the Soul if desired. Disable unrelated tools and skills with `hermes tools` and `hermes skills config`; do not disable `skills` or `terminal`.

## Connect Google Workspace

Never commit OAuth files. Create a Desktop OAuth client, then run:

```bash
python setup/google-workspace/setup.py --install-deps
python setup/google-workspace/setup.py --client-secret /path/to/client-secret.json
python setup/google-workspace/setup.py --auth-url --format json
```

Open the returned URL, approve access, copy the full localhost redirect URL, then run:

```bash
python setup/google-workspace/setup.py --auth-code "FULL_REDIRECT_URL" --format json
python setup/google-workspace/setup.py --check-live
python "$HERMES_HOME/skills/productivity/ingest/scripts/verify.py"
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
python -m unittest discover -s skills/productivity/ingest/tests -v
python -m unittest discover -s skills/productivity/chief-of-staff/tests -v
```

Live smoke test after OAuth:

```bash
python skills/productivity/ingest/scripts/ingest.py
python skills/productivity/chief-of-staff/scripts/brief.py --max-chars 9000
```

## Portability and demo data

The agent does not depend on the synthetic emails, crowded calendar, or RTX Spark files used in the original demonstration. Those were account data used to exercise real retrieval and write paths. On another account, the agent reasons over the Workspace data that actually exists.

The tracker-specific path currently expects a tab named `Campaign Lanes` with columns A:J matching the demonstrated schema. General Gmail, Calendar, and Drive planning works without that sheet. Supporting arbitrary tracker schemas requires a small schema adapter rather than another hard-coded workbook.
