# Updating Project Tracker

A tracker update request authorizes evidence-backed changes to the requested tracker and work items.

## 1. Gather evidence

Use [Command reference](command-reference.md) for `actions.py` commands and arguments. Do not run ingest or Start of Day.

1. **Read the tracker.** Use `sheets get` unless its current contents are already in context. Find an unknown tracker ID with `drive search`. Do not search local notes for it. Use returned tab names and a range for another known tab. Identify each requested entry’s deliverable, status, and blocker, plus the tracker’s status definitions.
2. **Check existing email evidence.** Use at most one relevant email per lane, reusing it across lanes when applicable. If sufficient evidence is already in context, do not search or reread it.
3. **Find missing email evidence.** Batch bounded Gmail searches by verified sender or short project term. Select one relevant email per lane and read it once with `gmail get`. Do not read whole threads or additional emails for that lane. Search misses do not prove inputs are missing.
4. **Email evidence only.** Do not read supporting documents, decks, or Second Brain notes. Preserve statuses when the evidence does not support a change.

## 2. Reconcile entries

1. **Establish scope.** Identify the lane's deliverable and required dependencies. Exclude other lanes' work and downstream uses of its output. Do not add unstated requirements or hypothetical steps.
2. **Check completion first.** If current evidence confirms the deliverable is finished, use **Complete**. Do not add downstream work to keep it open. An outdated tracker entry does not mean the deliverable is unfinished.
3. **Check whether a change is supported.** If evidence establishes no change to the lane's progress, inputs, or blockers, preserve its status. Contact introductions alone do not establish progress. Tracker timestamps do not establish status accuracy.
4. **Classify unfinished work.**
   - **Awaiting update:** Required input is still missing.
   - **In progress:** Required input has arrived; the lane's drafting or edits remain.
   - **Blocked:** Evidence explicitly identifies a dependency preventing the lane's work from proceeding.
   - **On track:** Work remains and is progressing without a blocker.

   Missing input alone does not change **Awaiting update** to **Blocked**; evidence must establish an impediment to progress. Pending approvals block only work that requires them.
5. **Check consistency before writing.** The status, next action, and blocker must describe the same lane. A completed deliverable cannot remain **On track** or **In progress**. Apply shared evidence to every requested lane. Received inputs cannot remain missing.

- Preserve accurate values. Clear values only when evidence shows they no longer apply, never because information is missing.

## 3. Apply and verify

If no changes are supported, report that without modifying the tracker.

- Include each changed lane once in a JSON array, with its exact `lane` name and evidence-backed `status`, even for details-only updates or retries. Valid statuses: `On track`, `In progress`, `Awaiting update`, `Blocked`, `Complete`.
- Use `--include-details` for supported `latest`, `next`, `due`, `blocker`, and `evidence` changes. When explicitly asked for status-only changes, use `--status-only` with only `lane` and `status`.
- When changing status with `--include-details`, include any existing `blocker`: preserve or revise its text, or use `""` only when evidence confirms resolution.
- Omit unchanged or unsupported optional fields. Preserve formulas, source metric names, units, and approval scope.
- Batch changes in one `sheets update-lanes` call with the verified spreadsheet ID, actual tab name via `--sheet`, and `--confirm`. Use `--updates-file -` with the quoted input format in the “[Supporting notes](command-reference.md#supporting-notes)” section of the command reference.
- Submit the example directly to the shell tool, without a `powershell -Command` wrapper. Inside the single-quoted here-string, use plain JSON quotes (`"`), not `\"`.
- Read back once to verify writes and catch missed evidence-backed changes.

## 4. Report results

Report only requested tracker work using collected evidence.

- “Updated”: Table: **Lane | Original status | Updated status | Reason**. One row per changed lane with pre-edit and confirmed read-back statuses and a source-linked reason. Say if nothing changed.
- “Still needs action”: Missing updates or blockers requiring others’ action. Mark unclear ownership as unconfirmed.
- “Waiting on you”: Only actions or decisions explicitly assigned to the user. Presenting, attending, or receiving email does not establish ownership.
- “Next step”: At most one question offering a draft to a verified contact who owes information. No unrelated edits, requests for the user’s decisions from others, or drafts saved without approval.

List open items as bullet points, each under either “Still needs action” or “Waiting on you”, never both. Exclude healthy, unblocked lanes from both. Use confirmed statuses, not stale summary counts. Do not suggest maintaining those counts or imply other files were edited.
