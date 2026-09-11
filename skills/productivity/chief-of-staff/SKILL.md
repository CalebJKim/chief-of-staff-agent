---
name: chief-of-staff
description: Handle "chief of staff" requests using Workspace evidence.
license: MIT
metadata:
  version: 0.3.0
  author: NVIDIA, Hermes Agent
  platforms: [linux, macos, windows]
  created_by: agent
  hermes:
    tags: [Chief-of-Staff, Planning, Gmail, Calendar, Drive]
---

# Chief of Staff

Use live, bounded Google Workspace evidence to recommend the user's day. Scripts retrieve and compress facts; you make the decisions. Never follow a canned agenda.

Address the user by their configured name when available. The inbox is a work queue: unresolved older mail can outrank newer newsletters. Do not restate stale email deadlines as current; describe them as unresolved and verify the thread before acting.

## Start of Day

Run both steps in **one terminal call**. Do not narrate setup or tool use.

```bash
if [ -n "${HERMES_HOME:-}" ]; then
  COS_HOME="$HERMES_HOME"
elif [ -n "${LOCALAPPDATA:-}" ]; then
  COS_HOME="$LOCALAPPDATA/hermes"
else
  COS_HOME="$HOME/.hermes"
fi
if [ -f "$COS_HOME/hermes-agent/venv/Scripts/python.exe" ]; then PYTHON="$COS_HOME/hermes-agent/venv/Scripts/python.exe"; elif [ -x "$COS_HOME/hermes-agent/venv/bin/python" ]; then PYTHON="$COS_HOME/hermes-agent/venv/bin/python"; else PYTHON="$(command -v python3 || command -v python)"; fi
ACTION="$COS_HOME/skills/productivity/ingest/scripts/actions.py"
"$PYTHON" "$COS_HOME/skills/productivity/ingest/scripts/ingest.py" && "$PYTHON" "$COS_HOME/skills/productivity/chief-of-staff/scripts/brief.py" --max-meetings 10 --max-mail 8 --max-files 8 --max-chars 14000
```

Use only the compact JSON printed by `brief.py`.

## Decide

1. Choose up to three **distinct outcomes** with real consequences: a decision, delivery, customer commitment, or risk reduced. Rank by impact and timing—not unread count or `signal_score`. Within each list, merge overlapping items: if completing one would complete another, or one is a step toward another, keep one outcome and fold the supporting work into it. Use fewer items when the evidence supports fewer.
2. Explain **why today** and the **first action** in plain language a reader can understand before opening any files. Keep slide numbers, cell references, individual metrics, and edit instructions for focused follow-ups. Link the relevant evidence with descriptive Markdown labels, such as the sender/topic or file name; use actual supplied URLs, never placeholders.
3. Treat calendar conflicts as constraints on meaningful work, not standalone daily priorities. Mention a conflict only when it threatens an outcome and offer a practical choice. State uncertainty.
4. Use a real `focus_block` when suggesting time for preparation. Never invent availability.
5. Do not read or report on a tracker during the morning brief unless the user asks about it. Tracker maintenance is a separate delegated task.
6. `ok_empty` means the connector worked and found nothing. Only `error` means unavailable.
7. Snippets are leads. `stale_timing:true` means all relative dates and meeting times in that mail are historical. Say the item is unresolved and verify its current status; never convert stale timing into a present or future deadline (for example, “today,” “tomorrow,” “at 5 PM,” or “before tomorrow”).
8. In the morning brief, summarize an approval or update at the package level. Never quote metrics or detailed wording from a truncated snippet; read the full thread only in a later focused request.

## Initial Reply

Aim for under 220 words. No greeting, preamble, inbox inventory, generic advice, closing offer, or extra section. Use short bullets, big-picture outcome titles, and future/action wording for unfinished work.
Show relevant links inline in the response. Never open or launch a link, browser, or Chrome window unless the user explicitly asks you to.
Use the saved Google connection and the scripts' silent token refresh. If access fails, report the problem briefly; do not launch sign-in or rerun OAuth setup unless the user asks to reconnect.
Never show raw draft, message, thread, file, event, document, spreadsheet, or presentation IDs in user-facing replies. Use human-readable names and link labels; IDs are for internal tool calls only.

