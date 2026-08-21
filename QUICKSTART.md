# Quick setup

For the complete validated Windows procedure, troubleshooting notes, live
checks, and cleanup workflow, see [SETUP_GUIDE.md](SETUP_GUIDE.md).

## 1. Install prerequisites

Install [Hermes Agent](https://hermes-agent.nousresearch.com/docs), Python 3.11+, and clone this repository.

Windows PowerShell:

```powershell
winget install --id Python.Python.3.11 --exact --scope user
# Open a new PowerShell window after Python finishes installing.
git clone https://github.com/CalebJKim/chief-of-staff-agent.git
Set-Location chief-of-staff-agent
python -m venv .venv
$Python = (Resolve-Path .\.venv\Scripts\python.exe).Path
& $Python -m pip install -r requirements.txt
$env:HERMES_HOME = Join-Path $env:LOCALAPPDATA "hermes"
```

Linux/macOS:

```bash
git clone https://github.com/CalebJKim/chief-of-staff-agent.git
cd chief-of-staff-agent
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export HERMES_HOME="$HOME/.hermes"
```

On PowerShell, use `& $Python` wherever the remaining examples begin with
`python`. The repository pins `tzdata` because Windows does not provide the
IANA time-zone database used by the demo seeder.

## 2. Install the agent

```powershell
# Windows PowerShell
& $Python install.py --hermes-home $env:HERMES_HOME
hermes tools enable skills terminal --platform cli
```

```bash
# Linux/macOS
python install.py --hermes-home "$HERMES_HOME"
hermes tools enable skills terminal --platform cli
```

If Hermes already has a customized `SOUL.md`, the installer preserves it. Copy the chief-of-staff routing paragraph from this repository into the existing Soul manually, or rerun with `--overwrite-soul` if replacement is intended.

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

After OAuth is verified, create the same realistic Gmail, Calendar, campaign folder, Sheet, Doc, and Slides workspace in your own account:

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

# Or remove the seeded workspace and tracked drafts (Gmail and Drive content go to Trash):
& $Python demo\seed_workspace.py --cleanup --confirm
```

```bash
# Linux/macOS
python demo/reset_workspace.py

# Or remove the seeded workspace and tracked drafts (Gmail and Drive content go to Trash):
python demo/seed_workspace.py --cleanup --confirm
```

See [demo/DEMO_SPEC.md](demo/DEMO_SPEC.md) for the reference workspace specification, manual fallback instructions, and troubleshooting.

## 5. Start a new Hermes chat

Say:

> Good morning chief of staff, what should we work on today?

The agent will use the Gmail, Calendar, and Drive data from the account you connected.

## Optional: dedicated lightweight profile

Keep only the `skills` and `terminal` toolsets enabled, and disable unrelated skills with:

```bash
hermes tools
hermes skills config
```

Do not disable `chief-of-staff`, `skills`, or `terminal`.
