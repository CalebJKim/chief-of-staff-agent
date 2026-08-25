#!/usr/bin/env python
"""Create, reset, or remove the reference Chief of Staff Google Workspace."""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "productivity" / "ingest" / "scripts"))
from actions import credentials  # noqa: E402
from baseline import reset_sheet_baseline  # noqa: E402
from googleapiclient.discovery import build  # noqa: E402

MARKER = "chief-of-staff-reference-workspace-v1"
STATE_FILE = "chief-of-staff-workspace-state.json"
TZ_NAME = os.environ.get("CHIEF_OF_STAFF_WORKSPACE_TZ", "America/Los_Angeles")
STATUS_VALUES = ["On track", "In review", "Awaiting update", "Blocked", "Complete"]


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


def services():
    creds = credentials()
    return {
        "drive": build("drive", "v3", credentials=creds, cache_discovery=False),
        "docs": build("docs", "v1", credentials=creds, cache_discovery=False),
        "sheets": build("sheets", "v4", credentials=creds, cache_discovery=False),
        "slides": build("slides", "v1", credentials=creds, cache_discovery=False),
        "calendar": build("calendar", "v3", credentials=creds, cache_discovery=False),
        "gmail": build("gmail", "v1", credentials=creds, cache_discovery=False),
    }


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
def create_slides(drive, folder_id): return upload_template(drive, folder_id, "rtx-spark-exec-review.pptx", "RTX Spark Exec Review", "application/vnd.google-apps.presentation")
def create_sheet(drive, folder_id): return upload_template(drive, folder_id, "rtx-spark-campaign-tracker.xlsx", "RTX Spark Campaign Tracker", "application/vnd.google-apps.spreadsheet")

def import_mail(gmail, account: str, sender: str, subject: str, body: str, index: int) -> dict:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = account
    message["Subject"] = subject
    message["Date"] = format_datetime(datetime.now().astimezone())
    message["Message-ID"] = f"<{MARKER}-{index}@nvidia.example>"
    message.set_content(body + f"\n\n[{MARKER}]")
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    result = gmail.users().messages().import_(userId="me", body={"raw": raw, "labelIds": ["INBOX", "UNREAD", "IMPORTANT"]}, internalDateSource="dateHeader", neverMarkSpam=True, processForCalendar=False).execute()
    return {"id": result["id"], "thread_id": result.get("threadId", result["id"]), "url": f"https://mail.google.com/mail/u/0/#all/{result.get('threadId', result['id'])}"}


def create_emails(gmail, deck_url: str, sheet_url: str, doc_url: str) -> tuple[list[dict], dict[str, str]]:
    account = gmail.users().getProfile(userId="me").execute()["emailAddress"]
    data = [
        ("Elena Park <elena.park@nvidia.example>", "URGENT: RTX Spark Exec Review moved to 5 PM today", f"Hi,\n\nLeadership moved the RTX Spark Exec Review from Thursday to 5:00 PM today. This is the decision meeting, not a working session. Please arrive ready to close the agent-first keynote storyline and the IFA demo slate/owners.\n\nThe optional launch storyboard session is 3:00–4:00 PM; skip it if you need time to finish the Agent Security PRD and prep the deck.\n\nDeck: {deck_url}\n\n— Elena"),
        ("Mike Chen <mike.chen@nvidia.example>", "APPROVED: RTX Spark inference numbers for slide 4", "The performance package is approved for today's Exec Review. Use exactly: 2.1x faster time-to-first-token versus the prior approved release; 38 tokens/second sustained on the fixed 35B workflow; 22% lower energy per completed workflow. Required footnote: Pre-production measurements on the RTX Spark reference configuration. Results vary by model, quantization, and workload. Daniel cleared this wording for leadership review."),
        ("Aisha Rahman <aisha.rahman@nvidia.example>", "Exec Review deck pass: cut slide 6; protect slide 10", f"I finished the deck pass. Cut slide 6 from the live flow, carry its essential point into slide 7, and use the saved time on slide 10. Slide 10 needs room for two decisions: approve the agent-first keynote storyline and align on the IFA demos and owners. Mike's approved numbers belong on slide 4. The retail demo owner is still unassigned.\n\nDeck: {deck_url}"),
        ("Daniel Cho <daniel.cho@nvidia.example>", "Legal scope: RTX Spark wording cleared for leadership review", "The RTX Spark performance wording and pre-production qualification are cleared for today's leadership review. This is not blanket campaign-wide approval; keep the qualification intact and route final external copy through Legal."),
        ("Priya Nair <priya.nair@northstarcreative.example>", "Decision by 4:30 PM today: marketing shoot venue hold", f"The planned venue is unavailable. We can hold Studio B Friday or Studio C Tuesday, with the preferred crew, until 4:30 PM today. Choose one before the hold expires or we risk a campaign slip.\n\nTracker: {sheet_url}"),
        ("Elena Park <elena.park@nvidia.example>", "Agent Security PRD needs to reach Engineering today", f"Please finish and send the Agent Security PRD to Engineering today. Protect a focused hour for the final pass. You can skip the optional launch storyboard session; notes will be posted afterward.\n\nCampaign plan: {doc_url}"),
    ]
    created = [import_mail(gmail, account, *item, index) for index, item in enumerate(data, 1)]
    evidence = {"elena": created[0]["url"], "mike": created[1]["url"], "aisha": created[2]["url"], "daniel": created[3]["url"], "priya": created[4]["url"], "prd": created[5]["url"]}
    return created, evidence


