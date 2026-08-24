---
name: chief-of-staff
description: Build a Google Workspace-backed ranked daily plan and handle related or direct Workspace actions.
version: 0.7.0
author: NVIDIA, Hermes Agent
license: MIT
platforms: [linux, macos, windows]
created_by: agent
metadata:
  hermes:
    tags: [Chief-of-Staff, Planning, Gmail, Calendar, Drive]
---

# Chief of Staff

## Repository-managed Runtime

This demo skill and the `ingest` skill are immutable runtime dependencies managed by the repository and refreshed by `setup_profile.py`. Never call `skill_manage`, never create or patch a skill, and never edit installed skill files during a demo session. If guidance appears incomplete or a helper fails, continue with another documented helper when safe and report the gap for a repository change after the run.

## Request Routing

Choose the behavior that matches the user's current request:

- **Daily brief:** Only when the user asks what to work on today or asks to start the day, run `bash "$HERMES_HOME/skills/productivity/chief-of-staff/scripts/start_day.sh"` as the only terminal command. The helper returns one compact live-evidence packet, not a prepared answer. Interpret that packet under the bounded rules below and produce the final brief yourself. The default is three priorities. If the user explicitly asks for the top N items, append `--top N` to that command, using the positive integer from the request. Add no preamble, second copy, closing question, or offer.
- **Plan follow-up:** Resolve references such as "the first item" from the most recent brief in conversation history. Combine that evidence with the complete current request; the user's newest instructions and constraints override the earlier recommendation. Do not rerun Start of Day.
- **Direct Workspace request:** Handle supported Gmail, Calendar, Drive, Docs, Sheets, or Slides work even when it is unrelated to the brief. Use focused reads and actions below; a daily plan is not required.
- **General question:** Answer normally without running Start of Day or Workspace commands.

If a numbered item cannot be resolved from the current conversation, ask what the user means rather than guessing. Never translate an item number directly into a stored command.

Use bounded Workspace evidence to recommend the day and complete requested work. Begin with the documented skill helper. Never run `git`, `pwd`, `ls`, `echo`, environment-variable probes, date commands, repository checks, setup/config diagnostics, probe for `gws`, use `execute_code`, or search the filesystem for capabilities. If the decision packet reports a source as `ok`, its OAuth connection is proven; report a connection problem only when the focused helper returns an OAuth or token error.

Never launch Chrome or use browser/computer tools to open Workspace links. Return links inline so the user can Ctrl-click them.

## Start of Day

For the daily-brief path, use the single packet returned by Start of Day and do not run another tool, rerun the scan, or inspect its saved snapshot. The packet already reports source failures. Never add redirection, fallbacks, diagnostics, pipes, or extra commands. Do not use or mention the implementation helpers documented later in this skill while writing the brief; recommendations state the desired end state and scope only.

The packet contains compact Gmail, Calendar, Drive, and generic Sheet evidence. For Sheets it supplies exact visible headers, representative row units, and validation previews without assigning business meaning to any column. Infer meaning only from those live values. Never assume canonical field names, fixed status meanings or order, row positions, or action types. Never use remembered, user-learned, or workspace-specific mappings. Follow the packet's `selection_rules` in order. Treat each independently actionable `sheet_evidence.tabs.row_units` entry or standalone request as a separate priority; never combine separate row units merely because they use the same app, field, or operation. Group messages only when their live contents clearly support the same outcome. Ignore rows whose own text says no action remains. After explicit same-day or Gmail-Important blockers, rank remaining row units by `source_order`; do not override that stable order with vague timing labels or an invented status ranking. The packet creates recommendations only; it never stores executable actions.

## Initial Reply

Follow the packet's `response_contract` exactly. Output only one workload-summary sentence with no heading or preamble, immediately followed by the requested number of ranked items (three by default). Render each item as exactly three lines: a bold outcome line; one separate indented sub-bullet labeled `Evidence:` containing a complete sentence and ending with exactly one real action-target link plus a distinct `[Mail — SENDER](URL)` link for every live message whose unique facts or participant the item relies on, bounded to at most three Mail links; and one indented action sub-bullet labeled `Recommended action item(s):` that states only the desired end state and scope. Never put evidence text or links on the outcome line. When several messages support one outcome, attribute each distinct fact to its live sender in that same evidence sentence and copy each sender name exactly from live `mail.from`. Copy the action-target URL from the relevant Calendar event, Sheet, recent Drive file, or URL-valued cell in the selected row; label it Calendar, Sheet, Doc, Slides, or Drive according to the live URL. Never relabel a target or add unrelated mail. Before finalizing, silently verify the item count, three-line format, that every evidence line has one target link and all relied-on Mail links, exact sender names, and that no raw IDs, helper names, flags, commands, row numbers, cell coordinates, backticks, extra sections, closing question, or offer appears. End after the final action line.

1. **Outcome**
   - **Evidence:** Why this matters now. [Calendar, Sheet, Doc, Slides, or Drive](URL) [Mail — Sender](URL)
   - **Recommended action item(s):** Take the specific next action.

Recommend only; never claim an action happened before a successful write.

