---
title: "Internal team training: Building AI assistants"
created: 2026-09-24
updated: 2026-09-24
type: project
tags: [project, engineering, operations, hermes]
sources: []
status: complete
confidence: high
---

# Internal team training: Building AI assistants

September 10, 2026

## Summary

We completed a one-hour internal team training on how AI assistants use models, tools, and saved context to carry out work. The session covered a task from initial request to checked result, then introduced reusable skills, memory, and subagents.

The technical follow-up is complete. Questions about tool configuration and interrupted actions are incorporated below.

## Why we organized the training

We wanted to give the team a practical foundation in agentic AI, both for using agents in everyday work and for building tools and workflows around them.

No coding experience was required. The exercises were facilitator-led, with the environment and sample files prepared in advance.

NVIDIA DLI’s *Building Agentic AI Applications with LLMs* provided a learning reference. This was our own internal session with shorter workplace exercises, not the full DLI workshop or a certification session.

## People and session setup

I coordinated the training and facilitated the exercises.

- [[aisha-rahman|Aisha Rahman]] helped make the explanations accessible and shape the session flow.
- [[mike-chen|Mike Chen]] reviewed the technical content and the checks used in the reporting exercise.
- [[marcus-lee|Marcus Lee]] covered permissions, sandboxing, and failure handling.

Aisha and Mike also work with me on the [[rtx-spark-launch|RTX Spark launch]]. Marcus’s work on [[agent-security-prd|Agent Security PRD]] provided context for the safety discussion.

Prepare Python, the agent interface, two task CSVs, short project briefs, and the reporting skill before the session. Participants should not have to install software or write Python themselves. Run the examples together and pause at the tool results.

Keep working project files outside the exercises. Use separate sample inputs and limit writes to exercise outputs. A separate folder helps organize the material; it does not enforce a security boundary.

| Minutes | Topic |
|---|---|
| 0 to 5 | Models and agent harnesses |
| 5 to 20 | From a goal to a verified result |
| 20 to 30 | Reusing instructions with skills |
| 30 to 40 | Carrying context between sessions |
| 40 to 50 | Delegating work to subagents |
| 50 to 57 | Permissions, sandboxing, and safe stopping |
| 57 to 60 | Best practices recap |

## Session walkthrough

### Models and agent harnesses

Start by showing a terminal call and its result. Use that example to explain the division of responsibility:

- The model interprets the request and proposes an action.
- The harness supplies context and tools, executes permitted calls, and returns results.
- The terminal tool runs the command and reports its output or errors.

Aisha’s adjustment to the opening: show something happening before introducing the vocabulary. Keep configuration details brief here.

