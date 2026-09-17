# Chief of Staff Agent demo script

## Core value proposition

Everyone gets a chief of staff to help manage their life.

The chief of staff protects attention, prioritizes, chases down non-focus
threads, and proactively watches for things falling through the cracks. This
gives users more time and focus for their best work while taking away stress.

The Chief of Staff Agent runs best locally on RTX Spark. It connects to your
apps for context. Personal data stays on the device for inference: the agent
uses a local model rather than a cloud LLM, with tools running in an OpenShell
sandbox.

## Opening

Many of us are very busy. When we open our laptops in the morning, we are
flooded by email and Slack messages. We often have busy schedules with lots of
meetings. It is hard to focus.

I am already behind and multitasking. The chief of staff gives me immense
mental peace.

We are going to show how agents can act as your personal chief of staff:
cutting through the noise to tell you only what you need to know right now,
helping you identify which projects have to be done today and when, and even
taking on some of the less complicated work.

## Query 1 — Morning brief and protecting attention

On this RTX Spark, I have set up Hermes with local models. I have already
configured everything it needs to be my chief of staff, including access to my
tools and instructions for how I like to do things. Let's get started.

**Prompt**

> Good morning Chief of Staff — what should we work on today?

**Intended response**

> **What you need to know today**
>
> - Leadership moved the RTX Spark Exec Review from Thursday to 5:00 p.m.
>   today. It is a decision meeting, not a working session.
> - Mike's inference package is approved, and Legal cleared the qualified
>   wording for leadership review.
> - The replacement marketing-shoot venue hold expires at 4:30 p.m.
>
> **What you need to get done today**
>
> - **Prepare for leadership's launch decisions** — agree on the keynote story
>   and proposed demos before today's review, using the team's latest feedback.
> - **Finish the security requirements** — complete the final review and hand
>   the PRD to Engineering so implementation can move forward.
> - **Choose the marketing-shoot venue** — select an available option before
>   the hold expires to protect the crew booking and campaign schedule.
>
> **What I can take care of for you**
>
> - Consolidate the team's requested changes into proposed presentation edits
>   for your review.
> - Prepare coordination drafts once you've chosen the venue.

The live brief includes descriptive links to its supporting emails and files.
Keep each list free of overlapping outcomes or a parent task repeated as a subtask.
The optional seeded Google Tasks list provides a checklist the presenter can
check off in Google Tasks; Hermes chat bullets do not sync completion state.

As you can see, I have set up my chief of staff to be succinct and help me cut
through the noise. But how do we know the answers are correct?

Alongside current email, calendar, and files, it can read my Second Brain
project notes in Obsidian. Those notes provide background and relationships;
the latest workspace evidence determines current status and requested changes.
You can see how the graph of linked notes looks in Obsidian. The demo reads
these notes without rewriting them or importing Slack messages.

**Follow-up prompt — Second Brain**

> What notes from my Second Brain would help me prepare for the executive review?

*Show Obsidian.*

## Query 2 — Meeting preparation

Let me show you a couple more things it can do. We have an executive review at
5:00 p.m. that moved to today, and I have not prepared for it. I have not met
with the team, and I need to gather all the project updates. Let's have our
chief of staff help us.

**Prompt**

> Help me prepare for the Exec Review.

**Intended response**

> **Context**
>
> - The review moved to today and needs leadership decisions. Performance
>   evidence is approved, and the latest deck feedback explains the remaining
>   preparation.
>
> **What needs to get done before the meeting**
>
> - Incorporate the approved performance evidence and required qualification.
> - Streamline the presentation and prepare the proposed demo choices and owners.
>
> **Goals for the meeting**
>
> - Approval of the agent-first keynote storyline.
> - Alignment on the IFA demo slate and owners.

The live response links the feedback, leadership request, and deck. This prompt
produces a preparation briefing; artifact edits are requested in follow-ups.

## Query 3 — Project tracking

You can also delegate work to the chief of staff, such as updating trackers. A
major launch like RTX Spark has many moving pieces, and chasing people for
updates is always a pain.

This is an example campaign tracker with several items that need updates. Let's
ask the chief of staff to help.

**Prompt**

> Update the RTX Spark campaign tracker using the latest email evidence, then save follow-up drafts for any items still missing updates. Show me the drafts for review. Don’t send anything.

*Switch the campaign tracker to full screen while the agent works. Keep it full
screen for the completion summary so every update shown by the agent corresponds
to a visible row.*

**Intended response**

> **Updated**
>
> - Product performance claims — Complete
> - Exec Review deck — In progress
> - Agent Messaging — In progress
> - Legal intake — Complete
>
> **Still needs action**
>
> - Marketing shoot — Priya is waiting for a venue decision before the hold
>   expires.
> - Social rollout — Rafael has not provided a current status.
> - Retail demo readiness — the final owner is still unassigned.
>
> I saved follow-up drafts for the items still missing updates. Here are the
> drafts for your review. Nothing was sent.

Show the actual saved drafts' recipients, subjects, and contents. The number
and recipients depend on the current evidence, not a fixed list. An unresolved
decision or unassigned owner does not by itself mean a status update is missing.

## Optional — Scheduled project tracking

The same tracker-and-draft workflow can run through Hermes's native scheduler.
Only include this segment after the scheduled workflow has passed live validation;
installation alone does not create a job or demonstrate a successful run.

Use the [job-creation prompt and validation checklist](README.md#scheduled-project-tracking-optional)
to set it up explicitly in the Chief of Staff profile. Show the job's schedule,
time zone, and next run. Scheduled work updates the tracker and prepares drafts;
it never sends email. There is no fixed number of follow-ups or recipients.

To demonstrate without waiting for the scheduled time, use an enabled job and ask:

> Run Campaign tracker follow-ups now.

Review the actual run output, tracker, and saved drafts. Do not overlap this run
with Query 3 or a reset. If the job is paused, resume it first; a manual trigger
still performs real writes and model inference.

After the demonstration:

> Pause Campaign tracker follow-ups.

Confirm it is paused and any in-progress execution has finished before resetting
the workspace. Recurring execution and duplicate-draft avoidance must be tested,
not assumed from the presentation script.

## Close

As you can see, the chief of staff I put together simplifies my life. It helps
me focus and be more productive. The key is to create a good set of skills that
describe how we like things done, give the agent access to tools so it can
actively help, and teach it about our projects so it has context.

In this session, we will walk through all of these concepts and demystify
agents. By the end, you will know how they work, and hopefully we will have
given you the tools to go home and set up your own chief of staff.

## Expansion ideas and working notes

- Email management and sorting.
- Important and prioritized work.
- Drafting rather than sending email.
- Morning brief and plan for the day.
- News.
- Workfront or Jira updates.
- Blocked projects, missing dependencies, slipping deadlines, and stakeholders
  waiting for feedback.
- Event or launch tracker.
- Follow-up agent and tracker updater.
- Executive event recap and audit.
- Social and online listening: sentiment, quotes, and headlines.
- Pulling in photos.
- Comparing events and producing recap reports.
- Asset audits for messaging or product changes.
- Mockups and design iteration.
- Merchandise and website work.
- Creating decks and key visuals.
- GTMK assets across social, newsletter, website, and print, including resizing
  and minor crops. Add the example tracker link at demo time.
- Explore Adobe as a tool.

**BAC**

- Email and news morning brief.

**Chief of Staff**

- Morning brief across tracker, calendar, email, and Slack.
- Jira and follow-ups.
- Executive event recap and audit.
- Security and OpenShell, including personal photos and confidential documents.
- Personal access from a phone.
