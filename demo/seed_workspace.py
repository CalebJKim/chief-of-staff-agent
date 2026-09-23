#!/usr/bin/env python
"""Create, reset, or remove the reference Chief of Staff Google Workspace."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import random
import sys
import uuid
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree
from zipfile import ZipFile
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "productivity" / "ingest" / "scripts"))
from actions import credentials  # noqa: E402
from baseline import reset_sheet_baseline  # noqa: E402
from second_brain_seed import check_reset, reset_second_brain  # noqa: E402
from googleapiclient.discovery import build  # noqa: E402
from googleapiclient.errors import HttpError  # noqa: E402

MARKER = "chief-of-staff-reference-workspace-v1"
STATE_FILE = "chief-of-staff-workspace-state.json"
TZ_NAME = os.environ.get("CHIEF_OF_STAFF_WORKSPACE_TZ", "America/Los_Angeles")
STATUS_VALUES = ["On track", "In progress", "Awaiting update", "Blocked", "Complete"]
MEANINGFUL_EMAIL_COUNT = 6
BACKGROUND_EMAIL_COUNT = 70
CONTACT_EMAIL_COUNT = 1
EMAIL_REFERENCE_HOUR = 9
EMAIL_REFERENCE_MINUTE = 12
BATCH_SIZE = 50
TASKS_SCOPE = "https://www.googleapis.com/auth/tasks"

BACKGROUND_IDENTITIES = [
    ("Amara", "Okafor"), ("Aarav", "Shah"), ("Sofia", "Alvarez"), ("Liam", "Carter"),
    ("Chloe", "Bennett"), ("Mateo", "Silva"), ("Iris", "Kimura"), ("Jonah", "Foster"),
    ("Nora", "Dubois"), ("Ethan", "Novak"), ("Amina", "Hassan"), ("Diego", "Morales"),
    ("Hana", "Park"), ("Ravi", "Desai"), ("Lucia", "Romero"), ("Felix", "Schneider"),
    ("Yara", "Haddad"), ("Kofi", "Mensah"), ("Mei", "Chen"), ("Hugo", "Pereira"),
    ("Zainab", "Ali"), ("Theo", "Martin"), ("Anika", "Rao"), ("Carlos", "Mendoza"),
    ("Fatima", "Zahra"), ("Kenji", "Sato"), ("Imani", "Brooks"), ("Miguel", "Santos"),
    ("Laila", "Nasser"), ("Arjun", "Patel"), ("Camille", "Laurent"), ("Javier", "Torres"),
    ("Nia", "Johnson"), ("Haruto", "Tanaka"), ("Gabriela", "Costa"), ("Omar", "Farouk"),
    ("Ana", "Ferreira"), ("Nikhil", "Gupta"), ("Samira", "Rahman"), ("Paolo", "Ricci"),
    ("Emi", "Nakamura"), ("Tariq", "Mahmoud"), ("Beatriz", "Souza"), ("Kai", "Nguyen"),
    ("Dalia", "Khalil"), ("Andre", "Walker"), ("Mina", "Lee"), ("Rafael", "Ortega"),
    ("Alina", "Popov"), ("Yusuf", "Demir"), ("Esme", "Clarke"), ("Bao", "Tran"),
    ("Noemi", "Rossi"), ("Jun", "Choi"), ("Farah", "Saleh"), ("Sora", "Yamamoto"),
    ("Grace", "Wilson"), ("Dev", "Kapoor"), ("Ines", "Martins"), ("Akira", "Watanabe"),
    ("Rosa", "Delgado"), ("Santiago", "Ruiz"), ("Nadia", "Ibrahim"), ("Ren", "Ito"),
    ("Maja", "Kowalski"), ("Luis", "Herrera"), ("Leila", "Mansour"), ("Owen", "Murphy"),
    ("Priyanka", "Bose"), ("Dae", "Kim"),
]

BACKGROUND_TOPICS = [
    ("Community volunteering opportunities", "The community team shared optional volunteering opportunities for colleagues who are interested."),
    ("Photography club photo walk", "The employee photography club posted details for its next optional photo walk."),
    ("Cafeteria menu highlights", "The workplace team shared this week's cafeteria menu highlights."),
    ("Wellness webinar recording", "The wellness team posted a recording for anyone who would like to watch it."),
    ("Office shuttle information", "The facilities team shared general office shuttle information."),
    ("Employee book club selection", "The employee book club announced its next optional reading selection."),
    ("Sustainability challenge recap", "The sustainability group posted a recap of its recent employee challenge."),
    ("Learning library recommendations", "The learning team shared a few optional additions to the employee library."),
    ("Community event photos", "The community team posted photos from a recent employee event."),
    ("Workspace tips digest", "The workplace team shared a short collection of optional workspace tips."),
]

BACKGROUND_AUDIENCES = ["Americas", "EMEA", "APAC", "Remote", "Santa Clara", "Austin", "New York"]

BACKLOG_TASKS = [
    {
        "key": "customer_faq", "title": "Publish a customer demo FAQ",
        "sender": "Amina Patel <amina.example@nvidia.com>",
        "requested_days_ago": 12, "due_days_ago": 7,
        "request": "Please put together and share answers to the questions customers asked during our local AI demos. The sales team needs a consistent explanation of what works offline and what requires an internet connection.",
    },
    {
        "key": "pilot_lessons", "title": "Share the pilot-program lessons learned",
        "sender": "Jorge Almeida <jorge.example@nvidia.com>",
        "requested_days_ago": 8, "due_days_ago": 3,
        "request": "Please collect the lessons from the completed employee AI pilot and share the recommended improvements with the rollout team. We need to address the onboarding friction before bringing in the next group.",
    },
    {
        "key": "workshop_budget", "title": "Finalize the developer workshop budget",
        "sender": "Hana Ito <hana.example@nvidia.com>",
        "requested_days_ago": 4, "due_days_ago": 1,
        "request": "Please finish the budget proposal for next month's developer workshop and route it for approval. We need the funding decision before committing to the venue and equipment rentals.",
    },
]


def hermes_home() -> Path:
    if os.environ.get("HERMES_HOME"):
        return Path(os.environ["HERMES_HOME"]).expanduser()
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "hermes"
    return Path.home() / ".hermes"


def state_path() -> Path:
    return hermes_home() / STATE_FILE


def local_now() -> datetime:
    return datetime.now(ZoneInfo(TZ_NAME))


def week_monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def utc_offset() -> str:
    raw = local_now().strftime("%z")
    return raw[:3] + ":" + raw[3:]


def iso(day: date, hm: str) -> str:
    return f"{day.isoformat()}T{hm}:00{utc_offset()}"


def task_service(creds, *, required: bool = False):
    """Check optional Tasks access before any seed/reset writes begin."""
    setup_hint = "Enable Google Tasks API in the OAuth client's project and rerun setup/google-workspace/setup.py to grant Google Tasks access."
    issue = "Google Tasks permission has not been granted."
    if creds.has_scopes([TASKS_SCOPE]):
        api = build("tasks", "v1", credentials=creds, cache_discovery=False)
        try:
            api.tasklists().list(maxResults=1).execute()
            return api
        except HttpError as error:
            if error.resp.status != 403:
                raise
            issue = "Google Tasks API access is unavailable."
    if required:
        raise RuntimeError(f"{issue} {setup_hint} No workspace reset or cleanup was started.")
    print(f"Skipping sample Google Tasks: {issue} {setup_hint}", file=sys.stderr)
    return None


def services(*, tasks_required: bool = False):
    creds = credentials()
    return {
        "tasks": task_service(creds, required=tasks_required),
        "drive": build("drive", "v3", credentials=creds, cache_discovery=False),
        "docs": build("docs", "v1", credentials=creds, cache_discovery=False),
        "sheets": build("sheets", "v4", credentials=creds, cache_discovery=False),
        "slides": build("slides", "v1", credentials=creds, cache_discovery=False),
        "calendar": build("calendar", "v3", credentials=creds, cache_discovery=False),
        "gmail": build("gmail", "v1", credentials=creds, cache_discovery=False),
    }


def execute_batched(api: Any, requests: list[Any], *, ignore_errors: bool = False) -> list[Any]:
    """Execute independent Google API requests in small HTTP batches."""
    results: list[Any] = [None] * len(requests)
    failures: list[tuple[int, Exception]] = []

    for offset in range(0, len(requests), BATCH_SIZE):
        batch = api.new_batch_http_request()

        def callback(request_id: str, response: Any, exception: Exception | None) -> None:
            index = int(request_id)
            if exception is not None:
                if not ignore_errors:
                    failures.append((index, exception))
            else:
                results[index] = response

        for index in range(offset, min(offset + BATCH_SIZE, len(requests))):
            batch.add(requests[index], callback=callback, request_id=str(index))
        batch.execute()

    if failures:
        index, error = failures[0]
        raise RuntimeError(f"Google batch request {index + 1} failed: {error}")
    return results


def move_to_folder(drive, file_id: str, folder_id: str) -> None:
    parents = drive.files().get(fileId=file_id, fields="parents").execute().get("parents", [])
    drive.files().update(
        fileId=file_id,
        addParents=folder_id,
        removeParents=",".join(parents),
        fields="id,parents",
    ).execute()


def create_folder(drive) -> dict:
    item = drive.files().create(
        body={"name": "RTX Spark Campaign", "mimeType": "application/vnd.google-apps.folder", "description": MARKER},
        fields="id,name,webViewLink",
    ).execute()
    return {"id": item["id"], "url": item.get("webViewLink", f"https://drive.google.com/drive/folders/{item['id']}")}


def upload_template(drive, folder_id: str, filename: str, name: str, mime_type: str) -> dict:
    from googleapiclient.http import MediaFileUpload
    source = ROOT / "demo" / "templates" / filename
    source_mimes = {"application/vnd.google-apps.document": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/vnd.google-apps.spreadsheet": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/vnd.google-apps.presentation": "application/vnd.openxmlformats-officedocument.presentationml.presentation"}
    result = drive.files().create(body={"name": name, "parents": [folder_id], "mimeType": mime_type}, media_body=MediaFileUpload(str(source), mimetype=source_mimes[mime_type], resumable=False), fields="id,name,mimeType,webViewLink").execute()
    return {"id": result["id"], "url": result.get("webViewLink", "")}

def create_doc(drive, folder_id): return upload_template(drive, folder_id, "rtx-spark-campaign-plan.docx", "RTX Spark Campaign Plan", "application/vnd.google-apps.document")
def create_slides(drive, folder_id):
    result = upload_template(drive, folder_id, "rtx-spark-exec-review.pptx", "RTX Spark Exec Review", "application/vnd.google-apps.presentation")
    result["template_sha256"] = deck_template_hash()
    return result
def create_sheet(drive, folder_id): return upload_template(drive, folder_id, "rtx-spark-campaign-tracker.xlsx", "RTX Spark Campaign Tracker", "application/vnd.google-apps.spreadsheet")

def reset_original_sheet(drive, sheets, state: dict, evidence: dict, refreshed: str) -> None:
    """Keep one comparison copy at the seeded baseline, separate from the working tracker."""
    if state.get("original_sheet", {}).get("id") == state["sheet"]["id"]:
        raise ValueError("The original comparison copy must be separate from the working tracker.")
    if not state.get("reference_folder", {}).get("id"):
        folder = drive.files().create(
            body={"name": "Reference Materials - DO NOT MODIFY", "mimeType": "application/vnd.google-apps.folder",
                  "parents": [state["folder"]["id"]]},
            fields="id,webViewLink",
        ).execute()
        state["reference_folder"] = {"id": folder["id"], "url": folder["webViewLink"]}
        if state.get("original_sheet", {}).get("id"):
            move_to_folder(drive, state["original_sheet"]["id"], folder["id"])
    if not state.get("original_sheet", {}).get("id"):
        copied = drive.files().copy(
            fileId=state["sheet"]["id"],
            body={"name": "[ORIGINAL] RTX Spark Campaign Tracker", "parents": [state["reference_folder"]["id"]]},
            fields="id,webViewLink",
        ).execute()
        state["original_sheet"] = {"id": copied["id"], "url": copied["webViewLink"]}
    if state["original_sheet"]["id"] == state["sheet"]["id"]:
        raise ValueError("The original comparison copy must be separate from the working tracker.")
    # Keep the same evidence/working-file links; only the write target changes.
    comparison_state = {**state, "sheet": {**state["sheet"], "id": state["original_sheet"]["id"]}}
    reset_sheet_baseline(sheets, comparison_state, evidence, refreshed)

def seeded_email_times(count: int, now: datetime | None = None) -> list[datetime]:
    """Repeat an irregular local-time schedule relative to each reset date."""
    current = (now or local_now()).astimezone(ZoneInfo(TZ_NAME))
    cursor = current.replace(hour=EMAIL_REFERENCE_HOUR, minute=EMAIL_REFERENCE_MINUTE, second=0, microsecond=0)
    # A local fixed seed keeps each email's time stable without uniform spacing.
    rng = random.Random("chief-of-staff-email-times")
    times = []
    for _ in range(count):
        times.append(cursor)
        cursor -= timedelta(minutes=rng.randint(5, 24))
    return times


def background_email_specs() -> list[tuple[str, str, str]]:
    specs = []
    for index, (first, last) in enumerate(BACKGROUND_IDENTITIES):
        subject, body = BACKGROUND_TOPICS[index % len(BACKGROUND_TOPICS)]
        audience = BACKGROUND_AUDIENCES[index // len(BACKGROUND_TOPICS)]
        specs.append((
            f"{first} {last} <{first.lower()}.{last.lower()}.example@nvidia.com>",
            f"{subject} — {audience}",
            f"Hi,\n\n{body} This is informational only; no action is required.\n\nThanks,\n{first}",
        ))
    return specs


def mail_import_request(
    gmail,
    account: str,
    sender: str,
    subject: str,
    body: str,
    index: int,
    received_at: datetime,
    seed_run_id: str,
    *,
    important: bool,
) -> Any:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = account
    message["Subject"] = subject
    message["Date"] = format_datetime(received_at)
    message["Message-ID"] = f"<{MARKER}-{seed_run_id}-{index}@demo.invalid>"
    message.set_content(body + f"\n\n[{MARKER}]")
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    labels = ["INBOX", "UNREAD"]
    if important:
        labels.append("IMPORTANT")
    return gmail.users().messages().import_(userId="me", body={"raw": raw, "labelIds": labels}, internalDateSource="dateHeader", neverMarkSpam=True, processForCalendar=False)


EXEC_REVIEW_ROLES = "You will present the storyline and proposed demo slate. Planned attendees: you, Elena Park (chair and your manager), Mike Chen (performance evidence), Aisha Rahman (deck and partner readiness), and Daniel Cho (Legal). Final demo selection and the retail demo owner remain open decisions."


def create_emails(gmail, deck_url: str, sheet_url: str, doc_url: str) -> tuple[list[dict], dict[str, str]]:
    account = gmail.users().getProfile(userId="me").execute()["emailAddress"]
    meaningful = [
        ("Elena Park <elena.example@nvidia.com>", "URGENT: RTX Spark Exec Review moved to 5 PM today", f"Hi,\n\nAs your manager, I need your focus on today's leadership decisions. Leadership moved the RTX Spark Exec Review from Thursday to 5:00 PM today. This is a decision meeting, not a working session. We need two outcomes: approval of the agent-first keynote storyline, and alignment on the IFA demo slate and owners.\n\n{EXEC_REVIEW_ROLES}\n\nDeck: {deck_url}\n\n— Elena"),
        ("Mike Chen <mike.example@nvidia.com>", "APPROVED: RTX Spark inference numbers for slide 4", "The performance package is approved for today's Exec Review. Use exactly: 2.1x faster time-to-first-token versus the prior approved release; 38 tokens/second sustained on the fixed 35B workflow; 22% lower energy per completed workflow. Required footnote: Pre-production measurements on the RTX Spark reference configuration. Results vary by model, quantization, and workload. Daniel cleared this wording for leadership review."),
        ("Aisha Rahman <aisha.example@nvidia.com>", "Exec Review deck pass: cut slide 6; protect slide 10", f"My review is complete; I have not edited the deck. These edits are still for you to apply: put Mike's approved numbers on slide 4. Summarize the proposed customer-use example from slide 6 in the Customer Example section of slide 7, then remove slide 6 from the live flow. Preserve the local laptop comparison, the draft follow-up reviewed by the associate, and customer details staying on the device. This is a proposed use case, not customer validation or an approved demo selection; the demo slate and owners still need a decision. Move quickly through the opening so there is enough discussion time on slide 10.\n\nDeck: {deck_url}"),
        ("Daniel Cho <daniel.example@nvidia.com>", "Legal scope: RTX Spark wording cleared for leadership review", "The RTX Spark performance wording and pre-production qualification are cleared for today's leadership review. This is not blanket campaign-wide approval; keep the qualification intact and route final external copy through Legal."),
        ("Priya Nair <priya.example@nvidia.com>", "Decision by 4:30 PM today: marketing shoot venue hold", f"The planned venue is unavailable. We can hold Studio B Friday or Studio C Tuesday, with the preferred crew, until 4:30 PM today. Choose one before the hold expires or we risk a campaign slip.\n\nTracker: {sheet_url}"),
        ("Elena Park <elena.example@nvidia.com>", "Agent Security PRD needs to reach Engineering today", f"Please finish and send the Agent Security PRD to Engineering today. Protect a focused hour for the final pass. You can skip the optional launch storyboard session; notes will be posted afterward.\n\nCampaign plan: {doc_url}"),
    ]
    background = background_email_specs()
    contacts = [
        ("Rafael Costa <rafael.example@nvidia.com>", "REFERENCE CONTACT ONLY - Social rollout", "Hi,\n\nThis message only provides my contact address for RTX Spark social rollout coordination. It is not a project status update.\n\nThanks\nRafael"),
    ]
    data = [(*item, True) for item in meaningful] + [(*item, False) for item in background + contacts]
    times = seeded_email_times(len(data))
    backlog_start = len(data)
    now = local_now()
    for item in BACKLOG_TASKS:
        due = (now.date() - timedelta(days=item["due_days_ago"])).isoformat()
        data.append((item["sender"], item["title"], f"Hi,\n\n{item['request']}\n\nRequested completion date: {due}.\n\nThanks", False))
        times.append(now.replace(hour=10, minute=0, second=0, microsecond=0) - timedelta(days=item["requested_days_ago"]))
    seed_run_id = uuid.uuid4().hex
    requests = [
        mail_import_request(
            gmail,
            account,
            sender,
            subject,
            body,
            index,
            times[index - 1],
            seed_run_id,
            important=important,
        )
        for index, (sender, subject, body, important) in enumerate(data, 1)
    ]
    results = execute_batched(gmail, requests)
    created = [
        {"id": result["id"], "thread_id": result.get("threadId", result["id"]), "url": f"https://mail.google.com/mail/u/0/#all/{result.get('threadId', result['id'])}"}
        for result in results
    ]
    evidence = {"elena": created[0]["url"], "mike": created[1]["url"], "aisha": created[2]["url"], "daniel": created[3]["url"], "priya": created[4]["url"], "prd": created[5]["url"]}
    evidence.update({item["key"]: created[backlog_start + index]["url"] for index, item in enumerate(BACKLOG_TASKS)})
    return created, evidence


def create_tasks(api, state: dict, evidence: dict[str, str]) -> None:
    if api is None:
        return
    task_list = api.tasklists().get(tasklist="@default").execute()
    state["task_list"] = {"id": task_list["id"], "title": task_list["title"]}
    specs = [
        ("Prepare RTX Spark leadership decisions", "Prepare the keynote storyline and proposed IFA demos and owners for today's executive review. Incorporate the approved performance wording, its qualification, and the deck review feedback.", ("elena", "mike", "aisha", "daniel"), "slides", 0),
        ("Choose the marketing shoot venue", "Choose Studio B Friday or Studio C Tuesday before the 4:30 PM hold expires so Priya can protect the crew and campaign schedule.", ("priya",), "sheet", 0),
        ("Finish and send the Agent Security PRD", "Complete the final PRD pass and send it to Engineering today. Protect focused time for the handoff.", ("prd",), "doc", 0),
    ]
    today = local_now().date()
    for item in BACKLOG_TASKS:
        requested = (today - timedelta(days=item["requested_days_ago"])).isoformat()
        context = f"Backlog: requested on {requested} and still unfinished. {item['request']}"
        specs.append((item["title"], context, (item["key"],), None, item["due_days_ago"]))
    requests = []
    for title, context, sources, file_key, due_days_ago in specs:
        links = "\n".join(evidence[source] for source in sources)
        working_file = f"\n\nWorking file: {state[file_key]['url']}" if file_key else ""
        body = {
            "title": title,
            "notes": f"{context}\n\nSource emails:\n{links}{working_file}\n\n[{MARKER}]",
            "status": "needsAction",
            "due": (today - timedelta(days=due_days_ago)).isoformat() + "T00:00:00Z",
        }
        requests.append(api.tasks().insert(tasklist=state["task_list"]["id"], body=body))
    state["tasks"] = [
        {"id": item["id"], "title": item["title"], "url": item.get("webViewLink", "")}
        for item in execute_batched(api, requests)
    ]


def clear_seeded_tasks(api, state: dict) -> None:
    """Remove seeded tasks only; preserve the list and any personal tasks."""
    task_list = state.get("task_list", {}).get("id")
    if not task_list:
        return
    try:
        tracked = {item["id"] for item in state.get("tasks", [])}
        requests = []
        page_token = None
        while True:
            page = api.tasks().list(tasklist=task_list, maxResults=100, showCompleted=True, showHidden=True, pageToken=page_token).execute()
            requests.extend(
                api.tasks().delete(tasklist=task_list, task=item["id"])
                for item in page.get("items", [])
                if item["id"] in tracked or MARKER in (item.get("notes") or "")
            )
            page_token = page.get("nextPageToken")
            if not page_token:
                break
        execute_batched(api, requests)
    except HttpError as error:
        if error.resp.status != 404:
            raise
        state.pop("task_list", None)
    state["tasks"] = []


WEEKDAY_EVENTS = [
    [
        ("08:30", "09:00", "Launch-week priorities", "Set the week's critical path and decision owners."),
        ("09:30", "10:15", "Keynote speaker risk review", "Review the speaker lineup, alternates, and outreach."),
        ("10:30", "11:30", "IFA keynote structure workshop", "Align the four-talk sequence with the agent-first narrative."),
        ("12:00", "13:00", "Working lunch — partner story", "Review how partner proof points support the launch narrative."),
        ("13:30", "14:15", "Campaign operations sync", "Check creative, legal, partner, and production dependencies."),
        ("15:00", "16:00", "Focus block — campaign plan", "Update the campaign plan and unresolved decisions."),
        ("16:30", "17:00", "EMEA handoff", "Share decisions and risks with the regional team."),
    ],
    [
        ("08:45", "09:15", "Product claims check-in", "Review validation progress and open qualification questions."),
        ("09:30", "10:30", "Resolve RTX Spark creative comments", "Update the hero claim, stage banner, and product UI imagery."),
        ("11:00", "11:45", "Partner enablement review", "Review partner slides and the staged Windows pilot."),
        ("12:30", "13:15", "Lunch with developer relations", "Align launch examples and developer proof points."),
        ("13:30", "14:30", "Local AI Summit demo QA", "Review the three-station script, blockers, and AV dependencies."),
        ("15:15", "16:00", "Agency production check-in", "Review storyboard feedback, budget scenarios, and crew holds."),
        ("16:30", "17:15", "Focus block — partner edits", "Apply the agreed partner-slide changes."),
    ],
    [
        ("08:15", "08:45", "Midweek campaign pulse", "Review delivery risk and the decisions still waiting on owners."),
        ("09:00", "10:00", "Retail demo rehearsal", "Validate the retail demo flow and identify coverage gaps."),
        ("10:30", "11:15", "Social rollout planning", "Review asset readiness, timing, and channel dependencies."),
        ("11:30", "12:00", "Manager one-on-one", "Review launch priorities and executive-meeting goals."),
        ("13:00", "14:30", "Focus block — Agent Security PRD", "Complete the final security and engineering review pass."),
        ("15:00", "15:45", "Legal office hours", "Review qualification language and external-copy routing."),
        ("16:15", "17:00", "Creative production review", "Review the shoot plan and unresolved venue options."),
    ],
    [
        ("08:30", "09:00", "IFA campaign PMO", "Review critical path, partner commitments, and print readiness."),
        ("09:30", "10:15", "Performance package review", "Check the latest inference evidence and required footnote."),
        ("10:45", "11:30", "Executive deck working session", "Reconcile review comments before leadership circulation."),
        ("12:00", "13:00", "Working lunch — demo slate", "Narrow the IFA demo options and proposed owners."),
        ("13:30", "14:15", "Launch video agency review", "Resolve venue, crew, and production tradeoffs."),
        ("15:00", "16:00", "Focus block — executive deck", "Apply final content updates and verify decision slides."),
        ("16:30", "17:15", "Leadership pre-read handoff", "Prepare the decision-focused pre-read for leadership."),
    ],
    [
        ("08:30", "09:00", "Friday launch pulse", "Close open owners and flag anything that could slip next week."),
        ("09:30", "10:30", "Demo readiness review", "Confirm demo coverage, AV readiness, and escalation owners."),
        ("11:00", "11:45", "Campaign metrics review", "Review readiness signals and outstanding evidence."),
        ("12:30", "13:15", "Team lunch", "Informal launch-team check-in."),
        ("14:00", "15:00", "Weekly planning", "Set next week's milestones and owner commitments."),
        ("16:00", "16:30", "APAC decision handoff", "Share decisions and unresolved risks with APAC."),
    ],
]

WEEKDAY_ADDITIONAL_EVENTS = [
    [
        ("08:00", "08:15", "Executive briefing prep", "Review the overnight brief before the first leadership discussion."),
        ("08:15", "08:45", "Product leadership prep", "Review the day's executive decisions before the launch-week kickoff."),
        ("09:00", "09:30", "Finance and procurement checkpoint", "Clear launch purchases and budget questions awaiting a decision."),
        ("09:50", "10:40", "Executive communications check", "Align leadership messaging and open speaker questions."),
        ("10:50", "11:20", "Speaker outreach huddle", "Confirm outreach owners and backup speakers."),
        ("11:30", "12:00", "Chief of staff office hours", "Resolve quick owner and sequencing questions before lunch."),
        ("12:30", "13:15", "Partner escalation office hours", "Resolve urgent partner dependencies during the working lunch."),
        ("13:15", "13:30", "Decision log review", "Record decisions and flag follow-ups for the afternoon."),
        ("13:50", "14:40", "Creative delivery checkpoint", "Review priority creative handoffs and delivery risk."),
        ("14:40", "15:00", "Agency callback", "Close urgent agency questions before the focus block."),
        ("16:40", "17:20", "Regional decisions debrief", "Close the loop on launch decisions with regional leads."),
    ],
    [
        ("08:00", "08:30", "Overnight media scan", "Review overnight coverage and issues needing an executive response."),
        ("08:30", "09:00", "Morning leadership briefing", "Review overnight changes and today's escalation path."),
        ("09:15", "09:30", "Speaker confirmation", "Confirm the day's speaker and outreach commitments."),
        ("09:50", "10:20", "Brand review follow-up", "Resolve the remaining brand questions from creative review."),
        ("10:30", "10:50", "Launch partner callback", "Close a time-sensitive partner question before enablement review."),
        ("10:50", "11:20", "Partner launch escalation", "Unblock time-sensitive partner launch dependencies."),
        ("11:45", "12:30", "Product leadership pre-brief", "Prepare decisions and open questions for the afternoon reviews."),
        ("12:45", "13:30", "Developer ecosystem check-in", "Review developer commitments and launch examples."),
        ("14:00", "14:45", "Demo owner office hours", "Resolve ownership gaps raised during demo QA."),
        ("15:30", "16:30", "Production budget review", "Review agency tradeoffs and protected crew holds."),
    ],
    [
        ("08:00", "08:30", "Executive inbox triage", "Resolve urgent requests before the midweek campaign pulse."),
        ("08:45", "09:00", "Customer insights readout", "Review the latest customer signal before retail rehearsal."),
        ("09:30", "10:15", "Retail partner escalation", "Close partner questions discovered during rehearsal."),
        ("10:15", "10:30", "Editorial stand-up", "Confirm messaging handoffs for the rest of the day."),
        ("10:45", "11:30", "Content approvals huddle", "Review social assets and approvals needed today."),
        ("13:30", "14:15", "Security stakeholder check-in", "Align reviewers during the protected PRD work block."),
        ("14:30", "15:00", "Engineering handoff", "Transfer approved security decisions to the engineering team."),
        ("15:20", "16:00", "Claims escalation review", "Resolve qualification questions raised in legal office hours."),
        ("16:00", "16:15", "Approval queue closeout", "Clear pending approvals before creative production review."),
        ("16:30", "17:15", "Production decisions huddle", "Close venue and production decisions before end of day."),
    ],
    [
        ("08:15", "08:45", "Leadership agenda check", "Confirm decisions and presenters for upcoming leadership reviews."),
        ("09:45", "10:30", "Performance messaging sync", "Align approved evidence with the executive narrative."),
        ("11:00", "12:00", "Executive communications review", "Polish the decision story while the deck is being updated."),
        ("12:00", "12:30", "Executive sponsor check-in", "Review the decisions that need sponsorship before the working lunch."),
        ("12:30", "13:30", "Demo owner working lunch", "Resolve ownership and readiness questions for the demo slate."),
        ("13:30", "13:50", "Demo production callback", "Close urgent production questions from the working lunch."),
        ("13:50", "14:40", "Agency escalation huddle", "Close open venue, crew, and production tradeoffs."),
        ("14:40", "15:00", "Leadership materials check", "Confirm the materials needed for the afternoon pre-read."),
        ("15:30", "16:30", "Pre-read quality check", "Verify decision framing before the leadership handoff."),
    ],
    [
        ("08:00", "08:15", "Week-close inbox scan", "Identify urgent items that need attention before the Friday launch pulse."),
        ("08:15", "08:45", "End-of-week executive triage", "Resolve urgent requests before the Friday launch pulse."),
        ("09:00", "09:30", "Customer readiness check", "Review customer-facing readiness and outstanding commitments."),
        ("09:45", "10:15", "Demo escalation huddle", "Close the highest-risk findings from readiness review."),
        ("10:30", "10:45", "PR and analyst callback", "Resolve a time-sensitive external communications question."),
        ("10:45", "11:30", "Metrics narrative review", "Connect readiness evidence to the leadership story."),
        ("11:45", "12:30", "Finance and planning review", "Review launch spend and next week's planning assumptions."),
        ("12:45", "13:30", "Team commitments check", "Confirm owners and next steps during the team lunch."),
        ("13:30", "14:00", "Talent and staffing check-in", "Review staffing coverage for next week's launch milestones."),
        ("14:20", "14:50", "Planning decisions checkpoint", "Resolve open decisions before next week's plan is finalized."),
        ("15:00", "15:30", "Executive follow-up block", "Close outstanding leadership follow-ups before the global handoff."),
        ("16:10", "17:00", "Global handoff closeout", "Coordinate end-of-week decisions with the APAC handoff."),
    ],
]

TODAY_EVENTS = [
    ("08:00", "08:25", "Today's priorities", "Review overnight changes and today's critical decisions."),
    ("09:00", "09:45", "IFA campaign PMO", "Review critical path, partner commitments, and print readiness."),
    ("10:15", "11:00", "Agent messaging review", "Align campaign wording with the approved performance package."),
    ("11:00", "12:00", "Focus block — Agent Security PRD", "Complete the final pass before sending the PRD to Engineering."),
    ("12:30", "13:15", "Partner working lunch", "Review partner proof points and pilot readiness."),
    ("14:00", "14:30", "Legal qualification check", "Confirm leadership-review wording and the required footnote."),
    ("15:00", "16:00", "Launch storyboard working session — notes available", "Optional working session; notes will be posted afterward."),
    ("16:00", "17:00", "Executive prep block", "Apply deck feedback and prepare the two leadership decisions."),
    ("17:00", "17:45", "RTX Spark Exec Review — leadership decisions", f"Decision meeting: approve the agent-first keynote storyline and align on IFA demos and owners. {EXEC_REVIEW_ROLES}"),
    ("17:00", "17:30", "Decision follow-up triage", "Capture decisions, unresolved owners, and required follow-ups."),
]


def calendar_event_specs(
    start_day: date,
    deck_url: str,
    doc_url: str,
    sheet_url: str,
    reference_day: date | None = None,
) -> list[tuple[date, str, str, str, str]]:
    current = reference_day or local_now().date()
    active_offset = (current - start_day).days
    if active_offset not in range(5):
        active_offset = 4
    specs = []
    for offset, weekday_events in enumerate(WEEKDAY_EVENTS):
        day = start_day + timedelta(days=offset)
        events = TODAY_EVENTS if offset == active_offset else weekday_events
        for begin, end, title, description in [*events, *WEEKDAY_ADDITIONAL_EVENTS[offset]]:
            link = f"\nDeck: {deck_url}" if title.startswith("RTX Spark Exec Review") else f"\nNotes: {doc_url}" if title.startswith("Launch storyboard") else f"\nTracker: {sheet_url}" if title == "IFA campaign PMO" else ""
            specs.append((day, begin, end, title, f"{description}{link}"))
    return specs


def create_calendar(calendar, start_day: date, deck_url: str, doc_url: str, sheet_url: str) -> list[dict]:
    requests = []
    for day, begin, end, title, description in calendar_event_specs(start_day, deck_url, doc_url, sheet_url):
        requests.append(calendar.events().insert(calendarId="primary", body={"summary": title, "description": f"{description}\n[{MARKER}]", "start": {"dateTime": iso(day, begin), "timeZone": TZ_NAME}, "end": {"dateTime": iso(day, end), "timeZone": TZ_NAME}}, sendUpdates="none"))
    return [
        {"id": result["id"], "url": result.get("htmlLink", "")}
        for result in execute_batched(calendar, requests)
    ]


def seeded_gmail_message_ids(gmail) -> set[str]:
    message_ids = set()
    page_token = None
    while True:
        kwargs = {
            "userId": "me",
            "q": f'"{MARKER}"',
            "includeSpamTrash": True,
            "maxResults": 500,
        }
        if page_token:
            kwargs["pageToken"] = page_token
        page = gmail.users().messages().list(**kwargs).execute()
        message_ids.update(item["id"] for item in page.get("messages", []) if item.get("id"))
        page_token = page.get("nextPageToken")
        if not page_token:
            return message_ids


def clear_all_drafts(gmail) -> int:
    draft_ids = []
    page_token = None
    while True:
        kwargs = {"userId": "me", "maxResults": 500}
        if page_token:
            kwargs["pageToken"] = page_token
        page = gmail.users().drafts().list(**kwargs).execute()
        draft_ids.extend(item["id"] for item in page.get("drafts", []) if item.get("id"))
        page_token = page.get("nextPageToken")
        if not page_token:
            break
    requests = [gmail.users().drafts().delete(userId="me", id=draft_id) for draft_id in draft_ids]
    execute_batched(gmail, requests)
    return len(draft_ids)


def remove_dynamic_items(state: dict, svc: dict, *, clear_drafts: bool = False) -> None:
    if clear_drafts:
        clear_all_drafts(svc["gmail"])
    email_ids = {item.get("id") for item in state.get("emails", []) if item.get("id")}
    email_ids.update(seeded_gmail_message_ids(svc["gmail"]))
    if email_ids:
        svc["gmail"].users().messages().batchDelete(
            userId="me",
            body={"ids": sorted(email_ids)},
        ).execute()
    try:
        start = state.get("week_of") + "T00:00:00" + utc_offset()
        end = (date.fromisoformat(state.get("week_of")) + timedelta(days=5)).isoformat() + "T00:00:00" + utc_offset()
        found_events = svc["calendar"].events().list(calendarId="primary", timeMin=start, timeMax=end, singleEvents=True, maxResults=2500).execute().get("items", [])
    except Exception:
        found_events = []
    event_ids = {item.get("id") for item in state.get("events", [])} | {item.get("id") for item in found_events if MARKER in (item.get("description") or "")}
    delete_requests = [
        svc["calendar"].events().delete(calendarId="primary", eventId=event_id, sendUpdates="none")
        for event_id in event_ids
        if event_id
    ]
    execute_batched(svc["calendar"], delete_requests, ignore_errors=True)


def cleanup(state: dict) -> None:
    svc = services(tasks_required=bool(state.get("task_list")))
    clear_seeded_tasks(svc["tasks"], state)
    remove_dynamic_items(state, svc)
    if state.get("folder", {}).get("id"):
        try: svc["drive"].files().update(fileId=state["folder"]["id"], body={"trashed": True}).execute()
        except Exception: pass


def seed(week_of: date) -> dict:
    svc = services()
    state = {"schema": 1, "marker": MARKER, "week_of": week_of.isoformat(), "events": [], "emails": []}
    try:
        state["folder"] = create_folder(svc["drive"])
        state["doc"] = create_doc(svc["drive"], state["folder"]["id"])
        state["slides"] = create_slides(svc["drive"], state["folder"]["id"])
        reset_deck_baseline(svc["slides"], state["slides"]["id"], drive=svc["drive"])
        state["sheet"] = create_sheet(svc["drive"], state["folder"]["id"])
        state["emails"], evidence = create_emails(svc["gmail"], state["slides"]["url"], state["sheet"]["url"], state["doc"]["url"])
        create_tasks(svc["tasks"], state, evidence)
        reset_sheet_baseline(svc["sheets"], state, evidence, local_now().date().isoformat())
        reset_original_sheet(svc["drive"], svc["sheets"], state, evidence, local_now().date().isoformat())
        state["events"] = create_calendar(svc["calendar"], week_of, state["slides"]["url"], state["doc"]["url"], state["sheet"]["url"])
        state_path().parent.mkdir(parents=True, exist_ok=True)
        state_path().write_text(json.dumps(state, indent=2), encoding="utf-8")
        return state
    except Exception:
        cleanup(state)
        raise


def reset_in_place(state: dict, week_of: date) -> dict:
    svc = services(tasks_required=bool(state.get("task_list")))
    template_hash = deck_template_hash()
    reset_deck_baseline(svc["slides"], state["slides"]["id"], drive=svc["drive"],
                        restore_template=state["slides"].get("template_sha256") != template_hash)
    state["slides"]["template_sha256"] = template_hash
    clear_seeded_tasks(svc["tasks"], state)
    remove_dynamic_items(state, svc, clear_drafts=True)
    state["emails"], evidence = create_emails(svc["gmail"], state["slides"]["url"], state["sheet"]["url"], state["doc"]["url"])
    create_tasks(svc["tasks"], state, evidence)
    reset_sheet_baseline(svc["sheets"], state, evidence, local_now().date().isoformat())
    reset_original_sheet(svc["drive"], svc["sheets"], state, evidence, local_now().date().isoformat())
    state["events"] = create_calendar(svc["calendar"], week_of, state["slides"]["url"], state["doc"]["url"], state["sheet"]["url"])
    state["week_of"] = week_of.isoformat()
    state_path().write_text(json.dumps(state, indent=2), encoding="utf-8")
    return state


def deck_template_hash() -> str:
    return hashlib.sha256((ROOT / "demo" / "templates" / "rtx-spark-exec-review.pptx").read_bytes()).hexdigest()


def reset_deck_baseline(slides, presentation_id: str, *, drive=None, restore_template=False) -> None:
    presentation = slides.presentations().get(presentationId=presentation_id).execute()
    source = ROOT / "demo" / "templates" / "rtx-spark-exec-review.pptx"
    with ZipFile(source) as template:
        root = ElementTree.fromstring(template.read("ppt/presentation.xml"))
    ns = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main"}
    expected_slides = len(root.findall("p:sldIdLst/p:sldId", ns))
    if not expected_slides:
        raise RuntimeError("The seed deck template contains no slides")
    if restore_template or len(presentation.get("slides", [])) != expected_slides:
        if drive is None:
            raise RuntimeError("The demo deck template or structure changed; reset needs Drive access to restore its template")
        from googleapiclient.http import MediaFileUpload

        # Refresh the design or restore deleted slides without changing existing deck links.
        drive.files().update(
            fileId=presentation_id,
            body={"mimeType": "application/vnd.google-apps.presentation"},
            media_body=MediaFileUpload(str(source), mimetype="application/vnd.openxmlformats-officedocument.presentationml.presentation", resumable=False),
            fields="id",
        ).execute()
        presentation = slides.presentations().get(presentationId=presentation_id).execute()
        if len(presentation.get("slides", [])) != expected_slides:
            raise RuntimeError("The demo deck template was not fully restored; retry the reset before running the demo")
    wanted = {
        3: ("Campaign readiness", """CLAIMS