EVENTS = [
    ("08:00", "08:25", "Chief of Staff daily priorities", "Overnight changes, today's decision calendar, stakeholder risks, and executive air cover."),
    ("08:30", "09:30", "Keynote speaker risk review", "Final speaker lineup, alternates, and outreach required before print."),
    ("09:00", "10:00", "Finalize IFA four-talk keynote structure", "Finish the cut from six talks to four and align the speaker sequence with the agent-first narrative."),
    ("09:15", "10:00", "IFA campaign PMO stand-up", "Critical path, blocked decisions, partner commitments, creative status, and print readiness."),
    ("10:00", "10:45", "Creative / claims escalation", "Resolve hero claim, disclaimer, stage-banner resize, and old-UI screenshot."),
    ("10:30", "11:30", "Resolve RTX Spark creative comments", "Update the hero claim, resize the stage banner, and replace the old screenshot."),
    ("12:00", "13:00", "Working lunch — agent-first narrative", "Stress-test the agent-first story and decide which specifications support the narrative."),
    ("13:00", "14:00", "Assign Local AI Summit demo QA DRI", "Name the QA DRI in the tracker and document blockers and owners."),
    ("13:30", "14:30", "Local AI Summit demo QA producer sync", "QA DRI, three-station script, blockers, and AV dependencies."),
    ("15:00", "16:00", "Local AI Summit demo and AV readiness review", "Review the demo plan, AV confirmation, QA status, and blockers."),
    ("15:00", "16:00", "Launch storyboard working session — notes available", "Optional working session; notes will be posted afterward."),
    ("15:30", "16:30", "Launch video agency review — Northstar", "Storyboard feedback, production plan, budget scenarios, and crew-hold risk."),
    ("16:00", "17:00", "Executive prep — print handoff", "Prepare the decision and risk brief: speakers, claims, partners, legal status, and owners."),
    ("17:00", "17:45", "RTX Spark Exec Review — leadership decisions", "Decision meeting: approve the agent-first keynote storyline and align on IFA demos and owners."),
    ("17:00", "17:30", "Decision follow-up triage", "Send decision notes, chase unresolved owners, and update the escalation list."),
    ("18:00", "18:45", "APAC executive handoff — decisions and risks", "Close the day with decisions, unresolved risks, and tomorrow's critical path."),
]


def create_calendar(calendar, start_day: date, deck_url: str, doc_url: str, sheet_url: str) -> list[dict]:
    created = []
    for offset in range(5):
        day = start_day + timedelta(days=offset)
        for begin, end, title, description in EVENTS:
            link = f"\nDeck: {deck_url}" if title.startswith("RTX Spark Exec Review") else f"\nNotes: {doc_url}" if title.startswith("Launch storyboard") else f"\nTracker: {sheet_url}" if "DRI" in title else ""
            result = calendar.events().insert(calendarId="primary", body={"summary": title, "description": f"{description}{link}\n[{MARKER}]", "start": {"dateTime": iso(day, begin), "timeZone": TZ_NAME}, "end": {"dateTime": iso(day, end), "timeZone": TZ_NAME}}, sendUpdates="none").execute()
            created.append({"id": result["id"], "url": result.get("htmlLink", "")})
    return created


