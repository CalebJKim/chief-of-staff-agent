# Workspace seed specification

The seeder creates a self-contained realistic Chief of Staff workspace in the Google account connected through OAuth. It contains no account IDs, credentials, or links from the reference workspace.

## What it creates

- **6 imported Gmail messages** marked Inbox, Unread, and Important:
  - Exec Review moved to 5 PM
  - Approved performance metrics
  - Slide 6/7/10 review feedback
  - Leadership-review legal clearance
  - Marketing shoot venue deadline
  - Agent Security PRD deadline
- **95 Calendar events**: 19 per weekday, 8:00 AM–6:45 PM, with intentional overlaps.
- **1 Google Sheet**: `RTX Spark Campaign Tracker`
  - Tab: `Campaign Lanes`
  - Columns A:J: Lane, PIC, Status, Latest update, Next action, Due, Dependency/blocker, Evidence, Artifact, Notes
  - Status dropdown: On track, In review, Awaiting update, Blocked, Complete
- **1 Google Doc**: `RTX Spark Campaign Plan`
- **1 Google Slides deck**: `RTX Spark Exec Review`
  - 10 slides
  - Slide 4 intentionally waits for Mike’s performance figures
  - Slide 6 intentionally needs to move out of the live flow
  - Slide 10 contains the two leadership decisions

Generated IDs are stored only in the local file:

```text
$HERMES_HOME/chief-of-staff-workspace-state.json
```

The reset and cleanup commands use this file to delete imported mail/events and move generated Drive files to trash.

## Seed

First connect your own Google account as described in `QUICKSTART.md`. Then:

```bash
python demo/seed_workspace.py --confirm
```

To target a particular Monday:

```bash
python demo/seed_workspace.py --week-of 2026-08-17 --confirm
```

## Reset and cleanup

```bash
python demo/reset_workspace.py

# Permanently remove the seeded workspace instead:
python demo/seed_workspace.py --cleanup --confirm
```

## Manual fallback

If OAuth scopes or organization policy prevent the script from creating a resource, create the components manually:

1. **Sheet** — Create `RTX Spark Campaign Tracker`, tab `Campaign Lanes`, with the A:J columns listed above. Add at least these lanes: Product performance claims (Awaiting update), Exec Review deck (Awaiting update), Agent Messaging (Awaiting update), Marketing shoot (Blocked), Partner enablement (On track), Social rollout (Awaiting update), Retail demo readiness (Blocked), Legal intake (Awaiting update).
2. **Slides** — Create a 10-slide `RTX Spark Exec Review`. Put `Performance to go here - Mike Chen to provide` on slide 4, `Move the detail out of the live flow` on slide 6, and two decision asks on slide 10.
3. **Doc** — Create `RTX Spark Campaign Plan` with an agent-first narrative and open work for claims, retail demo ownership, shoot date, and Exec Review preparation.
4. **Calendar** — Add overlapping weekday events from 8 AM through roughly 7 PM. Include an RTX Spark Exec Review at 5 PM and an overlapping decision-triage event.
5. **Gmail** — Send or import messages to yourself containing the six topics above. Mark them unread/important. Include the generated Sheet/Slides/Doc links where relevant.

The exact names are helpful for artifact matching, but the Chief of Staff logic still reasons from the actual evidence rather than fixture IDs.

## Troubleshooting

- `403 insufficientPermissions`: reauthorize with all scopes in `setup/google-workspace/setup.py`.
- API not enabled: enable Gmail, Calendar, Drive, Docs, Sheets, and Slides APIs in the OAuth project.
- Workspace admin restriction: ask the administrator to allow the OAuth client/scopes.
- Existing state file: run cleanup first, or inspect/remove the local state only after manually cleaning created resources.
- Gmail import blocked by policy: send the six messages to the connected account manually; the rest of the seed can still be created.
