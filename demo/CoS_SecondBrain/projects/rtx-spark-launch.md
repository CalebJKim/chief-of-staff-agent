---
title: RTX Spark Launch
created: 2026-09-09
updated: 2026-09-22
type: project
tags: [project, rtx-spark, launch, strategy]
sources: [raw/meetings/leadership-staff-2026-09-08.md, raw/updates/product-performance-package.md]
status: at-risk
confidence: high
---

# RTX Spark Launch

This project brings together the presentation, product evidence, partner demos, retail preparation, and campaign materials for the RTX Spark launch. The immediate goal is to help leadership choose the keynote story and the demos to show at IFA.

## Where things stand
The recorded performance evidence is approved for use with its stated conditions. The executive presentation and marketing materials still need updates. The retail demo still needs a confirmed owner, and the marketing shoot needs a replacement date.

Approved evidence is ready to use, but the slides still need editing and proposed demo owners still need to accept their assignments.

## Who is involved
- [[elena-park]] coordinates the [[rtx-spark-executive-review]].
- [[mike-chen]] owns the [[inference-performance-claims|product evidence]].
- [[aisha-rahman]] and [[sofia-alvarez]] connect the presentation to the [[hermes-partner-program|partner program]].
- [[marketing-claims-rollout]] covers updates to campaign materials.
- [[marketing-shoot]] covers production and the venue decision.
- [[grant-walker]] is the retail-readiness contact; the final demo assignment remains open.

## What leadership needs to decide
1. Approve the [[agent-first-storyline|proposed keynote story]].
2. Choose the [[ifa-demo-slate|IFA demos]] and confirm who is responsible for each.
3. Select a replacement shoot date.

Before the review, prepare a recommendation and explain the alternatives. The decisions themselves belong in the meeting.

## What to put in the presentation
Start with a problem the audience recognizes. Show how the proposed workflow helps, what information it uses, and what the person still reviews or decides. Compare candidate demos by the benefit they show, the preparation they need, and any unresolved setup or ownership questions.

Keep the sources for existing claims close to the relevant material. Shortening a claim must not remove the conditions that make it accurate.

## What could delay the work
An unassigned retail demo could hold up the final list. The venue change could reduce preparation or editing time. Unclear product wording could require another review.

If a live demo cannot be shown, prepare reviewed screenshots or a narrated walkthrough. Present it as a walkthrough, not as proof of a successful live run. This preparation adds no new product performance claims.

## Product learning notes
Reference reading, September 22, 2026. These notes help explain the product and the launch story. They do not change the project status or assign additional launch work.

