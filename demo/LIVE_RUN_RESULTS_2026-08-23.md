# Hermes Chief of Staff live run record — August 23, 2026

## Method

- Profile: `chief-of-staff-demo`
- Model: `qwen3.6:35b-a3b` through Ollama
- Reasoning setting: `medium`
- Turn limit: 40
- Each run started with `demo/reset_workspace.py`, then used the same two prompts:
  1. `Hey chief of staff, what should we work on today?`
  2. `Take care of the first item.`
- Agent time is brief plus follow-up time. End-to-end time also includes reset/reseed. Audit time is excluded.
- Every run was audited from live Gmail and Calendar state and its Hermes session trace.

## Timings and automated audit

| Run | Reset | Brief | Action | Agent total | End to end | Pre-write rejections | State/tool gate |
|---:|---:|---:|---:|---:|---:|---:|:---|
| 1 | 38.8 s | 41.1 s | 77.1 s | 118.3 s | 157.0 s | 1 | Fail — one malformed Gmail search call |
| 2 | 37.6 s | 38.9 s | 74.2 s | 113.1 s | 150.6 s | 0 | Pass |
| 3 | 37.0 s | 37.3 s | 71.2 s | 108.6 s | 145.6 s | 1 | Pass |
| 4 | 37.9 s | 37.0 s | 77.2 s | 114.1 s | 152.0 s | 0 | Pass |
| 5 | 37.9 s | 56.2 s | 97.6 s | 153.8 s | 191.7 s | 1 | Pass |
| 6 | 36.2 s | 34.4 s | 93.1 s | 127.5 s | 163.7 s | 0 | Fail — brief not present and one extra draft flag |
| 7 | 39.4 s | 40.5 s | 92.4 s | 132.8 s | 172.3 s | 2 | Pass |
| 8 | 36.5 s | 41.9 s | 51.9 s | 93.8 s | 130.3 s | 1 | Pass |
| 9 | 38.0 s | 38.0 s | 63.2 s | 101.2 s | 139.2 s | 0 | Pass |
| 10 | 42.1 s | 37.8 s | 91.6 s | 129.5 s | 171.6 s | 0 | Fail — attempted reply-subject override |

## Timing summary

| Metric | Mean | Median | Minimum | Maximum |
|:---|---:|---:|---:|---:|
| Reset/reseed | 38.1 s | 37.9 s | 36.2 s | 42.1 s |
| Morning brief | 40.3 s | 38.4 s | 34.4 s | 56.2 s |
| First-item action | 79.0 s | 77.2 s | 51.9 s | 97.6 s |
| Agent total | 119.3 s | 116.2 s | 93.8 s | 153.8 s |
| End to end | 157.4 s | 154.5 s | 130.3 s | 191.7 s |

## Reliability observations

- Live external state was correct in 10/10 runs: exactly one release-review event at the selected Tuesday 1:00–2:00 PM PDT slot and exactly one tracked, unsent Gmail draft.
- Draft content passed read-back validation in 10/10 runs: Priya was the primary recipient, Daniel was copied, all five live Calendar facts were present, real line breaks rendered, and the final closing was exactly `Thanks`.
- The automated state/tool gate passed 7/10 runs. Runs 1, 6, and 10 recovered to correct state but exposed one red helper error each.
- Five runs used the safe pre-write rejection path, for six total rejected bodies. No rejected body created a Gmail draft.
- No run called `skill_manage`, and no run created a duplicate Calendar event.
- The brief presentation contract was exact in 6/10 final responses. Run 3 omitted the workload summary, run 6 referred to a missing brief “above,” run 9 added a preamble, and run 10 rewrote the summary.
- Both required action links appeared in only 2/10 final responses even though the underlying helper returned valid URLs every time.

## Changes made after the measured batch

- Removed the contradictory brief instruction that could make the model treat the terminal preview as the answer.
- Added a generic verified `confirmation_markdown` result containing both Calendar and Draft links; the skill now returns it verbatim.
- Made an unnecessary draft `--confirm`, an attempted reply-recipient/subject override, and a trailing empty Gmail-search argument recoverable without a red command failure.
- Removed internal Calendar notification fields and raw draft/message/thread IDs from model-visible success output.
- Excluded draft messages from Gmail evidence reads and reject draft/self-authored reply sources before any Gmail write.
- Made Calendar rescheduling require a target-date authority. Gmail-derived dates are reread from the cited received message and must match; a user-directed date is accepted only through the separate explicit-user path.
- Calendar lookup now defaults to a bounded 14-day window in the live Calendar timezone, so the model does not need shell or Python date calculations.

The ten rows above describe the unchanged measured batch. Post-batch fixes are deliberately not mixed into those timings.

## Post-fix verification

- All 74 regression tests pass: 29 repository tests, 40 ingest/action tests, and 5 Chief-of-Staff skill tests.
- A final continuous live walkthrough completed the default top-three flow in one Hermes session: it moved the correct release-review event to Tuesday, August 25 at 1:00–2:00 PM PDT, saved one validated unsent draft to Priya with Daniel copied, changed the latency-evaluation status to `Ready for review` after inspecting the live Sheet schema and dropdown, and replaced the seeded Slides placeholder with the approved headline.
- The audited session contained 9 tool calls with zero tool failures, zero `skill_manage` calls, zero malformed nested action-wrapper calls, and zero Chrome, browser, computer, or open-URL calls. Workspace links remained inline in the responses.
- Direct live read-back verified real paragraph breaks in the nonempty draft, a final closing of exactly `Thanks` with no comma, the correct recipients and event, the requested Sheet value, and the approved Slides text with the placeholder removed.
- The final active-profile reset/reseed restored the baseline review to Monday, August 24 at 2:00–3:00 PM PDT, the evaluation status to `In progress`, and the Slides placeholder. It left 76 seeded messages, 12 seeded events, and zero tracked drafts.

## Friendly-storyline verification

- Replaced the technical-facing RTX Agent Runtime examples with an RTX AI Assistant launch story while preserving the same top-three design: coordinate a launch review and draft, update one tracker value, and replace one approved slide headline.
- Two read-only trial briefs exposed a semantic naming collision and a lower-priority item that could outrank the intended deck task. The seed data was clarified by giving the unrelated feedback summary a distinct name and later due date, and by linking the launch blocker directly to its Calendar event. Neither trial made Workspace changes.
- A fresh full walkthrough then returned the intended three priorities in order and completed all three actions in one session. The audited trace contained 10 tool calls, including the two expected skill reads and seven documented action-helper calls, with zero tool failures, zero `skill_manage` calls, zero nested action wrappers, and zero browser, Chrome, computer, or open-URL calls.
- Direct read-back verified exactly one nonempty draft to Priya with Daniel copied, real paragraph breaks, a final closing of exactly `Thanks` with no comma, the existing launch review moved to Tuesday, August 25 at 1:00–2:00 PM PDT, the Customer Demo Readiness Check set to the live dropdown value `Ready for review`, and the approved Partner Preview headline present with the placeholder removed.
- The runtime skills and action implementation contain none of the friendly storyline's scenario names. The operation set, approval boundaries, working-hours constraint, draft-only policy, schema-aware Sheet validation, and verification behavior remain unchanged.
