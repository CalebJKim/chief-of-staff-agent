---
title: Enterprise Support Model
created: 2026-09-09
updated: 2026-09-22
type: project
tags: [project, strategy, operations]
sources: [raw/meetings/portfolio-planning-2026-09-09.md]
status: active
confidence: medium
---

# Enterprise Support Model

This project defines how customers get help after a deployment: where they report a problem, how it reaches the right team, and who keeps the customer informed.

Northstar's implementation-to-support gap is the concrete case being used to discuss the model.

## Proposed handoff checklist
| Section | Contents to assemble | Review needed |
|---|---|---|
| Deployment profile | Intended workflow, configuration reference, integration boundaries | Implementation confirms the description |
| Operating limits | Known limitations, safe workarounds, restricted actions | Relevant technical owner reviews scope |
| Case routing | Intake route, severity context, escalation path | Support confirms the receiving process |
| Change control | Difference between an incident, access request, and design change | Both teams resolve ambiguous cases |
| Customer handoff | Support route and remaining limitations | Customer confirmation remains pending |

Missing information should lead to a request for context, not an abandoned case.

## How a case should move
Start with the customer's impact, configuration, and last known working state. Route the investigation internally by the affected area: product, infrastructure, integration, policy, or customer configuration. The customer should not have to solve the ownership question first.

Keep one customer-facing coordinator when several specialists contribute. A transfer to Engineering should include observations, attempted workarounds, and the specific question Engineering needs to answer.

## What to check in the first walkthrough
Use an access problem and an unavailable-source problem. Confirm who receives each case, what information they need, and who can approve a change. These are proposed exercises, not completed tests.

Response, temporary mitigation, and permanent correction are different outcomes. Closure should record the resolution, remaining limitations, and customer confirmation where needed.

Connect repeat problems to [[operational-resilience]] and [[northstar-customer-recovery]]. Confirm ownership through [[weekly-leadership-staff]] and record agreements in [[decision-log]]. No coverage level or response-time commitment is established here.