### What NVIDIA is presenting
NVIDIA describes RTX Spark as a platform for slim laptops and compact desktops that combines a Grace CPU, Blackwell RTX GPU, and unified memory. The page connects AI agents with creative applications, development, and gaming. It lists Windows 11 support and native CUDA support. Its agent examples include carrying out tasks, creating assets, and writing code; its developer section discusses local model prototyping, fine-tuning, and inference. The laptop story emphasizes portability, while the desktop story includes running personal agents at a desk. [NVIDIA RTX Spark product page](https://www.nvidia.com/en-us/products/rtx-spark/).

My reading of the positioning: NVIDIA wants the buyer to picture a useful everyday computer with AI work woven into it. The audience needs to understand how an agent fits into a normal day before technical specifications mean much. That interpretation is a working view of the messaging, not a confirmed customer preference. [Product positioning reference](https://www.nvidia.com/en-us/products/rtx-spark/).

### Terms I want to be able to explain
Inference means using a trained model to produce an answer or another output. Fine-tuning changes a model through additional training. Connecting an assistant to a document collection is a separate operation: the assistant may retrieve passages to answer a question without changing the model itself.

An agent combines a model with software that can read information and carry out actions. In the Chief of Staff example, understanding a request, finding the right email, and saving a draft are different steps. The model's answer is only one part of the result.

CUDA is NVIDIA's software platform for GPU computing. Its toolkit includes a compiler, libraries, and development tools; developers can also work through languages and frameworks such as Python and PyTorch. My takeaway is that the development story needs to include the software people already use. A hardware specification alone does not tell a developer whether their application is ready to run. [NVIDIA CUDA overview](https://developer.nvidia.com/cuda).

Unified memory describes a memory pool shared by the CPU and GPU. Capacity, application support, and the responsiveness of a particular workflow are separate questions. I would keep those distinctions visible in a technical conversation instead of treating a memory figure as an answer to every workload question.

### A more concrete creative story
NVIDIA Studio provides a useful vocabulary for discussing creative work: video editing, 3D design, broadcasting, graphic design, and photography. It also describes tools such as Broadcast for audio and video effects and RTX Video for supported playback applications. Those are ecosystem references; support on a particular system still needs checking. [NVIDIA Studio](https://www.nvidia.com/en-us/studio/).

For a launch presentation, I would choose one recognizable creative task and follow it through. An example could start with a rough brief, show the material prepared for review, and end with the person's selection or correction. That is a possible story to evaluate, not a promise that a named application completes every step.

The audience should be able to tell what the software generated and what the creator chose. A polished final image by itself leaves that process unclear. Showing one revision would make the person's role easier to follow.

### Questions behind the audience story
Different audiences will use different evidence to decide whether the idea matters to them. These are questions I would bring to research or a walkthrough:

| Audience | Question to explore | What I would want to see |
|---|---|---|
| Someone managing a busy working day | Can the assistant prepare something useful from the information I already have? | A traceable result, such as a draft with the right recipient and context |
| A creator | Where does assistance fit into the existing editing process? | The input, proposed output, and the creator's revision |
| A developer | Can I reproduce the example with the software and access available to me? | Setup requirements, a runnable example, and a clear failure report |
| A person choosing a general-purpose PC | How does the proposed workflow fit alongside the other things I use the computer for? | An understandable account of setup, daily use, and support |

These are hypotheses about what to demonstrate. They are not findings from customer interviews.

### Local computation and connected work
For this demo, local model processing and Google Workspace access are different parts of the system. Reading Gmail or saving a Google draft still involves Google's services. Running the model on the PC does not make that workflow fully offline.

I would sketch where information travels before making a privacy claim. Which content is retrieved? Where is it processed? What is written back? Is any of it retained in logs or Second Brain? Each answer depends on the application and its configuration.

The same applies to permissions. A model being available locally does not grant access to an inbox or permission to send a message. The setup and the user's request determine which actions are appropriate. [[agent-security-prd|The Agent Security PRD]] and [[openshell|OpenShell]] hold related control questions.

### How I would connect this to our launch example
The [[agent-first-storyline|agent-first storyline]] is easiest to explain through work the audience recognizes. A daily brief can show whether the assistant separates new information from tasks needing personal judgment. Meeting preparation can show whether it understands why the meeting matters. A tracker change or email draft can show whether it can produce a useful result from that context.

For a draft, I would look beyond whether text appeared. Was it addressed to the intended person? Did it use the relevant conversation? Was it saved where the user can review it? For a tracker, I would check whether the status reflects the evidence and whether unrelated cells stayed intact.

Those checks make the demonstration meaningful without introducing a hardware benchmark. They also help explain why an assistant may prepare an action for review instead of completing every possible next step.

The [[ifa-demo-slate|IFA demo list]] should give each candidate a distinct purpose. If two examples tell the same story, changing the application or output format alone may not justify showing both. A short description of what the audience learns from each would help compare them.

### Questions to keep for later reading
- Which exact application and system configuration does a proposed example require?
- What setup must a first-time user complete before reaching the useful part?
- Where can the person inspect sources, correct an answer, or stop an action?
- What happens if the source is unavailable or its information has changed?
- Which details belong in the spoken explanation, and which are better left in a supporting note?

The product page is a source for public product positioning. It does not verify our internal launch evidence, approve our deck, or resolve a pending assignment. Existing claim wording still belongs with [[inference-performance-claims|its recorded evidence]] and [[marketing-claims-rollout|the materials review]].
