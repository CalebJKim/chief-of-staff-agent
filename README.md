# Hermes Chief of Staff Agent

A portable Hermes Agent configuration for a Google Workspace chief of staff. It reads bounded Gmail, Calendar, Drive, Docs, Sheets, and Slides evidence; ranks the day; resolves calendar conflicts; prepares meetings; drafts email; and proposes guarded tracker and document updates.

This README is the complete setup path for a new machine. [`QUICKSTART.md`](QUICKSTART.md) is a shorter checklist, while [`SETUP_GUIDE.md`](SETUP_GUIDE.md) provides the detailed Windows procedure, troubleshooting guidance, and maintainer workflow.

## What the reference demo creates

The optional seeder creates data in the Google account you authorize:

- 6 meaningful Gmail messages supporting 5 distinct workstreams, all Inbox and Unread; the two release-blocker messages are Important.
- 70 older, unread, low-signal messages from fictional people; none are Important.
- 12 Calendar resources producing 47 visible meeting instances across one workweek, including three lightly overlapping series.
- An `RTX AI Assistant Demo` Drive folder containing a polished 14-row launch-tracker Sheet with color-coded statuses, a plain-language customer-demo-readiness Doc, and a 6-slide partner-preview deck built from a reusable visual template.
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

If Hermes already has a working model, keep the existing configuration. Use a current Hermes release rather than requiring one exact version.

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
$ProfileName = "chief-of-staff-demo"
$HermesRoot = Join-Path $env:LOCALAPPDATA "hermes"
$env:HERMES_HOME = Join-Path $HermesRoot "profiles\$ProfileName"
```

On Windows ARM, if the standalone Python cannot install a binary dependency,
use Hermes' bundled interpreter to create the project environment instead:

```powershell
$BootstrapPython = Join-Path $env:LOCALAPPDATA "hermes\hermes-agent\venv\Scripts\python.exe"
& $BootstrapPython -m venv .venv
$Python = (Resolve-Path .\.venv\Scripts\python.exe).Path
& $Python -m pip install --upgrade pip
& $Python -m pip install -r requirements.txt
```

Keep this PowerShell window open while completing the setup. In a later window, recreate the two variables with:

```powershell
$Python = (Resolve-Path .\.venv\Scripts\python.exe).Path
$ProfileName = "chief-of-staff-demo"
$HermesRoot = Join-Path $env:LOCALAPPDATA "hermes"
$env:HERMES_HOME = Join-Path $HermesRoot "profiles\$ProfileName"
```

### Linux or macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
export PROFILE_NAME="chief-of-staff-demo"
export HERMES_ROOT="$HOME/.hermes"
export HERMES_HOME="$HERMES_ROOT/profiles/$PROFILE_NAME"
```

The repository pins `tzdata` because Windows does not include the IANA time-zone database used by the seeder.

## 5. Create the isolated Hermes demo profile and install the agent

Use a dedicated profile so the demo exposes only its two skills and two required
toolsets. This avoids routing competition from unrelated skills and does not
change the model, provider, skills, or tools in the default profile.

Run the idempotent profile setup on Windows:

```powershell
& $Python setup_profile.py --profile-name $ProfileName --hermes-root $HermesRoot
```

Or on Linux/macOS:

```bash
python setup_profile.py --profile-name "$PROFILE_NAME" --hermes-root "$HERMES_ROOT"
```

The script creates the profile with `--no-skills` when it is missing, copies the
default profile's model configuration only on first creation, installs the two
demo skills and `SOUL.md`, enables only the `skills` and `terminal` toolsets, and
sets `agent.max_turns` to `40`. It also sets `skills.creation_nudge_interval` to
`0` and installs an immutable-skill instruction so a demo run can read the two
skills but cannot decide to rewrite them. It is safe to rerun: an existing profile is not
recreated and its model configuration is not replaced. If that provider uses a
secret in the default profile's `.env`, configure it separately with
`hermes -p chief-of-staff-demo model`; do not commit or publish profile secrets.

## 6. Run the offline tests

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

Expected result: all tests pass across the three suites.

## 7. Verify the installed agent

```powershell
# Windows PowerShell
hermes -p $ProfileName skills list
hermes -p $ProfileName config get agent.max_turns
hermes -p $ProfileName config get skills.creation_nudge_interval
```

```bash
# Linux/macOS
hermes -p "$PROFILE_NAME" skills list
hermes -p "$PROFILE_NAME" config get agent.max_turns
hermes -p "$PROFILE_NAME" config get skills.creation_nudge_interval
```

Confirm that `chief-of-staff` and `ingest` are the only skills in the profile.
Confirm that the turn limit is `40` and the skill-creation nudge interval is `0`.
Rerun `setup_profile.py` to refresh the skills, routing instructions, toolsets,
turn limit, and immutable-skill setting after pulling repository updates.