Approved evidence is ready to incorporate.

DECK
The latest review pass defines the required edits.

DECISIONS
Leadership needs to close the keynote storyline and IFA demo slate."""),
        4: ("Inference performance — update required", """Performance to go here - Mike Chen to provide

OWNER
Mike Chen / Marketing"""),
        5: ("One claim across every surface", """IFA DECK
Agent Messaging • Campaign plan • Creative assets

DECISION GATE
Approve wording and disclaimer once, then propagate without drift.

CONTROL
Do not invent, extrapolate, or preserve superseded multipliers."""),
        6: ("Customer use example", """SCENARIO
A retail associate compares two laptops using a local product catalog.

ASSISTANCE
The assistant summarizes the differences and drafts a customer follow-up.

CUSTOMER VALUE
The associate reviews the draft before sending. Customer details stay on the device."""),
        7: ("IFA demos — alignment needed", """DECISION
Choose demos that show useful assistance with the user in control.

CUSTOMER EXAMPLE
Candidate use case still to be summarized for the review.

OPEN
Confirm the demo slate and owners. No selection is approved yet."""),
        8: ("Execution dependencies", """CLAIMS
Approval unlocks deck, messaging, and creative updates.

PRODUCTION
Venue and crew timing depend on a same-day decision.

PARTNERS
Commitments must map back to the approved keynote and demo decisions."""),
        9: ("Marketing shoot — decision required", """BLOCKER
