# Workspace seed specification

The seeder creates a self-contained fictional RTX AI Assistant executive-review workspace in the Google account connected through OAuth. Runtime logic remains scenario-neutral: Python ranks live Gmail metadata, and guarded helpers discover live file structure, validation, recipients, and replacement text.

## Seeded workspace

- **Gmail:** six meaningful unread messages above 70 older low-signal messages. The three messages that drive the daily brief are marked Important so they stay together in Gmail's standard and Priority Inbox views.
  - Maya's Important message says the executive review moved from Friday to 3:00 PM today. In natural prose, it asks the recipient to read the product summary, use it to update the deck's Introduction slide, and mark the Executive Review Deck `Done` afterward. It links the meeting, Doc, Slides, and Sheet and does not label Maya as the recipient's manager or present a numbered/bulleted checklist.
  - Priya asks for a decision on customer-pilot scope.
  - Elena asks for a plain-language review of the partner briefing.
  - Jordan reports that the morning demo-environment check passed and asks for a final check.
  - Mateo and Aisha provide lower-priority background items.
- **Calendar:** ten tightly scheduled weekday series from 8:00 AM through 5:30 PM, three supplemental series, and one `RTX AI Assistant Executive Review` at 3:00–4:00 PM on the demo day. The 2:00–3:00 PM hour stays open on Monday and Thursday for conflict-free rescheduling. The event description links the Doc, Slides, and Sheet.
- **Google Doc:** `RTX AI Assistant Product Summary`, a concise formatted brief covering product value, operation, pilot signals, safeguards, and the decision requested.
- **Google Slides:** `RTX AI Assistant Executive Review`, a six-slide reusable dark template. Slide 2 is `Introduction` and contains the unique text `INTRODUCTION BULLETS PLACEHOLDER`.
- **Google Sheet:** `RTX AI Assistant Exec Review Prep Tracker`, tab `Pre-Exec Review`. The `Executive Review Deck` row starts at `In progress`; its live status validation includes `Done`.

Generated IDs and tracked demo draft IDs exist only in `$HERMES_HOME/chief-of-staff-workspace-state.json`.

## Expected flow

1. `Hey chief of staff, what should I work on today? Give me the top three things.`
   - Start of Day batches bounded Gmail, Calendar, Drive, and Sheet reads.
   - Python returns distinct work items in deterministic order. The executive review is first because Maya's message is Important; pilot scope and partner briefing follow.
   - Each item has a name and one or two high-level `Context:` sentences. No action checklist appears in this initial brief.
   - An explicit top N returns that many available distinct items.
2. `Help me prepare for the Executive Review meeting.`
   - The agent rereads Maya's message and returns, in order, the three evidence-backed tasks: understand the product summary, write the Introduction slide from it, and mark the deck `Done` in the tracker.
3. `Summarize the product summary Maya linked into a few bullet points so I can understand it before the meeting.`
   - The agent reads the live Doc and returns a concise bullet summary with its link.
4. `Put those bullet points on the Introduction slide of the executive review deck.`
   - The agent reads the live deck, replaces only the confirmed placeholder with the bullets from conversation, and verifies the write.
5. `Mark the Executive Review Deck as Done in the prep tracker.`
   - The agent inspects the live Sheet schema, resolves the row/header intersection, reads the cell's allowed values, changes only that status from `In progress` to `Done`, and verifies it.
6. `Draft a reply to Maya saying that all three preparation items are done.`
   - The agent uses Maya's received message as the thread and recipient source, creates one unsent reply draft, verifies it, and ends with `Thanks` without a comma.

## Runtime invariants

- The dedicated profile remains on `qwen3.6:35b-a3b-mtp-q4_K_M`.
- Start of Day keeps the existing batched Gmail, Calendar, Drive, and Sheet ingestion path.
- No project names, dates, recipients, task lists, Sheet coordinates, status meanings, or replacement text are implemented as runtime routing rules.
- Docs, Slides, Sheets, and Gmail actions use generic focused helpers and live IDs.
- The skill and `SOUL.md` remain lightweight; full story detail lives here and in the seeder.

## Seed, reset, and cleanup

```bash
python demo/seed_workspace.py --confirm
python demo/reset_workspace.py
python demo/seed_workspace.py --cleanup --confirm
```

Reset permanently deletes only tracked seeded mail and calendar resources, moves the tracked Drive folder to Trash, and creates a fresh workspace. Keep the state file if cleanup is incomplete.