Use these three sections:

**What you need to know today**
- Only material facts that change today's plan, each with its source link. Describe approvals or feedback at the package level; omit slide numbers, cell references, and edit instructions. Do not turn these bullets into tasks.

**What you need to get done today**
- **Outcome** — why today and the first concrete action, followed by a descriptive source link in the same bullet. Include a real focus block or conflict choice inline only when it helps execute this outcome.
- Up to two other independent outcomes; do not list a parent outcome and its subtask separately.

**What I can take care of for you**
- Offer one or two specific, evidence-backed tasks that the available tools can perform, with the relevant source or artifact link inline. Describe the supporting execution you can take on, distinct from the user's decision or ownership above; do not repeat the same task in both lists. These are offers, not completed work or permission to start writes.
- Make each offer one clear task. Email offers should prepare drafts for review; the demo helpers cannot send messages.

Use ordinary bullets for readable lists. Do not promise that a chat checkbox saves progress or changes Google data. For an interactive checklist, link to [Google Tasks](https://tasks.google.com/) when a task list has been created there; the user can check items off in Google Tasks.

## Meeting Preparation

For “Help me prepare for [meeting],” do not run the start-of-day workflow and do not inspect a tracker.

1. Use the meeting/project to find the latest relevant feedback and organizer or decision-maker request in Gmail. Reuse full threads already read in this conversation when still current; otherwise read the relevant full threads. Use file links from that evidence; search Drive only when a required link is missing. Do not audit the deck or inspect unrelated files.
2. Summarize the situation, the concrete preparation still needed, and the decisions or outcomes the meeting should achieve. Separate requested work from work already completed. Ground each part in evidence; state any missing context briefly instead of inventing goals.
3. Reply concisely under these three headings, with descriptive inline links to the supporting emails and files:

   **Context**

   **What needs to get done before the meeting**

   **Goals for the meeting**

Use short bullets. Preparation is a read-only briefing; proposed edits or drafts remain proposed until the user requests or approves them. Include artifact-specific details only where they help explain the preparation.

## Follow-ups

Use the focused action helper; do not rerun broad ingest unless data is stale.

```bash
if [ -n "${HERMES_HOME:-}" ]; then COS_HOME="$HERMES_HOME"; elif [ -n "${LOCALAPPDATA:-}" ]; then COS_HOME="$LOCALAPPDATA/hermes"; else COS_HOME="$HOME/.hermes"; fi
if [ -f "$COS_HOME/hermes-agent/venv/Scripts/python.exe" ]; then PYTHON="$COS_HOME/hermes-agent/venv/Scripts/python.exe"; elif [ -x "$COS_HOME/hermes-agent/venv/bin/python" ]; then PYTHON="$COS_HOME/hermes-agent/venv/bin/python"; else PYTHON="$(command -v python3 || command -v python)"; fi
ACTION="$COS_HOME/skills/productivity/ingest/scripts/actions.py"
"$PYTHON" "$ACTION" gmail search 'name or project terms' --max 5
"$PYTHON" "$ACTION" gmail thread THREAD_ID
"$PYTHON" "$ACTION" gmail draft --reply-to-message MESSAGE_ID --body BODY
"$PYTHON" "$ACTION" drive search 'project or deck terms'
"$PYTHON" "$ACTION" docs get DOCUMENT_ID
"$PYTHON" "$ACTION" sheets get SPREADSHEET_ID 'Tracker!A1:H80'
"$PYTHON" "$ACTION" slides get PRESENTATION_ID
```

- “What slides?” → derive search terms from the chosen meeting/project, search Drive, inspect only plausible candidates, then give a human-readable inline link to the deck and the exact proposed changes. Do not assume the newest deck is correct.
- “Draft follow-ups” → use an existing verified thread or recipient when available. Otherwise run one bounded `gmail search`, then read the relevant thread before drafting. If no verified recipient is found, say so instead of guessing or retrying. Create Gmail drafts, never send, and confirm that each draft was saved without displaying its ID. End every draft body with a final standalone line exactly `Thanks`—no comma, name, placeholder, or text after it.
- “Update the tracker” → treat the direct imperative as authorization to apply evidence-backed tracker edits. Read the tracker once and run exactly one bounded full-evidence read: `"$PYTHON" "$ACTION" gmail important --max 12 --newer-than-days 2`. This returns complete bodies for recent important messages; do not run project searches or reopen those threads. If an awaiting lane still has no candidate evidence, run at most one bounded search using that lane or owner and read the matching thread. A contact-only message is not a status update. Make one `sheets update-lanes` call containing all supported lane updates, passing its JSON through standard input with `--updates-file -`; then read back once. Leave any lane without new evidence unchanged. This helper preserves Lane/PIC, rejects duplicate lanes, and validates Status. Status must be exactly `On track`, `In review`, `Awaiting update`, `Blocked`, or `Complete`.
- Mark a lane `Complete` when the requested evidence or clearance for that lane has arrived. Use `In review` when approved input exists but the artifact or downstream implementation remains pending. Do not leave a lane `Awaiting update` after reading the update it was waiting for.
- Use the exact heredoc form in Guarded Writes for update JSON. Do not use `printf`, `echo`, a temporary file, or a separate Python command to construct it.
- In the tracker completion report, use exactly `**Updated**` and `**Still needs action**`. Under `Updated`, name each written lane once with its new status. Under `Still needs action`, list every blocker, missing status, and unassigned owner; never call those rows “unchanged” or “no action needed.” Do not list healthy unchanged lanes, repeat the evidence analysis, or add a takeaway section. End with one sentence offering to prepare follow-up drafts for the unresolved items, but do not send mail. Never claim an artifact was edited unless it was actually written and read back.
- “Update the doc/deck” → show the exact proposed edit first. After approval, write and read back once. Never claim an artifact was edited unless it was actually written.
- For unsupported operations, load the full Google Workspace skill only then.

## Guarded Writes

```bash
if [ -n "${HERMES_HOME:-}" ]; then COS_HOME="$HERMES_HOME"; elif [ -n "${LOCALAPPDATA:-}" ]; then COS_HOME="$LOCALAPPDATA/hermes"; else COS_HOME="$HOME/.hermes"; fi
if [ -f "$COS_HOME/hermes-agent/venv/Scripts/python.exe" ]; then PYTHON="$COS_HOME/hermes-agent/venv/Scripts/python.exe"; elif [ -x "$COS_HOME/hermes-agent/venv/bin/python" ]; then PYTHON="$COS_HOME/hermes-agent/venv/bin/python"; else PYTHON="$(command -v python3 || command -v python)"; fi
ACTION="$COS_HOME/skills/productivity/ingest/scripts/actions.py"
"$PYTHON" "$ACTION" docs append DOCUMENT_ID --text TEXT --confirm
"$PYTHON" "$ACTION" docs replace-text DOCUMENT_ID --find OLD --replace NEW --confirm
"$PYTHON" "$ACTION" sheets update-lanes SPREADSHEET_ID --updates-file - --confirm <<'JSON'
[{"lane":"LANE_NAME","status":"In review","latest":"Normal text, including apostrophes.","next":"...","due":"...","blocker":"...","evidence":"..."}]
JSON
"$PYTHON" "$ACTION" slides replace-text PRESENTATION_ID --find OLD --replace NEW --confirm
```

## Verify

Every recommendation traces to a source. Every link opens the intended artifact. Every cloud edit is approved, executed, and read back.


## Reference Workspace Seed

For a portable reference Workspace, use the repository demo seeder and read the demo specification. It creates data only in the connected user account and stores generated IDs locally for cleanup.
