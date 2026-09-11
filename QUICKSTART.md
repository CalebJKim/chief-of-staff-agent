# Quick setup

## 1. Install prerequisites

Install [Hermes Agent](https://hermes-agent.nousresearch.com/docs), Python 3.11+, and clone this repository.

```bash
git clone YOUR_REPOSITORY_URL
cd chief-of-staff-agent
python -m pip install -r requirements.txt
```

## 2. Install the agent

```bash
python install.py
```

This creates a separate **chief-of-staff** profile, carrying over the default
profile's settings, Soul, installed skills, local authentication, and existing
demo workspace state. It leaves the default profile and Google data unchanged.
Rerunning refreshes the demo skills without replacing existing profile credentials
or workspace state.

Set the target for the OAuth and seed/reset commands below:

```powershell
# Windows PowerShell
$env:HERMES_HOME = Join-Path $env:LOCALAPPDATA 'hermes\profiles\chief-of-staff'
```

```bash
# Windows Git Bash
export HERMES_HOME="$LOCALAPPDATA/hermes/profiles/chief-of-staff"
# Linux/macOS
# export HERMES_HOME="$HOME/.hermes/profiles/chief-of-staff"

hermes -p chief-of-staff tools list --platform cli
```

The installer keeps only `chief-of-staff` and `ingest` enabled in the target
profile's skill catalog. Other installed skills remain installed but disabled.
It also disables `desktop_ui` and pins Desktop to `skills,terminal` to prevent
automatic link previews. The existing Hermes Python runtime is shared through
a local link, so the skill commands remain unchanged.

If Hermes already has a customized `SOUL.md`, the installer preserves it and adds
chief-of-staff routing if missing. Use `--overwrite-soul` only if replacement is intended.

## 3. Connect your own Google account

If the copied Google connection already works, no new authorization is needed.
Otherwise create a **Desktop OAuth client** in Google Cloud and enable the Gmail,
Calendar, Drive, Docs, Sheets, and Slides APIs (and Tasks for the sample checklist).
Download the client-secret JSON, then run:

```bash
python setup/google-workspace/setup.py --client-secret /path/to/client-secret.json
python setup/google-workspace/setup.py --auth-url
```

Open the returned URL, approve your own account, and copy the full localhost redirect URL. Finish authorization:

```bash
python setup/google-workspace/setup.py --auth-code "FULL_REDIRECT_URL"
python setup/google-workspace/setup.py --check-live
python "$HERMES_HOME/skills/productivity/ingest/scripts/verify.py"
```

Credentials remain under your local `HERMES_HOME`. Never commit them.

## 4. Optional: populate the reference workspace

After OAuth is verified, create the realistic reference workspace in your own account
if it has not already been seeded. The copied workspace-state file reuses existing
Google resources; do not seed a second copy merely because the profile is new:

```bash
python demo/seed_workspace.py --confirm
```

Reset it to the original pre-email/pre-edit baseline with:

```bash
python demo/reset_workspace.py

# Or remove it entirely:
python demo/seed_workspace.py --cleanup --confirm
```

Keep `HERMES_HOME` set to the new profile for resets. Do not use both profiles to
reset or edit the same Google workspace concurrently.

See [demo/DEMO_SPEC.md](demo/DEMO_SPEC.md) for the reference workspace specification, manual fallback instructions, and troubleshooting.

## 5. Start a new Hermes chat

Restart Hermes Desktop, select **chief-of-staff** in the profile picker, and start
a new chat. For the CLI use `hermes -p chief-of-staff chat`. Say:

> Good morning chief of staff, what should we work on today?

The agent will use the Gmail, Calendar, and Drive data from the account you connected.

## Dedicated lightweight profile

The installer disables unrelated skills automatically. Keep only the `skills`
and `terminal` toolsets enabled; use these commands to review the configuration:

```bash
hermes -p chief-of-staff tools
hermes -p chief-of-staff skills config
```

Do not disable `chief-of-staff`, `skills`, or `terminal`.
