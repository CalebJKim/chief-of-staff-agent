---
name: ingest
description: 'Pull bounded Gmail, Calendar, Drive, and Google Tasks evidence.'
---
<!-- Original authors: NVIDIA, Hermes Agent. License: MIT. -->

# Ingest Skill

Pull a bounded, metadata-first Workspace snapshot for planning. It deliberately avoids full email bodies and document contents; retrieve those only after relevance is established.

## When to Use

- Refresh the chief-of-staff brief.
- Pull recent Gmail, Calendar, and Drive changes.
- Diagnose data coverage before making a plan.
- Don't use for sending mail or editing files.

## Prerequisites

- The installed Chief of Staff skill includes a saved Google token. Its initialization prepares a writable token copy in the current workspace’s `.chief-of-staff-state` folder for silent refresh. A permission error is not evidence that OAuth is missing; report the exact failed path and operation instead of asking for sign-in.
- Gmail, Calendar, Drive, Docs, Sheets, and Slides APIs enabled.
- Google Tasks API and Tasks read access for the optional unfinished-task evidence. A Tasks error is reported separately and does not discard other Workspace evidence.
- Use Perplexity’s Python, or system Python if absent. The selected Python must have the Google dependencies installed during setup. No Desktop checkout is required.

## How to Run

Use Perplexity's `shell` tool with Windows PowerShell 5.1 from the current thread workspace. Load the runtime initialization at the start of each call; `CosRoot` is the read-only installed skill and `CosHome` is writable state in the thread workspace:

```powershell
. (Join-Path $env:PPLX_SKILLS_DIR 'productivity\chief-of-staff\scripts\runtime.ps1')
& $Python "$CosRoot/scripts/ingest.py"
if ($LASTEXITCODE -ne 0) { throw 'Chief of Staff command failed; inspect the error above.' }
```

The snapshot is written to `$CosHome/chief-of-staff/snapshot.json`. The command prints only counts and connector errors.

Tasks retrieval reads one page of up to 20 unfinished tasks from My Tasks by default. Use `--task-list LIST_ID` for another list and `--max-tasks N` (1-100) to change the bound. Task titles, date-only due values, short notes, and source links are included; `coverage.tasks_has_more` indicates more tasks remain outside the page. No tasks are changed.

## Quick Reference

```powershell
. (Join-Path $env:PPLX_SKILLS_DIR 'productivity\chief-of-staff\scripts\runtime.ps1')
# Today plus tomorrow; active inbox and recent Drive files
& $Python "$CosRoot/scripts/ingest.py"
if ($LASTEXITCODE -ne 0) { throw 'Chief of Staff command failed; inspect the error above.' }

# Explicit local day and tighter bounds
& $Python "$CosRoot/scripts/ingest.py" --days-ahead 1 --days-back 30 --max-messages 35
if ($LASTEXITCODE -ne 0) { throw 'Chief of Staff command failed; inspect the error above.' }

# Use a focused Gmail query
& $Python "$CosRoot/scripts/ingest.py" --gmail-query 'in:inbox (is:unread OR label:important) -category:promotions'
if ($LASTEXITCODE -ne 0) { throw 'Chief of Staff command failed; inspect the error above.' }
```

## Procedure

1. Run ingestion once. Continue only when output says `"ok":true`.
2. Inspect `coverage.errors`. Name any failed connector instead of treating missing data as an empty inbox or calendar.
3. Pass the saved snapshot to the chief-of-staff packet builder. Do not print the full snapshot into model context.
4. Fetch a full Gmail thread or document only when the packet identifies it as relevant.

## Pitfalls

- Snapshot snippets are leads, not complete email evidence.
- Calendar events come from selected calendars and exclude declined/cancelled events.
- Fuzzy mail/file links are suggestions, not facts.
- Keep bounds small for local models; increase one source at a time.

## Verification

- `coverage` has nonzero expected sources and no unexplained errors.
- `generated_at` is current and `timezone` matches the Google account.
- The snapshot contains IDs and links needed for targeted follow-up reads.
