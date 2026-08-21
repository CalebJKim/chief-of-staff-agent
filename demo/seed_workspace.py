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


def create_doc(docs, drive, folder_id: str) -> dict:
    result = docs.documents().create(body={"title": "RTX Spark Campaign Plan"}).execute()
    doc_id = result["documentId"]
    text = (
        "RTX Spark Campaign Plan\n\n"
        "Campaign objective\n"
        "Make RTX Spark the clearest example of useful local AI agents: fast, private, efficient, and ready for real work.\n\n"
        "Narrative\n"
        "Lead with agents and user outcomes. Use specifications and approved performance claims as evidence, not as the opening story.\n\n"
        "Workstreams\n"
        "1. Executive storyline and IFA keynote structure\n"
        "2. Inference performance claims and legal qualification\n"
        "3. Exec Review deck and Agent Messaging consistency\n"
        "4. IFA demo slate, owners, and partner commitments\n"
        "5. Marketing shoot venue, storyboard, budget, and crew hold\n"
        "6. Local AI Summit demo QA and AV readiness\n\n"
        "Current decisions\n"
        "- Approve the agent-first keynote storyline\n"
        "- Align on IFA demos and owners\n"
        "- Choose a replacement marketing shoot date\n"
        "- Assign the retail demo owner\n\n"
        "Operating rule\n"
        "Do not propagate provisional performance language. Once Product and Legal approve the wording, update slide 4, Agent Messaging, and dependent campaign surfaces without drift.\n"
    )
    docs.documents().batchUpdate(documentId=doc_id, body={"requests": [{"insertText": {"location": {"index": 1}, "text": text}}]}).execute()
    move_to_folder(drive, doc_id, folder_id)
    return {"id": doc_id, "url": f"https://docs.google.com/document/d/{doc_id}/edit"}


SLIDES = [
    ("RTX Spark\nExec Review", "Campaign plan\nDecision-ready working deck"),
    ("Lead with the agent", "THE PROMISE\nUseful AI coworkers running locally\n\nTHE PROOF\nPerformance, privacy, and readiness support that promise\n\nTHE ASK\nApprove the agent-first keynote storyline"),
    ("Campaign state at a glance", "8 ACTIVE LANES\n4 awaiting updates • 2 blocked\n\nATTENTION TODAY\nClaims approval • Exec deck • Marketing shoot date"),
    ("Inference performance — update required", "Performance to go here - Mike Chen to provide\n\nOWNER\nMike Chen / Marketing"),
    ("One claim across every surface", "IFA DECK\nAgent Messaging • Campaign plan • Creative assets\n\nDECISION GATE\nApprove wording and disclaimer once, then propagate without drift.\n\nCONTROL\nDo not invent, extrapolate, or preserve superseded multipliers."),
    ("Move the detail out of the live flow", "RECOMMENDATION\nCut this standalone detail slide from the live presentation.\n\nWHY\nIt duplicates the storyline and delays the decisions.\n\nUSE\nKeep supporting detail in the appendix or presenter notes; carry the essential point into slide 7."),
    ("IFA demos — alignment needed", "DECISION\nAlign on the demo slate that best proves the agent-first story.\n\nKNOWN\nThe event brief requires this decision.\n\nOPEN\nConfirm the proposed demos and owners before final review."),
    ("Execution dependencies", "CLAIMS\nApproval unlocks deck, messaging, and creative updates\n\nOWNERS\nTwo campaign lanes still need current PIC updates\n\nPARTNERS\nCommitments must map back to the approved keynote and demo decisions"),
    ("Marketing shoot — decision required", "BLOCKER\nThe planned venue is unavailable.\n\nDECISION\nChoose a replacement shoot date.\n\nIMPACT\nPriya cannot rebook the venue or protect downstream crew holds until the date is set."),
    ("Two decisions to leave with", "1  APPROVE THE PROPOSED KEYNOTE STORYLINE\nLead with agents; use specifications as evidence.\n\n2  ALIGN ON THE DEMOS FOR IFA\nConfirm the slate and owners that prove the story.\n\nWorking files\nCampaign tracker • Campaign plan"),
]


