---
title: Data Governance Program
created: 2026-09-09
updated: 2026-09-22
type: project
tags: [project, strategy, operations]
sources: [raw/meetings/portfolio-planning-2026-09-09.md]
status: active
confidence: medium
---

# Data Governance Program

This project defines who can use information, how long it is kept, and what happens when it changes. It follows source documents, generated answers, logs, and exported copies rather than treating them as one record.

## Meridian's proposed policy collection
The [[meridian-strategic-account|Meridian evaluation]] gives a concrete case. A document owner would identify the approved policy or FAQ, its version, and its audience. Access must then reflect the individual user, not just the person who created the collection.

If a procedure is replaced, the team needs to identify the newer source and review references to the old one. If a user changes roles, access to originals and retained copies may need to change.

## Questions by record type
| Data category | Design question | Evidence to request |
|---|---|---|
| Source documents | Does the consumer retain the source's access restrictions? | Access mapping and denied-access test |
| Generated summaries | Can sensitive details be reproduced outside the original audience? | Destination permissions and correction process |
| Activity logs | What is needed for investigation without retaining unnecessary content? | Field definitions and retention rationale |
| Exported or copied records | How are deletion and policy changes propagated? | Copy inventory and lifecycle ownership |

No retention period or customer approval is established here.

## Responsibilities still to resolve
Document owners, access administrators, application operators, and support all have a part. Decide who handles an outdated answer, revokes access, and verifies that a correction reached relevant copies.

An exception should explain its business purpose, added risk, compensating controls, approver, and revisit condition.

## Proposed walkthrough
Follow a revoked permission, a corrected policy, and an unavailable document source. Check originals, generated material, retained copies, and logs.

[[arcadia-cloud]] is a possible integration discussion, not a selected Meridian supplier. Coordinate control questions with [[agent-security-prd]] and [[operational-resilience]]. Record agreed responsibilities through [[weekly-leadership-staff]] and [[decision-log]].
