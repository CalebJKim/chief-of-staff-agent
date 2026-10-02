---
title: Local Agent Platform
created: 2026-09-09
updated: 2026-09-22
type: concept
tags: [strategy, operations, research]
sources: [raw/briefings/executive-operating-principles.md]
status: reference
confidence: high
---

# Local Agent Platform

A local agent platform combines a model running locally with tools that can act, controls on those actions, and saved context from earlier work.

## Checking the whole workflow
The model interprets a request, tools carry out actions, and policy controls determine what is allowed. A capable model cannot guarantee that a tool succeeds. Running locally also does not establish that permissions and sensitive information are handled appropriately.

Review where data is read and stored, how an action is authorized, how a failure is reported, and how the user can inspect the result.

## Saved context and current evidence
Saved context can help work continue across sessions. It also needs a way to distinguish historical information from current evidence.

Use these questions when reviewing [[hermes-partner-program|the Hermes partner program]] and [[openshell|OpenShell]]. Check what changed, who owns the outcome, and which decision is needed next. Evaluate the complete workflow before drawing conclusions from a single component.