The setup preserves Hermes model/provider defaults and unrelated profile
settings. It installs `chief-of-staff` and `ingest`, enables `skills` and
`terminal`, and applies the demo's bounded agent-step limit.

## 8. Create Google OAuth credentials

For the current screen-by-screen Google Cloud procedure, including screenshots,
see [`docs/GOOGLE_DESKTOP_OAUTH.md`](docs/GOOGLE_DESKTOP_OAUTH.md). The concise
steps below remain the setup checklist.

In [Google Cloud Console](https://console.cloud.google.com/):

1. Create or select a project.
2. Enable the Gmail API, Google Calendar API, Google Drive API, Google Docs API, Google Sheets API, and Google Slides API.
3. Configure the OAuth consent screen. If the app is in testing, add the Google account used for the demo as a test user.
4. Go to **APIs & Services > Credentials > Create credentials > OAuth client ID**.
5. Choose **Desktop app** as the application type and download the client-secret JSON file.

Never add the downloaded secret, generated token, or generated workspace state file to Git.

## 9. Authorize the Google account

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
$RedirectSecure = Read-Host "Paste the full localhost redirect URL" -AsSecureString
$RedirectUrl = [System.Net.NetworkCredential]::new("", $RedirectSecure).Password
& $Python setup\google-workspace\setup.py --auth-code $RedirectUrl
Remove-Variable RedirectUrl, RedirectSecure
& $Python setup\google-workspace\setup.py --check-live
& $Python (Join-Path $env:HERMES_HOME "skills\productivity\ingest\scripts\verify.py")
```

Secure input masks the one-time redirect URL and keeps it out of PowerShell
command history.

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

If this same Google account was already authorized and seeded in the default
profile, migrate its local credentials and state instead of authorizing or
seeding again. Close Hermes first, then on Windows run:

```powershell
$ExistingHome = $HermesRoot
foreach ($Name in @("google_client_secret.json", "google_token.json", "chief-of-staff-workspace-state.json")) {
    $Source = Join-Path $ExistingHome $Name
    if (Test-Path -LiteralPath $Source) {
        Copy-Item -LiteralPath $Source -Destination (Join-Path $env:HERMES_HOME $Name)
    }
}
& $Python setup\google-workspace\setup.py --check-live
& $Python (Join-Path $env:HERMES_HOME "skills\productivity\ingest\scripts\verify.py")
```

Copy the workspace-state file only with the OAuth token for the account that
owns those seeded resources. For a different or suspended account, follow the
account-switch procedure instead; pairing old state with a new token causes the
expected Drive permission failure.

If the demo may switch between a primary and backup Google account, add both as
OAuth test users before demo day. Changing accounts does not automatically
change the active workspace-state file. Follow
[`Switch or fail over to another Google account`](docs/GOOGLE_DESKTOP_OAUTH.md#8-switch-or-fail-over-to-another-google-account)
for the planned cleanup flow and the suspended-account archive fallback.

## 10. Seed the reference workspace

This step writes the fake demo data to the authorized Google account. It is not required if you want the agent to work only with data already in that account.

```powershell
# Windows PowerShell
& $Python demo\seed_workspace.py --confirm
```

```bash
# Linux/macOS
python demo/seed_workspace.py --confirm
```

The command resolves a consistent demo day automatically: it uses the current
day on Monday through Friday and the upcoming Monday on Saturday or Sunday. The
release-review meeting is created on that demo day, and the seeded evidence asks
the agent to find the earliest non-conflicting one-hour slot on the next business
day. To seed another week, add its Monday date as `--week-of YYYY-MM-DD` before
`--confirm`.

A successful result reports `"emails": 76`, `"events": 12`, the resolved
`"demo_day"`, and links for the folder, Sheet, Doc, and Slides deck. The 12
Calendar resources render as 47 meeting instances across the week. The six
meaningful messages have the newest seeded timestamps; the 70 background
messages are older, non-actionable inbox noise with natural, unnumbered subject
lines. The seeder writes the background set first and the six meaningful
messages in a final dedicated batch so they also appear within Gmail's first 20
in the dedicated demo inbox.

- Windows: `%LOCALAPPDATA%\hermes\profiles\chief-of-staff-demo\chief-of-staff-workspace-state.json`
- Linux/macOS: `$HOME/.hermes/profiles/chief-of-staff-demo/chief-of-staff-workspace-state.json`

Do not manually delete that state file; reset and cleanup need its exact resource IDs. The seeder refuses to create a duplicate while the state file exists.

## 11. Verify the live demo data

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

The commands should report successful service access and a bounded evidence packet without Python tracebacks. The packet includes compact Sheet schemas, representative rows, and validation previews for the agent to interpret during Start of Day; it does not contain a repository-ranked action plan.

Ingestion uses the same automatic weekday/weekend rule, so a weekend verification
reads the upcoming Monday without an extra flag. If you seeded an explicitly
chosen week with `--week-of`, point ingestion at the `demo_day` reported by the
seeder:

```powershell
# Needed only for an explicitly selected week; replace with its reported demo_day.
& $Python (Join-Path $env:HERMES_HOME "skills\productivity\ingest\scripts\ingest.py") --date 2026-08-24
& $Python (Join-Path $env:HERMES_HOME "skills\productivity\chief-of-staff\scripts\brief.py") --max-meetings 6 --max-mail 8 --max-files 4 --max-chars 14000
```

The packet's `requested_top_n` should be `3`, `source_status` should show successful sources, and `sheets` should contain the live structural preview. The packet intentionally contains no preselected workstreams or stored action commands.

Gmail does not guarantee the order returned by `messages.list`. Ingestion scans
metadata for up to 120 matching Inbox messages, sorts that bounded set by
Gmail's `internalDate`, and then retains only the newest 20 for the snapshot.
With the 76-message reference workspace, that keeps all six meaningful messages
plus 14 background messages while preserving a bounded model context.

## 12. Run the demo

For CLI rehearsal, start Hermes from the repository directory without changing
the active Desktop profile:

```bash
hermes -p chief-of-staff-demo
```

For Hermes Desktop, select the profile before launching the app:

```powershell
hermes profile use chief-of-staff-demo
```

Restart Hermes Desktop and confirm the active profile is
`chief-of-staff-demo`. After the demo, restore the normal profile with
`hermes profile use default` and restart Desktop. This selection changes only
which profile Desktop opens; it does not alter the default profile's files.

At the prompt, say:

> Hey chief of staff, what should we work on today?

The reply begins with a summary of today's workload in no more than three sentences. It returns three priorities by default; requests such as `What are the top 5 things we should work on today?` return that many when available. The expected default top three, in order, are the RTX AI Assistant repeated-task issue, the completed Customer Demo Readiness Check, and the Partner Preview Deck. The seeded top four and five continue with Partner demo checklist and Creator Demo Feedback Summary. Each item includes inline links to its supporting mail and action target followed by a `Recommended action item(s):` sub-bullet. Continue with:

- `Take the action items for the first thing.` This resolves item one from conversation history, checks current availability, moves the existing launch review to the earliest valid non-conflicting slot, and creates an unsent threaded draft to Priya with Daniel copied. The request authorizes the displayed actions; the agent does not ask for confirmation again.
- Natural wording such as `Can you take care of the first item on the list for me?` follows the same evidence-driven flow without rerunning Start of Day. Added constraints such as `but use Thursday afternoon` override the earlier recommendation.
- `Take the action items for the second thing.` This changes only the `Customer Demo Readiness Check` tracker status to `Ready for review`.
- Optional backup: `Take the action items for the third thing.` This replaces only the slide-4 placeholder with Elena's approved headline.

The three-item plan is conversational context, not a capability boundary. Direct Gmail, Calendar, Drive, Docs, Sheets, and Slides requests outside the plan use the same focused helpers and current Workspace data.

Use [`DEMO_SCRIPT.md`](DEMO_SCRIPT.md) for the complete staged presentation flow. Gmail responses are created as drafts and are never sent by these scripts. While a seeded reference workspace is active, drafts created through the chief-of-staff flow are recorded by exact ID so cleanup can remove them without touching unrelated drafts.

## Reset or remove the demo data

Reset deletes the currently tracked reference data and immediately creates a
fresh copy aligned to today on weekdays or the upcoming Monday on weekends. Run
it before a demo on a different day so the release-review story follows that
day:

```powershell
# Windows PowerShell
$env:HERMES_HOME = Join-Path $env:LOCALAPPDATA "hermes\profiles\chief-of-staff-demo"
& $Python demo\reset_workspace.py
```

```bash
# Linux/macOS
export HERMES_HOME="$HOME/.hermes/profiles/chief-of-staff-demo"
python demo/reset_workspace.py
```

Cleanup removes the reference workspace without recreating it:

```powershell
# Windows PowerShell
$env:HERMES_HOME = Join-Path $env:LOCALAPPDATA "hermes\profiles\chief-of-staff-demo"
& $Python demo\seed_workspace.py --cleanup --confirm
```

```bash
# Linux/macOS
export HERMES_HOME="$HOME/.hermes/profiles/chief-of-staff-demo"
python demo/seed_workspace.py --cleanup --confirm
```

On successful cleanup:

- Drafts explicitly recorded in the demo state are deleted; unrelated drafts are untouched.
- Seeded Gmail messages use a unique RFC message ID for every seed cycle and are permanently deleted by their recorded Gmail IDs, so they do not remain as deleted-message placeholders or get deduplicated into reused conversations.
- Seeded Calendar events are deleted.
- The generated Drive folder, including its Sheet, Doc, and Slides files, is moved to Drive Trash.
- The local state file is removed only after all tracked cleanup operations succeed.

Gmail deletion is immediate and cannot be undone; unrelated messages are untouched. Drive items remain recoverable from Drive Trash. If cleanup reports a partial failure, keep the state file and rerun cleanup after correcting the error.

## Troubleshooting

- **`Workspace already exists` even though the connected account looks empty**:
  the local state file can remain after switching OAuth accounts or clients. It
  records exact resource IDs and is intentionally account-independent. Do not
  delete it manually. Run cleanup first; resources that are already absent are
  treated as cleared, and the state file is removed only after cleanup succeeds:

  ```powershell
  & $Python demo\seed_workspace.py --cleanup --confirm
  & $Python demo\seed_workspace.py --confirm
  ```

  If cleanup reports a partial failure, keep the state file. A Drive 403 with
  `insufficientFilePermissions` means the recorded folder belongs to another
  account. Either reconnect that original account and rerun cleanup, or archive
  the stale state locally before seeding the new account. Archiving unblocks the
  new account but does not delete resources in the old account:

  ```powershell
  $StatePath = Join-Path $env:HERMES_HOME "chief-of-staff-workspace-state.json"
  $State = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
  $ArchiveName = "chief-of-staff-workspace-state.stale-{0}-{1}.json" -f `
      (Get-Date -Format "yyyyMMdd-HHmmss"), $State.seed_run_id
  $ArchivePath = Join-Path $env:HERMES_HOME $ArchiveName
  if (Test-Path -LiteralPath $ArchivePath) { throw "Archive already exists: $ArchivePath" }
  Move-Item -LiteralPath $StatePath -Destination $ArchivePath
  Write-Output "Archived stale state at $ArchivePath"
  ```

  Preserve that archive until the original account has been cleaned up. Do not
  run a new seed while the active state path still exists. If the original
  account is suspended, archive the state rather than repeatedly attempting
  cleanup; use the archive for cleanup only if access to that account is later
  restored.

- **`No workspace state` during cleanup**: the script no longer has the IDs needed for safe cleanup. Use [`demo/DEMO_SPEC.md`](demo/DEMO_SPEC.md) to identify the generated data manually.
- **API not enabled or access denied**: confirm all six APIs are enabled, the OAuth client type is Desktop, the account is an allowed test user, and all requested scopes were approved. Then run `--auth-url` again to begin a fresh authorization flow.
- **`disabled_client`**: verify the client and its secret under Google Auth Platform > Clients. If the console already says Enabled, wait briefly and rerun `--check-live`; status propagation can lag. Enable the client/secret or replace it only if the error persists.
- **OAuth state mismatch**: generate a new URL with `--auth-url` and submit only the redirect URL produced by that same attempt.
- **Time-zone error on Windows**: activate the repository environment and rerun `pip install -r requirements.txt`; `tzdata` is required.
- **Hermes cannot find the skills**: confirm `HERMES_HOME`, rerun `install.py`, then run `hermes -p chief-of-staff-demo skills list`.
- **Hermes has no usable model**: run `hermes model` and choose a tool-calling provider/model.

## Repository contents and safety

- `SOUL.md` routes natural-language chief-of-staff requests.
- `skills/productivity/chief-of-staff/` contains decision policy, packet building, and tests.
- `skills/productivity/ingest/` contains bounded ingestion, focused actions, verification, and tests.
- `setup/google-workspace/` contains the portable OAuth helper.
- `demo/` contains the reference-workspace seeder, reset wrapper, specification, and fixtures.
- `config.example.yaml` documents the recommended tool surface.

No sessions, OAuth credentials, account IDs, generated Workspace IDs, email/calendar fixtures from a real account, or model files are included. Broad ingestion is bounded and metadata/snippet-first; one-time codes are redacted before model context; the daily brief saves no executable action plan; Calendar rescheduling uses literal local dates, the live timezone, working hours, and conflict checks; Gmail reply recipients come from real message IDs, and reply bodies must contain substantive text plus any evidence-derived facts the caller marks as required before a draft can be created; spreadsheet updates discover the live header/row intersection and enforce that exact cell's validation, formula, protection, and current-value state. A direct request to complete a displayed action authorizes that scoped write without a redundant confirmation question, while each mutation still requires its internal `--confirm` guard and read-back verification.

The seeded Sheet still defines the fictional demo's table and dropdowns, but runtime code does not depend on its tab name, row numbers, column letters, or status list. See [`demo/DEMO_SPEC.md`](demo/DEMO_SPEC.md) for the exact reference data and manual fallback procedure.