def create_slides(slides, drive, folder_id: str) -> dict:
    result = slides.presentations().create(body={"title": "RTX Spark Exec Review"}).execute()
    presentation_id = result["presentationId"]
    requests = []
    if result.get("slides"):
        requests.append({"deleteObject": {"objectId": result["slides"][0]["objectId"]}})
    for index, (title, body) in enumerate(SLIDES, 1):
        slide_id = f"rtx_slide_{index}"
        title_id = f"rtx_title_{index}"
        body_id = f"rtx_body_{index}"
        requests.extend([
            {"createSlide": {"objectId": slide_id, "slideLayoutReference": {"predefinedLayout": "BLANK"}}},
            {"createShape": {"objectId": title_id, "shapeType": "TEXT_BOX", "elementProperties": {"pageObjectId": slide_id, "size": {"width": {"magnitude": 620, "unit": "PT"}, "height": {"magnitude": 90, "unit": "PT"}}, "transform": {"scaleX": 1, "scaleY": 1, "translateX": 45, "translateY": 35, "unit": "PT"}}}},
            {"insertText": {"objectId": title_id, "text": title}},
            {"updateTextStyle": {"objectId": title_id, "style": {"fontSize": {"magnitude": 26, "unit": "PT"}, "bold": True, "foregroundColor": {"opaqueColor": {"rgbColor": {"red": 0.12, "green": 0.20, "blue": 0.32}}}}, "textRange": {"type": "ALL"}, "fields": "fontSize,bold,foregroundColor"}},
            {"createShape": {"objectId": body_id, "shapeType": "TEXT_BOX", "elementProperties": {"pageObjectId": slide_id, "size": {"width": {"magnitude": 620, "unit": "PT"}, "height": {"magnitude": 280, "unit": "PT"}}, "transform": {"scaleX": 1, "scaleY": 1, "translateX": 50, "translateY": 145, "unit": "PT"}}}},
            {"insertText": {"objectId": body_id, "text": body}},
            {"updateTextStyle": {"objectId": body_id, "style": {"fontSize": {"magnitude": 16, "unit": "PT"}, "foregroundColor": {"opaqueColor": {"rgbColor": {"red": 0.18, "green": 0.22, "blue": 0.28}}}}, "textRange": {"type": "ALL"}, "fields": "fontSize,foregroundColor"}},
        ])
    slides.presentations().batchUpdate(presentationId=presentation_id, body={"requests": requests}).execute()
    move_to_folder(drive, presentation_id, folder_id)
    return {"id": presentation_id, "url": f"https://docs.google.com/presentation/d/{presentation_id}/edit"}


