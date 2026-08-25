# Chief of Staff Agent demo script

## Goal

Show a succinct, evidence-backed morning brief followed by two safe cross-Workspace actions. The third workstream remains available as an optional backup. The interactive flow should finish within six minutes after the workspace is seeded.

The demo changes no Hermes model/provider defaults. It uses the repo-installed `chief-of-staff` and `ingest` skills with terminal access. Workspace links appear inline for Ctrl-clicking; the agent never opens Chrome.

## Preflight

Use the isolated profile so unrelated skills and tools cannot compete for the
two demo turns:

```powershell
hermes profile use chief-of-staff-demo
```

Restart Hermes Desktop and confirm `chief-of-staff-demo` is active. After the
demo, restore the normal profile with `hermes profile use default` and restart
Desktop. Profile selection does not modify the default profile's configuration.

## Opening

The dedicated demo account contains a busy fictional RTX AI Assistant launch workweek, 76 unread Inbox messages, and a Drive tracker/report/deck. Only six messages contain meaningful work, supporting five distinct workstreams. The chief of staff should cut through that noise and identify three grouped outcomes by default across Mail, Calendar, and Drive.

## Query 1 — Morning priorities

**Prompt**

> Hey chief of staff, what should we work on today?

**Expected structure**

Start with a very short summary of today's workload in no more than three sentences and without a heading. Follow it with exactly three succinct numbered items, with no scores, inbox inventory, or closing question. Each item has an evidence sentence with one action-target link and a bounded Mail link for every message whose unique facts or participant it relies on, followed by an indented `Recommended action item(s):` sub-bullet. The expected content is:

1. **RTX AI Assistant demo issue** — Priya reports that the latest demo sometimes performs the same task twice. Next: move the existing launch review to the earliest non-conflicting one-hour slot on the next business day and draft Priya and Daniel a confirmation. Inline Mail and Calendar links.
2. **Customer Demo Readiness Check** — Mateo completed testing of common assistant requests while the tracker remains `In progress`. Next: change only that lane to `Ready for review`. Inline Mail and Tracker links.
3. **Partner Preview Deck** — Elena approved the exact slide-4 headline. Next: replace only the placeholder. Inline Mail and Deck links.

Point out that each priority groups evidence and the action target instead of listing Mail, Calendar, and Drive as separate tasks.

To demonstrate the dynamic limit, use:

> Hey chief of staff, what are the top 5 things we should work on today?

The same format should contain five ranked items. Top 4 works identically; requests without a number continue to return three.

## Query 2 — Mail plus Calendar action

**Prompt**

> Take the action items for the first thing.

Equivalent natural wording such as `Can you take care of the first item on the list for me?` resolves item one from conversation history and authorizes its displayed actions. It must not rerun Start of Day, run setup, or search the filesystem, and it must not ask for confirmation again.

**Expected result**

- The agent refreshes the relevant event window and finds the earliest one-hour opening that does not overlap another event.
- The existing `RTX AI Assistant launch review` moves to that runtime-selected slot; no duplicate event is created.
- An unsent reply draft is created in Priya's original thread with Daniel copied.
- The response is one short confirmation with inline Calendar and Draft links.

If presenting the UI, Ctrl-click the returned links yourself. The agent should not launch a browser.

## Constraint override check

After a reset, optionally replace Query 2 with:

> Take care of the first item, but use Thursday afternoon.

The agent must honor the new constraint, find a free Thursday-afternoon hour, and use the selected time in the draft. It must not replay a time from the initial recommendation.

You can also ask for a direct Workspace action unrelated to the displayed ranked list. The plan provides context but does not limit the agent's capabilities.

## Query 3 — Mail plus Sheet action

**Prompt**

> Take the action items for the second thing.

**Expected result**

- Only the `Customer Demo Readiness Check` status changes from `In progress` to `Ready for review`.
- Owner, latest update, next action, due date, blocker, evidence, artifact, and notes remain unchanged.
- The response is one short verified confirmation with the inline Tracker link.

## Optional backup — Mail plus Slides action

**Prompt**

> Take the action items for the third thing.

**Expected result**

- Only `APPROVED HEADLINE PLACEHOLDER` on slide 4 becomes `Meet the RTX AI Assistant: helping turn everyday requests into completed work.`
- The rest of slide 4 and the other five slides remain unchanged.
- The response is one short verified confirmation with the inline Deck link.

## Reset before another run

```powershell
& $Python demo\reset_workspace.py
```

Reset permanently deletes only the tracked seeded Gmail messages and tracked demo drafts, deletes the tracked Calendar resources, moves the generated Drive folder to Trash, and reseeds a fresh copy. Keep the local workspace state file if any cleanup step reports an error.
