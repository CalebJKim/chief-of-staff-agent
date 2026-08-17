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

The RTX Spark emails, events, deck, tracker, and campaign documents were real records in one test Google account. They are not included here and are not required by the agent. The skill mentions generic examples such as an exec review because those are valid workflow triggers, not hidden answers.

The only structural specialization is the `Campaign Lanes` tracker schema (A:J). Tracker lane updates use that schema and named lanes. Other tracker layouts require an adapter/configuration layer.

## What was not cheated

The tested workflow made live Google API calls. The model discovered current messages/events/files, read selected full threads/artifacts, proposed changes, waited for approval, wrote to Google, and read back results. The scripts do deterministic retrieval, compression, conflict detection, and validation; they do not contain the expected RTX Spark answer.

The demo account was deliberately seeded with coherent emails, calendar conflicts, and stale tracker/deck state. That is staged test data, equivalent to a demo dataset. It improves reproducibility but does not bypass reasoning or Google writes.

## Known limitations

- Quality depends on the model following tools and concise instructions.
- Artifact linking is token-overlap based and can be fuzzy; the skill requires confirmation before relying on ambiguous matches.
- Calendar retrieval uses selected calendars and a bounded horizon.
- Gmail uses a bounded active-inbox query; archived work is not included unless queried explicitly.
- The setup helper creates local OAuth credentials; credentials must never enter git.
- Sending email is intentionally unsupported by the focused actions helper; drafts only.
