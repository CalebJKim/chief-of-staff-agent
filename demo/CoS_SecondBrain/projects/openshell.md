---
title: OpenShell
created: 2026-09-09
updated: 2026-09-22
type: project
tags: [project, openshell, agent-security, engineering]
sources: [raw/updates/openshell-status.md]
status: at-risk
confidence: medium
---

# OpenShell

OpenShell is the secure runtime layer for partner-facing agent work. The existing note records passed Windows pilot integration tests. That evidence covers the tested path; it does not settle every security or operating question.

## The open decision
Should partner demos block outside network connections unless they are explicitly allowed?

The recorded recommendation is default-deny: block other destinations and allow only approved, logged exceptions. This supports [[agent-security-prd]], but may add setup work for the [[hermes-partner-program|partner program]].

| Approach | Operational appeal | Exposure to examine |
|---|---|---|
| Default-deny with narrow allowlists | Predictable approved destinations | Setup and maintenance of legitimate exceptions |
| Broad network access | Low initial configuration effort | Larger access surface and weaker destination control |
| Environment-specific policies | Different controls for development and demonstration | Configuration drift and confusion about the active policy |

## Proposed operator walkthrough
Check that the operator can identify the policy, understand a denial, and request a limited exception. Exercise an approved destination, an unexpected destination, a revoked exception, and an unavailable policy service. Include a restart or interruption.

Record the environment and limits of the evidence. A smoke check is a basic test of one path, not proof of every failure case.

Before using OpenShell in [[ifa-demo-slate|the IFA demo list]], resolve the policy choice and validate the operator workflow. The table and walkthrough are preparation, not new approval or completed test results.
