# Chief of Staff demo setup guide

This guide records the repeatable setup used to validate the demo on Windows.
It covers local installation, Google Workspace authorization, reference-data
seeding, verification, cleanup, and the maintainer Git workflow.

## Validated environment

- Windows on ARM64
- Hermes Agent 0.20.4 (the repository originally targeted 0.20.1)
- Ollama with `qwen3.6:35b-a3b-mtp-q4_K_M`
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

Install Hermes Agent, Ollama, Git, and Python 3.11 or newer. On Windows:

```powershell
winget install --id Python.Python.3.11 --exact --scope user
```

Open a new PowerShell window after installation so the updated user `PATH` is
loaded, then verify:

```powershell
python --version
python -m pip --version
hermes --version
ollama --version
```

If Hermes is installed but a standalone Python is not yet available, its
bundled interpreter can bootstrap the virtual environment temporarily:

```powershell
$BootstrapPython = Join-Path $env:LOCALAPPDATA "hermes\hermes-agent\venv\Scripts\python.exe"
& $BootstrapPython -m venv .venv
```

The project environment is used for setup, seeding, and tests. On Windows, the
live Chief of Staff skill uses Hermes' bundled Python so it does not depend on
the desktop process inheriting a separately installed Python from `PATH`.

## 3. Create the project environment

```powershell
python -m venv .venv
$Python = (Resolve-Path .\.venv\Scripts\python.exe).Path
& $Python -m pip install -r requirements.txt
$ProfileName = "chief-of-staff-demo"
$HermesRoot = Join-Path $env:LOCALAPPDATA "hermes"
$env:HERMES_HOME = Join-Path $HermesRoot "profiles\$ProfileName"
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

Expected result: 76 tests pass across the three suites.

## 5. Create or refresh the isolated Hermes profile

```powershell
& $Python setup_profile.py --profile-name $ProfileName --hermes-root $HermesRoot
hermes -p $ProfileName skills list
hermes -p $ProfileName config get model.default
hermes -p $ProfileName config get agent.max_turns
hermes -p $ProfileName config get skills.creation_nudge_interval
```

The setup script creates the dedicated profile if needed, pulls and selects
`qwen3.6:35b-a3b-mtp-q4_K_M` through local Ollama with medium reasoning, installs
only `ingest` and `chief-of-staff`, enables the `skills` and `terminal` toolsets,
and sets Max Agent Steps to `40`. It can be rerun after repository updates
without recreating the profile. The normal Hermes profile and unrelated settings
remain unchanged. The script also disables skill-creation nudges and installs
repository-managed-skill instructions; the agent can load the skills but must
not modify them during a demo run.

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

Approve all requested scopes, including full Gmail access. Full Gmail access is
required so cleanup can permanently delete the tracked seeded messages without
leaving deleted-message placeholders in conversations. The browser will redirect to
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
meaningful Gmail messages, 70 older low-signal messages, 12 Calendar resources
(47 visible weekly meeting instances), and an `RTX AI Assistant Demo`
Drive folder with a launch-tracker Sheet, customer-demo-readiness Doc, and
partner-preview deck. Gmail ingestion scans metadata for up to 120 matching
Inbox messages, sorts by Gmail's `internalDate`, and retains the newest 20,
which keeps all six meaningful messages in scope. Seed the automatic demo day
with:

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
& $Python $Action gmail reply-draft $State.emails[0].id `
  --body "Thanks, I am preparing the decision brief." --track-demo-state