## Follow-ups and Direct Actions

Use conversation history to resolve a displayed priority, then perform focused live reads before writing. Do not rerun broad ingest unless the snapshot is stale. A request to "take care of," "do," or otherwise complete a displayed priority is explicit authorization for its displayed actions and any constraints in the current request. Do not ask for redundant confirmation; pass `--confirm` to guarded helpers, verify the result, and report it.

Include `--confirm` in the first invocation of every authorized write helper; never probe a write by deliberately omitting it. For a displayed Calendar priority, the date and participant facts came from the displayed evidence, not from a later shorthand request such as "reschedule it." Reread the focused Calendar/Gmail evidence, call `calendar find` immediately before the write, and use the received scheduling message as `--date-source-message`. Never rewrite a date from the earlier brief into `--user-request-text`; that flag is valid only when the literal current user message itself contains the date or weekday.

Do not treat a recommendation as a command. The current request controls what happens: "only draft the email" authorizes no calendar write, while "find a conflict-free time" requires an availability check before moving. If live state has changed so substantially that the authorized action is no longer applicable, stop and explain the mismatch.

For a request outside the ranked workstreams, use the same focused helper directly. Read only the relevant thread, event window, tracker range, document, or deck needed to determine exact values.

```bash
bash "$HERMES_HOME/skills/productivity/chief-of-staff/scripts/action.sh" gmail search 'message or project terms' --from 'optional sender filter' --subject 'optional subject filter'
bash "$HERMES_HOME/skills/productivity/chief-of-staff/scripts/action.sh" gmail thread THREAD_ID
bash "$HERMES_HOME/skills/productivity/chief-of-staff/scripts/action.sh" gmail reply-draft MESSAGE_ID --include-sender-from-message OTHER_MESSAGE_ID --body 'BODY' --verify-calendar-event EVENT_ID
bash "$HERMES_HOME/skills/productivity/chief-of-staff/scripts/action.sh" calendar find --query 'exact meeting title or terms'
bash "$HERMES_HOME/skills/productivity/chief-of-staff/scripts/action.sh" calendar get EVENT_ID_FROM_FIND
bash "$HERMES_HOME/skills/productivity/chief-of-staff/scripts/action.sh" calendar reschedule EVENT_ID_FROM_FIND --query 'exact meeting title' --date YYYY-MM-DD --expected-weekday WEEKDAY --date-source-message MESSAGE_ID --confirm
bash "$HERMES_HOME/skills/productivity/chief-of-staff/scripts/action.sh" drive search 'project or artifact terms'
bash "$HERMES_HOME/skills/productivity/chief-of-staff/scripts/action.sh" docs get DOCUMENT_ID
bash "$HERMES_HOME/skills/productivity/chief-of-staff/scripts/action.sh" sheets inspect SPREADSHEET_ID --row-match 'exact row identifier' --column 'exact column header'
bash "$HERMES_HOME/skills/productivity/chief-of-staff/scripts/action.sh" sheets set-cell SPREADSHEET_ID --row-match 'exact row identifier' --column 'exact column header' --expected-current 'value from inspection' --value 'requested value' --confirm
bash "$HERMES_HOME/skills/productivity/chief-of-staff/scripts/action.sh" slides get PRESENTATION_ID
bash "$HERMES_HOME/skills/productivity/chief-of-staff/scripts/action.sh" slides replace-text PRESENTATION_ID --find 'OLD' --replace 'NEW' --confirm
```

