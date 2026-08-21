# Chief of Staff demo setup guide

This guide records the repeatable setup used to validate the demo on Windows.
It covers local installation, Google Workspace authorization, reference-data
seeding, verification, cleanup, and the maintainer Git workflow.

## Validated environment

- Windows on ARM64
- Hermes Agent 0.20.4 (the repository originally targeted 0.20.1)
- Python 3.11
- PowerShell
- Google Workspace APIs: Gmail, Calendar, Drive, Docs, Sheets, and Slides

Do not commit `google_client_secret.json`, `google_token.json`, pending OAuth
state, or generated Workspace IDs. These files live under `HERMES_HOME` and
are ignored by this repository.

## 1. Clone the setup branch

Once the maintainer has published the setup branch:

```powershell
git clone --branch demo_updates https://github.com/CalebJKim/chief-of-staff-agent.git
Set-Location chief-of-staff-agent
```

For repository maintenance, create the branch directly from the remote main
commit and remove its upstream until it is intentionally published:

```powershell
git fetch origin main
git switch --create demo_updates --track origin/main
git branch --unset-upstream
```

This prevents an unqualified `git push` from targeting `main`. Publish only
with an explicit command after review:

```powershell
git push --set-upstream origin demo_updates
```

## 2. Install prerequisites

Install Hermes Agent, Git, and Python 3.11 or newer. On Windows:

```powershell
winget install --id Python.Python.3.11 --exact --scope user
```

Open a new PowerShell window after installation so the updated user `PATH` is
loaded, then verify:

```powershell
python --version
python -m pip --version
hermes --version
```

If Hermes is installed but a standalone Python is not yet available, its
bundled interpreter can bootstrap the virtual environment temporarily:

```powershell
$BootstrapPython = Join-Path $env:LOCALAPPDATA "hermes\hermes-agent\venv\Scripts\python.exe"
& $BootstrapPython -m venv .venv
```

A standalone Python should still be installed because the Chief of Staff skill
invokes `python` from Hermes terminal sessions.

## 3. Create the project environment

```powershell
python -m venv .venv
$Python = (Resolve-Path .\.venv\Scripts\python.exe).Path
& $Python -m pip install -r requirements.txt
$env:HERMES_HOME = Join-Path $env:LOCALAPPDATA "hermes"
```

The pinned `tzdata` dependency is required on Windows for the seeder's IANA
time zone (`America/Los_Angeles`). Without it, `zoneinfo` cannot calculate the
calendar event offsets.

## 4. Run the offline verification suite

```powershell
& $Python -m compileall -q demo setup skills tests
& $Python -m unittest discover -s tests -v
& $Python -m unittest discover -s skills/productivity/ingest/tests -v
& $Python -m unittest discover -s skills/productivity/chief-of-staff/tests -v
```

Expected result: 19 tests pass across the three suites.

## 5. Install the skills into Hermes

```powershell
& $Python install.py --hermes-home $env:HERMES_HOME
hermes tools enable skills terminal --platform cli
hermes skills list
```

The installer copies `ingest` and `chief-of-staff` under
`$env:HERMES_HOME\skills\productivity`. It preserves an existing `SOUL.md` and
appends the Chief of Staff routing paragraph only when it is absent.

Optional Hermes health checks:

```powershell
hermes status
hermes doctor
```

## 6. Configure Google Workspace OAuth

In Google Cloud, create a **Desktop application** OAuth client and enable:

- Gmail API
- Google Calendar API
- Google Drive API
- Google Docs API
- Google Sheets API
- Google Slides API

Download the client JSON, then store it in the active Hermes profile:

```powershell
& $Python setup\google-workspace\setup.py --client-secret C:\path\to\client-secret.json
$AuthUrl = & $Python setup\google-workspace\setup.py --auth-url
Start-Process $AuthUrl
```

Approve all requested scopes. The browser will redirect to
`http://localhost:1` and may show a connection error; this is expected. Copy
the entire URL from the browser address bar and exchange it immediately:

```powershell
& $Python setup\google-workspace\setup.py --auth-code "FULL_REDIRECT_URL"
```

The authorization code is single-use. Do not save it in the repository or a
setup log.

Verify both the token and all live services:

```powershell
& $Python setup\google-workspace\setup.py --check-live
& $Python skills\productivity\ingest\scripts\verify.py
```

Expected result: the live check succeeds and the verifier reports `ok: true`
for Gmail, Calendar, Drive, Docs, Sheets, and Slides.

## 7. Seed the reference workspace

The seeder writes demo content to the connected Google account. It creates six
meaningful Gmail messages, 100 older low-signal messages, 95 Calendar events,
a Drive folder, a campaign Sheet, a plan Doc, and an executive-review Slides
deck. Gmail ingestion reads only the newest 20 matching Inbox messages, which
keeps all six meaningful messages in scope. Seed the current workweek with:

```powershell
& $Python demo\seed_workspace.py --confirm
```

Or choose a specific Monday:

```powershell
& $Python demo\seed_workspace.py --week-of 2026-08-17 --confirm
```

Generated resource IDs are stored only at:

```text
$HERMES_HOME/chief-of-staff-workspace-state.json
```

To exercise draft tracking directly during setup validation, create a reply to
one seeded message through the installed action helper:

```powershell
$StatePath = Join-Path $env:HERMES_HOME "chief-of-staff-workspace-state.json"
$State = Get-Content -Raw $StatePath | ConvertFrom-Json
$Action = Join-Path $env:HERMES_HOME "skills\productivity\ingest\scripts\actions.py"
& $Python $Action gmail draft --reply-to-message $State.emails[0].id `
  --body "Thanks, I am preparing the decision brief." --track-demo-state
```

Confirm that the state file now contains one entry under `drafts`. During an
interactive reference demo, the Chief of Staff skill applies this flag when it
detects the active state file.

After seeding, repeat the live verifier and build a decision packet:

```powershell
& $Python skills\productivity\ingest\scripts\verify.py
& $Python skills\productivity\ingest\scripts\ingest.py --stdout summary
& $Python skills\productivity\chief-of-staff\scripts\brief.py --max-meetings 6 --max-mail 8 --max-files 4 --max-chars 14000
```

## 8. Run the demo

Start a new Hermes session and say:

> Good morning chief of staff, what should we work on today?

Useful follow-ups are listed in `DEMO_SCRIPT.md`.

## 9. Reset or remove the reference data

Reset the workspace to its original seeded state:

```powershell
& $Python demo\reset_workspace.py
```

Delete explicitly tracked demo drafts, move imported messages to Gmail Trash,
delete imported calendar events, and move the generated Drive folder and its
contents to Trash:

```powershell
& $Python demo\seed_workspace.py --cleanup --confirm
```

On success, the command reports exact counts for drafts deleted, messages
trashed, events deleted, and folders trashed. If any operation fails, cleanup
exits with an error and preserves the state file so the remaining resources
can be retried. A retry treats already-absent resources as successfully
cleared. Gmail messages and Drive items remain recoverable from their respective
Trash views.

Drafts are eligible for cleanup only when the action helper creates them with
`--track-demo-state` while the reference-workspace state file exists. This
records the exact Gmail draft ID; cleanup never guesses by subject or deletes
ordinary account drafts.

Review `demo/DEMO_SPEC.md` before manually deleting the local state file. The
state file is needed to identify the resources created by the seeder.

## Validation record

The following checks passed on August 21, 2026:

- Google OAuth token exchange and a live API call.
- Gmail, Calendar, Drive, Docs, Sheets, and Slides service verification.
- Creation and read-back of 106 demo messages (6 meaningful and 100
  background), 95 calendar events, one campaign folder, one 14-row tracker
  Sheet, one campaign Doc, and one 10-slide deck.
- Bounded ingestion of the newest 20 Inbox messages with all 6 meaningful
  messages present, 19 same-day events, 4 Drive items, and no source errors.
- Decision-packet generation with the expected conflict groups, 30-minute
  focus block, Exec Review evidence, and campaign tracker lanes.
- A real Hermes prompt using the installed skill and configured local model:
  `Good morning chief of staff, what should we work on today?`
- Two live 106-message seed/cleanup cycles. Trial 1 took 121.18 seconds to seed,
  5.26 seconds to ingest, and 63.41 seconds to clean up. Trial 2 took 113.39
  seconds to seed, 5.44 seconds to ingest, and 65.96 seconds to clean up. Each
  cleanup reported 106 messages trashed, 95 events deleted, and 1 Drive folder
  trashed. Final read-back found no seeded Inbox messages, seeded events,
  active Drive items, source errors, or local state file.
- The 14,000-character decision packet retained all 6 meaningful messages,
  all 5 conflict groups, 3 prioritized meetings, and 6 compact tracker rows.

The first one-shot response from the 35B local model took approximately two
minutes while the command buffered output. `ollama ps` showed the model loaded
at 100% GPU with a 32K context, and the completed response contained the
expected top-three priorities and schedule recommendations.

## Issues found during the Windows validation

1. The upstream seeder contained committed merge-conflict markers and could
   not be imported. The obsolete conflict block was removed.
2. The seeder unit test still targeted the older one-argument `create_sheet`
   API. It was updated for the current Sheets/Drive workflow and full A1:J14
   layout.
3. Windows Python did not have an IANA time-zone database. `tzdata` was added
   to `requirements.txt`.
4. The machine initially had only the Microsoft Store `python.exe` alias.
   Python 3.11 was installed with `winget`; the Hermes-bundled interpreter was
   used only to bootstrap the first local virtual environment.
5. Generic `hermes verify` detects `pytest` for this repository, while the
   repository intentionally documents `unittest`. Use the three explicit test
   commands above as the authoritative offline verification.
6. Cleanup used Gmail's permanent-delete endpoint, which was not allowed by
   the intentionally limited `gmail.modify` scope, and silently ignored the
   errors. Cleanup now moves imported messages to Gmail Trash, reports exact
   counts, raises on partial failure, and preserves recovery state until every
   operation succeeds.
7. Drafts created during the interactive demo were not represented in the
   seeder state, so cleanup could not identify them. The draft helper now has
   explicit demo-state tracking, and cleanup deletes only those recorded draft
   IDs while leaving all untracked drafts alone. One legacy fake draft created
   before tracking existed was removed once by its exact Gmail draft ID.
8. With 20 scanned messages and the dense demo calendar, the original packet
   fitter discarded mail until only one message remained. Conflict and tracker
   data are now compacted, low-value duplicate context is trimmed first, and
   the normal 14,000-character budget preserves the six highest-signal emails.
