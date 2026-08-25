# Quick setup

For the complete current procedure, troubleshooting notes, live checks, and
cleanup workflow, see [README.md](README.md). The screen-by-screen OAuth flow
is in [docs/GOOGLE_DESKTOP_OAUTH.md](docs/GOOGLE_DESKTOP_OAUTH.md).

## 1. Install prerequisites

Install [Hermes Agent](https://hermes-agent.nousresearch.com/docs), [Ollama](https://ollama.com/download), Python 3.11+, and clone this repository.

Windows PowerShell:

```powershell
winget install --id Python.Python.3.11 --exact --scope user
# Open a new PowerShell window after Python finishes installing.
git clone --branch demo_updates https://github.com/CalebJKim/chief-of-staff-agent.git
Set-Location chief-of-staff-agent
python -m venv .venv
$Python = (Resolve-Path .\.venv\Scripts\python.exe).Path
& $Python -m pip install -r requirements.txt
$ProfileName = "chief-of-staff-demo"
$HermesRoot = Join-Path $env:LOCALAPPDATA "hermes"
$env:HERMES_HOME = Join-Path $HermesRoot "profiles\$ProfileName"
```

Linux/macOS:

```bash
git clone --branch demo_updates https://github.com/CalebJKim/chief-of-staff-agent.git
cd chief-of-staff-agent
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export PROFILE_NAME="chief-of-staff-demo"
export HERMES_ROOT="$HOME/.hermes"
export HERMES_HOME="$HERMES_ROOT/profiles/$PROFILE_NAME"
```

On PowerShell, use `& $Python` wherever the remaining examples begin with
`python`. The repository pins `tzdata` because Windows does not provide the
IANA time-zone database used by the demo seeder.

## 2. Create the isolated profile and install the agent

```powershell
# Windows PowerShell
& $Python setup_profile.py --profile-name $ProfileName --hermes-root $HermesRoot
```

```bash
# Linux/macOS
python setup_profile.py --profile-name "$PROFILE_NAME" --hermes-root "$HERMES_ROOT"
```

The dedicated profile contains only `chief-of-staff` and `ingest`; `--no-skills`
prevents later Hermes updates from repopulating unrelated bundled skills. The
setup script also enables only `skills` and `terminal` and sets Max Agent Steps
to `40`. It disables skill-creation nudges and marks the installed demo skills as
repository-managed so they are read but not edited during a run. The default
profile remains unchanged. The script pulls and selects
`qwen3.6:35b-a3b-mtp-q4_K_M` with medium reasoning in the demo profile. Rerunning
it refreshes that demo model selection and the repository-managed installation
without recreating the profile or changing unrelated settings.

## 3. Connect your own Google account

Create a **Desktop OAuth client** in Google Cloud and enable the Gmail, Calendar, Drive, Docs, Sheets, and Slides APIs. Download the client-secret JSON, then run:

```powershell
# Windows PowerShell
& $Python setup\google-workspace\setup.py --client-secret C:\path\to\client-secret.json
$AuthUrl = & $Python setup\google-workspace\setup.py --auth-url
Start-Process $AuthUrl
```

```bash
# Linux/macOS
python setup/google-workspace/setup.py --client-secret /path/to/client-secret.json
python setup/google-workspace/setup.py --auth-url
```

Open the returned URL, approve your own account, and copy the full localhost redirect URL. Finish authorization:

```powershell
# Windows PowerShell
& $Python setup\google-workspace\setup.py --auth-code "FULL_REDIRECT_URL"
& $Python setup\google-workspace\setup.py --check-live
& $Python (Join-Path $env:HERMES_HOME "skills\productivity\ingest\scripts\verify.py")
```

```bash
# Linux/macOS
python setup/google-workspace/setup.py --auth-code "FULL_REDIRECT_URL"
python setup/google-workspace/setup.py --check-live
python "$HERMES_HOME/skills/productivity/ingest/scripts/verify.py"
```

Credentials remain under your local `HERMES_HOME`. Never commit them.

## 4. Optional: populate the reference workspace

After OAuth is verified, create the same realistic workspace in your own account: 6 meaningful Gmail messages, 70 older low-signal messages, 12 Calendar resources (47 visible weekly instances), and an RTX AI Assistant folder containing a launch-tracker Sheet, customer-demo-readiness Doc, and partner-preview deck. Gmail ingestion scans up to 120 matching Inbox messages, sorts them by `internalDate`, and retains the newest 20. The demo date is today on weekdays and the upcoming Monday on weekends.

```powershell
# Windows PowerShell
& $Python demo\seed_workspace.py --confirm
```

```bash
# Linux/macOS
python demo/seed_workspace.py --confirm
```

Remove it later with:

```powershell
# Windows PowerShell
& $Python demo\reset_workspace.py

# Or remove the seeded workspace and tracked drafts (seeded Gmail is permanently deleted; Drive goes to Trash):
& $Python demo\seed_workspace.py --cleanup --confirm
```

```bash
# Linux/macOS
python demo/reset_workspace.py

# Or remove the seeded workspace and tracked drafts (seeded Gmail is permanently deleted; Drive goes to Trash):
python demo/seed_workspace.py --cleanup --confirm
```

See [demo/DEMO_SPEC.md](demo/DEMO_SPEC.md) for the reference workspace specification, manual fallback instructions, and troubleshooting.

## 5. Start a new Hermes chat

For CLI testing, run `hermes -p chief-of-staff-demo`. For Hermes Desktop, run
`hermes profile use chief-of-staff-demo`, restart Desktop, and confirm the demo
profile is active. Restore the normal profile afterward with
`hermes profile use default` and restart Desktop.

Say:

> Hey chief of staff, what should we work on today?

Then try `Take care of the first item.` or a modified follow-up such as `Take care of the first item, but use Thursday afternoon.` You can also make a direct Workspace request unrelated to the brief. The agent uses live Gmail message IDs for reply recipients, Calendar's local timezone and working hours for rescheduling, and the Sheet's discovered schema and cell validation for updates. A direct request to complete a displayed action does not trigger a redundant confirmation question. The dedicated profile uses the repository-tested MTP model; the normal Hermes profile and unrelated tools are unchanged.
