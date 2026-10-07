# Updating Slide Decks

Use the main skill's “How to run the scripts” subsection and [Command reference](command-reference.md).

## 1. Gather context

- Reuse relevant evidence. Read the target deck and gather only missing information needed for the edits. Do not run Start of Day.
- Use the supplied deck or identify it from the request and evidence. Do not assume the newest match is correct.
- Map slide numbers to `object_id` values from `slides get`. Retain source and destination IDs before deleting or reordering slides. Numbers change afterward.
- For formatting, use `slides inspect` scoped to the relevant slide and text. It reports explicit styles, not all inherited master/layout styles.

## 2. Prepare the edits

Show proposed changes, including deletions, and wait for approval unless the user already supplied or approved them. Preserve factual qualifications, metric names, units, and approval scope.

## 3. Apply the edits

- Use `slides replace-text` with `--slide-id`. Match text within one text box, uniquely identifying the passage unless all matches on that slide should change.
- Keep wording concise within the existing layout. Use `slides format` for requested formatting, specifying only properties to change. For unsupported changes, explain the limitation or use an available presentation-editing skill.
- When merging slides, integrate substantive source content into existing destination paragraphs. Do not merely append a section or say content moved elsewhere.
- Read back the destination before deleting the source with `slides delete`. If transfer fails, retain the source.
- Editorial instructions are not content to transfer. If no distinct substantive content exists, report that limitation without inventing or claiming a transfer.

## 4. Verify and report

After text or structural edits, read back once to confirm changes and slide order. `slides format` already verifies formatting. Do not repeat that read. Use `slides preview` for affected slides, saving inside the workspace. Inspect the PNGs with an image-viewing tool for clipping, spacing, and layout. If unavailable, report that visual verification was not performed. Text read-back alone cannot verify appearance.

Link the deck and summarize completed changes and anything incomplete.