def tracker_rows(slides_url: str, doc_url: str, sheet_url: str, evidence: dict[str, str]) -> list[list[str]]:
    return [
        ["Lane", "PIC", "Status", "Latest update", "Next action", "Due", "Dependency / blocker", "Evidence", "Artifact", "Notes"],
        ["Product performance claims", "Mike Chen", "Awaiting update", "Performance validation is still pending; the tracker does not yet contain approved inference figures.", "Get Mike’s approved performance package, then update slide 4 and dependent campaign copy.", "", "Awaiting approved Product performance evidence.", "Pending Product confirmation", slides_url, "Required qualification must accompany all figures."],
        ["Exec Review deck", "Elena Park", "Awaiting update", "The Exec Review deck still uses provisional performance language and has not incorporated the latest review notes.", "Apply approved numbers when received; reconcile slide 6, slide 7, and slide 10 feedback before the Exec Review.", "", "Blocked on approved figures and final review direction.", "Pending Mike and Aisha updates", slides_url, "Two decisions: keynote storyline and IFA demos/owners."],
        ["Agent Messaging", "Workspace Owner", "Awaiting update", "Agent Messaging still carries provisional performance wording and is waiting on the approved claims package.", "Replace provisional wording after Product confirmation and align it exactly with slide 4.", "", "Awaiting approved performance wording and qualification.", "Pending Product / Legal confirmation", doc_url, "Lead with agents; use specifications as proof."],
        ["Marketing shoot", "Priya Nair", "Blocked", "The planned venue is unavailable. Northstar is holding Studio B Friday and Studio C Tuesday until 4:30 PM.", "Choose Studio B Friday or Studio C Tuesday before the hold expires.", "", "Executive replacement-date decision; venue and preferred crew will be released without it.", evidence.get("priya", "Priya update"), sheet_url, "Missing the hold risks a campaign slip."],
        ["Partner enablement", "Aisha Rahman", "On track", "The VP requested a review of the partner slides, and the staged Windows pilot passed its smoke check and is ready for an inclusion decision.", "Review the partner section and decide whether the pilot belongs in the demo.", "", "Keynote and IFA demo-owner decisions remain open.", "Partner review evidence", slides_url, "Production inclusion is not yet approved."],
        ["Social rollout", "Rafael Costa", "Awaiting update", "No current status has been received.", "Request asset readiness, timing, and blockers from Rafael.", "", "PIC status", "Email / Slack", "", "Follow-up draft needed."],
        ["Retail demo readiness", "Grant Walker", "Blocked", "Aisha confirmed that the retail demo lane still has no final owner, so the IFA demo slate cannot be presented as closed.", "Assign the final retail demo owner and confirm coverage during the Exec Review.", "", "Final retail demo owner is unassigned.", evidence.get("aisha", "Aisha update"), slides_url, "No direct current update from Grant was received."],
        ["Legal intake LGL-2026-0847", "Daniel Cho", "Awaiting update", "Legal intake is open and the tracker has no recorded clearance for the performance wording.", "Confirm Daniel’s clearance and record the required qualification before campaign-wide propagation.", "", "Awaiting legal confirmation of wording and disclaimer.", "Pending Daniel / Product evidence", sheet_url, "Leadership review and external-copy clearance may differ."],
    ]


