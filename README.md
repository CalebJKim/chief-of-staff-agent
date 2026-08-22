# Hermes Chief of Staff Agent

A portable Hermes Agent configuration for a Google Workspace chief of staff. It reads bounded Gmail, Calendar, Drive, Docs, Sheets, and Slides evidence; ranks the day; resolves calendar conflicts; prepares meetings; drafts email; and proposes guarded tracker and document updates.

This README is the complete setup path for a new machine. [`QUICKSTART.md`](QUICKSTART.md) is a shorter checklist, while [`SETUP_GUIDE.md`](SETUP_GUIDE.md) records the validated Windows procedure, troubleshooting history, and maintainer workflow.

## What the reference demo creates

The optional seeder creates data in the Google account you authorize:

- 6 meaningful Gmail messages, marked Inbox, Unread, and Important.
- 100 older background messages from fictional people, marked read and not Important.
- 95 Calendar events across one workweek.
- A Drive folder containing a 14-row campaign tracker Sheet, a campaign-plan Doc, and a 10-slide executive-review deck.
- A local state file under `HERMES_HOME` containing only the generated resource IDs needed for reset and cleanup.

Use a dedicated test or demo Google account. Seeding and cleanup modify real Google Workspace data in the connected account, and cleanup permanently deletes the exact seeded Gmail message IDs.

## 1. Install prerequisites

