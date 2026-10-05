# Updating Google Docs

Use the main skill's **How to run the scripts** subsection and [Command reference](command-reference.md).

## 1. Gather context

- Reuse relevant evidence. Read the target document and gather only missing information needed for the edits. Do not run Start of Day.
- Use the supplied file or identify it from the request and evidence. Do not assume the newest match is correct.
- `docs get` returns paragraph text. For formatting, use `docs inspect` scoped with `--find` and, when needed, `--tab-id`. It covers body paragraphs, including tabs and tables. Do not treat omitted content as absent.

## 2. Prepare the edits

Show proposed changes and wait for approval unless the user already supplied or approved them. Preserve factual qualifications, units, and approval scope.

## 3. Apply and verify

- Use `docs replace-text` for existing text or `docs append` for additions. Replacement affects every match. Use a unique passage unless all matches should change.
- Use `docs format` for requested text or paragraph formatting. Include only properties to change. Preserve surrounding content and style. For unsupported changes, explain the limitation or use an available document-editing skill.
- After text edits, read back once. Zero replacements is not success. `docs format` already reads back and verifies formatting. Do not repeat that read.
- For changes affecting appearance, use `docs preview` for affected pages, saving inside the workspace. Inspect the PNGs with an image-viewing tool for clipping, spacing, and layout. If unavailable, report that visual verification was not performed. Text read-back alone cannot verify appearance.

Link the document and summarize completed changes and anything incomplete.
