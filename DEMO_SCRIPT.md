# Chief of Staff Agent demo script

## Goal

Show a succinct, evidence-backed morning brief followed by two safe cross-Workspace actions. The third workstream remains available as an optional backup. The interactive flow should finish within six minutes after the workspace is seeded.

The demo changes no Hermes model/provider defaults. It uses the repo-installed `chief-of-staff` and `ingest` skills with terminal access. Workspace links appear inline for Ctrl-clicking; the agent never opens Chrome.

## Opening

The dedicated demo account contains a busy fictional RTX Spark Agent Runtime workweek, 106 unread Inbox messages, and a Drive tracker/report/deck. Only six messages contain meaningful work. The chief of staff should cut through that noise and identify three grouped outcomes across Mail, Calendar, and Drive.

## Query 1 — Morning priorities

**Prompt**

> Hey chief of staff, what should we work on today?

**Expected structure**

Exactly three succinct numbered items, with no heading, scores, inbox inventory, or closing question:

1. **Agent Runtime regression** — Priya's P0 duplicate-completion blocker. Next: move the existing release review to Monday at 11:00 AM PT and draft Priya and Daniel a confirmation. Inline Mail and Calendar links.
2. **Agent Runtime Latency Evaluation** — Mateo completed it while the tracker remains `In progress`. Next: change only that lane to `Ready for review`. Inline Mail and Tracker links.
3. **Partner Readout Deck** — Elena approved the exact slide-4 headline. Next: replace only the placeholder. Inline Mail and Deck links.

Point out that each priority groups evidence and the action target instead of listing Mail, Calendar, and Drive as separate tasks.

## Query 2 — Mail plus Calendar action

**Prompt**

> Take the action items for the first thing.

**Expected result**

- The existing `RTX Spark Agent Runtime release review` moves to Monday at 11:00 AM Pacific; no duplicate event is created.
- An unsent reply draft is created in Priya's original thread with Daniel copied.
- The response is one short confirmation with inline Calendar and Draft links.

If presenting the UI, Ctrl-click the returned links yourself. The agent should not launch a browser.

## Query 3 — Mail plus Sheet action

**Prompt**

> Take the action items for the second thing.

**Expected result**

- Only the `Agent Runtime Latency Evaluation` status changes from `In progress` to `Ready for review`.
- Owner, latest update, next action, due date, blocker, evidence, artifact, and notes remain unchanged.
- The response is one short verified confirmation with the inline Tracker link.

## Optional backup — Mail plus Slides action

**Prompt**

> Take the action items for the third thing.

**Expected result**

- Only `APPROVED HEADLINE PLACEHOLDER` on slide 4 becomes `Meet the RTX Spark Agent Runtime: a faster path from intent to completed work.`
- The rest of slide 4 and the other five slides remain unchanged.
- The response is one short verified confirmation with the inline Deck link.

## Reset before another run

```powershell
& $Python demo\reset_workspace.py
```

Reset permanently deletes only the tracked seeded Gmail messages and tracked demo drafts, deletes the tracked Calendar resources, moves the generated Drive folder to Trash, and reseeds a fresh copy. Keep the local workspace state file if any cleanup step reports an error.
