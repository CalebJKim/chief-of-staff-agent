---
name: chief-of-staff
description: Build a Google Workspace-backed daily top-three plan and handle related or direct Workspace actions.
version: 0.6.0
author: NVIDIA, Hermes Agent
license: MIT
platforms: [linux, macos, windows]
created_by: agent
metadata:
  hermes:
    tags: [Chief-of-Staff, Planning, Gmail, Calendar, Drive]
---

# Chief of Staff

## Request Routing

Choose the behavior that matches the user's current request:

- **Daily brief:** Only when the user asks what to work on today or asks to start the day, run `bash "$HERMES_HOME/skills/productivity/chief-of-staff/scripts/start_day.sh"` as the only terminal command and return its preformatted Markdown verbatim.
- **Plan follow-up:** Resolve references such as "the first item" from the most recent brief in conversation history. Combine that evidence with the complete current request; the user's newest instructions and constraints override the earlier recommendation. Do not rerun Start of Day.
- **Direct Workspace request:** Handle supported Gmail, Calendar, Drive, Docs, Sheets, or Slides work even when it is unrelated to the brief. Use focused reads and actions below; a daily plan is not required.
- **General question:** Answer normally without running Start of Day or Workspace commands.

If a numbered item cannot be resolved from the current conversation, ask what the user means rather than guessing. Never translate an item number directly into a stored command.

Use bounded Workspace evidence to recommend the day and complete requested work. Do not run setup checks, probe for `gws`, use `execute_code`, or search the filesystem for capabilities. If the decision packet reports a source as `ok`, its OAuth connection is proven; report a connection problem only when the focused helper returns an OAuth or token error.

Never launch Chrome or use browser/computer tools to open Workspace links. Return links inline so the user can Ctrl-click them.

## Start of Day

For the daily-brief path, answer immediately with the command's output and no added preamble, heading, explanation, question, or closing. It already reports failures, so do not add redirection, fallbacks, diagnostics, pipes, or extra commands. Do not rerun the scan or inspect its snapshot.

The script dynamically ranks Workspace evidence and preformats each grouped workstream exactly once; never rewrite, split, merge, or re-rank its output. Never expose internal scores, raw IDs, helper commands, or OAuth diagnostics. The script creates recommendations only; it never stores executable actions.

## Initial Reply

`brief.py` owns this presentation contract: a one-sentence workload summary with no heading, followed by exactly three numbered items. Each item has a bold outcome line, one evidence sentence ending with exactly two links, and an indented action sub-bullet labeled `Recommended action item(s):`. The script uses the matching meeting's Calendar URL for scheduling and ends after item 3. Return that text verbatim.

1. **Outcome**
   Why this matters now. [Mail](URL) [Calendar or Drive](URL)
   - **Recommended action item(s):** Take the specific next action.

Recommend only; never claim an action happened before a successful write.

## Follow-ups and Direct Actions

Use conversation history to resolve a displayed priority, then perform focused live reads before writing. Do not rerun broad ingest unless the snapshot is stale. A request to "take care of," "do," or otherwise complete a displayed priority is explicit authorization for its displayed actions and any constraints in the current request. Do not ask for redundant confirmation; pass `--confirm` to guarded helpers, verify the result, and report it.

Do not treat a recommendation as a command. The current request controls what happens: "only draft the email" authorizes no calendar write, while "find a conflict-free time" requires an availability check before moving. If live state has changed so substantially that the authorized action is no longer applicable, stop and explain the mismatch.

For a request outside the ranked workstreams, use the same focused helper directly. Read only the relevant thread, event window, tracker range, document, or deck needed to determine exact values.

```bash
ACTION="$HERMES_HOME/skills/productivity/chief-of-staff/scripts/action.sh"

bash "$ACTION" gmail thread THREAD_ID
bash "$ACTION" gmail draft --reply-to-message MESSAGE_ID --cc ADDRESS --body 'BODY'
bash "$ACTION" calendar get EVENT_ID
bash "$ACTION" calendar list --start ISO_DATETIME --end ISO_DATETIME --query 'meeting terms'
bash "$ACTION" calendar availability --start ISO_DATETIME --end ISO_DATETIME --duration-minutes 60 --exclude-event EVENT_ID
bash "$ACTION" calendar move EVENT_ID --start ISO_DATETIME --end ISO_DATETIME --confirm
bash "$ACTION" drive search 'project or artifact terms'
bash "$ACTION" docs get DOCUMENT_ID
bash "$ACTION" sheets get SPREADSHEET_ID "'Campaign Lanes'!A6:J20"
bash "$ACTION" sheets update-lanes SPREADSHEET_ID --lane 'Lane name' --status 'In review' --confirm
bash "$ACTION" slides get PRESENTATION_ID
bash "$ACTION" slides replace-text PRESENTATION_ID --find 'OLD' --replace 'NEW' --confirm
```

- Gmail drafts are threaded and never sent. Unless the user requests a different closing, end each draft with `Thanks,` and never `Best regards,`. The helper tracks demo drafts automatically when a reference workspace is active.
- Before moving an event, read the relevant date and use `calendar availability` when the requested or recommended time may conflict. Preserve the event's duration. Unless the user explicitly requests otherwise, constrain availability and rescheduling to working hours in the calendar's local timezone: the event must start no earlier than 8:00 AM and end no later than 5:00 PM. If a proposed slot is occupied, automatically use the earliest slot satisfying the user's stated day or window; ask only when no valid slot exists.
- `calendar move` updates the existing event, preserves its other details, and rejects conflicts unless the user explicitly asks to allow one. Do not create a duplicate.
- `sheets update-lanes` preserves unspecified cells and validates the status.
- Read a deck before editing unless the exact file, placeholder, and replacement are already visible in current conversation evidence.
- The helper verifies every write. After success, report the verified result and returned inline URLs concisely.

## Safety

Draft rather than send. A direct request to complete a displayed action or a direct Workspace mutation is approval for that scoped write; do not ask twice. Never delete mail, events, or Drive artifacts through this skill. Every recommendation must trace to evidence, and every claimed write must be verified.

## Reference Workspace Seed

The repository demo seeder creates portable reference data in the connected account and records generated IDs locally for exact cleanup.
