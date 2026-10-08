# Perplexity demo setup

**Native runtime update:** this branch now uses the bundled Windows ARM64 Rust
executable. The old interpreter-selection and Python runtime notes below are
historical. See [RUNTIME_README.md](skills/productivity/chief-of-staff/RUNTIME_README.md)
for the current runtime and [native/README.md](skills/productivity/chief-of-staff/native/README.md)
for builds and tests. Setup/reset utilities still use Python. Use your own OAuth
credentials; never distribute installed `runtime/` or local state folders.

## Local model server

The versioned launcher `setup/perplexity/start-llama-server.ps1` reproduces this
machine's Qwen3.6 server configuration, including `--reasoning-budget 756`.
It expects llama.cpp and the named GGUF model/projector files under
`C:\llama.cpp-n1x-b9775`; adjust `$llamaRoot` in the script for another location.
Model files and server binaries are not included in this repository.

```powershell
& .\setup\perplexity\start-llama-server.ps1
```

The launcher leaves an existing server running. To apply changed server arguments,
stop that server while idle and then run the launcher. The 756-token setting caps
thinking per model request, not the whole task or final answer. Perplexity requests
that disable thinking do not use this budget; request-level overrides may also
change the effective setting. Skill installation does not start the model server.

## Consolidated skill installation

Perplexity exposes only `chief-of-staff` for this demo. Its bundled scripts include
ingestion and packet generation; the agent follows Start of Day or Updating Second
Brain guidance to invoke the evidence launcher. Focused tasks use the action launcher.
All helper source files live in `skills/productivity/chief-of-staff/scripts`,
matching the installed skill. The legacy ingest folder retains its guidance and tests only.

Installation and refresh retire any existing standalone ingest installation to
`.pplx-state/retired-skills` outside the installed skills directory. The code-only
staging bundle follows the same convention. Credentials and demo data are preserved.
Start a new Perplexity session after deployment so previously loaded ingest guidance
is not retained in the conversation.

## Previous setup notes

Installed skill source: GitHub branch `editors_day_gtc_demo`, commit `3e161d733dfee1f39c2bbc67b8bfde773341ec42` (Prepare condensed start-of-day skill for demo testing), fetched again after the user's new commit on 2026-09-29. The installed skills use this committed version, with Perplexity frontmatter, PowerShell, self-contained runtime, and callout formatting adaptations. The manager callout uses a standard Markdown blockquote with a bold linked label; the GitHub alert marker is omitted. `setup/perplexity/source-version.json` and the installed `SOURCE_VERSION.json` record the exact deployed commit. The Desktop PPLX checkout's broader demo/setup files retain their earlier base; this update does not reset or reseed Google Workspace. Original repo and Hermes installation are preserved, as are installed notes, credentials, runtime, and state.

The current manual test is the first prompt only. This branch deliberately uses 9:30 AM on the snapshot's local date for demo planning while keeping the actual collection timestamp. Its condensed skill replaces the older detailed multi-task guidance; those removed sections have not been merged back in.

## Current configuration

