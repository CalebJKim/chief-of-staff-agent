# Portability assessment

## What is genuinely general

- OAuth-backed reads from Gmail, selected calendars, and recently modified Drive files.
- Bounded decision packet generation for smaller local models.
- Calendar conflict detection and focus-block calculation.
- Gmail thread reads and draft creation.
- Docs/Sheets/Slides reads and guarded writes.
- Natural-language chief-of-staff routing from SOUL.md.
- Evidence-first prioritization, stale-timing handling, and safe mutation rules.

## What was demo-specific

The repository can seed a fictional RTX AI Assistant executive-review story into a dedicated test account. Its names, dates, messages, tasks, and artifacts live in the seeder and demo documentation, not in runtime routing.

Tracker writes inspect the live workbook to discover the tab, header row, target row, target column, current value, validation, formula, and protection state. Runtime code does not depend on the seeded `Pre-Exec Review` tab, fixed coordinates, or its status list.

## What was not cheated

The tested workflow made live Google API calls. The model discovered current messages/events/files, read selected full threads/artifacts, proposed changes, waited for approval, wrote to Google, and read back results. The scripts do deterministic retrieval, compression, conflict detection, and validation; they do not contain the expected RTX Spark answer.

The demo account is deliberately seeded with coherent email, calendar, Doc, tracker, and deck state. That staged dataset improves reproducibility but does not bypass focused reads, live validation, or Google writes.

## Known limitations

- Quality depends on the model following tools and concise instructions.
- Artifact linking is token-overlap based and can be fuzzy; the skill requires confirmation before relying on ambiguous matches.
- Calendar retrieval uses selected calendars and a bounded horizon.
- Gmail uses a bounded active-inbox query; archived work is not included unless queried explicitly.
- The setup helper creates local OAuth credentials; credentials must never enter git.
- Sending email is intentionally unsupported by the focused actions helper; drafts only.
