# Private Perplexity installation

Run this skill in a local Perplexity Computer session on Windows. Its PowerShell
commands locate this directory through `PPLX_SKILLS_DIR`, then load
`scripts/runtime.ps1`. No Desktop checkout is required during execution.

- `scripts/`: briefing, ingestion, Google actions, verification, and local notes.
- `runtime/state/`: read-only seed credentials, workspace references, and cached evidence.
- `notes/`: the active copied Second Brain vault.
- `runtime-local.json`: paths relative to this installed directory.

Each local thread keeps writable state in `<thread-workspace>/.chief-of-staff-state`.
The initialization copies seed credentials once; token refresh and snapshot writes
use this workspace copy. Updated workspace tokens are never overwritten by seeds.
The installed skill directory is read-only to Perplexity's sandbox. Run commands
from the thread workspace (or its subdirectories), so initialization can find it.
Standalone diagnostics can set `COS_WORKSPACE_ROOT` to an existing writable folder.

Python comes from the account's `template/venv/Scripts/python.exe`. If absent,
initialization selects system `python.exe` or `python3.exe` from PATH, excluding
Windows Store aliases. It checks the interpreter and Google dependencies before
any work. If the selected interpreter fails, report the error without retrying.
Required packages are installed during setup, never during a brief.

`COS_STATE_DIR` points to writable workspace state. Perplexity scripts require it
and have no Hermes-directory fallback. For Start of Day, run `scripts/daily_brief.ps1`.
It initializes the workspace and invokes the brief once. Add `-Fixture` for the
offline fixture test. Other scripts still use `runtime.ps1` in the same shell call.
The Google token can refresh silently in the workspace; no new sign-in is needed.

This is the active installation. Editing its `SKILL.md` changes the installed
instructions; start a fresh conversation to load them. The Desktop source and
backup are not automatically synchronized. The companion `ingest` skill uses this
runtime, but Chief of Staff includes its ingestion helpers and can run by itself.

Perplexity still controls execution and write permissions. If prompted, approve
the installed folder through its normal permission UI. This package does not
alter permission settings or bypass the sandbox.

The runtime includes private credentials and cached mail. Exclude `runtime/`
before sharing source or instructions with anyone else.