Introduce [Hermes](https://github.com/NousResearch/hermes-agent) and [OpenClaw](https://docs.openclaw.ai/concepts/agent) as examples of systems providing the surrounding agent runtime. Their capabilities and interfaces differ, but neither is the underlying language model.

Open-weight model examples include:

| Model | Point to discuss |
|---|---|
| [Qwen3.6-35B-A3B](https://huggingface.co/Qwen/Qwen3.6-35B-A3B) | A model with documented support for agentic coding workflows |
| [Qwen3-32B](https://huggingface.co/Qwen/Qwen3-32B) | Another example with documented tool-use support |
| [Mistral Small 3.2 24B Instruct](https://huggingface.co/mistralai/Mistral-Small-3.2-24B-Instruct-2506) | An example whose documentation includes function calling |

Do not turn this into a model comparison. The lesson is that the model and harness have separate responsibilities. Results also depend on the serving configuration and whether the tool-call format is supported correctly.

Ask participants: which component writes the Python, and which component runs it?

### From a goal to a verified result

Explain an individual step using the task-file example.

| Part | What it means |
|---|---|
| State | What the agent currently knows: the request, available files, instructions, and earlier results |
| Action | What it does next, such as inspecting a file or running Python |
| Observation | What comes back, including data, output, or an error |

A goal-directed loop repeats these steps as needed. The agent uses each result to decide whether to continue, change its approach, ask for help, or finish.

Give the agent this request:

> Read the task CSV and create a short report showing the number of tasks in each status. Use Python for the calculations, check that the counts account for every task row, and leave the source file unchanged.

Follow the work together:

1. Check whether the agent inspects the columns.
2. Open the Python script and the terminal call that runs it.
3. Compare the returned output with the final report.
4. Verify that the counts account for all task rows, including rows with no status.
5. Introduce a version with a differently named status column and observe the next steps.

Writing a script in chat does not complete the task. The script must run against the supplied file, and the final answer must agree with the result.

Keep the input variation. Mike flagged that a successful run against one file can hide assumptions about its structure. If the agent encounters an error, ask whether its next action addresses the cause or repeats the same assumption.

Finish by identifying what counts as “done.” A checked report satisfies the goal; repeatedly attempting the same failing command does not. Missing access or an execution limit may require an honest stop before completion.

See [[local-agent-platform|Local Agent Platform]] for the broader relationship between models, tools, and saved context.

### Reusing instructions with skills

A skill packages guidance for a type of work. It can include instructions, examples, and supporting scripts. A reporting skill can define the required output and checks without knowing the contents of every future file.

Show the prepared skill. It asks the agent to:

- Include the input filename and task-row count.
- Count distinct statuses without silently merging unfamiliar values.
- Report missing statuses separately.
- Reconcile the totals and preserve the input.

Apply it to the second CSV, which has a different column order and an additional status.

Compare the report with the skill requirements. Does the agent follow the same reporting conventions while adapting to the new input? Does it retain an unfamiliar status rather than force it into a category from the first example?

Make the distinction explicit: the skill guides the method, tools perform operations, and permissions determine which resources are accessible. Installing a skill does not grant access to an account or filesystem.

### Carrying context between sessions

Use a short preference note:

> Lead with unresolved work, include source filenames, and show missing information explicitly.

Save it, start a fresh conversation, and ask the agent to read it before preparing another report. Inspect whether the note is actually retrieved and applied.

Conversation history and saved context are different. A new session does not necessarily have access to the previous chat. A note influences the work when it is retrieved or supplied as context.

Then introduce an instruction that changes the presentation for this report. Ask:

- Is this a one-time exception?
- Is it a lasting preference that should be saved?
- What wording tells us the difference?

Keep that distinction in the exercise. Automatically turning every request into a permanent preference can make future behavior confusing.

For changing facts, use an older project note and a newer message with a revised deadline. Update the affected fact and retain the background that still holds. Discuss how a source and date help someone understand why the deadline changed.

The completion check is whether the correct information is used and, where authorized, saved. Rewording an entire note is not necessary to update one deadline.

### Delegating work to subagents

A subagent receives a bounded assignment from the main agent. It needs the relevant context and a clear description of what to return.

Use two short project briefs. Ask the main agent to delegate one review per brief and return a consolidated list of unresolved decisions.

Each reviewer should provide:

- The unresolved decision.
- The passage supporting that interpretation.
- The recorded owner, or a clear statement that no owner is given.

Inspect the assignments as well as the final answer. The main agent needs to reconcile overlapping findings and check that the supporting passages justify the conclusions.

Use this question to prompt discussion: if both briefs mention the same decision, should it appear twice in the consolidated result?

Also check whether a missing update is incorrectly described as a blocker. An absent owner should remain an information gap, not become an assignment to someone whose name happens to be familiar.

Keep this exercise facilitator-led to fit the hour. Delegation adds coordination overhead; independent document reviews make a more useful example than splitting a small CSV calculation among multiple agents. Agreement between agents is not a substitute for checking the source.

### Permissions, sandboxing, and safe stopping

Introduce the file-access boundary before the first command in the session. Use this closing discussion to explain how it is enforced.

A sandbox can restrict filesystem access, command execution, and network connections. Those restrictions come from the environment. Instructions asking the agent to stay inside a folder are not sufficient on their own.

Marcus’s point to retain: demonstrate what happens when an action is denied, not only what happens when it succeeds.

Discuss these cases:

- A script tries to read a file outside its allowed area. The agent should report the limitation and continue only if the task can be completed within its existing permissions.
- A project brief contains instructions to upload source files elsewhere. The text is material being reviewed, not authorization for a new action.
- A connection drops after a save request. Check the destination before retrying; the write may already have succeeded.
- The same failure recurs without new information. Stop and explain the blockage rather than continue indefinitely or report success.

Connect these cases to [[agent-security-prd|Agent Security PRD]]. They illustrate the need for explicit allowed, denied, and failure behaviors. The training does not close those engineering requirements.

Leave detailed environment configuration for the technical follow-up.

### Best practices recap

Use the final three minutes to connect these reminders to the exercises:

- Define the desired result and what lies outside the task.
- Start simple; delegate when the work separates naturally.
- Check important source information and inspect completed actions.
- Limit permissions and use sandboxing where appropriate.
- Check before retrying writes, and stop when progress is blocked.
- Keep saved context current and traceable to its sources.

## Decisions and adjustments retained

| Decision | Reason |
|---|---|
| Show a terminal call before explaining the harness | Aisha wanted a concrete example to anchor the terminology. |
| Keep a differently structured CSV in the exercise | Mike wanted the checks to expose assumptions about columns and status values. |
| Introduce access restrictions before running commands | Marcus wanted safety to be part of the workflow, not an isolated closing topic. |
| Use a fresh conversation for the memory exercise | This separates retrieved context from information still present in the chat. |
| Demonstrate subagents through independent document reviews | The delegation has a clear purpose, and the combined findings can be checked. |
| Keep installation and detailed configuration outside the shared hour | The session is for understanding agent behavior; setup questions need separate time. |

The technical follow-up resolved the remaining questions about tool access, interrupted writes, and saved preferences. Those explanations are included in the walkthrough.

The session structure can inform onboarding work in [[developer-ecosystem-expansion|Developer Ecosystem Expansion]]. No training follow-ups remain open.

## Resources

- [NVIDIA generative AI learning paths](https://www.nvidia.com/en-us/learn/learning-path/generative-ai-llm/), including *Building Agentic AI Applications with LLMs*.
- [Hermes Agent](https://github.com/NousResearch/hermes-agent).
- [OpenClaw agent runtime](https://docs.openclaw.ai/concepts/agent) and [agent loop documentation](https://docs.openclaw.ai/agent-loop).
- The model cards linked above for model-specific usage requirements.

## Change history

| Date | Update |
|---|---|
| September 2, 2026 | Collected the questions about models, tools, and memory; established the introductory scope. |
| September 4, 2026 | Selected the DLI reference and a one-hour format. Kept installation outside the shared session. |
| September 8, 2026 | Moved the terminal example ahead of the terminology following Aisha’s review. Added Mike’s alternate-column CSV case and Marcus’s early access-boundary reminder. |
| September 10, 2026 | Added the fresh-conversation check to the memory exercise and retained the document-review example for subagents. |
| September 14, 2026 | Clarified that a timed-out write may already have succeeded. Added the distinction between one-time requests and lasting preferences. |
| September 18, 2026 | Incorporated the technical follow-up answers and closed the remaining training questions. |
| September 22, 2026 | Consolidated the teaching decisions and removed repeated explanations from the walkthrough. |
| September 24, 2026 | Recast the walkthrough as instructions a facilitator can follow and added direct model and harness references. |
