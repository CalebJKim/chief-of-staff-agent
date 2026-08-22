# Workspace seed specification

The seeder creates a self-contained RTX Spark Agent Runtime workspace in the Google account connected through OAuth. It contains no real account IDs, credentials, or reference-workspace links.

## What it creates

- **6 meaningful Gmail messages**, all in Inbox and Unread:
  1. Priya reports a P0 duplicate tool-completion regression and asks to postpone the release review. Important.
  2. Daniel supplies the replacement slot—Monday at 11:00 AM Pacific—and asks for an unsent confirmation draft to Priya and Daniel. Important.
  3. Mateo says the latency evaluation is complete and ready for review.
  4. Aisha confirms that only the evaluation tracker's status should change.
  5. Elena supplies the exact approved slide-4 headline.
  6. Rafael identifies the Partner Readout deck containing the placeholder.
- **100 background Gmail messages** from unique fictional people:
  - Each has a unique sender, subject, timestamp, and harmless low-signal body.
  - They are Inbox and Unread but not Important.
  - They are older than all six meaningful messages.
  - Ingestion reads only the newest 20 Inbox messages, so it sees all six meaningful messages plus 14 background messages.
- **12 Calendar resources** producing 47 visible meeting instances across one workweek:
  - Eight routine weekday series.
  - Three two-day series that overlap existing meetings at different times.
  - One Friday `RTX Spark Agent Runtime release review` that action 1 moves to Monday at 11:00 AM Pacific.
- **1 Google Sheet**: `RTX Spark Delivery Tracker`
  - Tab: `Campaign Lanes`
  - Columns A:J: Lane, PIC, Status, Latest update, Next action, Due, Dependency/blocker, Evidence, Artifact, Notes.
  - Eight data rows with a validated status dropdown.
  - The three actionable rows are Agent Runtime regression, Agent Runtime Latency Evaluation, and Partner Readout Deck.
- **1 Google Doc**: `RTX Spark Agent Runtime Latency Evaluation`
  - States that the evaluation is complete and ready for review.
- **1 Google Slides deck**: `RTX Spark Partner Readout`
  - Six slides.
  - Slide 4 contains `APPROVED HEADLINE PLACEHOLDER` and keeps all surrounding content intact.

Generated resource IDs and explicitly tracked demo draft IDs are stored only in:

```text
$HERMES_HOME/chief-of-staff-workspace-state.json
```

The reset and cleanup commands use this file to delete tracked demo drafts, permanently delete imported mail by exact message ID, delete imported Calendar resources, and move the generated Drive folder to Trash. Ordinary Gmail messages and drafts are never listed or deleted.

The start-of-day skill also writes a data-derived follow-up plan to:

```text
$HERMES_HOME/chief-of-staff/action-plan.json
```

That file contains only the resolved operations for the current three ranked workstreams. It is runtime state, not a Hermes default or model/provider setting.

## Expected demo flow

1. `Hey chief of staff, what should we work on today?`
   - Return exactly three succinct items in this order: regression, evaluation, deck.
   - End every item with its inline Mail link and Calendar, Tracker, or Deck link.
   - Do not show internal ranking scores and do not open a browser.
2. `Take the action items for the first thing.`
   - Move the existing release review to Monday at 11:00 AM Pacific without creating a duplicate.
   - Create an unsent reply draft in Priya's thread with Daniel copied.
3. `Take the action items for the second thing.`
   - Change only `Agent Runtime Latency Evaluation` from `In progress` to `Ready for review`.
4. Optional backup: `Take the action items for the third thing.`
   - Replace only `APPROVED HEADLINE PLACEHOLDER` with `Meet the RTX Spark Agent Runtime: a faster path from intent to completed work.`

## Seed, reset, and cleanup

First connect a dedicated demo Google account as described in `QUICKSTART.md`, then run:

```bash
python demo/seed_workspace.py --confirm
```

To target a particular Monday:

```bash
python demo/seed_workspace.py --week-of 2026-08-17 --confirm
```

Reset to a fresh copy:

```bash
python demo/reset_workspace.py
```

Remove the seeded workspace instead:

```bash
python demo/seed_workspace.py --cleanup --confirm
```

Gmail deletion is permanent; the Drive folder goes to Trash. If cleanup is partial, keep the state file and retry after fixing the reported problem.

## Manual fallback

If an organization policy prevents one resource from being created, reproduce the names and exact action data above. The most important constraints are:

1. Keep the six meaningful messages newer than the background mail, with Priya and Daniel marked Important.
2. Use one existing release-review event and provide Monday at 11:00 AM Pacific as the new slot.
3. Keep the Sheet tab named `Campaign Lanes` with the A:J schema and exact evaluation lane name.
4. Put the exact placeholder and approved replacement text in the Partner Readout evidence.

The skill resolves actions from current evidence and generated IDs; it does not depend on IDs committed to the repository.

## Troubleshooting

- `403 insufficientPermissions`: authorize all scopes in `setup/google-workspace/setup.py`.
- `disabled_client`: enable the OAuth client in Google Cloud or install a new Desktop client secret and authorize again. Retrying the old token does not help.
- API not enabled: enable Gmail, Calendar, Drive, Docs, Sheets, and Slides APIs.
- Workspace admin restriction: ask the administrator to allow the OAuth client/scopes.
- Existing or partial state file: run reset or cleanup; do not discard the file while tracked resources remain.
- Gmail import blocked by policy: manually create the six meaningful messages; the other resources can still be reproduced from this specification.