- Run exactly one documented helper invocation per `terminal` call, beginning with `bash "$HERMES_HOME/skills/productivity/chief-of-staff/scripts/action.sh"`. Do not assign a shell variable, join commands with `;` or `&&`, use a pipe, `echo`, or any command substitution, or submit to `process`. These helpers finish within the terminal timeout; `process` is valid only if a terminal result explicitly returns a running process ID.
- Gmail reply drafts are threaded and never sent. Before creating anything, search or read enough Gmail evidence to obtain one distinct real message ID for every intended recipient. Gmail evidence reads exclude draft messages; never use a draft or a self-authored message as reply-recipient evidence, and choose a received message from the intended recipient instead. When a task names multiple recipients but the displayed message supplies only one of them, run one `gmail search` for the shared task, meeting, or subject phrase and use its structured message results directly. If that bounded subject search still omits a named recipient, run at most one simple name-only search for each missing person. Never pipe a Gmail result into another command or repeatedly vary speculative query syntax. The primary message supplies the thread, To recipient, and subject; each distinct `--include-sender-from-message` supplies an evidence-backed Cc recipient. When several messages discuss one action, use the original issue/request message as the primary reply and later coordination messages only as additional-recipient evidence, unless the user explicitly identifies another reply target. Never type or infer an address, never reuse the primary ID as an additional-recipient ID, and create exactly one final draft after all recipients are resolved. The helper rejects draft/self-authored sources before writing. Use real paragraph breaks; the helper also converts shell-escaped `\n` and common literal Unicode punctuation escapes into their rendered characters. Unless the user requests a different closing, end each draft with exactly `Thanks` with no comma or other punctuation. A reply body must contain a substantive message before the closing. For a Calendar action-confirmation draft, prepare the body before the first draft call by copying the full verified event title, date, start time, end time, and timezone abbreviation returned by `calendar reschedule`; express the new start and end together as an interval, with natural compact ranges such as `1:00–2:00 PM PDT` accepted. State only scheduling facts supported by the verified Calendar result or received Gmail evidence; omit speculative causes, availability claims, or calendar-day references. Then pass that event's returned `id` once as `--verify-calendar-event EVENT_ID`. Do not pass those values as separate fact flags. The helper rereads the live event and validates all five facts before creating anything. For non-Calendar facts that must be present, use one quoted `--require-body-fact 'VALUE'` per evidence-derived value. A result with `status: rejected` and `created: false` is validation feedback, not a completed draft: correct only the body from the same verified result and retry once. Preserve the original reply message, every `--include-sender-from-message`, and `--verify-calendar-event`; never weaken recipient scope or verification to bypass validation. Move on only after `status: drafted` or `status: already_drafted`, with `content_validated: true` and `verified: true`. An identical tracked draft is returned as `already_drafted` rather than created again. The helper then reads the saved draft back and tracks it automatically when a reference workspace is active.
- For date-based Calendar work, finish the focused evidence reads before any mutation. First obtain the literal target date and any named weekday from the request or Gmail evidence. If an authorized Calendar request omits the target date/time, first run one bounded `gmail search` using a short distinctive meeting phrase such as `release review`, not every word of the Calendar title. If that result contains only a postponement and no target date, broaden once to shorter distinctive terms; never choose a date yourself. Locate the event with `calendar find --query 'exact title or terms'` and no date calculation: the helper uses the live Calendar timezone and a bounded 14-day window by default. Use only the returned `id`; a Calendar URL is a link, not an event ID, so never decode or copy its `eid` value. Finally call `calendar reschedule` exactly once with the literal evidence-backed target `--date`, passing `--expected-weekday` whenever evidence names a weekday. If Gmail supplied the date, pass that received scheduling message as `--date-source-message MESSAGE_ID`; the helper rereads it and refuses a different or invented date before moving anything. Use `--user-directed-date --user-request-text 'EXACT CURRENT USER REQUEST'` instead only when that quoted current request itself states the target date or weekday; context from a prior brief is not the current request. A missing date authority is returned as structured validation feedback before any write, so correct that one call rather than chaining a fallback. Never construct dates, IDs, or UTC offsets with shell `date`, Python, command substitution, or platform-specific flags. `calendar reschedule` gets the calendar timezone, validates weekday/date agreement and date authority, preserves the event duration and details, finds the earliest conflict-free slot, moves the existing event, and verifies it. Its default working window is 8:00 AM through 5:00 PM; pass narrower `--work-start` or `--work-end` values when the user requests a specific part of the day. Pass the live event ID and exact evidence-backed title in `--query`; the query is only a bounded, unique recovery path if that returned ID becomes stale. Never create a duplicate.
- Before changing any spreadsheet value, use `sheets inspect` with the row identifier and column header from evidence; copy the full row identifier when it is visible. Review its resolved target, match mode, current value, value kind, validation, formula, and protection metadata. An unambiguous partial row match is accepted, but multiple matches are refused. Then pass the returned current value to `sheets set-cell`. The guarded write resolves the cell again from the live schema, refuses ambiguity, formulas, protection, invalid values, or concurrent changes, and verifies only that cell. Never assume a tab name, row number, column letter, or list of allowed values.
- Read a deck before editing unless the exact file, placeholder, and replacement are already visible in current conversation evidence.
- The helper verifies every write. Report only fields confirmed by its structured result. For a reschedule, copy `original_display` and `new_display` rather than reconstructing dates, weekdays, or timezone labels; use the returned `timezone_abbreviation` exactly and never infer a daylight/standard abbreviation. Return the verified URL when useful; never expose raw event, message, file, spreadsheet, presentation, document, draft, thread IDs, or Sheet coordinates. Gmail results with `sent: false` are drafts only. When any successful result contains non-empty `confirmation_markdown`, make the final response exactly that field and nothing else; it is the verified, user-facing completion for Calendar/Gmail, Sheets, or Slides. Otherwise, say `draft saved (not sent)` or equivalent and include the returned links. Never say `draft sent`, offer to send mail, mention internal notification settings, add a closing question/offer, or fabricate, echo, or simulate an out-of-band user-message marker.

### Completion boundary

After a successful write returns non-empty `confirmation_markdown`, copy it verbatim as the final response and stop generating immediately. Do not add a separator. Do not recap earlier items, announce that a list is complete, or ask what to do next. This rule applies even when the write completes the last displayed priority. Never replace `saved (not sent)` with any phrase containing `sent`.

## Safety

Draft rather than send. A direct request to complete a displayed action or a direct Workspace mutation is approval for that scoped write; do not ask twice. Never delete mail, events, or Drive artifacts through this skill. Every recommendation must trace to evidence, and every claimed write must be verified.

## Reference Workspace Seed

The repository demo seeder creates portable reference data in the connected account and records generated IDs locally for exact cleanup.
