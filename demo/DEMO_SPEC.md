# Workspace seed specification

The seeder creates a self-contained RTX Spark Agent Runtime workspace in the Google account connected through OAuth. It contains no real account IDs, credentials, or reference-workspace links.

The fictional scenario is fixed seed data. The Chief of Staff skill does not contain RTX Spark-specific actions: it reads the current Workspace evidence, interprets a bounded generic schema/sample/validation packet, renders the prescribed brief format, and decides follow-up operations from the user's current request. Spreadsheet writes discover the live tab, header row, target row, target column, value type, validation, formula, and protection state before updating one verified cell; runtime code does not copy the seeded status list, map business fields, or assume fixed coordinates.

## What it creates

- **6 meaningful Gmail messages**, all in Inbox and Unread:
  1. Priya reports a P0 duplicate tool-completion regression and asks to postpone the release review. Important.
  2. Daniel asks for the earliest non-conflicting one-hour slot on the next business day and an unsent confirmation reply in Priya's blocker thread with Daniel copied. Important.
  3. Mateo says the latency evaluation is complete and ready for review.
  4. Aisha reports that the completed reliability matrix is ready for review and asks for only that lane's status to change.
  5. Elena supplies the exact approved slide-4 headline.
  6. Jordan confirms that the partner-demo checklist is ready to start and asks for only that lane's status to change.
  - These six messages support five distinct actionable workstreams; Priya and Daniel jointly support the release-review workstream.
- **70 background Gmail messages** from unique fictional people:
  - Each has a unique sender, natural unnumbered subject, timestamp, and harmless low-signal body.
  - They are Inbox and Unread but not Important.
  - They are older than all six meaningful messages.
  - The seeder writes them before a final dedicated batch containing the six meaningful messages, keeping all six within Gmail's first 20 in the dedicated demo inbox.
  - Ingestion scans metadata for up to 120 matching Inbox messages, sorts by `internalDate`, and retains the newest 20, so it sees all six meaningful messages plus 14 background messages.
- **12 Calendar resources** producing 47 visible meeting instances across one workweek:
  - Eight routine weekday series.
  - Three two-day series that overlap existing meetings at different times.
  - One `RTX Spark Agent Runtime release review` on the resolved demo day.
  - Busy blocks on the next business day force scheduling actions to use current availability rather than a predetermined time.
- **1 Google Sheet**: `RTX Spark Delivery Tracker`
  - Tab: `Campaign Lanes`
  - Columns A:J: Lane, PIC, Status, Latest update, Next action, Due, Dependency/blocker, Evidence, Artifact, Notes.
  - Eight data rows with a validated, color-coded status dropdown, a frozen/filterable header, and task-specific column widths.
  - The seeded evidence contains five strongly supported workstreams. When interpreted from the live headers and rows alongside Gmail, Calendar, and Drive evidence, it should yield Agent Runtime regression, Agent Runtime Latency Evaluation, and Partner Readout Deck as the default top three, followed by Partner demo checklist and Reliability test matrix for top-four/top-five requests.
- **1 Google Doc**: `RTX Spark Agent Runtime Latency Evaluation`
  - Uses a structured internal-report layout with a branded title, section hierarchy, status and action callouts, and a true bulleted scope list.
  - States that the evaluation is complete and ready for review.
- **1 Google Slides deck**: `RTX Spark Partner Readout`
  - Six slides rendered from a reusable dark visual template with consistent typography, accent bars, content cards, footers, and page numbers.
  - Slide 4 contains `APPROVED HEADLINE PLACEHOLDER` and keeps all surrounding content intact.

Generated resource IDs and explicitly tracked demo draft IDs are stored only in:

```text
$HERMES_HOME/chief-of-staff-workspace-state.json
```

The reset and cleanup commands use this file to delete tracked demo drafts, permanently delete imported mail by exact message ID, delete imported Calendar resources, and move the generated Drive folder to Trash. Ordinary Gmail messages and drafts are never listed or deleted.

Start of Day writes only the bounded Workspace snapshot used to build the brief. It does not create an executable action plan.

## Expected demo behavior

1. `Hey chief of staff, what should we work on today?`
   - Read the current Workspace snapshot.
   - Return a short workload summary followed by three numbered priorities by default, or the explicitly requested top N.
   - Give every item two evidence links and a `Recommended action item(s):` sub-bullet.
   - Do not expose scores, internal IDs, or commands.
2. `Take care of the first item.`
   - Resolve the first item from conversation history.
   - Treat the request as authorization for the displayed actions without asking again.
   - Refresh the relevant email, event, and target-day availability.
   - Move the existing event to the earliest valid non-conflicting slot, preserve its duration and other details, and create the requested unsent draft.
   - Verify both writes and report the result.
3. `Take care of the first item, but use Thursday afternoon.`
   - Honor the new constraint instead of replaying the original recommendation.
   - Find a valid Thursday-afternoon slot before moving.
4. `Take care of the second item.` or `Take care of the third item.`
   - Derive exact values from the displayed recommendation and focused live reads.
   - Execute and verify the authorized change without a redundant confirmation prompt.
5. Requests unrelated to the displayed ranked list still work through the same focused Workspace helpers; they do not require rerunning Start of Day.

The current seed is designed to produce a stable demo narrative, but the interpretation and action flow contain no hardcoded project names, recipients, dates, status meanings/order, field aliases, or replacement text. Each run uses only the bounded live packet; it does not learn or retain per-user mappings. Changing the seeded evidence changes the presented contents and subsequent actions.

## Seed, reset, and cleanup

First connect a dedicated demo Google account as described in `QUICKSTART.md`, then run:

```bash
python demo/seed_workspace.py --confirm
```

By default, the demo day is today on weekdays or the upcoming Monday on weekends. To target a particular week instead:

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

If an organization policy prevents one resource from being created, reproduce the names and evidence above. The most important constraints are:

1. Keep the six meaningful messages newer than the background mail, with Priya and Daniel marked Important.
2. Use one existing release-review event on the demo day and enough next-business-day calendar activity to exercise availability-aware scheduling.
3. Keep the Sheet tab named `Campaign Lanes` with the A:J schema and exact evaluation lane name.
4. Put the exact placeholder and approved replacement text in the Partner Readout evidence.

The skill resolves resources from current evidence and generated IDs; it does not depend on IDs committed to the repository.

## Troubleshooting

- `403 insufficientPermissions`: authorize all scopes in `setup/google-workspace/setup.py`.
- `disabled_client`: enable the OAuth client in Google Cloud or install a new Desktop client secret and authorize again. Retrying the old token does not help.
- API not enabled: enable Gmail, Calendar, Drive, Docs, Sheets, and Slides APIs.
- Workspace admin restriction: ask the administrator to allow the OAuth client/scopes.
- Existing or partial state file: run reset or cleanup; do not discard the file while tracked resources remain.
- Gmail import blocked by policy: manually create the six meaningful messages; the other resources can still be reproduced from this specification.
