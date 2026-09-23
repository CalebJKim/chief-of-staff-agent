---
title: Operational Resilience
created: 2026-09-09
updated: 2026-09-22
type: project
tags: [project, strategy, operations]
sources: [raw/meetings/portfolio-planning-2026-09-09.md]
status: at-risk
confidence: medium
---

# Operational Resilience

This project prepares teams to detect service problems, protect users, restore operation, and communicate clearly. A written recovery procedure is useful only if someone other than its author can follow it.

## Proposed exercise: unavailable document source
Use a document-reference workflow and examine three different conditions:
- The system cannot connect to the source.
- The user no longer has permission.
- The document has been removed.

The user may see a similar failure, but the investigation and response are different.

## Walk through the response
Identify the first visible signal, affected function, receiving team, diagnostic information, and message to the user. If old material is retained, decide whether it may be shown and how its age is explained. A saved copy is not automatically safe to present as current.

Then identify the last safe state, conditions for a workaround, recovery steps, and checks before announcing normal operation. Include partial failure as well as a complete outage.

## What the exercise should produce
| Review area | Useful artifact |
|---|---|
| Detection | Signal that distinguishes user impact from a harmless warning |
| Recovery | Reproducible steps, prerequisites, and rollback conditions |
| Coordination | Clear technical and customer-facing responsibilities |
| Learning | Findings tied to an owner and a verification step |

The exercise has not been run merely because this plan exists. No recovery-time target is promised.

Coordinate with [[enterprise-support-model]], [[data-governance-program]], and the possible integration discussion in [[arcadia-cloud]]. Confirm ownership through [[weekly-leadership-staff]] and record accepted commitments in [[decision-log]].
