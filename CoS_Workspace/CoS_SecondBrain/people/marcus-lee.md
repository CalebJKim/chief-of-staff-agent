---
title: Marcus Lee
created: 2026-09-09
updated: 2026-09-22
type: person
tags: [person, operations]
sources: [raw/meetings/leadership-staff-2026-09-08.md]
status: active
confidence: high
---

# Marcus Lee

Marcus leads agent security engineering, with responsibility for [[agent-security-prd|the Agent Security PRD]] and related work on [[openshell|OpenShell]].

## What Engineering needs
The product requirements document needs to explain what the system should do when it allows an action, denies one, or encounters a failed dependency. Requirements should say what gets logged and how exceptions are handled. Without those details, teams can implement the same policy differently.

A useful handoff identifies the threat, where trust ends, and the behavior a test should demonstrate. List unresolved decisions before asking Engineering to treat the document as approved requirements.

## OpenShell review
Integration test results and the decision about network access answer different questions. Passing tests can show that an integration works; they do not settle which network actions policy should permit.

Bring decisions and supporting evidence to [[weekly-leadership-staff|weekly leadership staff]]. Record executive commitments in the [[decision-log|decision log]].
