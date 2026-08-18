# Quick setup

This installs the Chief of Staff skills into a Hermes profile and connects that
profile to the user's own Google Workspace account. The repository contains no
model configuration, account credentials, or private Workspace data.

The current portable package covers Gmail, Calendar, Drive, Docs, Sheets, and
Slides. Slack, Obsidian, Jira, Workfront, news, and OpenShell integrations
mentioned in the [demo script](DEMO_SCRIPT.md) are not included and require
separate setup.

## 1. Install and configure Hermes

Install a recent [Hermes Agent release](https://hermes-agent.nousresearch.com/docs/getting-started/installation),
then make sure Hermes has a model provider configured:

```bash
hermes model
hermes doctor
```

If inference must stay local, select the local or OpenAI-compatible endpoint
that is already serving your model. This repository does not install or serve a
model. Use a tool-calling model with enough context for the 9,000-character
briefing packet.

Hermes uses its unsandboxed local terminal backend by default. This repository
does not install or configure OpenShell. If the deployment requires an isolated
terminal, configure a supported backend separately with `hermes setup terminal`
before connecting private data.

## 2. Install the Chief of Staff skills

```bash
git clone https://github.com/CalebJKim/chief-of-staff-agent.git
cd chief-of-staff-agent
PYTHON="$(command -v python3 || command -v python)"
"$PYTHON" --version
"$PYTHON" -m pip install -r requirements.txt
"$PYTHON" install.py
hermes tools enable skills terminal --platform cli
hermes tools list --platform cli
```

These commands use a POSIX shell, including Git Bash on Windows. In native
Windows PowerShell, use `py -3` in place of `"$PYTHON"`.

The installer uses the active `HERMES_HOME`, or the normal Hermes profile when
that variable is unset (`~/.hermes` on Linux/macOS and
`%LOCALAPPDATA%\hermes` on native Windows). It safely adds the Chief of Staff
routing instructions to an existing `SOUL.md`; `--overwrite-soul` is only for a
dedicated profile whose Soul should be replaced completely.

For a non-default profile, set `HERMES_HOME` before running the installer,
Google setup, and Hermes itself.

## 3. Create Google OAuth credentials

In [Google Cloud Console](https://console.cloud.google.com/):

1. Create or select a project.
2. Enable the Gmail, Google Calendar, Google Drive, Google Docs, Google Sheets,
   and Google Slides APIs.
3. Configure the Google Auth consent screen. If its audience is **External**
   and its publishing status is **Testing**, add the account you will connect as
   a test user.
4. Create an OAuth client with application type **Desktop app**, then download
   its client-secret JSON file.

Each user should create and keep their own client-secret file. Never add that
file to this repository.

## 4. Authorize the user's account

```bash
PYTHON="$(command -v python3 || command -v python)"
"$PYTHON" setup/google-workspace/setup.py --client-secret /path/to/client-secret.json
"$PYTHON" setup/google-workspace/setup.py --auth-url
```

Open the printed URL and approve access. The browser will redirect to
`http://localhost:1` and may show a connection error; that is expected. Copy the
**entire URL from the browser address bar**, including its `code` and `state`
parameters, and run:

```bash
"$PYTHON" setup/google-workspace/setup.py --auth-code "FULL_REDIRECT_URL"
"$PYTHON" setup/google-workspace/setup.py --check-live
"$PYTHON" skills/productivity/ingest/scripts/verify.py
```

Both checks must succeed. Credentials remain under the user's local
`HERMES_HOME` as `google_client_secret.json` and `google_token.json`; `.gitignore`
excludes them. Google OAuth apps left in **Testing** can require authorization
again after seven days.

## 5. Start a fresh Hermes chat

```bash
hermes
```

Say:

> Good morning chief of staff, what should we work on today?

A working setup returns a sourced top-three plan based on the connected
account. If a connector reports an error, fix that error rather than treating
the source as empty.

## Optional: keep the profile minimal

The workflow only needs the `skills` and `terminal` toolsets. To hide unrelated
skills or change platforms, use:

```bash
hermes tools
hermes skills config
```

Do not disable `chief-of-staff`, `ingest`, `skills`, or `terminal`.