You need Git, Python 3.11 or newer, [Hermes Agent](https://hermes-agent.nousresearch.com/docs/getting-started/installation), and a tool-calling model supported by Hermes.

### Windows PowerShell

Install Git and Python if they are not already available:

```powershell
winget install --id Git.Git --exact --source winget
winget install --id Python.Python.3.11 --exact --scope user
```

Install Hermes:

```powershell
iex (irm https://hermes-agent.nousresearch.com/install.ps1)
```

Close and reopen PowerShell so the new commands are on `PATH`, then verify them:

```powershell
git --version
python --version
hermes --version
```

If `python` opens the Microsoft Store or is not found, the new PowerShell window is important. If it still fails, turn off the `python.exe` App Installer alias in **Settings > Apps > Advanced app settings > App execution aliases**.

### Linux or macOS

Install Git and Python 3.11+ with your operating system's package manager, then install Hermes:

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
```

Open a new terminal if instructed, then verify:

```bash
git --version
python3 --version
hermes --version
```

## 2. Configure a Hermes model

Run the Hermes model picker and configure a provider/model that supports tool calling:

```bash
hermes model
```

If Hermes already has a working model, keep the existing configuration. The reference setup on this project was validated with Hermes 0.20.4; use a current release rather than requiring that exact version.

## 3. Clone the demo branch

The setup fixes are maintained on `demo_updates`. Clone that branch explicitly:

```powershell
# Windows PowerShell
git clone --branch demo_updates https://github.com/CalebJKim/chief-of-staff-agent.git
Set-Location chief-of-staff-agent
```

```bash
# Linux/macOS
git clone --branch demo_updates https://github.com/CalebJKim/chief-of-staff-agent.git
cd chief-of-staff-agent
```

Confirm that the branch is correct before making local changes:

```bash
git branch --show-current
```

The output must be `demo_updates`.

## 4. Create the project Python environment

These repository scripts use a project environment for setup, seeding, and tests. On Windows, the live installed skills use Hermes' bundled Python rather than relying on the desktop process's `PATH`.

### Windows PowerShell

```powershell
python -m venv .venv
$Python = (Resolve-Path .\.venv\Scripts\python.exe).Path
& $Python -m pip install --upgrade pip
& $Python -m pip install -r requirements.txt
$env:HERMES_HOME = Join-Path $env:LOCALAPPDATA "hermes"
```

Keep this PowerShell window open while completing the setup. In a later window, recreate the two variables with:

```powershell
$Python = (Resolve-Path .\.venv\Scripts\python.exe).Path
$env:HERMES_HOME = Join-Path $env:LOCALAPPDATA "hermes"
```

### Linux or macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
export HERMES_HOME="$HOME/.hermes"
```

The repository pins `tzdata` because Windows does not include the IANA time-zone database used by the seeder.

## 5. Run the offline tests

Run these before connecting Google Workspace so setup problems are separated from account or API problems.

```powershell
# Windows PowerShell
& $Python -m unittest discover -s tests -v
& $Python -m unittest discover -s skills\productivity\ingest\tests -v
& $Python -m unittest discover -s skills\productivity\chief-of-staff\tests -v
```

```bash
# Linux/macOS
python -m unittest discover -s tests -v
python -m unittest discover -s skills/productivity/ingest/tests -v
python -m unittest discover -s skills/productivity/chief-of-staff/tests -v
```

Expected result: 24 tests pass across the three suites.

## 6. Install the agent into Hermes

```powershell
# Windows PowerShell
& $Python install.py --hermes-home $env:HERMES_HOME
hermes tools enable skills terminal --platform cli
hermes skills list
```

```bash
# Linux/macOS
python install.py --hermes-home "$HERMES_HOME"
hermes tools enable skills terminal --platform cli
hermes skills list
```

Confirm that `chief-of-staff` and `ingest` appear in the skills list. The installer preserves an existing customized `SOUL.md`; either copy this repository's chief-of-staff routing paragraph into that file or rerun the installer with `--overwrite-soul` only if replacement is intentional.

Do not disable the `skills` or `terminal` toolsets. You can optionally use `hermes tools` and `hermes skills config` to disable unrelated capabilities for a lightweight demo profile.

## 7. Create Google OAuth credentials

In [Google Cloud Console](https://console.cloud.google.com/):

1. Create or select a project.
2. Enable the Gmail API, Google Calendar API, Google Drive API, Google Docs API, Google Sheets API, and Google Slides API.
3. Configure the OAuth consent screen. If the app is in testing, add the Google account used for the demo as a test user.
4. Go to **APIs & Services > Credentials > Create credentials > OAuth client ID**.
5. Choose **Desktop app** as the application type and download the client-secret JSON file.

Never add the downloaded secret, generated token, or generated workspace state file to Git.

## 8. Authorize the Google account

Store the downloaded Desktop client secret and generate an authorization URL.

### Windows PowerShell

Replace the example path with the downloaded file's real path:

```powershell
& $Python setup\google-workspace\setup.py --client-secret "C:\Users\YOUR_NAME\Downloads\client_secret.json"
$AuthUrl = & $Python setup\google-workspace\setup.py --auth-url
Start-Process $AuthUrl
```

Approve all requested scopes, including full Gmail access. That scope is required so reset can permanently delete only the tracked seeded messages instead of leaving deleted-message placeholders in Gmail conversations. Google then redirects to a URL beginning with `http://localhost:1/`. The browser may say that it cannot connect; that is expected because no local web server is listening there. Copy the **entire URL from the browser address bar**, including its `state` and `code` parameters, and run:

```powershell
& $Python setup\google-workspace\setup.py --auth-code "FULL_LOCALHOST_REDIRECT_URL"
& $Python setup\google-workspace\setup.py --check-live
& $Python (Join-Path $env:HERMES_HOME "skills\productivity\ingest\scripts\verify.py")
```

### Linux or macOS

```bash
python setup/google-workspace/setup.py --client-secret "/path/to/client_secret.json"
python setup/google-workspace/setup.py --auth-url
```

Open the printed URL, approve all scopes, then copy the full `http://localhost:1/...` redirect URL from the browser address bar even if the page fails to load:

```bash
python setup/google-workspace/setup.py --auth-code "FULL_LOCALHOST_REDIRECT_URL"
python setup/google-workspace/setup.py --check-live
python "$HERMES_HOME/skills/productivity/ingest/scripts/verify.py"
```

Both checks should succeed for Gmail, Calendar, Drive, Docs, Sheets, and Slides. The resulting `google_client_secret.json` and `google_token.json` stay under the local `HERMES_HOME`.

## 9. Seed the reference workspace

This step writes the fake demo data to the authorized Google account. It is not required if you want the agent to work only with data already in that account.

```powershell
# Windows PowerShell
& $Python demo\seed_workspace.py --confirm
```

```bash
# Linux/macOS
python demo/seed_workspace.py --confirm
```

The command defaults to the current workweek. To seed another week, add a Monday date such as `--week-of 2026-08-17` before `--confirm`.

A successful result reports `"emails": 106`, `"events": 95`, and links for the folder, Sheet, Doc, and Slides deck. The six meaningful messages are the newest seeded mail; the 100 background messages are older, non-actionable inbox noise. It also creates:

On the validated Windows demo account, two complete trials averaged about 117 seconds to seed and 65 seconds to clean up. The bounded 20-message ingestion averaged about 5.4 seconds. Google API and network conditions will affect these times.

- Windows: `%LOCALAPPDATA%\hermes\chief-of-staff-workspace-state.json`
- Linux/macOS: `$HOME/.hermes/chief-of-staff-workspace-state.json`

Do not manually delete that state file; reset and cleanup need its exact resource IDs. The seeder refuses to create a duplicate while the state file exists.

## 10. Verify the live demo data

```powershell
# Windows PowerShell
& $Python (Join-Path $env:HERMES_HOME "skills\productivity\ingest\scripts\verify.py")
& $Python (Join-Path $env:HERMES_HOME "skills\productivity\ingest\scripts\ingest.py")
& $Python (Join-Path $env:HERMES_HOME "skills\productivity\chief-of-staff\scripts\brief.py") --max-meetings 6 --max-mail 8 --max-files 4 --max-chars 14000
```

```bash
# Linux/macOS
python "$HERMES_HOME/skills/productivity/ingest/scripts/verify.py"
python "$HERMES_HOME/skills/productivity/ingest/scripts/ingest.py"
python "$HERMES_HOME/skills/productivity/chief-of-staff/scripts/brief.py" --max-meetings 6 --max-mail 8 --max-files 4 --max-chars 14000
```

The commands should report successful service access, a bounded evidence packet, and a ranked brief without Python tracebacks.

Gmail ingestion is capped at the newest 20 matching Inbox messages. With the reference data, that scan contains all six meaningful messages plus 14 background messages; the packet builder ranks eight candidates and preserves the six highest-signal messages within its bounded model context.

## 11. Run the demo

Start Hermes from the repository directory:

```bash
hermes
```

At the prompt, say:

> Good morning chief of staff, what should we work on today?

Useful follow-ups are:

- Help me prepare for the exec review.
- What slides should I prepare?
- Compare the latest email updates with the campaign tracker.
- Apply the approved tracker updates.
- Draft a follow-up to the owner of this blocked lane.

Use [`DEMO_SCRIPT.md`](DEMO_SCRIPT.md) for the complete staged presentation flow. Gmail responses are created as drafts and are never sent by these scripts. While a seeded reference workspace is active, drafts created through the chief-of-staff flow are recorded by exact ID so cleanup can remove them without touching unrelated drafts.

## Reset or remove the demo data

Reset deletes the currently tracked reference data and immediately creates a fresh copy for the current workweek:

```powershell
# Windows PowerShell
& $Python demo\reset_workspace.py
```

```bash
# Linux/macOS
python demo/reset_workspace.py
```

Cleanup removes the reference workspace without recreating it:

```powershell
# Windows PowerShell
& $Python demo\seed_workspace.py --cleanup --confirm
```

```bash
# Linux/macOS
python demo/seed_workspace.py --cleanup --confirm
```

On successful cleanup:

- Drafts explicitly recorded in the demo state are deleted; unrelated drafts are untouched.
- Seeded Gmail messages are permanently deleted by their recorded IDs, so they do not remain as deleted-message placeholders in conversations.
- Seeded Calendar events are deleted.
- The generated Drive folder, including its Sheet, Doc, and Slides files, is moved to Drive Trash.
- The local state file is removed only after all tracked cleanup operations succeed.

Gmail deletion is immediate and cannot be undone; unrelated messages are untouched. Drive items remain recoverable from Drive Trash. If cleanup reports a partial failure, keep the state file and rerun cleanup after correcting the error.

## Troubleshooting

- **`Workspace already exists`**: run reset or cleanup. Do not delete the state file unless you have manually removed every generated resource.
- **`No workspace state` during cleanup**: the script no longer has the IDs needed for safe cleanup. Use [`demo/DEMO_SPEC.md`](demo/DEMO_SPEC.md) to identify the generated data manually.
- **API not enabled or access denied**: confirm all six APIs are enabled, the OAuth client type is Desktop, the account is an allowed test user, and all requested scopes were approved. Then run `--auth-url` again to begin a fresh authorization flow.
- **OAuth state mismatch**: generate a new URL with `--auth-url` and submit only the redirect URL produced by that same attempt.
- **Time-zone error on Windows**: activate the repository environment and rerun `pip install -r requirements.txt`; `tzdata` is required.
- **Hermes cannot find the skills**: confirm `HERMES_HOME`, rerun `install.py`, then run `hermes skills list`.
- **Hermes has no usable model**: run `hermes model` and choose a tool-calling provider/model.

## Repository contents and safety

- `SOUL.md` routes natural-language chief-of-staff requests.
- `skills/productivity/chief-of-staff/` contains decision policy, packet building, and tests.
- `skills/productivity/ingest/` contains bounded ingestion, focused actions, verification, and tests.
- `setup/google-workspace/` contains the portable OAuth helper.
- `demo/` contains the reference-workspace seeder, reset wrapper, specification, and fixtures.
- `config.example.yaml` documents the recommended tool surface.

No sessions, OAuth credentials, account IDs, generated Workspace IDs, email/calendar fixtures from a real account, or model files are included. Broad ingestion is bounded and metadata/snippet-first; one-time codes are redacted before model context; Docs, Sheets, Slides, and Calendar writes require explicit confirmation; and tracker updates preserve lane ownership and validate statuses.

The tracker-specific update path expects a tab named `Campaign Lanes` with columns A:J matching the demonstrated schema. General Gmail, Calendar, and Drive planning works without that sheet. See [`demo/DEMO_SPEC.md`](demo/DEMO_SPEC.md) for the exact reference data and manual fallback procedure.
