# Hermes Chief of Staff Agent

> Perplexity copy: use [PERPLEXITY_SETUP.md](PERPLEXITY_SETUP.md) for this installed demo. The Hermes installation instructions below are retained from the original; commands are translated to PowerShell.

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

```powershell
$Python = (Get-Command python.exe -ErrorAction Stop).Source
& $Python -m pip install -r requirements.txt
```

## Install into a Hermes profile

```powershell
& $Python install.py
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
disables `desktop_ui` and sets `HERMES_TUI_TOOLSETS=skills,terminal,cronjob` in the
profile's `.env` so Desktop auto-discovery cannot add preview tools back.
Restart Hermes Desktop after installation. Links remain available inline;
the agent uses the saved API connection instead of opening embedded web previews.
The `cronjob` tool manages Hermes's native scheduler; installation does not create,
enable, copy, or run scheduled jobs. Existing jobs in the target profile are preserved.

Select **chief-of-staff** in Hermes Desktop and start a new chat. Before running
OAuth or seed/reset scripts from a separate terminal, select the same profile:

```powershell
# Windows PowerShell
$env:HERMES_HOME = Join-Path $env:LOCALAPPDATA 'hermes\profiles\chief-of-staff'
```


Copied credentials still point at the same Google account and existing demo data.
Use the new profile for future resets; do not run two profiles against that shared
workspace at the same time. No Google data is reset or changed by installation.

## Connect Google Workspace

On Windows, run one of these commands from this checkout after installing the
chosen harness and demo skills/profile:

```powershell
.\setup.ps1 -Harness hermes
.\setup.ps1 -Harness perplexity
```

The launcher selects the harness's managed Python, with system Python as a
fallback only if the managed interpreter is absent. It reuses a working Google
connection or guides you through sign-in. First-time setup asks for your downloaded
Desktop OAuth client JSON. You can also pass `-ClientSecret 'C:\path\client.json'`.
It does not install the harness or demo skills, seed/reset Google data, or change
model settings.

Hermes uses its `chief-of-staff` profile by default. Perplexity uses
`CoS_Workspace\.chief-of-staff-state` beside the launcher. Override these with
`-Profile` / `-HermesRoot`, or `-WorkspaceRoot` / `-SkillsDir`, respectively.
Omit `-Harness` to choose interactively. Add `-Check` for a read-only local path
check, without contacting Google, installing dependencies, or signing in.
Environment settings are restored when the launcher exits.

The shared OAuth helper honors `COS_STATE_DIR` first and otherwise preserves
the existing Hermes profile lookup. The individual commands below remain
available for other shells and manual setup.

Never commit OAuth files. Create a Desktop OAuth client, then run:

```powershell
& $Python setup/google-workspace/setup.py --install-deps
& $Python setup/google-workspace/setup.py --client-secret /path/to/client-secret.json
& $Python setup/google-workspace/setup.py --auth-url
```

Open the returned URL and approve access. The `http://localhost:1` redirect may
show a connection error; this is expected. Copy the full URL from the browser
address bar, then run:

```powershell
& $Python setup/google-workspace/setup.py --auth-code "FULL_REDIRECT_URL"
& $Python setup/google-workspace/setup.py --check-live
& $Python skills/productivity/ingest/scripts/verify.py
```

The resulting google_token.json and google_client_secret.json live under HERMES_HOME and are ignored by git.

Normal demo commands refresh the saved token silently and do not open a sign-in
window. Reconnection is a setup step when access expires or is revoked. To add
Google Tasks to an existing connection, enable its API in the same OAuth project
and repeat `--auth-url` / `--auth-code` once to approve the additional Tasks scope.
The existing Workspace connection remains usable before this extra consent.

## Reset the demo data

Use this before each demo trial, after the workspace has been seeded and Google
OAuth is connected. Finish any running agent jobs and pause scheduled jobs that
could modify the same workspace before resetting.

**Warning:** reset permanently deletes the old seeded emails and **all Gmail
drafts in the connected account**, including non-demo drafts. Use a dedicated
demo account and save any drafts you need before proceeding.

