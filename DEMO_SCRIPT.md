# Chief of Staff Agent demo script

## Goal

Show a succinct, evidence-backed morning brief followed by two safe cross-Workspace actions. The third workstream remains available as an optional backup. The interactive flow should finish within six minutes after the workspace is seeded.

The dedicated demo profile uses `qwen3.6:35b-a3b-mtp-q4_K_M` through local Ollama with medium reasoning. The normal Hermes profile remains unchanged. The demo uses the repo-installed `chief-of-staff` and `ingest` skills with terminal access. Workspace links appear inline for Ctrl-clicking; the agent never opens Chrome.

## Preflight

Use the isolated profile so unrelated skills and tools cannot compete during
the demo flow:

```powershell
hermes profile use chief-of-staff-demo
```

Restart Hermes Desktop and confirm `chief-of-staff-demo` is active. After the
demo, restore the normal profile with `hermes profile use default` and restart
Desktop. Profile selection does not modify the default profile's configuration.

## Opening

The dedicated demo account contains a busy fictional RTX AI Assistant launch workweek, 76 unread Inbox messages, and a Drive tracker/report/deck. Only six messages contain meaningful work, supporting five distinct workstreams. The chief of staff should cut through that noise and identify three grouped outcomes by default across Mail, Calendar, and Drive.

## Query 1 — Introduction

**Prompt**

> Hey chief of staff, give me a quick intro? What kinds of things can you help me with?

Keep the next prompt in this same conversation so the loaded Chief of Staff skill remains in context. The response should be a concise overview of its planning and Google Workspace capabilities.

## Query 2 — Ranked work

**Prompt**

> Hey chief of staff, what should we work on today?

**Expected structure**

Start with one very short summary sentence and no heading. Follow it with exactly three succinct numbered items, with no scores, ranking commentary, inbox inventory, or closing question. Python applies the generic Gmail metadata policy before the model sees the packet, and the model must preserve that selection and order without reranking, merging, replacing, or skipping entries. The packet still includes Calendar, Drive, and Sheet context, so a clearly matching action-target link can appear alongside the selected Mail link. Each item also has an indented `Recommended action item(s):` sub-bullet. With a fresh seed, the expected content is:

1. **Priya's latest blocker** — the latest demo sometimes performs the same task twice, so today's review should be postponed.
2. **Daniel's scheduling request** — move the existing launch review to the next business day and prepare a confirmation in Priya's thread with Daniel copied.
3. **Mateo's readiness update** — testing is complete and the tracker should move from `In progress` to `Ready for review`.

Point out that the order comes from a transparent deterministic metadata policy, not an AI-generated priority ranking, even though the full Workspace context is still available to explain the items.

To demonstrate the dynamic limit, use:

> Hey chief of staff, what are the top 5 things we should work on today?

The same format should contain five deterministically ranked messages. With the reference seed those are Priya, Daniel, Mateo, Aisha, and Elena. Requests without a number continue to return three. All daily-brief requests use the same deterministic ranking.

## Query 3 — Mail plus Calendar action

**Prompt**

> Can you reschedule the launch review meeting, and prepare the email draft for my review?

The direct request authorizes the Calendar move and unsent draft. The agent must not rerun Start of Day, run setup, search the filesystem, or ask for confirmation again.

**Expected result**

- The agent refreshes the relevant event window and finds the earliest one-hour opening that does not overlap another event.
- The existing `RTX AI Assistant launch review` moves to that runtime-selected slot; no duplicate event is created.
- An unsent reply draft is created in Priya's original thread with Daniel copied.
- The response is one short confirmation with inline Calendar and Draft links.

If presenting the UI, Ctrl-click the returned links yourself. The agent should not launch a browser.

## Constraint override check

After a reset, optionally replace Query 3 with:

> Reschedule the launch review and prepare the email draft, but use Thursday afternoon.

The agent must honor the new constraint, find a free Thursday-afternoon hour, and use the selected time in the draft. It must not replay a time from the initial recommendation.

You can also ask for a direct Workspace action unrelated to the displayed brief. The list provides context but does not limit the agent's capabilities.

## Query 4 — Mail plus Sheet action

**Prompt**

> Update the Customer Demo Readiness Check tracker status based on Mateo's message.

**Expected result**

- Only the `Customer Demo Readiness Check` status changes from `In progress` to `Ready for review`.
- Owner, latest update, next action, due date, blocker, evidence, artifact, and notes remain unchanged.
- The response is one short verified confirmation with the inline Tracker link.

## Optional backup — Mail plus Slides action

**Prompt**

> Update the Partner Preview deck with Elena's approved headline.

**Expected result**

- Only `APPROVED HEADLINE PLACEHOLDER` on slide 4 becomes `Meet the RTX AI Assistant: helping turn everyday requests into completed work.`
- The rest of slide 4 and the other five slides remain unchanged.
- The response is one short verified confirmation with the inline Deck link.

## Reset before another run

```powershell
& $Python demo\reset_workspace.py
```

Reset permanently deletes only the tracked seeded Gmail messages and tracked demo drafts, deletes the tracked Calendar resources, moves the generated Drive folder to Trash, and reseeds a fresh copy. Keep the local workspace state file if any cleanup step reports an error.
