# Second Brain Schema

## Domain
Executive operating system for RTX Spark, Hermes, agent security, partner programs, launch execution, decisions, people, and meeting preparation.

## Architecture
- `raw/` contains immutable source notes and meeting records.
- `projects/`, `people/`, `organizations/`, `concepts/`, and `meetings/` are maintained synthesis.
- `index.md` is the content catalog; read it first.
- `log.md` is an append-only record of changes.

## Conventions
- File names use lowercase kebab-case.
- Every maintained page has YAML frontmatter: `title`, `created`, `updated`, `type`, `tags`, `sources`, `status`, `confidence`.
- Use at least two `[[wikilinks]]` per maintained page.
- Update `index.md` and append `log.md` whenever knowledge changes.
- Record decisions with owner, date, rationale, and affected projects.
- Preserve disagreements; do not silently replace contradictory claims.
- Pages over 200 lines should be split.

## Types
`project`, `person`, `organization`, `concept`, `meeting`, `query`, `summary`.

## Status
`active`, `blocked`, `at-risk`, `planned`, `complete`, `reference`.

## Tag Taxonomy
- Work: `project`, `person`, `organization`, `meeting`, `decision`, `priority`
- Product: `rtx-spark`, `hermes`, `openshell`, `agent-security`, `inference`
- Functions: `engineering`, `marketing`, `legal`, `partners`, `retail`, `communications`
- Meta: `strategy`, `launch`, `risk`, `research`, `operations`

## Page Thresholds
Create a page when a subject is central to active work, appears in two or more sources, or carries an executive decision. Add passing mentions to an existing project page.

## Update Policy
Prefer newer dated evidence. When evidence conflicts, retain both claims, identify dates and owners, lower confidence, and flag the question in `Open questions`.