The planned venue is unavailable.

DECISION
Choose a replacement shoot date.

IMPACT
Priya cannot rebook the venue or protect downstream crew holds until the date is set."""),
        10: ("Two decisions to leave with", """1  APPROVE THE PROPOSED KEYNOTE STORYLINE
Lead with agents; use specifications as evidence.

2  ALIGN ON THE DEMOS FOR IFA
Confirm the slate and owners that prove the story.

Working files
Campaign tracker • Campaign plan"""),
    }
    requests = []
    for slide_number, (title, body) in wanted.items():
        slide = presentation["slides"][slide_number - 1]
        text_boxes = []
        for element in slide.get("pageElements", []):
            text = "".join(item.get("textRun", {}).get("content", "") for item in element.get("shape", {}).get("text", {}).get("textElements", [])).strip()
            if text:
                text_boxes.append(element["objectId"])
        if len(text_boxes) < 2:
            raise RuntimeError(f"Slide {slide_number} does not contain title/body text boxes")
        for object_id, value in ((text_boxes[0], title), (text_boxes[1], body)):
            requests.append({"deleteText": {"objectId": object_id, "textRange": {"type": "ALL"}}})
            requests.append({"insertText": {"objectId": object_id, "text": value}})
    slides.presentations().batchUpdate(presentationId=presentation_id, body={"requests": requests}).execute()

def main() -> int:
    parser = argparse.ArgumentParser(description="Seed, reset, or remove the reference Chief of Staff workspace")
    parser.add_argument("--week-of", help="Monday date (YYYY-MM-DD); defaults to the current week")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument("--confirm", action="store_true", help="Required because this writes to Google Workspace")
    args = parser.parse_args()
    if not args.confirm:
        raise SystemExit("Refusing Google Workspace writes without --confirm")
    path = state_path()
    if args.cleanup:
        if not path.exists(): raise SystemExit(f"No workspace state at {path}")
        cleanup(json.loads(path.read_text(encoding="utf-8")))
        path.unlink(missing_ok=True)
        print(json.dumps({"ok": True, "status": "removed"}))
        return 0
    chosen_week = date.fromisoformat(args.week_of) if args.week_of else week_monday(local_now().date())
    if args.reset:
        if not path.exists(): raise SystemExit(f"No workspace state at {path}")
        previous = json.loads(path.read_text(encoding="utf-8"))
        chosen_week = date.fromisoformat(args.week_of or previous["week_of"])
        check_reset(ROOT, hermes_home())
        state = reset_in_place(previous, chosen_week)
        second_brain = reset_second_brain(ROOT, hermes_home())
        print(json.dumps({"ok": True, "status": "reset", "state": str(path), "week_of": state["week_of"], "folder": state["folder"], "sheet": state["sheet"], "doc": state["doc"], "slides": state["slides"], "emails": len(state["emails"]), "events": len(state["events"]), "tasks": len(state.get("tasks", [])), "second_brain": second_brain}, indent=2))
        return 0
    elif path.exists():
        raise SystemExit(f"Workspace already exists. Run reset or cleanup first: {path}")
    state = seed(chosen_week)
    print(json.dumps({"ok": True, "state": str(path), "week_of": state["week_of"], "folder": state["folder"], "sheet": state["sheet"], "doc": state["doc"], "slides": state["slides"], "emails": len(state["emails"]), "events": len(state["events"]), "tasks": len(state.get("tasks", []))}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
