# Meeting Preparation

Prepare a read-only, meeting-specific briefing. Do not run Start of Day or read tracker contents. Locate a spreadsheet tracker by filename only, as described below. List applying needed file edits as preparation tasks. Do not assume suggested edits have been completed. Apply edits or save drafts only when the user explicitly requests or approves those actions. A request for meeting preparation does not accept an earlier offer to edit files.

## 1. Gather evidence

Use [Command reference](command-reference.md) for syntax when needed; do not reread loaded guidance.

1. Reuse conversation evidence, including the daily brief (if available). Identify facts missing from the three briefing sections below. Do not open sources merely because they are linked or reread them for background or freshness.
2. Gather missing email facts with one `gmail evidence --requests-file -` call: supply known native `thread_ids` without queries and batch short, meeting-specific queries for the rest. Skip preliminary header searches and duplicate reads. Follow up on errors or truncation only when needed facts remain unresolved.
3. Reuse a spreadsheet link whose filename clearly matches the initiative. Otherwise, use one `drive search --raw-query` lookup with `name contains 'INITIATIVE_NAME'`, using a known filename prefix and no MIME filter. Select the spreadsheet from the returned names and file types. If its inputs and the email requests are already known, combine them with `run-actions.ps1 -Batch`. Judge relevance by filename only; do not read tracker contents or investigate further. Omit “Status of Workstreams:” if no filename clearly matches.
4. Once the sections are supported, write the brief; if only the tracker link is missing, perform only its lookup. Gather other file content only when specific facts are still needed; batch independent follow-ups and leave unsupported details unstated. Skip retrieval narration and intermediate summaries of findings.

**Evidence rules:**

- Reuse evidence links. Search Drive only for a missing, needed file link.
- Distinguish requested work from confirmed completion and planned from confirmed attendance. Flag missing context without guessing.
- If the meeting time has passed, flag it and still brief. Elapsed time does not prove preparation or decisions are complete.
- Do not inspect files merely for background or to check whether previously suggested edits were applied. Treat requested edits as incomplete unless available evidence confirms completion.

## 2. Write the briefing

Aim for 200–300 words. Fill this template in your reply with evidence-backed content. Preserve headings, labels, list styles, and order. Add list entries as needed. Omit unsupported fields, meeting time, and an unnecessary “Next steps”. Render Markdown without code fences. Add no sections, tables, timelines, or outside commentary.

Assume preparation starts now. Suggest work times or meeting changes only when requested.

**Preparation:** Include only outstanding tasks directly related to this meeting. Exclude unrelated work even if due earlier, meeting-conduct advice, and decisions reserved for the meeting.

**Goals:** Exclude completed approvals, status updates, and meeting-conduct advice. No introduction, callout, or checkboxes. Follow source order unless organizer evidence establishes priority.

```markdown
### Context

**Purpose:** [State only why the meeting is happening. Do not include scheduling details or preparation tasks. Put preparation tasks only under “What needs to get done before the meeting”, and desired outcomes under “Goals for the meeting”.]

**People:** [Other participants and roles, excluding the user.]

**Status of Workstreams:** [Spreadsheet filename](SPREADSHEET_URL)

> **Your Role:** [Source-linked role, including presenting when supported.]

### What needs to get done before the meeting

1. **[Concrete preparation action](SOURCE_URL)** — [Short explanation.]

### Goals for the meeting

- **[Outcome still to achieve](SOURCE_URL)** — [What must be decided or accomplished.]

**Next steps:** [If useful, offer help with a specific outstanding action identified in this briefing. Do not offer to prepare for the meeting again or repeat the daily brief’s offer. Omit this line if there is no relevant follow-up.]
```

## 3. Check and respond

- Check headings, labels, list styles, and order against the template. Remove extra content.
- State each fact once. Distinguish preparing recommendations beforehand from making decisions during the meeting.
- Source-link facts, preparation, and goals. Summarize detailed evidence instead of reproducing metrics, footnotes, or slide contents. Never invent slide contents or slide-specific URLs.
- Exclude unrelated work. Refer briefly to established context instead of repeating the daily brief.
