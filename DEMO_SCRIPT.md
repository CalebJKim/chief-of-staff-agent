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

> Hi Abhi!
>
> Here's what you need to know right now:
>
> - The Exec Review meeting moved from Thursday to today at 10:00 a.m.
> - We received the updated performance numbers for the new inference feature.
> - The new DeepSeek Flash model came out. It is 200B and great for two DGX
>   Sparks.
> - There is an email update on the status of OpenShell that you should read.
>   [Link]
>
> Here are the three things you need to get done today:
>
> 1. Finish and send the Agent Security PRD to Engineering. You can skip your
>    1:00–2:00 p.m. meeting to do it, then catch up from the meeting notes.
> 2. Your VP wants to review the Hermes partner-meeting slides. I can set up a
>    review from 4:30–5:00 p.m. today if you want.
> 3. Update the marketing documents with the new inference performance numbers.
>
> There are also several emails we need to answer. I can start preparing draft
> responses if you want.

As you can see, I have set up my chief of staff to be succinct and help me cut
through the noise. But how do we know the answers are correct?

It knows what to prioritize because I have given the agent access to a popular
technique called a second brain. It reads my email and Slack messages, and it
can see my prioritized projects in Obsidian. With that context, it can make
smart recommendations. You can see how the graph of nodes looks in Obsidian.

*Show Obsidian.*

## Query 2 — Meeting preparation

Let me show you a couple more things it can do. We have an executive review at
10:00 a.m. that moved to today, and I have not prepared for it. I have not met
with the team, and I need to gather all the project updates. Let's have our
chief of staff help us.

**Prompt**

> Help me prepare for the Exec Review.

**Intended response**

> Here are the slides we prepared.
>
> We have received updates that may be relevant to the content:
>
> - We received the performance numbers overnight. We need to update slide 4.
> - We received feedback to cut slide 6 and cover that material on slide 7.
> - Your manager recommended moving quickly through the intro so we can spend
>   time on slide 10. [Link]
>
> The key decisions we were trying to get from the meeting were:
>
> - Approval of our proposed keynote storyline.
> - Alignment on the demos for IFA.

## Query 3 — Project tracking

Another useful thing our chief of staff can do is help track project status. A
major launch like RTX Spark has many moving pieces, and chasing people for
updates is always a pain.

This is an example campaign tracker with several items that need updates. Let's
ask the chief of staff to help.

**Prompt**

> Update the status of the RTX Spark campaign tracker.

**Intended response**

> On it…
>
> Reading email and Slack messages…
>
> Updating Google Sheets…
>
> Done! I updated the tracker. We have not received updates for two lanes, and
> one lane is blocked.

**Prompt**

> Let's ask Rafael and Grant for updates on those two lanes. Prepare drafts.

**Intended response**

> Drafting…
>
> The drafts are ready for you to review.

**Prompt**

> Thanks! What's wrong with the blocked lane?

**Intended response**

> There is an issue with the marketing shoot. The venue is not available on
> Wednesday, and we need to decide on a new date. You have to weigh in here.
> [Link]

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