def remove_dynamic_items(state: dict, svc: dict) -> None:
    try:
        found = svc["gmail"].users().messages().list(userId="me", q=f"{MARKER}", maxResults=500).execute().get("messages", [])
    except Exception:
        found = []
    email_ids = {item.get("id") for item in state.get("emails", [])} | {item.get("id") for item in found}
    for message_id in email_ids:
        if not message_id: continue
        try: svc["gmail"].users().messages().delete(userId="me", id=message_id).execute()
        except Exception: pass
    for item in []:
        try: svc["gmail"].users().messages().delete(userId="me", id=item["id"]).execute()
        except Exception: pass
    try:
        start = state.get("week_of") + "T00:00:00" + utc_offset()
        end = (date.fromisoformat(state.get("week_of")) + timedelta(days=5)).isoformat() + "T00:00:00" + utc_offset()
        found_events = svc["calendar"].events().list(calendarId="primary", timeMin=start, timeMax=end, singleEvents=True, maxResults=2500).execute().get("items", [])
    except Exception:
        found_events = []
    event_ids = {item.get("id") for item in state.get("events", [])} | {item.get("id") for item in found_events if MARKER in (item.get("description") or "")}
    for event_id in event_ids:
        if not event_id: continue
        try: svc["calendar"].events().delete(calendarId="primary", eventId=event_id, sendUpdates="none").execute()
        except Exception: pass


def cleanup(state: dict) -> None:
    svc = services()
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
        state["sheet"] = create_sheet(svc["drive"], state["folder"]["id"])
        state["emails"], evidence = create_emails(svc["gmail"], state["slides"]["url"], state["sheet"]["url"], state["doc"]["url"])
        reset_sheet_baseline(svc["sheets"], state, evidence, local_now().date().isoformat())
        state["events"] = create_calendar(svc["calendar"], week_of, state["slides"]["url"], state["doc"]["url"], state["sheet"]["url"])
        state_path().parent.mkdir(parents=True, exist_ok=True)
        state_path().write_text(json.dumps(state, indent=2), encoding="utf-8")
        return state
    except Exception:
        cleanup(state)
        raise


def reset_in_place(state: dict, week_of: date) -> dict:
    svc = services()
    remove_dynamic_items(state, svc)
    state["emails"], evidence = create_emails(svc["gmail"], state["slides"]["url"], state["sheet"]["url"], state["doc"]["url"])
    reset_sheet_baseline(svc["sheets"], state, evidence, local_now().date().isoformat())
    reset_deck_baseline(svc["slides"], state["slides"]["id"])
    state["events"] = create_calendar(svc["calendar"], week_of, state["slides"]["url"], state["doc"]["url"], state["sheet"]["url"])
    state["week_of"] = week_of.isoformat()
    state_path().write_text(json.dumps(state, indent=2), encoding="utf-8")
    return state


def reset_deck_baseline(slides, presentation_id: str) -> None:
    presentation = slides.presentations().get(presentationId=presentation_id).execute()
    wanted = {
        4: ("Inference performance — update required", """Performance to go here - Mike Chen to provide

OWNER
Mike Chen / Marketing"""),
        7: ("IFA demos — alignment needed", """DECISION
Align on the demo slate that best proves the agent-first story.

KNOWN
The event brief requires this decision.

OPEN
Current project notes do not name an approved demo list; confirm the proposed demos and owners before final review."""),
        9: ("Marketing shoot — decision required", """BLOCKER
The planned venue is unavailable.

DECISION
Choose a replacement shoot date.

IMPACT
Priya cannot rebook the venue or protect downstream crew holds until the date is set."""),
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
        state = reset_in_place(previous, chosen_week)
        print(json.dumps({"ok": True, "status": "reset", "state": str(path), "week_of": state["week_of"], "folder": state["folder"], "sheet": state["sheet"], "doc": state["doc"], "slides": state["slides"], "emails": len(state["emails"]), "events": len(state["events"])}, indent=2))
        return 0
    elif path.exists():
        raise SystemExit(f"Workspace already exists. Run reset or cleanup first: {path}")
    state = seed(chosen_week)
    print(json.dumps({"ok": True, "state": str(path), "week_of": state["week_of"], "folder": state["folder"], "sheet": state["sheet"], "doc": state["doc"], "slides": state["slides"], "emails": len(state["emails"]), "events": len(state["events"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
