# Workspace seed specification

The seeder creates a self-contained realistic Chief of Staff workspace in the Google account connected through OAuth. It contains no account IDs, credentials, or links from the reference workspace.

## What it creates

- **8 imported Gmail messages** marked Inbox, Unread, and Important:
  - Exec Review moved to 5 PM
  - Approved performance metrics
  - Slide 6/7/10 review feedback
  - Leadership-review legal clearance
  - Marketing shoot venue deadline
  - Agent Security PRD deadline
  - SuperBox UI issues delay readiness; Engineering recommends holding SuperBox shoots and demos
  - Autonomous Robot Demo complete, engineering walkthrough passed, and ready for marketing shoots
- **70 low-priority background messages** and **1 contact message** so the inbox is realistic without hiding the important work. Synthetic senders use the visibly fake local-part pattern `name.example@nvidia.com`.
- **3 task-supporting emails** from Leah Moreno, Tessa Ellis and Evan Mercer, dated the seed/reset morning. They support a financial-analysis project ramp-up email, a GTC 2027 presenter reply awaiting the user's decision, and a request for the user’s proposed meeting-notes assistant design. The new fictional contacts use `example.com` addresses. These replace the old FAQ, pilot-lessons and workshop-budget requests. The 79 core/background/contact emails keep their repeatable, irregular timestamps, which normally run backward from 9:12 AM today into the previous afternoon/evening, in the configured workspace time zone. Before 9:12 AM, reset shifts this schedule so the newest message is one minute before the current minute, avoiding future timestamps while preserving gaps and ordering. Near midnight, some or all important messages may therefore be dated yesterday. Resets at or after 9:12 AM preserve the fixed clock times, with all eight important messages dated today.
- **89–90 Calendar events** across the workweek. Each day has a distinct, busy schedule with overlaps; the current workday also contains the 5 PM Exec Review.
- **3 unfinished Google Tasks in the default list (My Tasks)**, all due on the seed/reset date: draft Leah Moreno’s ramp-up email for the AI for Financial Analysis assistant, respond to the GTC 2027 presenter invitation, and define the Local AI Meeting Notes Assistant’s rough design in the project doc. Notes link to the source email and relevant files. They replace all six former demo tasks. Personal tasks are preserved.
- **3 additional Google Docs and a four-slide deck**: AI for Financial Analysis Assistant — Project Overview, Progress and Findings, and Next Steps, plus Local AI Meeting Notes Assistant — Design Outline. The latter contains the project’s purpose and four unfilled TODOs for the user experience diagram, local processing approach, review flow, and first-prototype scope and tradeoffs. Evan’s email follows up on the user’s proposed design and asks for a rough outline today. Tessa's email references the conversation seven days before seeding without deciding the user's availability. Resources are imported from editable Office templates and restored at the same Drive IDs on reset.
- **1 Google Sheet**: `NeoAgent V2 Campaign Tracker`
  - Tab: `Campaign Lanes`
  - Columns A:J: Lane, PIC, Status, Latest update, Next action, Due, Dependency/blocker, Evidence, Artifact, Notes
  - Status dropdown: On track, In progress, Awaiting update, Blocked, Complete
- **1 Google Doc**: `NeoAgent V2 Campaign Plan`
- **1 Google Slides deck**: `NeoAgent V2 Exec Review`
  - 10 slides
  - Slide 4 intentionally waits for Mike’s performance figures
  - Slide 6 intentionally needs to move out of the live flow
  - Slide 10 contains the two leadership decisions

Generated IDs are stored only in the local file:

```text
CoS_Workspace/.chief-of-staff-state/chief-of-staff-workspace-state.json
```

The reset and cleanup commands use this file to delete imported mail/events and move generated Drive files to trash. Google credentials live alongside it. Direct seed commands default to this directory, or use an explicit `COS_STATE_DIR`.

Google Tasks uses the account's default list, resolved through the API and saved in
the same state file. Reset replaces
only its seeded tasks, including completed ones, with fresh links to the new emails;
unrelated tasks are preserved. Cleanup also removes only seeded tasks and keeps the
list itself. Older states that refer to a separate demo list are cleaned there on
reset, then newly seeded tasks are placed in the default list. With an existing
connection that lacks Tasks permission, the first Tasks seed is skipped with setup
instructions; Gmail, Calendar, and Drive resets still work. Once a demo task list
exists, Tasks access is checked before any reset starts.


## Template fidelity

The Sheet, Doc, and Slides are imported from Office templates stored under `demo/templates/`. The executive deck uses a charcoal-and-green design with editable title/body fields and the same ten-slide scenario. Importing the templates preserves the tracker styling, conditional formatting, document structure, and slide design instead of rebuilding approximations through API calls. The imported files receive fresh Google IDs and are linked dynamically from seeded mail and calendar entries.

If slides were removed or added during the demo, or the local deck template has changed, reset re-imports the deck template into the same Google Slides file before restoring baseline text. The file ID and deck links stay unchanged; slide IDs may change, so start a fresh demo chat after reset. The workspace state records the template's SHA-256 fingerprint. Older states without that fingerprint receive a one-time refresh. With an unchanged template and the original slide count, reset keeps its existing text-only path. This restores the template deck, not custom structural edits.

## Seed

First connect your own Google account as described in `QUICKSTART.md`. Then:

```powershell
python demo/seed_workspace.py --confirm
```

To target a particular Monday:

