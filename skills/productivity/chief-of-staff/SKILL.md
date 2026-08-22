---
name: chief-of-staff
description: Build a Google Workspace-backed daily top-three plan and execute numbered follow-ups from that plan.
version: 0.5.0
author: NVIDIA, Hermes Agent
license: MIT
platforms: [linux, macos, windows]
created_by: agent
metadata:
  hermes:
    tags: [Chief-of-Staff, Planning, Gmail, Calendar, Drive]
---

# Chief of Staff

## Turn Router

Choose exactly one path after this skill is loaded:

- **Fresh daily plan:** Run `bash "$HERMES_HOME/skills/productivity/chief-of-staff/scripts/start_day.sh"` as the only terminal command, then return its preformatted Markdown verbatim as the entire answer.
- **Numbered follow-up:** When the user asks to act on the first, second, or third priority from the current conversation, run `bash "$HERMES_HOME/cos.sh" N` as the only tool call, replacing `N` with the matching item number, then report its verified result.

Never combine paths. For a numbered follow-up, do not load another skill, rerun Start of Day, inspect artifacts or help, run setup, use `execute_code`, or search the filesystem.

Use the returned, bounded Workspace evidence to recommend the day and complete approved follow-ups. This skill continues to own follow-up requests in the same conversation, including “do the first item,” “put that in Gmail,” and tracker or deck updates.

If the decision packet reports a source as `ok`, its OAuth connection is proven. For supported operations below, use the focused action helper. Do not load the generic Google Workspace skill, probe for `gws`, or run setup checks. Report a connection problem only when the focused helper returns an OAuth or token error.

Never launch Chrome or use browser/computer tools to open Workspace links. Return links inline so the user can Ctrl-click them.

## Start of Day

For the fresh-plan path, answer immediately with the command's output and no added preamble, heading, explanation, question, or closing. It already reports failures, so do not add redirection, fallbacks, diagnostics, pipes, or extra commands. Do not rerun the scan or inspect its snapshot.

The script dynamically ranks Workspace evidence and preformats each grouped workstream exactly once; never rewrite, split, merge, or re-rank its output. Never expose internal scores, raw IDs, helper commands, or OAuth diagnostics.

## Initial Reply

`brief.py` owns this presentation contract: a one-sentence workload summary with no heading, followed by exactly three numbered items. Each item has a bold outcome line, one evidence sentence ending with exactly two links, and an indented action sub-bullet labeled `Recommended action item(s):`. The script uses the matching meeting's Calendar URL for scheduling and ends after item 3. Return that text verbatim.

1. **Outcome**
   Why this matters now. [Mail](URL) [Calendar or Drive](URL)
   - **Recommended action item(s):** Take the specific next action.

Recommend only; never claim an action happened before a successful write.

## Follow-ups

Use evidence already present in the packet; do not rerun broad ingest unless it is stale. A direct request to take the actions for a ranked item authorizes that workstream's specific mutation. The packet persists resolved IDs in `chief-of-staff/action-plan.json`; the launcher resolves and verifies the selected workstream. After success, report the verified result and returned inline URLs in one sentence under 30 words.

For a supported follow-up that is not one of the ranked workstreams, use the focused helper directly. Read a full thread or artifact only when an exact value is genuinely missing. Never use `execute_code`, run setup, inspect `--help`, or load the generic Google Workspace skill.

```bash
ACTION="$HERMES_HOME/skills/productivity/chief-of-staff/scripts/action.sh"

bash "$ACTION" gmail thread THREAD_ID
bash "$ACTION" gmail draft --reply-to-message MESSAGE_ID --cc ADDRESS --body 'BODY'
bash "$ACTION" calendar move EVENT_ID --start ISO_DATETIME --end ISO_DATETIME --confirm
bash "$ACTION" drive search 'project or artifact terms'
bash "$ACTION" docs get DOCUMENT_ID
bash "$ACTION" sheets get SPREADSHEET_ID "'Campaign Lanes'!A6:J20"
bash "$ACTION" sheets update-lanes SPREADSHEET_ID --lane 'Lane name' --status 'In review' --confirm
bash "$ACTION" slides get PRESENTATION_ID
bash "$ACTION" slides replace-text PRESENTATION_ID --find 'OLD' --replace 'NEW' --confirm
```

- Gmail drafts are threaded and never sent. The helper tracks demo drafts automatically when a reference workspace is active.
- `calendar move` updates the existing event and preserves its other details; do not create a duplicate.
- `sheets update-lanes` preserves unspecified cells and validates the status.
- Read a deck before editing unless the current workstream action already provides the exact file, placeholder, and replacement.
- The helper verifies every write. Report only its returned result and inline URL. For unsupported operations only, load the full Google Workspace skill.

## Safety

Draft rather than send. Require an explicit user request before cloud writes. Never delete mail, events, or Drive artifacts through this skill. Every recommendation must trace to evidence, and every claimed write must be verified.

## Reference Workspace Seed

The repository demo seeder creates portable reference data in the connected account and records generated IDs locally for exact cleanup.
