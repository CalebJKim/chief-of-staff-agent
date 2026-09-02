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
# Windows Git Bash
export HERMES_HOME="$LOCALAPPDATA/hermes"

# Linux/macOS
# export HERMES_HOME="$HOME/.hermes"

python install.py --hermes-home "$HERMES_HOME"
hermes tools enable skills terminal --platform cli
```

The installer keeps only `chief-of-staff` and `ingest` enabled in the target
profile's skill catalog. Other installed skills remain installed but disabled.
It also disables `desktop_ui` to prevent automatic link previews.

If Hermes already has a customized `SOUL.md`, the installer preserves it. Copy the chief-of-staff routing paragraph from this repository into the existing Soul manually, or rerun with `--overwrite-soul` if replacement is intended.

## 3. Connect your own Google account

Create a **Desktop OAuth client** in Google Cloud and enable the Gmail, Calendar, Drive, Docs, Sheets, and Slides APIs. Download the client-secret JSON, then run:

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

After OAuth is verified, create the same realistic Gmail, Calendar, campaign folder, Sheet, Doc, and Slides workspace in your own account:

```bash
python demo/seed_workspace.py --confirm
```

Reset it to the original pre-email/pre-edit baseline with:

```bash
python demo/reset_workspace.py

# Or remove it entirely:
python demo/seed_workspace.py --cleanup --confirm
```

See [demo/DEMO_SPEC.md](demo/DEMO_SPEC.md) for the reference workspace specification, manual fallback instructions, and troubleshooting.

## 5. Start a new Hermes chat

Say:

> Good morning chief of staff, what should we work on today?

The agent will use the Gmail, Calendar, and Drive data from the account you connected.

## Dedicated lightweight profile

The installer disables unrelated skills automatically. Keep only the `skills`
and `terminal` toolsets enabled; use these commands to review the configuration:

```bash
hermes tools
hermes skills config
```

Do not disable `chief-of-staff`, `skills`, or `terminal`.
