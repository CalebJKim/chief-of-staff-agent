---
name: chief-of-staff
description: Plan the day from Google Workspace evidence and complete the resulting Gmail, Calendar, Drive, Sheets, Docs, and Slides follow-ups.
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

For any request asking what to work on today, immediately run the Start of Day command below with the terminal tool. It works from Hermes CLI and is the only source for that briefing. Never inspect the current folder, Git state, dependencies, or cron jobs, and never use `execute_code` for this request.

Use the returned, bounded Workspace evidence to recommend the day and complete approved follow-ups. This skill continues to own follow-up requests in the same conversation, including “do the first item,” “put that in Gmail,” and tracker or deck updates.

If the decision packet reports a source as `ok`, its OAuth connection is proven. For supported operations below, use the focused action helper. Do not load the generic Google Workspace skill, probe for `gws`, or run setup checks. Report a connection problem only when the focused helper returns an OAuth or token error.

Never launch Chrome or use browser/computer tools to open Workspace links. Return links inline so the user can Ctrl-click them.

## Start of Day

Make exactly one terminal tool call, passing the command below verbatim as its entire command. It already reports failures: do not add redirection, fallbacks, diagnostics, pipes, or extra commands. Then answer immediately from its compact JSON. Do not reload this skill, rerun the scan, inspect the snapshot, or call another tool in the same turn.

```bash
bash "$HERMES_HOME/skills/productivity/chief-of-staff/scripts/start_day.sh"
```

When the packet has three data-ranked `workstreams`, use them in order. Render each exactly once; never split a workstream's related mail, meeting, and files into separate priorities. Otherwise rank up to three distinct outcomes from the remaining evidence. Give the reason, first action, and supplied inline links. Resolve relevant calendar conflicts and use only real availability. Never expose internal scores or turn stale relative dates into current deadlines.

## Initial Reply

Use exactly three numbered items and at most 65 words total. No heading, preamble, tables, inbox inventory, skipped-item list, separate conflict section, approval section, closing question, or detailed rationale. End immediately after item 3. Each item ends with exactly two links: one supporting `[Mail]` link and one action-target `[Calendar]`, `[Tracker]`, or `[Deck]` link. For scheduling, use the matching meeting's `calendar_url`, never a link extracted from mail.

1. **Outcome** — why now. **Next:** action. [Mail](URL) [Calendar or Drive](URL)
2. ...
3. ...

Recommend only; never claim an action happened before a successful write.

## Follow-ups

Use evidence already present in the packet; do not rerun broad ingest unless it is stale. A direct request to take the actions for the first, second, or third item authorizes that workstream's specific mutation.

Each executable workstream has an `action_command`. Immediately copy that command verbatim into exactly one terminal tool call as its entire command. Do not reload this skill, read the thread or artifact, translate the command, use `execute_code`, inspect `--help`, or run setup. The command already contains the resolved IDs and exact values and verifies every write. After success, report the verified result and returned inline URLs in one sentence under 30 words.

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
