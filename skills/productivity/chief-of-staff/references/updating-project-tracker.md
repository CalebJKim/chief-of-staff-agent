# Updating Project Tracker

A tracker update request authorizes evidence-backed changes to the requested tracker and work items.

## 1. Gather evidence

Use [Command reference](command-reference.md) for `actions.py` commands and arguments.

- Read the tracker with `sheets get`. If its spreadsheet ID is unknown, find it with `drive search` first. Use the returned tab name, never a guessed name. Specify a range for another known tab.
- Read recent messages marked Important in Gmail: `gmail important --max 12 --newer-than-days 2`.
- Search only to fill evidence gaps. For an unresolved item lacking evidence, use one bounded search by verified sender or short project term, then read the matching thread.

## 2. Reconcile entries

- Review every requested item against current evidence, including unchanged entries. One update may affect several items.
- Apply the tracker’s status definitions to each item’s deliverable and explicitly required follow-up. Exclude unstated requirements, hypothetical next steps, and work tracked elsewhere.
- Reassess blockers. Received inputs are no longer missing. Distinguish unfinished work from missing prerequisites. Later-stage approvals block current work only if explicitly required to proceed.
- Keep status and details consistent with evidence. Preserve accurate values. Clear values only when evidence shows they no longer apply, never because information is missing.

## 3. Apply and verify

If no changes are supported, report that without modifying the tracker.

- Include each changed lane once in a JSON array, with its exact `lane` name and evidence-backed `status`, even for details-only updates or retries. Valid statuses: `On track`, `In progress`, `Awaiting update`, `Blocked`, `Complete`.
- Use `--include-details` for supported `latest`, `next`, `due`, `blocker`, and `evidence` changes. When explicitly asked for status-only changes, use `--status-only` with only `lane` and `status`.
- When changing status with `--include-details`, include any existing `blocker`: preserve or revise its text, or use `""` only when evidence confirms resolution.
- Omit unchanged or unsupported optional fields. Preserve formulas, source metric names, units, and approval scope.
- Batch changes in one `sheets update-lanes` call with the verified spreadsheet ID, actual tab name via `--sheet`, and `--confirm`. Use `--updates-file -` with the quoted input format in the [Supporting notes](command-reference.md#supporting-notes) section of the command reference.
- Read back once to verify writes and catch missed evidence-backed changes.

## 4. Report results

Report only requested tracker work using collected evidence.

- **Updated:** Table: **Lane | Original status | Updated status | Reason**. One row per changed lane with pre-edit and confirmed read-back statuses and a source-linked reason. Say if nothing changed.
- **Still needs action:** Missing updates or blockers requiring others’ action. Mark unclear ownership as unconfirmed.
- **Waiting on you:** Only actions or decisions explicitly assigned to the user. Presenting, attending, or receiving email does not establish ownership.
- **Next step:** At most one question offering a draft to a verified contact who owes information. No unrelated edits, requests for the user’s decisions from others, or drafts saved without approval.

List open items as bullet points, each under either **Still needs action** or **Waiting on you**, never both. Exclude healthy, unblocked lanes from both. Use confirmed statuses, not stale summary counts. Do not suggest maintaining those counts or imply other files were edited.