- Perplexity ARM64 MSIX version `2026.9.35878.0`.
- Personal Max account; sandbox installed through Settings > Permissions > Local file system access > Enable. `PerplexitySandboxSvc` is running and Desktop tools is enabled.
- Settings > Local Inference > Advanced > Custom inference endpoint: `http://127.0.0.1:8080/v1`, model `qwen3.6-35b-a3b`. Connection test passed. API key blank; vision off.
- Select **Computer**, then the **Custom** local model for a new conversation.
- The existing local model server must be running. This setup does not start or replace that server.
- Native skills are installed under `C:\Users\testuser\.pplx\users\e2e7d85487ed9501\skills\productivity`. Perplexity discovered and loaded `chief-of-staff` in a real local conversation.
- Perplexity's terminal is Windows PowerShell 5.1. Start of Day invokes `chief-of-staff\scripts\daily_brief.ps1`, which initializes the workspace and runs the brief in one call. Pass `-WorkspaceRoot` with the selected folder's absolute path. Add `-Fixture` for an offline test. Other commands load `runtime.ps1` with the same workspace argument within their shell call.
- Python selection: use the account's `template\venv\Scripts\python.exe`, or system `python.exe`/`python3.exe` from PATH only if Perplexity's interpreter is absent. Windows Store aliases are excluded. There is no Python bundle in the skill. The selected interpreter must pass startup, Google dependency, and time-zone checks before the brief runs.
- Install the Google dependencies once into the selected interpreter with `uv pip install --link-mode copy --python <selected-python> -r setup/perplexity/requirements.txt`. Use copy mode so files inherit the destination folder permissions instead of retaining shared-cache permissions. Never install packages or switch interpreters in response to a failed brief. Installed `scripts` hold the helpers, and `runtime\state` holds initial credentials, workspace references, and a cached snapshot. No Second Brain is bundled with the skill.
- Select `Desktop\ChiefOfStaff_PPLX\CoS_Workspace` with Perplexity's folder picker. Its direct `CoS_SecondBrain` subfolder is the demo vault. `runtime.ps1` prepares sibling `.chief-of-staff-state`, copying seed credentials only when absent. OAuth refresh and snapshot writes use this writable copy. Existing refreshed tokens are preserved.
- `runtime-local.json` version 4 uses relative `seed_state_root` and the `perplexity-then-system` Python selection policy. `COS_STATE_DIR` is the workspace data directory. Runtime initialization generates `second-brain.json` from `<WorkspaceRoot>\CoS_SecondBrain`, without reading a legacy installed vault setting. The working directory may differ from the selected workspace, so pass `-WorkspaceRoot` explicitly.
- `Desktop\ChiefOfStaff_PPLX` holds source code and the selected `CoS_Workspace`. `.pplx-runtime\skills` is a code-only staging copy. Packaged Perplexity loads skills from the account-specific folder above, while reset and runtime share the state under `CoS_Workspace`.

Start Perplexity normally from Windows. The optional `Launch Perplexity Demo.cmd` no longer supplies ignored development environment overrides. Model selection is saved through the app's settings. The launcher has not been retested; app launching was previously rejected by Codex's automatic approval review, and the user launched it manually.

Start a fresh local Computer conversation after this update so it loads the installed instructions. If an old conversation tries to use Desktop paths, tell it to reload the installed Chief of Staff skill and its runtime initialization. Perplexity may still request permission for execution or writes inside the installed runtime; moving the dependencies does not change its sandbox policy. Use the app's normal approval flow if prompted.

The installed runtime contains private Google credentials and cached mailbox data. Do not upload, publish, or share the entire installed folder. Source code and skill instructions can be shared without `runtime`.

## Connect or reconnect Google Workspace

After installing Perplexity and the demo skills, run from this checkout:

```powershell
.\setup.ps1 -Harness perplexity
```