For the Perplexity demo, run these commands from any PowerShell directory:

```powershell
Set-Location "$env:USERPROFILE\Desktop\ChiefOfStaff_PPLX"
.\demo\reset_workspace.ps1
```

Adjust the repository path if you cloned elsewhere. The launcher finds the installed
Perplexity account and uses its Python, falling back to system Python only if absent.
It uses `CoS_Workspace/.chief-of-staff-state` for Google credentials and resource IDs.
No environment setup is required. Append `-Check` to validate local setup without
resetting or calling Google. If multiple accounts have the skill installed, pass
`-SkillsDir` with the demo account's skills folder.

The wrapper supplies `--reset --confirm` automatically; it does not ask for
another confirmation. It replaces seeded emails, calendar events, and seeded
Google Tasks (when configured), restores the campaign tracker, Reference Tracker,
and slide deck, and resets the workspace's Second Brain as described below. Existing
Drive file IDs are retained. The campaign Google Doc is **not** restored by the
current reset. Chats and scheduled jobs are not deleted.

Reset reuses the calendar week saved by the previous seed/reset. To choose another
week, append `-WeekOf YYYY-MM-DD` using that week's Monday date. If a required state
file is missing, restore the demo state before resetting. Do not seed duplicates.

Wait for the successful JSON result (`"ok": true`, `"status": "reset"`), then start
a fresh Perplexity chat with `CoS_Workspace` selected. Do not start a trial after a failed
or interrupted reset; some data may have already changed.

## Second Brain

For Perplexity, select `CoS_Workspace/` from the chat's folder picker. Its direct
`CoS_SecondBrain/` subfolder is the active vault. Open that subfolder in Obsidian.
The skills pass the selected workspace root to `runtime.ps1` (or `daily_brief.ps1`)
with `-WorkspaceRoot`. Initialization derives the vault path and writes
`CoS_Workspace/.chief-of-staff-state/second-brain.json`; no manual vault setting is
needed. Runtime state stays alongside the vault. The entire working workspace is
Git-ignored; source changes remain in `skills/`, `setup/`, and `demo/`.

The installer copies skills and seed credentials into Perplexity's skill directory,
without bundling notes. Select the workspace again after moving it. Existing
scheduled jobs must use the new workspace path as well.

`.\demo\reset_workspace.ps1`
resets Google Workspace and restores **only** `CoS_Workspace/CoS_SecondBrain/` from
`demo/templates/CoS_SecondBrain.zip`. Existing demo notes, including job-created
files, are first moved into the Git-ignored `demo/.second-brain-backups/` folder.
Local `.obsidian` settings and sibling runtime state are preserved. Other vaults
are never reset. Finish running jobs before resetting and do not start new jobs
during a reset. No jobs are removed by reset.

Restored notes inherit the selected workspace's Windows permissions. Reset stages
them directly inside that workspace so replacing the vault retains sandbox access.

The baseline excludes machine-specific Obsidian settings. The active vault and generated state stay local; the checked-in baseline ZIP
and `demo/CoS_SecondBrain/` remain seed resources, not the active Perplexity vault.

The existing daily-brief call adds up to five relevant note excerpts in a separate
3,000-character allowance, without removing any of the existing bounded Google
evidence. Selection is a local word match, not an extra model call or vector index.
Excerpts show the matching passage. Each lookup scans at most 1,000 folders and
1,000 Markdown files (128 KiB per note), skipping hidden folders and notes.
Focused follow-ups can search or read a note when needed; already-returned context
is reused. Notes provide background, while current Google evidence controls
timing, status, approval scope, recipients, and writes. An unavailable vault is
reported separately and does not prevent the Google brief from running.

