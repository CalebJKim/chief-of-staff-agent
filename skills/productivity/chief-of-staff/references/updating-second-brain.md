# Updating Second Brain

Update Second Brain with meaningful Google Workspace changes. Do not modify Google Workspace. Follow the user's scope and requested output format.

When scheduling this task, instruct each run to load this reference and follow its current workflow. Do not replace it with standalone ingestion instructions.

## 1. Gather evidence

Use the vault configured in the active profile's `second-brain.json` (`vault_path`). If missing or inaccessible, stop and report the failed path and operation. Do not search other folders, recreate the vault, change permissions, or attempt workarounds.

Use the **How to run the scripts** subsection of the main skill to initialize the active profile's Python and script paths. Run the evidence helper once in Second Brain update mode:

```bash
"$PYTHON" "$DAILY_BRIEF" --mode second-brain-update
```

Wait for completion. Use its JSON packet to identify relevant notes. If output is truncated, read the saved `packet_path` using offsets. Do not generate a daily brief, rerun ingestion, read the full snapshot, or scan the entire vault. Report command failures without retries or repairs.

Read the Second Brain’s index note if present. Otherwise, use the Second Brain search helper to find relevant notes. Read only notes relevant to the packet. Treat snapshot snippets as leads. Retrieve additional Google Workspace source content only when needed to verify a change, using [Command reference](command-reference.md).

Read each source or note once and reuse its contents. Reread only if the earlier read failed or was truncated, the content changed, or you are verifying a saved edit. Before context compaction, preserve relevant facts, source links, files already read, and the next unfinished step. Resume from that step without repeating completed reads.

Update only what the collected evidence supports. Leave other notes unchanged.

## 2. Update relevant notes

Follow the vault’s note categories and formatting conventions in `SCHEMA.md`, when present.

Compare evidence with existing content. Update changed facts and add missing decisions, progress, blockers, plans, or commitments. Preserve unrelated content, structure, metadata, and source links. Flag unresolved conflicts rather than guessing.

Update the note's substantive content, not just its history. Leave unchanged notes untouched. Do not duplicate information already recorded.

Create a note only when relevant information has no suitable existing note. Link it from the appropriate index, if present.

Use existing file-editing tools. Read and write Markdown as UTF-8. Stop and report encoding errors rather than replacing or discarding characters.

## 3. Record and verify changes

Reuse each changed note's update/change-history section, creating one if absent. Unless the user specifies otherwise, use:

| Date | Updates |
|---|---|
| Date the edit was made | What changed in this note |

Preserve previous entries and append actual changes without duplicate rows on subsequent runs.

Read back edited content once to confirm the changes and formatting. Report only verified, saved edits:

| File Name | Updates |
|---|---|
| Note title without extension | One or two short sentences describing the changes |

If nothing changed, say so. If execution fails partway through, distinguish saved changes from unfinished work.