```

Confirm that the state file now contains one entry under `drafts`. During an
interactive reference demo, the Chief of Staff skill applies this flag when it
detects the active state file.

After seeding, repeat the live verifier and build a decision packet:

On Monday through Friday, both the seeder and ingestion use the current day as
the demo day. On Saturday and Sunday, both use the upcoming Monday. If you used
an explicit `--week-of`, add `--date YYYY-MM-DD` to ingestion with the
`demo_day` reported by the seeder.

```powershell
& $Python skills\productivity\ingest\scripts\verify.py
& $Python skills\productivity\ingest\scripts\ingest.py --stdout summary
& $Python skills\productivity\chief-of-staff\scripts\brief.py --max-meetings 6 --max-mail 8 --max-files 4 --max-chars 14000
```

## 8. Run the demo

Start a new Hermes session and say:

> Hey chief of staff, what should we work on today?

Then say `Take the action items for the first thing.` and `Take the action items for the second thing.` The first follow-up resolves the displayed item from conversation history, checks live availability, and proceeds without asking for confirmation again. The optional third-item action and a constraint-override example are documented in `DEMO_SCRIPT.md`.

## 9. Reset or remove the reference data

Reset the workspace to its original seeded state:

```powershell
$env:HERMES_HOME = Join-Path $env:LOCALAPPDATA "hermes\profiles\chief-of-staff-demo"
& $Python demo\reset_workspace.py
```

Delete explicitly tracked demo drafts, permanently delete imported messages by
their recorded IDs, delete imported calendar events, and move the generated Drive folder and its
contents to Trash:

```powershell
$env:HERMES_HOME = Join-Path $env:LOCALAPPDATA "hermes\profiles\chief-of-staff-demo"
& $Python demo\seed_workspace.py --cleanup --confirm
```

On success, the command reports exact counts for drafts deleted, messages
permanently deleted, events deleted, and folders trashed. If any operation fails, cleanup
exits with an error and preserves the state file so the remaining resources
can be retried. A retry treats already-absent resources as successfully
cleared. Gmail deletion is immediate and cannot be undone; Drive items remain
recoverable from Drive Trash.

Drafts are eligible for cleanup only when the action helper creates them with
`--track-demo-state` while the reference-workspace state file exists. This
records the exact Gmail draft ID; cleanup never guesses by subject or deletes
ordinary account drafts.

Review `demo/DEMO_SPEC.md` before manually deleting the local state file. The
state file is needed to identify the resources created by the seeder.

## Validation record

The original full acceptance checks passed on August 21, 2026:

- Google OAuth token exchange and a live API call.
- Gmail, Calendar, Drive, Docs, Sheets, and Slides service verification.
- Creation and read-back of 76 demo messages (6 meaningful and 70
  background), 12 calendar resources producing 47 visible weekly instances,
  one RTX AI Assistant folder, one 14-row launch tracker, one customer-demo-readiness
  Doc, and one 6-slide partner-preview deck.
- Decision-packet generation with generic Sheet schema/sample/validation evidence and no repository-defined field mappings, status ranking, or action routing. The live agent interpreted it into the expected repeated-task issue, readiness check, and deck order with inline Mail and action links.
- A real Hermes prompt using the installed skill and configured local model:
  `Hey chief of staff, what should we work on today?`
- The final acceptance reset/reseed took 42.2 seconds. The complete four-prompt
  Hermes flow then took 5 minutes 3 seconds, excluding reset. Final Gmail
  read-back found exactly 76 current seeded messages, no prior-run seeded
  messages, no seeded messages in Trash, and exact agreement between all 76
  saved cleanup IDs and live Gmail IDs. Each of the six meaningful threads
  contained exactly one message.
- The 14,000-character decision packet retained the meaningful messages and compact Sheet evidence needed for the agent to identify the action-ready workstreams.

The Gmail ordering and automatic demo-day update was revalidated live on August
22, 2026. Ingestion scanned all 76 matching messages, sorted before retaining
20, placed all 6 meaningful subjects first, selected the upcoming Monday on the
weekend, and retained the evidence needed to generate the same three ordered workstreams without source errors.
A clean reset then confirmed that Gmail's raw positions 1–6 were the six
meaningful messages, all 76 mailbox messages belonged to the current seed, all
76 subjects were unique, and no subject contained either the old `note NNN`
suffix or the temporary `FYI`/`Optional` variants. The measured migration reset
from the prior 106-message seed to this 76-message seed took 54.5 seconds; the
representative 76-to-76 reset took 46.1 seconds, and the bounded live ingestion
took 20.7 seconds.

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
6. An earlier cleanup used Gmail's permanent-delete endpoint without its
   required full Gmail scope and silently ignored the errors. The first fix
   moved imported messages to Trash and reported failures correctly, but repeated
   seeds then left deleted-message placeholders in reused conversations. Cleanup
   now requests full Gmail access and permanently deletes only the exact imported
   message IDs recorded in demo state. Each seed cycle also uses unique RFC
   message IDs so Gmail cannot deduplicate new imports against a prior cycle.
   Cleanup still raises on partial failure and
   preserves recovery state until every operation succeeds.
7. Drafts created during the interactive demo were not represented in the
   seeder state, so cleanup could not identify them. The draft helper now has
   explicit demo-state tracking, and cleanup deletes only those recorded draft
   IDs while leaving all untracked drafts alone. One legacy fake draft created
   before tracking existed was removed once by its exact Gmail draft ID.
8. With 20 scanned messages and the dense demo calendar, the original packet
   fitter discarded mail until only one message remained. Conflict and Sheet
   preview data are now compacted, low-value duplicate context is trimmed first,
   and the normal 14,000-character budget preserves the six highest-signal emails.
9. The local model occasionally rewrote the multi-line start-of-day command in
   `SKILL.md`, duplicated the Hermes path, and substituted an unsupported
   `actions.py gmail threads` call. The exact ingest-and-brief command now lives
   in `scripts/start_day.sh`; the skill invokes that file with one command.
10. Follow-up runs could improvise fixed tracker coordinates or repeat a status
    list in code. The spreadsheet helper now inspects the live workbook, finds a
    row and column from their contents, reads the target cell's validation and
    protection metadata, checks its current value again, writes only that cell,
    and verifies it. The runtime does not assume the seeded tab name, row number,
    column letter, or dropdown values.
11. A local-model run mixed GNU and macOS `date` flags, omitted a UTC offset,
    guessed recipient addresses, and attempted an unnecessary `skill_manage`
    patch. Calendar rescheduling now accepts a literal local date and performs
    timezone, working-hours, duration, and conflict logic in Python. Reply drafts
    derive recipients from real Gmail message IDs. The profile disables creation
    nudges and explicitly treats installed skills as immutable.
12. `disabled_client` is not a seeder or Hermes error. In the final run, Google
    returned it briefly even though the console showed the Desktop client as
    enabled; a later `--check-live` succeeded without replacing credentials.
    Verify both the client and secret status, allow for propagation, and replace
    credentials only if the error persists.
12. The final live action audit verified one moved launch-review event with no
    duplicate, one unsent threaded Priya draft with Daniel copied, only the
    readiness-check status changed in Sheets, and only the slide-4 placeholder
    changed in Slides.