Note links use the [Obsidian URI](https://help.obsidian.md/Extending+Obsidian/Obsidian+URI)
format and open only when the user clicks them. Restart Hermes Desktop or start a
fresh profile chat after installation to load the updated skill.

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

## Scheduled project tracking (optional)

Scheduling is a separate, explicit opt-in after the interactive workflow works.
Use Hermes's native scheduler from the **chief-of-staff** profile; no Windows
scheduled task or separate scheduling service is needed. Keep Hermes Desktop's
backend (or the profile's Hermes gateway), the model server, and the machine
running for scheduled execution. Do not run a scheduled job alongside manual
testing or a workspace reset against the same account.

For CLI scheduling, enable `cronjob` with `hermes -p chief-of-staff tools` if it
is not already available. `config.example.yaml` includes the CLI configuration
and a `cron` worker toolset limited to `skills` and `terminal`; the installer pins
the Desktop toolsets but does not replace existing platform toolset settings.

Example job-creation prompt (choose your own schedule and verify the reported
time zone and next run before leaving it active):

> Create a scheduled task named "Campaign tracker follow-ups" in this Chief of Staff profile, running every weekday at 9:00 AM America/Los_Angeles. Use only the skills and terminal toolsets for the scheduled worker, and load the chief-of-staff skill. On each run, check the latest email evidence and update the NeoAgent V2 campaign tracker where supported. Save follow-up drafts for items still missing updates, checking existing drafts first so the same unresolved request to the same recipient is not drafted again. Never send emails or make unrelated changes. Save a local report of what changed, what remains unresolved, and which drafts are ready for review. Show me the configured schedule and next run.

The name, tracker, time, and time zone are examples, not installer defaults.
Creating the job explicitly authorizes its recurring tracker edits and draft
creation, not sending mail. Ask Hermes to list existing jobs first; update or
reuse a matching job instead of creating another copy. Reports remain in the
job's run history/local output; do not assume delivery to the current chat.

Before leaving recurrence enabled, validate it when live testing is authorized:

1. Inspect the job's profile, schedule/time zone, workflow prompt, and worker toolsets.
2. Run the job once, then inspect its tracker changes, draft recipients/bodies,
   and local report. A manual trigger still writes to Workspace and uses the model.
3. Run it again without resetting data. Confirm that unchanged work creates no
   duplicate drafts. This is a prompted behavior to validate, not a guaranteed
   deduplication mechanism in the helper.
4. If a command is blocked by unattended execution approvals, inspect the failure;
   do not globally disable approvals or report that the work succeeded.
5. Pause the job after the demonstration and before resetting or manual testing.

Useful management prompts: "List my scheduled tasks", "Run Campaign tracker
follow-ups now", and "Pause Campaign tracker follow-ups". A paused job must be
resumed before a manual run. Check for an already-running execution before
triggering another or resetting the workspace.

## Safety behavior

- Broad ingestion is bounded and metadata/snippet-first.
- Gmail drafts are created but never sent by these scripts.
- A direct instruction to update a tracker is treated as approval for evidence-backed row changes; ambiguous requests and comparisons remain read-only.
- Other Docs, Sheets, Slides, and Calendar writes require approval and `--confirm`.
- Tracker updates preserve Lane/PIC, reject duplicate lanes, and validate statuses.
- One-time codes are redacted before model context.

## Tests

```powershell
& $Python -m unittest discover -s tests -v
& $Python -m unittest discover -s skills/productivity/ingest/tests -v
& $Python -m unittest discover -s skills/productivity/chief-of-staff/tests -v
```

Live smoke test after OAuth:

```powershell
& $Python skills/productivity/ingest/scripts/ingest.py
& $Python skills/productivity/chief-of-staff/scripts/brief.py --max-chars 14000
```

## Portability and demo data

The agent does not require seeded workspace data for ordinary use. The included reference-workspace seeder recreates the Gmail, Calendar, Drive, Sheet, Doc, and Slides environment used to exercise the complete workflow. On another account, the agent reasons over the Workspace data that actually exists.

The tracker-specific path currently expects a tab named `Campaign Lanes` with columns A:J matching the demonstrated schema. General Gmail, Calendar, and Drive planning works without that sheet. Supporting arbitrary tracker schemas requires a small schema adapter rather than another hard-coded workbook.