The launcher selects Perplexity's Python and this checkout's
`CoS_Workspace\.chief-of-staff-state` credential folder. It reuses a working
connection or guides you through Google authorization. First-time setup asks
for your downloaded Desktop OAuth client JSON. No `HERMES_HOME` setting is
needed. Append `-Check` for a read-only local path check, or see
[connection options](README.md#connect-google-workspace) for custom locations.
This connects Google only; it does not install skills, seed data, or reset the demo.

## Reset the demo

From PowerShell:

```powershell
Set-Location "$env:USERPROFILE\Desktop\ChiefOfStaff_PPLX"
.\demo\reset_workspace.ps1
```

The launcher selects Perplexity's Python, using system Python only if it is absent.
Credentials and resource IDs come from `CoS_Workspace/.chief-of-staff-state`.
No environment setup is required. It resets Google Workspace and restores
`CoS_Workspace/CoS_SecondBrain`, backing up the previous notes. Append `-Check` to
validate the local setup without resetting or calling Google, or `-WeekOf YYYY-MM-DD`
to change the saved demo week. After a successful reset, it removes generated
`daily-brief-*` folders and standalone packets/snapshots from `.chief-of-staff-state`
and its `chief-of-staff` subfolder, reporting removal counts. Credentials,
configuration, resource IDs, and unrelated workspace files are preserved.
See [reset details](README.md#reset-the-demo-data)
for what is replaced. Finish running jobs and pause scheduled jobs before resetting.

## Verification

The native-Python migration passed 45 Chief of Staff tests, 73 Google helper tests,
and eight startup regression tests. These cover Perplexity-Python preference,
system fallback when absent, missing dependencies, missing interpreters, the
single-call fixture pipeline, and rejection of missing `COS_STATE_DIR` even when
`HERMES_HOME` is set. These are standalone tests, not an in-app sandbox run.

Earlier installation checks (before this migration):

The `editors_day_gtc_demo` refresh passed all 40 installed Chief of Staff tests, including the new 9:30 AM planning tests. Windows PowerShell 5.1 parsed all five skill command blocks; local mocks executed them and verified that the first-prompt sequence runs ingestion before briefing and stops on ingestion failure. Bundled dependencies, notes, and cached briefing checks passed. The callout uses standard blockquote syntax with no alert marker. Live Perplexity generation and visual rendering are left for the user's manual first-prompt test.

The self-contained installation passed Windows PowerShell 5.1 checks: all five skill code blocks parse; four CLI helpers load; bundled Google/Python dependencies import with every Python search path inside the installed skill; local notes and a briefing from the existing snapshot work from a non-Desktop working directory. All 23 Second Brain tests pass, including resolution of a relative vault path. Reinstalling preserves installed state and notes. These are offline checks; they do not verify whether Perplexity will request execution/write permission for this folder. No live demo prompts or Google writes were run for this change.

Standalone Google API read checks and the PowerShell morning-brief helper sequence passed previously. A real Perplexity diagnostic verified shell execution, the native skills directory, and the managed Python path. The previous in-app evaluation was stopped at the user's request so they could test manually. The tracker and draft prompts were not run. Standalone checks do not count as in-app completion.

The earlier morning brief completed after folder access and runtime initialization were corrected. Exec preparation was interrupted when it moved toward unrequested deck edits. No result-quality evaluation was completed. This PowerShell-only refresh was checked offline; live demo prompts were not rerun.

See `DEMO_SCRIPT_PERPLEXITY.md` for the current first-prompt manual test. No tracker updates, drafts, schedules, or workspace resets are part of this test.

## Updating the demo later

To refresh skill code from a named local Git branch or commit, use `setup\perplexity\refresh-from-git.py --repository <original-repository> --ref <commit-or-branch> --skills-dir <account-skills-directory>`. This prepares an adaptation diff and proposed files without deploying. Add `--deploy` to update the PPLX source, staging, and installed skills after reviewing the diff. The refresh reads committed Git files, preserves the installed private runtime and notes, and records the resolved commit. It never checks out or edits the original repository. The converter fails if unsupported Bash/Hermes instructions remain; review new source syntax before proceeding.

Refresh this duplicate from the chosen source version and translate the original command examples to PowerShell. Retain the explicit workspace argument and direct `CoS_SecondBrain` subfolder convention. Run `setup\perplexity\install-self-contained.py --skills-dir <account-skills-directory>` using the existing Python runtime. The installer updates code and relative configuration while preserving existing credentials and state. It never copies Python or notes. On first installation it copies the prepared PPLX seed state. Python dependencies must be installed separately into the selected interpreter using the requirements file above. Do not use the older refresh scripts to deploy, because they restore obsolete runtime paths.

Do not place custom skills inside app-owned `skills\builtin`. Start a new conversation to load updated instructions. A different Perplexity account has its own skill directory; installation is not automatically shared between accounts. This demo is for Windows. The current Perplexity-managed Python is x64 3.12.12 on this ARM64 machine.

The latest refresh backup, source-to-PPLX skill diffs, and validation receipt are in `.pplx-state\powershell-refresh-20260929-105254`.

The previous enterprise-policy and Free-plan blockers are resolved by the Max account. `PERPLEXITY_SANDBOX_DIAGNOSTIC.md` retains the historical investigation. No package ACLs or security policies were changed. The supplied MSIX signing certificate was previously installed in Local Machine Trusted People (thumbprint `90AFE03B2859D675BF620C8477A99DA7802CF9AA`).