def create_sheet(sheets, drive, folder_id: str, slides_url: str, doc_url: str) -> dict:
    result = sheets.spreadsheets().create(body={"properties": {"title": "RTX Spark Campaign Tracker"}, "sheets": [{"properties": {"title": "Campaign Lanes", "gridProperties": {"rowCount": 100, "columnCount": 12, "frozenRowCount": 6, "hideGridlines": True}}}]}).execute()
    spreadsheet_id = result["spreadsheetId"]
    sheet_id = result["sheets"][0]["properties"]["sheetId"]
    sheet_url = result.get("spreadsheetUrl", f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit")
    rows = [["RTX Spark Campaign Tracker"], ["Decision-ready view of campaign execution"], ["Awaiting updates", "4", "", "Blocked", "2", "", "Active lanes", "8", "Last refreshed", local_now().date().isoformat()], ["Statuses are updated from current owner evidence; use the Artifact column to open the working file or decision source."], [], *tracker_rows(slides_url, doc_url, sheet_url, {})]
    sheets.spreadsheets().values().update(spreadsheetId=spreadsheet_id, range="'Campaign Lanes'!A1:J14", valueInputOption="USER_ENTERED", body={"values": rows}).execute()
    requests = [
        {"mergeCells": {"range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 10}, "mergeType": "MERGE_ALL"}},
        {"mergeCells": {"range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 2, "startColumnIndex": 0, "endColumnIndex": 10}, "mergeType": "MERGE_ALL"}},
        {"mergeCells": {"range": {"sheetId": sheet_id, "startRowIndex": 3, "endRowIndex": 4, "startColumnIndex": 0, "endColumnIndex": 10}, "mergeType": "MERGE_ALL"}},
        {"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 10}, "cell": {"userEnteredFormat": {"backgroundColor": {"red": 0.10, "green": 0.18, "blue": 0.30}, "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "fontSize": 18, "bold": True}, "verticalAlignment": "MIDDLE"}}, "fields": "userEnteredFormat"}},
        {"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": 5, "endRowIndex": 6, "startColumnIndex": 0, "endColumnIndex": 10}, "cell": {"userEnteredFormat": {"backgroundColor": {"red": 0.20, "green": 0.35, "blue": 0.55}, "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True}, "wrapStrategy": "WRAP"}}, "fields": "userEnteredFormat"}},
        {"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": 6, "endRowIndex": 14, "startColumnIndex": 0, "endColumnIndex": 10}, "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP", "verticalAlignment": "TOP"}}, "fields": "userEnteredFormat.wrapStrategy,userEnteredFormat.verticalAlignment"}},
        {"setDataValidation": {"range": {"sheetId": sheet_id, "startRowIndex": 6, "endRowIndex": 14, "startColumnIndex": 2, "endColumnIndex": 3}, "rule": {"condition": {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": value} for value in STATUS_VALUES]}, "strict": True, "showCustomUi": True}}},
        {"updateDimensionProperties": {"range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 10}, "properties": {"pixelSize": 170}, "fields": "pixelSize"}},
    ]
    sheets.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={"requests": requests}).execute()
    move_to_folder(drive, spreadsheet_id, folder_id)
    return {"id": spreadsheet_id, "url": sheet_url, "sheet_id": sheet_id}


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
    ("08:30", "09:15", "Campaign leadership pre-wire", "Review decisions, owners, and likely leadership objections."),
    ("08:30", "09:30", "Keynote speaker risk review", "Final speaker lineup, alternates, and outreach required before print."),
    ("09:00", "10:00", "Finalize IFA four-talk keynote structure", "Finish the cut from six talks to four and align the speaker sequence with the agent-first narrative."),
    ("09:15", "10:00", "IFA campaign PMO stand-up", "Critical path, blocked decisions, partner commitments, creative status, and print readiness."),
    ("09:15", "09:45", "Marketing PMO stand-up", "Critical path, blockers, creative status, and partner commitments."),
    ("10:00", "10:45", "Creative / claims escalation", "Resolve hero claim, disclaimer, stage-banner resize, and old-UI screenshot."),
    ("10:30", "11:30", "Resolve RTX Spark creative comments", "Update the hero claim, resize the stage banner, and replace the old screenshot."),
    ("12:00", "13:00", "Working lunch — agent-first narrative", "Stress-test the agent-first story and decide which specifications support the narrative."),
    ("13:00", "14:00", "Assign Local AI Summit demo QA DRI", "Name the QA DRI in the tracker and document blockers and owners."),
    ("13:30", "14:30", "Local AI Summit demo QA producer sync", "QA DRI, three-station script, blockers, and AV dependencies."),
    ("14:00", "15:00", "Partner enablement review", "Partner commitments, demo inclusion, owners, and launch materials."),
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


def update_tracker_evidence(sheets, state: dict, evidence: dict[str, str]) -> None:
    sheet = state["sheet"]
    values = tracker_rows(state["slides"]["url"], state["doc"]["url"], sheet["url"], evidence)
    sheets.spreadsheets().values().update(spreadsheetId=sheet["id"], range="'Campaign Lanes'!A6:J14", valueInputOption="USER_ENTERED", body={"values": values}).execute()


def resource_is_already_absent(exc: Exception) -> bool:
    return getattr(getattr(exc, "resp", None), "status", None) in {404, 410}


def cleanup(state: dict) -> dict[str, int]:
    svc = services()
    result = {"drafts_deleted": 0, "emails_trashed": 0, "events_deleted": 0, "folders_trashed": 0}
    failures = []
    for item in state.get("drafts", []):
        try:
            svc["gmail"].users().drafts().delete(userId="me", id=item["id"]).execute()
            result["drafts_deleted"] += 1
        except Exception as exc:
            if resource_is_already_absent(exc):
                result["drafts_deleted"] += 1
            else:
                failures.append(f"Gmail draft {item['id']}: {exc}")
    for item in state.get("emails", []):
        try:
            svc["gmail"].users().messages().trash(userId="me", id=item["id"]).execute()
            result["emails_trashed"] += 1
        except Exception as exc:
            if resource_is_already_absent(exc):
                result["emails_trashed"] += 1
            else:
                failures.append(f"email {item['id']}: {exc}")
    for item in state.get("events", []):
        try:
            svc["calendar"].events().delete(calendarId="primary", eventId=item["id"], sendUpdates="none").execute()
            result["events_deleted"] += 1
        except Exception as exc:
            if resource_is_already_absent(exc):
                result["events_deleted"] += 1
            else:
                failures.append(f"calendar event {item['id']}: {exc}")
    if state.get("folder", {}).get("id"):
        try:
            svc["drive"].files().update(fileId=state["folder"]["id"], body={"trashed": True}).execute()
            result["folders_trashed"] += 1
        except Exception as exc:
            if resource_is_already_absent(exc):
                result["folders_trashed"] += 1
            else:
                failures.append(f"Drive folder {state['folder']['id']}: {exc}")
    if failures:
        raise RuntimeError("Cleanup incomplete:\n" + "\n".join(failures))
    return result


def seed(week_of: date) -> dict:
    svc = services()
    state = {"schema": 2, "marker": MARKER, "week_of": week_of.isoformat(), "events": [], "emails": [], "drafts": []}
    try:
        state["folder"] = create_folder(svc["drive"])
        state["doc"] = create_doc(svc["docs"], svc["drive"], state["folder"]["id"])
        state["slides"] = create_slides(svc["slides"], svc["drive"], state["folder"]["id"])
        state["sheet"] = create_sheet(svc["sheets"], svc["drive"], state["folder"]["id"], state["slides"]["url"], state["doc"]["url"])
        state["emails"], evidence = create_emails(svc["gmail"], state["slides"]["url"], state["sheet"]["url"], state["doc"]["url"])
        update_tracker_evidence(svc["sheets"], state, evidence)
        state["events"] = create_calendar(svc["calendar"], week_of, state["slides"]["url"], state["doc"]["url"], state["sheet"]["url"])
        state_path().parent.mkdir(parents=True, exist_ok=True)
        state_path().write_text(json.dumps(state, indent=2), encoding="utf-8")
        return state
    except Exception:
        try:
            cleanup(state)
        except Exception as cleanup_error:
            state_path().parent.mkdir(parents=True, exist_ok=True)
            state_path().write_text(json.dumps(state, indent=2), encoding="utf-8")
            print(f"WARNING: Automatic rollback was incomplete: {cleanup_error}", file=sys.stderr)
            print(f"Cleanup state saved to {state_path()}", file=sys.stderr)
        raise


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
        cleanup_result = cleanup(json.loads(path.read_text(encoding="utf-8")))
        path.unlink(missing_ok=True)
        print(json.dumps({"ok": True, "status": "removed", **cleanup_result}))
        return 0
    chosen_week = date.fromisoformat(args.week_of) if args.week_of else week_monday(local_now().date())
    if args.reset:
        if not path.exists(): raise SystemExit(f"No workspace state at {path}")
        previous = json.loads(path.read_text(encoding="utf-8"))
        chosen_week = date.fromisoformat(args.week_of or previous["week_of"])
        cleanup(previous)
        path.unlink(missing_ok=True)
    elif path.exists():
        raise SystemExit(f"Workspace already exists. Run reset or cleanup first: {path}")
    state = seed(chosen_week)
    print(json.dumps({"ok": True, "state": str(path), "week_of": state["week_of"], "folder": state["folder"], "sheet": state["sheet"], "doc": state["doc"], "slides": state["slides"], "emails": len(state["emails"]), "events": len(state["events"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