```powershell
python demo/seed_workspace.py --week-of 2026-08-17 --confirm
```

## Reset and cleanup

```powershell
.\demo\reset_workspace.ps1

# Permanently remove the seeded workspace instead:
python demo/seed_workspace.py --cleanup --confirm
```

Reset also restores `CoS_Workspace/CoS_SecondBrain/` from the bundled baseline ZIP,
saving the previous demo vault under `demo/.second-brain-backups/`. It deletes all
other workspace contents except the four required `.chief-of-staff-state` files
listed in the README. Vaults outside `CoS_Workspace` and cron jobs are untouched.
`--cleanup` removes Google Workspace seed data only.

## Manual fallback

If OAuth scopes or organization policy prevent the script from creating a resource, create the components manually:

1. **Sheet** — Create `NeoAgent V2 Campaign Tracker`, tab `Campaign Lanes`, with the A:J columns listed above. Add at least these lanes: Product performance claims (Awaiting update), Exec Review deck (Awaiting update), Agent Messaging (Awaiting update), Marketing shoot (Blocked), Partner enablement (On track), Social rollout (Awaiting update), Retail demo readiness (Blocked), Legal intake (Awaiting update).
2. **Slides** — Create a 10-slide `NeoAgent V2 Exec Review`. Put `Performance to go here - Mike Chen to provide` on slide 4, a proposed retail customer-use example on slide 6 (local laptop comparison, an associate-reviewed follow-up draft, and customer details staying on the device), a pending Customer Example section on slide 7, and two decision asks on slide 10. Aisha's feedback asks to summarize that example in slide 7 before removing slide 6. The example is not customer validation or approval of the demo slate or owners.
3. **Doc** — Create `NeoAgent V2 Campaign Plan` with an agent-first narrative and open work for claims, retail demo ownership, shoot date, and Exec Review preparation.
4. **Calendar** — Add a varied schedule across the workweek rather than repeating the same meetings every day. On the current workday, include the NeoAgent V2 Exec Review at 5 PM and an overlapping decision-triage event.
5. **Gmail** — Send or import messages to yourself containing the six topics above. Mark them unread/important. Include the generated Sheet/Slides/Doc links where relevant. Use clearly synthetic addresses such as `elena.example@nvidia.com`.

## Fictional NeoAgent benchmark package

NeoAgent is an agent harness around an existing model. V2 is compared with NeoAgent V1 using the same 200 internal document, email, and scheduling workflows, model, and execution environment.

| Measure | NeoAgent V1 | NeoAgent V2 | V2 change versus V1 |
| --- | --- | --- | --- |
| Task success | 80% (160/200) | 92% (184/200) | +12 percentage points |
| Median completion time, normalized | 100 | 70 | 30% lower |
| Model tokens per completed task, normalized | 100 | 75 | 25% fewer |

These are fictional demo figures. Success requires the expected end state without an incorrect write. Time compares tasks completed by both versions. Tokens include input, output, and retries per completed task. Approval is for leadership review only. The evidence arrives in Mike's email and Second Brain, while slide 4 remains pending to support the deck-editing task.

`demo/neoagent_deck.json` is the shared content baseline for the richer 10-slide deck and the reset helper. `demo/build_neoagent_deck.mjs` builds its editable PPTX with the bundled artifact runtime. Preserve slide 6's example, slide 7's pending summary, and slide 10's open decisions when updating it.

The exact names are helpful for artifact matching, but the Chief of Staff logic still reasons from the actual evidence rather than fixture IDs.

## Troubleshooting

- `403 insufficientPermissions`: reauthorize with all scopes in `setup/google-workspace/setup.py`.
- API not enabled: enable Gmail, Calendar, Drive, Docs, Sheets, and Slides APIs in the OAuth project.
- Workspace admin restriction: ask the administrator to allow the OAuth client/scopes.
- Existing state file: run cleanup first, or inspect/remove the local state only after manually cleaning created resources.
- Gmail import blocked by policy: send the six messages to the connected account manually; the rest of the seed can still be created.

## Refresh only the task scenario

Using Python with the Google dependencies installed, run from this repository:

```text
python demo/seed_workspace.py --refresh-task-scenario --confirm
```

This creates missing task resources, replaces only the marked task-supporting emails, and replaces seeded tasks. It preserves the RTX documents/deck/tracker, calendar events, drafts and personal tasks. It checkpoints new file/message IDs in the state file. A full reset also restores the task resource templates, including the ETA placeholder. The three task notes keep essential context within the brief packet’s 240-character note limit; resource URLs follow it.

The DOCX source is `build_task_documents.py` (python-docx). The four-slide deck source is `build_task_deck.mjs` (the bundled artifact runtime). Runtime paths are supplied to the builders rather than stored in generated project documents. The seed process imports the checked-in templates and does not need the authoring runtimes.

## Product news scenarios

SuperBox and Autonomous Robot Demo are fictional projects. Morgan Reeves reports a recommended SuperBox hold, with no confirmed readiness date; this does not affect the NeoAgent shoot. Samira Noor confirms that the Autonomous Robot Demo is complete and ready for marketing shoots after its final engineering walkthrough. The robotics team has setup and reset instructions ready, but shoot dates have not been booked. Neither message requests a new user task. Both arrive on the seed morning under the existing timestamp policy. The two messages bring the total seeded email count to 82. Second Brain project and contact notes preserve their scope and ownership. The Financial Analysis project and its resources are unchanged.
