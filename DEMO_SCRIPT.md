# Chief of Staff demo presentation script

Revised pacing estimate: approximately 7:40 with the opening and ending narration unchanged. The original target remains 7:00; reaching it requires about 40 seconds of cuts elsewhere or faster responses. This revision changes only the tracker/draft narration and shifts subsequent timestamps.

Timing basis: manual trials 26-35. Tracker mean 1:59, median 1:53, range 1:27-3:20 across nine trials, excluding only trial 31's battery-interrupted tracker time. Draft mean 0:41, median 0:40, range 0:32-0:48 across all ten trials. The failed tracker trial is included in timing statistics. Opening/meeting-preparation timings remain the earlier video-based estimates, not newly measured results. These two-prompt trials began in a fresh session, matching the saved script's tracker-session switch.

Budgets below include response waiting, narration, navigation, and result review. Speak during processing; do not add narration time on top of the measured wait. Move to the result at a natural sentence break if the agent finishes early. A repeat of the observed 3:20 tracker run would extend this schedule by roughly 1:21.

## 0:00–0:30 — Introduce the Chief of Staff

*Show Gmail, then the packed calendar.*

Many of us start the day with a crowded inbox and a packed calendar, making it really hard to focus.

Having a Chief of Staff would give us some much-needed clarity. Today, I’ll show you how an AI agent running locally on this NVIDIA RTX Spark laptop can fill that role.

*Switch to Hermes.*

Let’s start with a question we ask ourselves every morning: what should we work on today?

*Submit:*

Hey chief of staff, what should we work on today?

## 0:30–2:02 — Get clarity on the day

*While the agent works:*

On this laptop, I’ve set up Hermes, an open-source agent harness, with a local AI model. I’ve also given it instructions on how I like things done.

But instructions alone aren’t enough. To help plan my day, the agent needs to know what I’m working on, what my schedule looks like, and what new information has come in.

So how does it know all this?

*Show the existing Calendar, Gmail, Docs, Slides, and Sheets tabs, then return to Hermes.*

It knows all this because I’ve given it access to my Google Workspace: my Google Calendar, my Gmail, and my Google Drive, which includes Google Docs, Slides, and Sheets.

It can bring relevant information from those sources together, so I don’t have to go digging through each one myself.

*When the response is ready, around 1:42:*

And here’s the result: what I need to know, what I need to get done, and what the agent can take care of for me—with links to the supporting information.

In this briefing, the rescheduled executive review meeting stands out. Let’s ask our Chief of Staff to help us prepare.

*Submit:*

Help me prepare for the exec review

## 2:02–2:55 — Prepare for the meeting

*While the agent works:*

Knowing that a meeting needs my attention is a useful start. But I also need to understand what it’s about, what’s expected of me, and what I should do beforehand.

Our Chief of Staff can gather that background for me. That means I can spend the time I have before the meeting on actual prep work, rather than hunting for context.

*When the response is ready, point through its sections:*

Here’s the context, my role, the prep work, and the meeting goals—all with supporting links.

The agent also offers to take simple tasks off my plate, further helping me make the most of the time I have before the meeting.

## 2:55–5:25 — Delegate the tracker update

*Open a new Hermes session, as in the recording, and show the tracker.*

Our Chief of Staff can also help us manage projects.

This campaign tracker shows our workstreams, but some statuses need updating. Let’s have our Chief of Staff take care of that.

*Submit by approximately 3:08:*

Hey chief of staff, update the status of the RTX Spark campaign tracker

*Allow about 1:59 from submission to the final response, approximately 3:08-5:07. Show Hermes and the tracker side by side. The paragraphs below are flexible narration, not additional waiting time.*

You can imagine what this would involve manually. For each workstream, I’d need to search emails and files, work out what’s changed, and then come back here to update the status.

And I’d have to repeat that for every row that needs attention. An approval might arrive in one email, while someone else sends feedback that changes what needs to happen next.

The information is already in my Google Workspace, but it’s scattered across different conversations and files. Keeping the tracker current means finding those updates, figuring out what they mean, and bringing them together.

That takes time and attention I could be putting toward the executive review. Our Chief of Staff can handle that coordination work for me, so I can focus on bigger picture, higher impact work.

*Keep the status column visible.*

We can watch the spreadsheet here and review the agent’s explanation alongside it. The updates appear in the Google Sheet my team already uses, so I can check what changed without copying an answer out of chat.

*If the agent is still working, point to Social rollout. Skip this paragraph if the result is ready.*

Some rows may still need information from another person. That’s useful to see too. Once the tracker is current, I can tell where I need to follow up and where the team already has what it needs to keep going.

*When the update is ready, allow about 18 seconds to show the changes and submit the follow-up. Describe the actual result; do not claim success if a status is incorrect.*

There are the updates: some workstreams are Complete, others are In progress, and the agent explains why.

Rafael’s social rollout is still awaiting an update. Let’s ask our Chief of Staff to draft the follow-up.

*Submit:*

Draft an email to Rafael asking for updates

## 5:25–6:15 — Follow up with Rafael

*Allow about 41 seconds for the response, through approximately 6:06, followed by 9 seconds to show the draft. Switch the browser pane to Gmail Drafts while the agent works.*

Notice how little I needed to specify. I didn’t give Rafael’s full name, explain his workstream, or list the questions to ask.

It already has the campaign context from the tracker update. Now it can look up Rafael’s address in Gmail and prepare a follow-up about the missing information, such as whether the assets are ready and what’s holding them up.

Because it’s a draft, I can review the wording before anything gets sent.

*As soon as Hermes reports success, refresh Gmail and open the draft.*

Here it is in Gmail, ready for me to review. That’s one more task off my plate before the meeting.

## 6:15–7:00 — Show context building over time

*Show Second Brain’s graph, then the index.*

So far, our Chief of Staff has helped us using information from Google Workspace. But what about the context we’ve built through previous work?

That’s where Second Brain comes in. It’s a collection of connected notes about our projects, teammates, and more.

*Open the internal team training note.*

Here’s our internal training on building AI assistants. We can see what it covered and who was involved.

*Go directly to the decisions and change history.*

Further down, we have the decisions, why we made them, and how the plan developed over time.

With that context, our Chief of Staff can answer questions about past work, including what we decided and why, without us having to reconstruct the history ourselves.

## 7:00–7:20 — Explain how that context stays current

*Open the existing Update Second Brain scheduled job. Don’t create or run it.*

But how do we keep those notes up to date?

One way to do it is to use a recurring agent job. Here’s an example of a recurring job I’ve set up in Hermes. It checks Google Workspace for meaningful changes and updates the relevant notes.

It’s set up to run daily.

## 7:20–7:40 — Bring it back to RTX Spark

So we’ve gone from an overwhelming workday to a clearer plan, better preparation, and busy work taken off our plate—with context we can keep building over time.

With an RTX Spark at our fingertips, we can run a variety of AI agents locally. Our Chief of Staff is just one example.

Pacing: If the agent finishes early, move to the result at the next natural sentence break. The waiting-time narration is flexible; the four prompts, visible results, Second Brain, and scheduled-job ending stay intact.
