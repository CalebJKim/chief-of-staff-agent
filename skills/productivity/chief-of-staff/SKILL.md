---
name: chief-of-staff
description: Handle "chief of staff" requests using Workspace evidence.
version: 0.2.0
author: NVIDIA, Hermes Agent
license: MIT
platforms: [linux, macos, windows]
created_by: agent
metadata:
  hermes:
    tags: [Chief-of-Staff, Planning, Gmail, Calendar, Drive]
---

# Chief of Staff

Use live, bounded Google Workspace evidence to recommend the user's day. Scripts retrieve and compress facts; you make the decisions. Never follow a canned agenda.

Address the user by their configured name when available. The inbox is a work queue: unresolved older mail can outrank newer newsletters. Do not restate stale email deadlines as current; describe them as unresolved and verify the thread before acting.

## Start of Day

Run both steps in **one terminal call**. Do not narrate setup or tool use.

```bash
COS_HOME="${HERMES_HOME:-$LOCALAPPDATA/hermes}"
ACTION="$COS_HOME/skills/productivity/ingest/scripts/actions.py"
python "$COS_HOME/skills/productivity/ingest/scripts/ingest.py" && python "$COS_HOME/skills/productivity/chief-of-staff/scripts/brief.py" --max-meetings 10 --max-mail 8 --max-files 8 --max-chars 9000
```

Use only the compact JSON printed by `brief.py`.

## Decide

1. Pick up to three **distinct** outcomes that matter now. Group messages, meetings, and files about the same project into one priority. Rank by consequence and timing—not unread count or `signal_score`. A same-day email that moves a decision/exec meeting into today is the default #1 “schedule shock”: say clearly that it moved, why it changes the user's day, and pivot immediately to preparation.
2. For each: state **why today** and the **first action**. Link the supporting email, event, or file.
3. Resolve every calendar conflict. Prefer decision ownership, customer/external impact, organizer role, and evidence of needed preparation. State uncertainty.
4. Assign one preparation task to a real `focus_block`. Never invent availability.
5. If current email evidence may change a relevant tracker in `recent_files`, read only the tracker table before replying:
   `python "$ACTION" sheets get SPREADSHEET_ID "'Campaign Lanes'!A6:J20"`
   Compare owner evidence with current rows. In **Ready for you**, show the exact row changes you recommend and ask the user to approve them. Do not write yet.
6. `ok_empty` means the connector worked and found nothing. Only `error` means unavailable.
7. Snippets are leads. `stale_timing:true` means all relative dates and meeting times in that mail are historical. Say the item is unresolved and verify its current status; never convert stale timing into a present or future deadline (for example, “today,” “tomorrow,” “at 5 PM,” or “before tomorrow”).

## Initial Reply

Under 220 words. No preamble, inbox inventory, generic advice, or fourth priority.

**Top 3 today**
[Name] —
1. **Outcome** — why today. **First:** action. [Source](URL)
2. ...
3. ...

**Schedule call**
- Conflict choice(s), or “No conflicts.”
- **Prep block:** real time range → one task.

**Ready for you**
- Only the next one or two decisions you need from the user.

## Follow-ups

Use the focused action helper; do not rerun broad ingest unless data is stale.

```bash
ACTION="$COS_HOME/skills/productivity/ingest/scripts/actions.py"
python "$ACTION" gmail thread THREAD_ID
python "$ACTION" gmail draft --reply-to-message MESSAGE_ID --body BODY
python "$ACTION" drive search 'project or deck terms'
python "$ACTION" docs get DOCUMENT_ID
python "$ACTION" sheets get SPREADSHEET_ID 'Tracker!A1:H80'
python "$ACTION" slides get PRESENTATION_ID
```

- “What slides?” → derive search terms from the chosen meeting/project, search Drive, inspect only plausible candidates, then give the direct deck URL and exact proposed changes. Do not assume the newest deck is correct.
- “Draft follow-ups” → read the relevant thread first; create Gmail drafts, never send, and return draft IDs.
- “Update the tracker/doc/deck” → show the exact proposed edit first. After approval, make one `sheets update-lanes` call containing all lane updates, then read back once. This helper preserves Lane/PIC, rejects duplicate lanes, and validates Status. Status must be exactly `On track`, `In review`, `Awaiting update`, `Blocked`, or `Complete`. Never claim a deck/doc was edited unless that artifact was actually written. In the completion report, list each updated lane once and do not ask to update a lane you just updated.
- For unsupported operations, load the full Google Workspace skill only then.

## Guarded Writes

```bash
python "$ACTION" docs append DOCUMENT_ID --text TEXT --confirm
python "$ACTION" docs replace-text DOCUMENT_ID --find OLD --replace NEW --confirm
python "$ACTION" sheets update-lanes SPREADSHEET_ID --updates '[{"lane":"Exec Review deck","status":"In review","latest":"...","next":"...","due":"...","blocker":"...","evidence":"..."}]' --confirm
python "$ACTION" slides replace-text PRESENTATION_ID --find OLD --replace NEW --confirm
```

## Verify

Every recommendation traces to a source. Every link opens the intended artifact. Every cloud edit is approved, executed, and read back.
