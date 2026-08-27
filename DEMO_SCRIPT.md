# Chief of Staff demo script

Use the dedicated `chief-of-staff-demo` profile in one conversation. The profile uses `qwen3.6:35b-a3b-mtp-q4_K_M`.

## 1. Start the day

> Hey chief of staff, what should I work on today? Give me the top three things.

Expected:

1. Executive Review preparation is first. The context says the meeting moved up to today and links Maya's email plus a matching Workspace resource.
2. Customer pilot feedback is second.
3. Partner briefing review is third.

The response uses one short summary sentence followed by three named items. Each item has one or two high-level `Context:` sentences; it does not include a detailed action checklist yet.

## 2. Ask for meeting preparation

> Help me prepare for the Executive Review meeting.

Expected action items, derived from Maya's email and shown in this order:

1. Read and understand the product summary.
2. Write the deck's Introduction slide from the summary.
3. Mark the Executive Review Deck `Done` in the prep tracker.

The agent should show inline Doc, Slides, Sheet, Mail, or Calendar links when supported. It should not execute the tasks yet.

## 3. Understand the product

> Summarize the product summary Maya linked into a few bullet points so I can understand it before the meeting.

Expected: a concise bullet summary grounded in the live `RTX AI Assistant Product Summary` Doc, with its link.

## 4. Update the Introduction slide

> Put those bullet points on the Introduction slide of the executive review deck.

Expected: the agent reads the live deck, replaces only `INTRODUCTION BULLETS PLACEHOLDER` on slide 2 with the bullet points from the prior response, verifies the write, and returns the Slides link.

## 5. Complete the tracker item

> Mark the Executive Review Deck as Done in the prep tracker.

Expected: the agent inspects the live Sheet, discovers the `Executive Review Deck` row and `Status` column, sees that `Done` is allowed, changes only that cell from `In progress` to `Done`, verifies it, and returns the Sheet link.

## 6. Draft the completion reply

> Draft a reply to Maya saying that all three preparation items are done.

Expected: one unsent reply draft in Maya's original thread. It says the product summary was reviewed, the Introduction slide was updated, and the deck status was marked `Done`. The body ends with exactly `Thanks` and no comma.

## Reset before another run

```powershell
$Python = (Resolve-Path .\.venv\Scripts\python.exe).Path
$env:HERMES_HOME = Join-Path $env:LOCALAPPDATA "hermes\profiles\chief-of-staff-demo"
& $Python demo\reset_workspace.py
```

Reset deletes only tracked seeded Gmail and Calendar resources, moves the old seeded Drive folder to Trash, and creates a fresh copy.
