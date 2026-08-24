#!/usr/bin/env python
"""Create, reset, or remove the reference Chief of Staff Google Workspace."""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import uuid
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
STATUS_VALUES = ["Not started", "In progress", "Ready for review", "On track", "In review", "Awaiting update", "Blocked", "Complete"]
STATUS_STYLES = {
    "Not started": ({"red": 0.91, "green": 0.93, "blue": 0.95}, {"red": 0.28, "green": 0.32, "blue": 0.38}),
    "In progress": ({"red": 0.82, "green": 0.90, "blue": 1.00}, {"red": 0.07, "green": 0.27, "blue": 0.52}),
    "Ready for review": ({"red": 0.90, "green": 0.84, "blue": 0.98}, {"red": 0.31, "green": 0.15, "blue": 0.50}),
    "On track": ({"red": 0.82, "green": 0.95, "blue": 0.86}, {"red": 0.06, "green": 0.36, "blue": 0.17}),
    "In review": ({"red": 0.80, "green": 0.94, "blue": 0.94}, {"red": 0.02, "green": 0.35, "blue": 0.37}),
    "Awaiting update": ({"red": 1.00, "green": 0.91, "blue": 0.76}, {"red": 0.51, "green": 0.27, "blue": 0.02}),
    "Blocked": ({"red": 1.00, "green": 0.82, "blue": 0.82}, {"red": 0.58, "green": 0.06, "blue": 0.06}),
    "Complete": ({"red": 0.75, "green": 0.91, "blue": 0.80}, {"red": 0.03, "green": 0.29, "blue": 0.12}),
}
TRACKER_COLUMN_WIDTHS = [220, 145, 145, 290, 330, 100, 250, 220, 170, 250]
SLIDE_THEME = {
    "background": {"red": 0.05, "green": 0.07, "blue": 0.11},
    "surface": {"red": 0.10, "green": 0.13, "blue": 0.19},
    "accent": {"red": 0.48, "green": 0.82, "blue": 0.22},
    "title": {"red": 0.97, "green": 0.98, "blue": 1.00},
    "body": {"red": 0.82, "green": 0.85, "blue": 0.90},
    "muted": {"red": 0.55, "green": 0.60, "blue": 0.68},
}
DOC_THEME = {
    "navy": {"red": 0.10, "green": 0.18, "blue": 0.30},
    "accent": {"red": 0.26, "green": 0.58, "blue": 0.16},
    "body": {"red": 0.20, "green": 0.24, "blue": 0.30},
    "muted": {"red": 0.40, "green": 0.45, "blue": 0.52},
    "success_fill": {"red": 0.88, "green": 0.96, "blue": 0.89},
    "action_fill": {"red": 0.91, "green": 0.95, "blue": 1.00},
}
MEANINGFUL_EMAIL_COUNT = 6
BACKGROUND_EMAIL_COUNT = 70
EMAIL_REFERENCE_HOUR = 13
EMAIL_SPACING_MINUTES = 2
API_BATCH_SIZE = 25
GMAIL_BATCH_SIZE = 20
CALENDAR_BATCH_SIZE = 5
API_BATCH_ATTEMPTS = 4
API_REQUEST_ATTEMPTS = 4

BACKGROUND_FIRST_NAMES = [
    "Maya", "Owen", "Sofia", "Liam", "Nora",
    "Ethan", "Chloe", "Mateo", "Iris", "Jonah",
]
BACKGROUND_LAST_NAMES = [
    "Bennett", "Foster", "Kimura", "Okafor", "Santos",
    "Dubois", "Mehta", "Novak", "Silva", "Tan",
]
BACKGROUND_DOMAINS = ["community.example", "office.example", "clubs.example", "bulletin.example"]
BACKGROUND_TOPICS = [
    ("Friday cafeteria menu", "Sharing the cafe menu for anyone who is curious. No response is needed."),
    ("Photos from the summer picnic", "The picnic photo album is available for casual browsing. No response is needed."),
    ("September book club selection", "The group chose a light mystery for September. Participation is entirely optional."),
    ("Office plant corner highlights", "A few new plants are now in the third-floor common area. This is simply a cheerful note."),
    ("Cycling group weekend photos", "Here are a few snapshots from the weekend ride. No response is needed."),
    ("Recording from the lunchtime history talk", "The recording is available for anyone interested in the topic. Nothing is expected from recipients."),
    ("New art in the third-floor hallway", "The hallway display now features work from local artists. This is informational only."),
    ("Recipe exchange favorites", "The recipe exchange collected several popular dishes this month. Enjoy them whenever convenient."),
    ("Volunteer day photo album", "The volunteer group shared a photo album from its recent outing. No response is needed."),
    ("Coffee tasting notes", "The coffee club posted tasting notes from its latest gathering. This is just for fun."),
    ("Neighborhood walking routes", "A few pleasant walking routes near the office are collected here for optional use."),
    ("Puzzle club results", "The puzzle club posted last week's results and a few favorite clues. Nothing is expected from recipients."),
    ("Common-room music playlist", "A new common-room playlist is available for anyone who would like background music."),
    ("Community garden harvest photos", "The garden group shared photos from this season's harvest. No response is needed."),
    ("Museum lecture recording", "A recording of the museum lecture is available for optional viewing."),
    ("Quiet workspace design ideas", "Here are several pleasant examples of quiet workspace design for casual inspiration."),
    ("Weekend hiking snapshots", "The hiking group shared a small set of trail photos. No response is needed."),
    ("Language circle phrase list", "The language circle collected favorite phrases from its last gathering for anyone interested."),
    ("Cafeteria chef profile", "This month's short chef profile is available for casual reading."),
    ("August film club favorites", "The film club collected its favorite titles from August. Participation is entirely optional."),
    ("Rooftop herb garden photos", "The rooftop garden group shared photos of this season's herbs for casual browsing."),
    ("Local bakery recommendations", "A few favorite neighborhood bakeries are collected here for anyone interested."),
    ("Commuter train photography album", "The photography group shared a small album from recent train rides. No response is needed."),
    ("Desk organization inspiration", "Here are several tidy desk arrangements for casual inspiration."),
    ("Favorite instrumental playlists", "A few instrumental playlists are available for anyone who enjoys background music."),
    ("Public park picnic spots", "The social group collected several pleasant public picnic spots for optional use."),
    ("Origami circle creations", "The origami circle shared photos from its latest gathering. Nothing is expected from recipients."),
    ("Seasonal fruit guide", "A short guide to seasonal fruit is available for casual reading."),
    ("Birdwatching sightings near campus", "The birdwatching group shared a few recent sightings near campus."),
    ("Weekend pottery class photos", "The pottery class shared photos of recent pieces. No response is needed."),
    ("Community choir recordings", "A few community choir recordings are available for optional listening."),
    ("Library reading nook photos", "The library group shared several cozy reading nooks for casual inspiration."),
    ("Homemade bread recipes", "The cooking circle collected a few favorite homemade bread recipes."),
    ("Office aquarium snapshots", "A few new aquarium snapshots are available for anyone curious about the common area."),
    ("Walking club trail map", "The walking club collected a simple map of nearby trails for optional use."),
    ("Street market photo collection", "A small street market photo collection is available for casual browsing."),
    ("Astronomy club sky chart", "The astronomy club shared a simple seasonal sky chart for anyone interested."),
    ("Casual chess puzzle collection", "The chess group collected a few light puzzles for optional enjoyment."),
    ("Tea tasting favorites", "The tea group shared several favorites from its latest gathering."),
    ("Campus architecture photo walk", "Photos from a recent campus architecture walk are available for casual browsing."),
    ("Indoor succulent care tips", "A few simple succulent care tips are collected here for anyone interested."),
    ("Regional food festival photos", "The food club shared photos from a regional festival. No response is needed."),
    ("Public art walking map", "A small map of nearby public art is available for an optional walk."),
    ("Weekend watercolor gallery", "The watercolor group shared a small gallery from its weekend session."),
    ("Vintage poster collection", "A collection of vintage poster images is available for casual browsing."),
    ("Local history trivia", "The history circle collected a few light local trivia questions for fun."),
    ("Nature photography favorites", "The photography group shared several favorite nature images."),
    ("Farmers market seasonal guide", "A brief seasonal guide to the farmers market is available for anyone interested."),
    ("Piano circle recordings", "The piano circle shared a few informal recordings for optional listening."),
    ("Textile craft showcase", "The craft group shared photos of recent textile projects. Nothing is expected from recipients."),
    ("Urban sketching gallery", "The sketching group shared drawings from a recent city walk."),
    ("Picnic recipe collection", "A small collection of picnic recipes is available for casual reading."),
    ("Fountain pen samples", "The stationery group shared several fountain pen writing samples for anyone interested."),
    ("Courtyard gardening photos", "Photos from the courtyard garden are available for casual browsing."),
    ("Beginner stargazing checklist", "A simple beginner stargazing checklist is available for optional use."),
    ("Sandwich recipe exchange", "The lunch group collected a few favorite sandwich recipes."),
    ("Ceramic studio gallery", "The ceramics group shared a gallery of recent pieces. No response is needed."),
    ("Park bench reading list", "A light reading list is available for anyone planning a quiet afternoon outside."),
    ("Rainy day photography", "The photography group shared a few favorite rainy day images."),
    ("Homemade jam flavors", "The recipe circle collected several favorite homemade jam flavors."),
    ("Weekend kayaking photos", "The kayaking group shared photos from a recent outing. No response is needed."),
    ("Classic radio recommendations", "A few classic radio programs are collected here for optional listening."),
    ("Office window sunset photos", "A small set of sunset photos from the office windows is available for casual browsing."),
    ("Botanical illustration gallery", "The art circle shared several botanical illustrations for anyone interested."),
    ("Short fiction reading list", "A short fiction reading list is available for optional reading."),
    ("Neighborhood mural photos", "Photos of neighborhood murals are available for casual browsing."),
    ("Autumn baking ideas", "The cooking circle shared several autumn baking ideas for anyone interested."),
    ("Acoustic guitar playlist", "An acoustic guitar playlist is available for optional background listening."),
    ("Local trail wildflower guide", "A small guide to wildflowers on nearby trails is available for casual use."),
    ("Community craft fair photos", "The community group shared photos from a recent craft fair. Nothing is expected from recipients."),
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


def next_demo_weekday(day: date) -> date:
    """Use the current weekday, or the upcoming Monday on a weekend."""
    if day.weekday() < 5:
        return day
    return day + timedelta(days=7 - day.weekday())


def default_demo_week(day: date) -> date:
    return week_monday(next_demo_weekday(day))


def demo_day_for_week(week_of: date, today: date) -> date:
    resolved_day = next_demo_weekday(today)
    if week_of <= resolved_day <= week_of + timedelta(days=4):
        return resolved_day
    return week_of


def email_reference_time(demo_day: date, now: datetime | None = None) -> datetime:
    """Return a non-future inbox time while preserving the logical demo day.

    On weekends the demo story advances to Monday, but Gmail renders imported
    messages with future Date headers at their common import time. Keep the
    Monday Calendar/Drive story and date the inbox messages on the current day
    instead so Gmail displays their deliberately staggered timestamps.
    """
    current = (now or local_now()).astimezone(ZoneInfo(TZ_NAME))
    inbox_day = min(demo_day, current.date())
    reference = datetime(
        inbox_day.year,
        inbox_day.month,
        inbox_day.day,
        EMAIL_REFERENCE_HOUR,
        tzinfo=ZoneInfo(TZ_NAME),
    )
    if reference > current:
        return current.replace(second=0, microsecond=0)
    return reference


def utc_offset() -> str:
    raw = local_now().strftime("%z")
    return raw[:3] + ":" + raw[3:]


def iso(day: date, hm: str) -> str:
    return f"{day.isoformat()}T{hm}:00{utc_offset()}"


def next_business_day(day: date) -> date:
    candidate = day + timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate


def display_date(day: date) -> str:
    return f"{day.strftime('%A, %B')} {day.day}"


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


def execute_batch_requests(
    service,
    entries: list[tuple[str, object]],
    operation: str,
    *,
    on_success=None,
    accept_exception=None,
    batch_size: int = API_BATCH_SIZE,
) -> None:
    """Execute independent API requests in bounded batches with per-item accounting."""
    for start in range(0, len(entries), batch_size):
        pending = entries[start:start + batch_size]
        for attempt in range(API_BATCH_ATTEMPTS):
            responses = {}
            errors = {}

            def callback(request_id, response, exception):
                if exception is None or (accept_exception and accept_exception(exception)):
                    responses[request_id] = response
                else:
                    errors[request_id] = exception

            batch = service.new_batch_http_request()
            for request_id, request in pending:
                batch.add(request, callback=callback, request_id=request_id)

            outer_error = None
            try:
                batch.execute()
            except Exception as exc:
                outer_error = exc

            for request_id, _ in pending:
                if request_id in responses and on_success:
                    on_success(request_id, responses[request_id])

            if outer_error is not None:
                raise RuntimeError(f"{operation} incomplete:\nbatch transport: {outer_error}")

            non_retryable = [
                (request_id, errors[request_id])
                for request_id, _ in pending
                if request_id in errors and not request_is_retryable(errors[request_id])
            ]
            if non_retryable:
                details = "\n".join(f"{request_id}: {exc}" for request_id, exc in non_retryable)
                raise RuntimeError(f"{operation} incomplete:\n{details}")

            pending = [(request_id, request) for request_id, request in pending if request_id in errors]
            if not pending:
                break
            if attempt == API_BATCH_ATTEMPTS - 1:
                details = "\n".join(f"{request_id}: {errors[request_id]}" for request_id, _ in pending)
                raise RuntimeError(f"{operation} incomplete after {API_BATCH_ATTEMPTS} attempts:\n{details}")
            time.sleep(2 ** attempt)


def request_is_retryable(exc: Exception) -> bool:
    return getattr(getattr(exc, "resp", None), "status", None) in {409, 429, 500, 502, 503, 504}


def execute_request(request, operation: str):
    """Execute one API request with bounded retries for transient failures."""
    for attempt in range(API_REQUEST_ATTEMPTS):
        try:
            return request.execute()
        except Exception as exc:
            if not request_is_retryable(exc) or attempt == API_REQUEST_ATTEMPTS - 1:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError(f"{operation} failed without returning a response")


def move_to_folder(drive, file_id: str, folder_id: str) -> None:
    parents = execute_request(
        drive.files().get(fileId=file_id, fields="parents"),
        "Read Drive parents",
    ).get("parents", [])
    execute_request(
        drive.files().update(
            fileId=file_id,
            addParents=folder_id,
            removeParents=",".join(parents),
            fields="id,parents",
        ),
        "Move Drive file",
    )


def create_folder(drive) -> dict:
    item = execute_request(
        drive.files().create(
            body={"name": "RTX Spark Agent Runtime Demo", "mimeType": "application/vnd.google-apps.folder", "description": MARKER},
            fields="id,name,webViewLink",
        ),
        "Create Drive folder",
    )
    return {"id": item["id"], "url": item.get("webViewLink", f"https://drive.google.com/drive/folders/{item['id']}")}


def _doc_range(text: str, fragment: str, *, include_newline: bool = False) -> dict[str, int]:
    offset = text.index(fragment)
    start = 1 + offset
    end = start + len(fragment)
    if include_newline and text[offset + len(fragment):].startswith("\n"):
        end += 1
    return {"startIndex": start, "endIndex": end}


def _doc_text_style(text: str, fragment: str, style: dict, fields: str) -> dict:
    return {
        "updateTextStyle": {
            "range": _doc_range(text, fragment),
            "textStyle": style,
            "fields": fields,
        }
    }


def _doc_paragraph_style(text: str, fragment: str, style: dict, fields: str) -> dict:
    return {
        "updateParagraphStyle": {
            "range": _doc_range(text, fragment, include_newline=True),
            "paragraphStyle": style,
            "fields": fields,
        }
    }


def evaluation_doc_requests(text: str) -> list[dict]:
    """Build the reusable formatting layer for the seeded evaluation report."""
    title = "RTX Spark Agent Runtime Latency Evaluation"
    eyebrow = "EVALUATION REPORT  •  INTERNAL"
    status = "Complete — ready for review."
    tracker_action = (
        "Update the Agent Runtime Latency Evaluation lane from In progress to Ready for review. "
        "Do not change its owner, due date, or notes."
    )
    scope = (
        "Interactive tool-call latency across the internal reference workflow\n"
        "Recovery behavior after a failed tool response\n"
        "Completion consistency across repeated local runs\n"
    )
    requests = [
        {"insertText": {"location": {"index": 1}, "text": text}},
        {
            "updateTextStyle": {
                "range": {"startIndex": 1, "endIndex": len(text) + 1},
                "textStyle": {
                    "weightedFontFamily": {"fontFamily": "Roboto"},
                    "fontSize": {"magnitude": 10.5, "unit": "PT"},
                    "foregroundColor": {"color": {"rgbColor": DOC_THEME["body"]}},
                },
                "fields": "weightedFontFamily,fontSize,foregroundColor",
            }
        },
        _doc_paragraph_style(
            text,
            title,
            {
                "namedStyleType": "TITLE",
                "spaceBelow": {"magnitude": 4, "unit": "PT"},
                "keepWithNext": True,
            },
            "namedStyleType,spaceBelow,keepWithNext",
        ),
        _doc_text_style(
            text,
            title,
            {
                "weightedFontFamily": {"fontFamily": "Roboto"},
                "fontSize": {"magnitude": 24, "unit": "PT"},
                "bold": True,
                "foregroundColor": {"color": {"rgbColor": DOC_THEME["navy"]}},
            },
            "weightedFontFamily,fontSize,bold,foregroundColor",
        ),
        _doc_text_style(
            text,
            eyebrow,
            {
                "weightedFontFamily": {"fontFamily": "Roboto"},
                "fontSize": {"magnitude": 9, "unit": "PT"},
                "bold": True,
                "foregroundColor": {"color": {"rgbColor": DOC_THEME["accent"]}},
            },
            "weightedFontFamily,fontSize,bold,foregroundColor",
        ),
        _doc_paragraph_style(
            text,
            eyebrow,
            {"spaceBelow": {"magnitude": 14, "unit": "PT"}, "keepWithNext": True},
            "spaceBelow,keepWithNext",
        ),
    ]
    for heading in ("Status", "Summary", "Evaluation scope", "Review notes", "Tracker action"):
        requests.extend([
            _doc_paragraph_style(
                text,
                heading,
                {
                    "namedStyleType": "HEADING_2",
                    "spaceAbove": {"magnitude": 12, "unit": "PT"},
                    "spaceBelow": {"magnitude": 4, "unit": "PT"},
                    "keepWithNext": True,
                },
                "namedStyleType,spaceAbove,spaceBelow,keepWithNext",
            ),
            _doc_text_style(
                text,
                heading,
                {
                    "weightedFontFamily": {"fontFamily": "Roboto"},
                    "fontSize": {"magnitude": 13, "unit": "PT"},
                    "bold": True,
                    "foregroundColor": {"color": {"rgbColor": DOC_THEME["navy"]}},
                },
                "weightedFontFamily,fontSize,bold,foregroundColor",
            ),
        ])
    requests.extend([
        _doc_text_style(
            text,
            status,
            {
                "bold": True,
                "foregroundColor": {"color": {"rgbColor": DOC_THEME["accent"]}},
                "backgroundColor": {"color": {"rgbColor": DOC_THEME["success_fill"]}},
            },
            "bold,foregroundColor,backgroundColor",
        ),
        _doc_paragraph_style(
            text,
            status,
            {
                "borderLeft": {
                    "color": {"color": {"rgbColor": DOC_THEME["accent"]}},
                    "width": {"magnitude": 3, "unit": "PT"},
                    "padding": {"magnitude": 8, "unit": "PT"},
                    "dashStyle": "SOLID",
                },
                "spaceAbove": {"magnitude": 4, "unit": "PT"},
                "spaceBelow": {"magnitude": 8, "unit": "PT"},
            },
            "borderLeft,spaceAbove,spaceBelow",
        ),
        {
            "createParagraphBullets": {
                "range": _doc_range(text, scope),
                "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
            }
        },
        _doc_paragraph_style(
            text,
            scope,
            {
                "indentStart": {"magnitude": 18, "unit": "PT"},
                "indentFirstLine": {"magnitude": 0, "unit": "PT"},
                "spaceBelow": {"magnitude": 3, "unit": "PT"},
            },
            "indentStart,indentFirstLine,spaceBelow",
        ),
        _doc_text_style(
            text,
            tracker_action,
            {
                "bold": True,
                "foregroundColor": {"color": {"rgbColor": DOC_THEME["navy"]}},
                "backgroundColor": {"color": {"rgbColor": DOC_THEME["action_fill"]}},
            },
            "bold,foregroundColor,backgroundColor",
        ),
        _doc_paragraph_style(
            text,
            tracker_action,
            {
                "borderLeft": {
                    "color": {"color": {"rgbColor": DOC_THEME["navy"]}},
                    "width": {"magnitude": 3, "unit": "PT"},
                    "padding": {"magnitude": 8, "unit": "PT"},
                    "dashStyle": "SOLID",
                },
                "spaceAbove": {"magnitude": 4, "unit": "PT"},
                "spaceBelow": {"magnitude": 8, "unit": "PT"},
            },
            "borderLeft,spaceAbove,spaceBelow",
        ),
    ])
    return requests


def create_doc(docs, drive, folder_id: str) -> dict:
    result = execute_request(
        docs.documents().create(body={"title": "RTX Spark Agent Runtime Latency Evaluation"}),
        "Create evaluation document",
    )
    doc_id = result["documentId"]
    text = (
        "RTX Spark Agent Runtime Latency Evaluation\n\n"
        "EVALUATION REPORT  •  INTERNAL\n\n"
        "Status\n"
        "Complete — ready for review.\n\n"
        "Summary\n"
        "The Agent Runtime evaluation completed its planned local test matrix. The duplicate-completion regression reported today is a separate release blocker and does not invalidate this report.\n\n"
        "Evaluation scope\n"
        "Interactive tool-call latency across the internal reference workflow\n"
        "Recovery behavior after a failed tool response\n"
        "Completion consistency across repeated local runs\n\n"
        "Review notes\n"
        "The results package, methodology notes, and raw-run references are complete. Mateo Chen has handed the report to the program team for review.\n\n"
        "Tracker action\n"
        "Update the Agent Runtime Latency Evaluation lane from In progress to Ready for review. Do not change its owner, due date, or notes.\n"
    )
    execute_request(
        docs.documents().batchUpdate(documentId=doc_id, body={"requests": evaluation_doc_requests(text)}),
        "Populate and format evaluation document",
    )
    move_to_folder(drive, doc_id, folder_id)
    return {"id": doc_id, "url": f"https://docs.google.com/document/d/{doc_id}/edit"}


SLIDES = [
    ("RTX Spark\nPartner Readout", "Agent Runtime partner demo\nInternal working deck"),
    ("What partners will see", "A short workflow showing how the fictional Agent Runtime coordinates local tools and keeps the user in control."),
    ("Demo flow", "1  Understand the request\n2  Gather the relevant workspace context\n3  Propose a bounded action\n4  Act only after confirmation"),
    ("Partner headline — approved copy pending", "APPROVED HEADLINE PLACEHOLDER\n\nOWNER\nElena Torres / Communications\n\nTIMING\nUpdate next week; this is not required today."),
    ("Presenter notes", "Keep the story focused on the workflow. Do not introduce unapproved performance figures or claims."),
    ("Backup", "Supporting material for questions after the primary demonstration."),
]


def _slide_element(object_id: str, slide_id: str, width: float, height: float, x: float, y: float) -> dict:
    return {
        "objectId": object_id,
        "shapeType": "TEXT_BOX",
        "elementProperties": {
            "pageObjectId": slide_id,
            "size": {
                "width": {"magnitude": width, "unit": "PT"},
                "height": {"magnitude": height, "unit": "PT"},
            },
            "transform": {
                "scaleX": 1,
                "scaleY": 1,
                "translateX": x,
                "translateY": y,
                "unit": "PT",
            },
        },
    }


def _slide_text_style(
    object_id: str,
    font_size: float,
    color: dict[str, float],
    *,
    bold: bool = False,
    font_family: str = "Roboto",
    text_range: dict | None = None,
) -> dict:
    return {
        "updateTextStyle": {
            "objectId": object_id,
            "style": {
                "fontFamily": font_family,
                "fontSize": {"magnitude": font_size, "unit": "PT"},
                "bold": bold,
                "foregroundColor": {"opaqueColor": {"rgbColor": color}},
            },
            "textRange": text_range or {"type": "ALL"},
            "fields": "fontFamily,fontSize,bold,foregroundColor",
        }
    }


def _solid_slide_shape(
    object_id: str,
    slide_id: str,
    shape_type: str,
    width: float,
    height: float,
    x: float,
    y: float,
    color: dict[str, float],
) -> list[dict]:
    element = _slide_element(object_id, slide_id, width, height, x, y)
    element["shapeType"] = shape_type
    return [
        {"createShape": element},
        {
            "updateShapeProperties": {
                "objectId": object_id,
                "shapeProperties": {
                    "shapeBackgroundFill": {"solidFill": {"color": {"rgbColor": color}}},
                    "outline": {"propertyState": "NOT_RENDERED"},
                },
                "fields": "shapeBackgroundFill,outline.propertyState",
            }
        },
    ]


def slide_template_requests(index: int, title: str, body: str) -> list[dict]:
    """Render one slide with the reusable seeded-demo visual template."""
    slide_id = f"rtx_slide_{index}"
    accent_id = f"rtx_accent_{index}"
    kicker_id = f"rtx_kicker_{index}"
    title_id = f"rtx_title_{index}"
    card_id = f"rtx_card_{index}"
    body_id = f"rtx_body_{index}"
    footer_rule_id = f"rtx_footer_rule_{index}"
    footer_id = f"rtx_footer_{index}"
    page_id = f"rtx_page_{index}"

    requests = [
        {"createSlide": {"objectId": slide_id, "slideLayoutReference": {"predefinedLayout": "BLANK"}}},
        {
            "updatePageProperties": {
                "objectId": slide_id,
                "pageProperties": {
                    "pageBackgroundFill": {"solidFill": {"color": {"rgbColor": SLIDE_THEME["background"]}}}
                },
                "fields": "pageBackgroundFill",
            }
        },
    ]
    requests.extend(_solid_slide_shape(accent_id, slide_id, "RECTANGLE", 720, 8, 0, 0, SLIDE_THEME["accent"]))
    requests.extend([
        {"createShape": _slide_element(kicker_id, slide_id, 620, 18, 46, 28)},
        {"insertText": {"objectId": kicker_id, "text": "RTX SPARK  /  AGENT RUNTIME"}},
        _slide_text_style(kicker_id, 9, SLIDE_THEME["accent"], bold=True),
        {"createShape": _slide_element(title_id, slide_id, 625, 72, 46, 53)},
        {"insertText": {"objectId": title_id, "text": title}},
        _slide_text_style(title_id, 28 if index == 1 else 25, SLIDE_THEME["title"], bold=True),
    ])
    requests.extend(_solid_slide_shape(card_id, slide_id, "ROUND_RECTANGLE", 644, 205, 38, 137, SLIDE_THEME["surface"]))
    requests.extend([
        {"createShape": _slide_element(body_id, slide_id, 594, 158, 63, 160)},
        {"insertText": {"objectId": body_id, "text": body}},
        _slide_text_style(body_id, 15, SLIDE_THEME["body"]),
    ])
    if "APPROVED HEADLINE PLACEHOLDER" in body:
        start = body.index("APPROVED HEADLINE PLACEHOLDER")
        requests.append(
            _slide_text_style(
                body_id,
                19,
                SLIDE_THEME["accent"],
                bold=True,
                text_range={"type": "FIXED_RANGE", "startIndex": start, "endIndex": start + len("APPROVED HEADLINE PLACEHOLDER")},
            )
        )
    requests.extend(_solid_slide_shape(footer_rule_id, slide_id, "RECTANGLE", 628, 1, 46, 365, SLIDE_THEME["muted"]))
    requests.extend([
        {"createShape": _slide_element(footer_id, slide_id, 520, 16, 46, 374)},
        {"insertText": {"objectId": footer_id, "text": "INTERNAL WORKING DECK  •  SEEDED DEMO"}},
        _slide_text_style(footer_id, 8, SLIDE_THEME["muted"], bold=True),
        {"createShape": _slide_element(page_id, slide_id, 35, 16, 638, 374)},
        {"insertText": {"objectId": page_id, "text": f"{index:02d}"}},
        _slide_text_style(page_id, 8, SLIDE_THEME["accent"], bold=True),
    ])
    return requests


def create_slides(slides, drive, folder_id: str) -> dict:
    result = execute_request(
        slides.presentations().create(body={"title": "RTX Spark Partner Readout"}),
        "Create partner readout",
    )
    presentation_id = result["presentationId"]
    requests = []
    if result.get("slides"):
        requests.append({"deleteObject": {"objectId": result["slides"][0]["objectId"]}})
    for index, (title, body) in enumerate(SLIDES, 1):
        requests.extend(slide_template_requests(index, title, body))
    execute_request(
        slides.presentations().batchUpdate(presentationId=presentation_id, body={"requests": requests}),
        "Populate partner readout",
    )
    move_to_folder(drive, presentation_id, folder_id)
    return {"id": presentation_id, "url": f"https://docs.google.com/presentation/d/{presentation_id}/edit"}


def tracker_rows(
    slides_url: str,
    doc_url: str,
    sheet_url: str,
    evidence: dict[str, str],
    demo_day: date,
) -> list[list[str]]:
    reschedule_day = next_business_day(demo_day)
    reschedule_label = reschedule_day.strftime("%A")
    return [
        ["Lane", "PIC", "Status", "Latest update", "Next action", "Due", "Dependency / blocker", "Evidence", "Artifact", "Notes"],
        ["Agent Runtime regression", "Priya Shah", "Blocked", "The current build duplicates tool-call completions in repeated local runs.", f"Move the existing release review to the earliest non-conflicting one-hour slot on {reschedule_label} and draft Priya and Daniel a confirmation; do not send it.", "Today", "Release review must move while the P0 regression is open.", evidence.get("bug", "Priya's blocker email"), sheet_url, "Calendar and draft follow-up are the immediate coordination actions."],
        ["Agent Runtime Latency Evaluation", "Mateo Chen", "In progress", "Mateo completed the evaluation report and handed it off for review.", "Change only this lane's status to Ready for review.", "Today", "None; the tracker status is stale.", evidence.get("evaluation", "Mateo's completion email"), doc_url, "Keep the owner, due date, and notes unchanged."],
        ["Partner Readout Deck", "Elena Torres", "Awaiting update", "Communications approved the replacement headline for slide 4.", "Replace APPROVED HEADLINE PLACEHOLDER with “Meet the RTX Spark Agent Runtime: a faster path from intent to completed work.” on slide 4; leave the rest unchanged.", "Next week", "None; intentionally lower priority than today's two actions.", evidence.get("copy", "Elena's approval email"), slides_url, "Optional backup demo; not required today."],
        ["Reliability test matrix", "Noah Williams", "In review", "Noah completed the expanded reliability matrix and submitted the results for review.", "Change only this lane's status to Ready for review.", "This week", "None; the tracker status has not caught up with the completed matrix.", evidence.get("reliability", "Reliability matrix completion email"), sheet_url, "Keep the owner, due date, and notes unchanged."],
        ["Developer guide refresh", "Maya Patel", "In review", "The draft is with technical writing for routine review.", "Wait for consolidated comments.", "Next week", "None", "Routine team update", doc_url, "No action needed today."],
        ["Partner demo checklist", "Jordan Lee", "Not started", "Jordan finalized the checklist and confirmed that execution can begin.", "Change only this lane's status to In progress.", "Next week", "None; the checklist is ready to start.", evidence.get("checklist", "Partner checklist kickoff email"), slides_url, "Keep the owner, due date, and notes unchanged."],
        ["Accessibility review", "Sofia Martin", "Complete", "The scheduled review is complete.", "No further action.", "Complete", "None", "Routine team update", sheet_url, "Closed."],
        ["Release notes", "Ethan Brooks", "On track", "The routine draft is progressing on schedule.", "Continue drafting after the regression is resolved.", "This week", "None", "Routine team update", doc_url, "Lower priority than the release blocker."],
    ]


def tracker_status_format_requests(sheet_id: int) -> list[dict]:
    status_range = {
        "sheetId": sheet_id,
        "startRowIndex": 6,
        "endRowIndex": 14,
        "startColumnIndex": 2,
        "endColumnIndex": 3,
    }
    requests = []
    for index, status in enumerate(STATUS_VALUES):
        background, foreground = STATUS_STYLES[status]
        requests.append({
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [status_range],
                    "booleanRule": {
                        "condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": status}]},
                        "format": {
                            "backgroundColor": background,
                            "textFormat": {"foregroundColor": foreground, "bold": True},
                        },
                    },
                },
                "index": index,
            }
        })
    return requests


def tracker_column_width_requests(sheet_id: int) -> list[dict]:
    return [
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": index,
                    "endIndex": index + 1,
                },
                "properties": {"pixelSize": width},
                "fields": "pixelSize",
            }
        }
        for index, width in enumerate(TRACKER_COLUMN_WIDTHS)
    ]


def create_sheet(sheets, drive, folder_id: str, slides_url: str, doc_url: str, demo_day: date) -> dict:
    result = execute_request(
        sheets.spreadsheets().create(body={"properties": {"title": "RTX Spark Delivery Tracker"}, "sheets": [{"properties": {"title": "Campaign Lanes", "gridProperties": {"rowCount": 100, "columnCount": 12, "frozenRowCount": 6, "hideGridlines": True}}}]}),
        "Create delivery tracker",
    )
    spreadsheet_id = result["spreadsheetId"]
    sheet_id = result["sheets"][0]["properties"]["sheetId"]
    sheet_url = result.get("spreadsheetUrl", f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit")
    rows = [["RTX Spark Delivery Tracker"], ["Decision-ready view of Agent Runtime work"], ["Awaiting updates", "1", "", "Blocked", "1", "", "Active lanes", "8", "Last refreshed", demo_day.isoformat()], ["Statuses are updated from current owner evidence; use the Artifact column to open the working file or decision source."], [], *tracker_rows(slides_url, doc_url, sheet_url, {}, demo_day)]
    execute_request(
        sheets.spreadsheets().values().update(spreadsheetId=spreadsheet_id, range="'Campaign Lanes'!A1:J14", valueInputOption="USER_ENTERED", body={"values": rows}),
        "Populate delivery tracker",
    )
    requests = [
        {"mergeCells": {"range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 10}, "mergeType": "MERGE_ALL"}},
        {"mergeCells": {"range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 2, "startColumnIndex": 0, "endColumnIndex": 10}, "mergeType": "MERGE_ALL"}},
        {"mergeCells": {"range": {"sheetId": sheet_id, "startRowIndex": 3, "endRowIndex": 4, "startColumnIndex": 0, "endColumnIndex": 10}, "mergeType": "MERGE_ALL"}},
        {"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 10}, "cell": {"userEnteredFormat": {"backgroundColor": {"red": 0.10, "green": 0.18, "blue": 0.30}, "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "fontSize": 18, "bold": True}, "verticalAlignment": "MIDDLE"}}, "fields": "userEnteredFormat"}},
        {"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 2, "startColumnIndex": 0, "endColumnIndex": 10}, "cell": {"userEnteredFormat": {"backgroundColor": {"red": 0.90, "green": 0.94, "blue": 0.98}, "textFormat": {"foregroundColor": {"red": 0.16, "green": 0.24, "blue": 0.34}, "fontSize": 12, "italic": True}, "verticalAlignment": "MIDDLE"}}, "fields": "userEnteredFormat"}},
        {"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": 2, "endRowIndex": 3, "startColumnIndex": 0, "endColumnIndex": 10}, "cell": {"userEnteredFormat": {"backgroundColor": {"red": 0.96, "green": 0.97, "blue": 0.98}, "textFormat": {"foregroundColor": {"red": 0.20, "green": 0.25, "blue": 0.32}, "bold": True}, "verticalAlignment": "MIDDLE", "horizontalAlignment": "CENTER"}}, "fields": "userEnteredFormat"}},
        {"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": 3, "endRowIndex": 4, "startColumnIndex": 0, "endColumnIndex": 10}, "cell": {"userEnteredFormat": {"backgroundColor": {"red": 0.94, "green": 0.97, "blue": 1.00}, "textFormat": {"foregroundColor": {"red": 0.24, "green": 0.32, "blue": 0.42}, "italic": True}, "wrapStrategy": "WRAP", "verticalAlignment": "MIDDLE"}}, "fields": "userEnteredFormat"}},
        {"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": 5, "endRowIndex": 6, "startColumnIndex": 0, "endColumnIndex": 10}, "cell": {"userEnteredFormat": {"backgroundColor": {"red": 0.20, "green": 0.35, "blue": 0.55}, "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True}, "wrapStrategy": "WRAP"}}, "fields": "userEnteredFormat"}},
        {"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": 6, "endRowIndex": 14, "startColumnIndex": 0, "endColumnIndex": 10}, "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP", "verticalAlignment": "TOP"}}, "fields": "userEnteredFormat.wrapStrategy,userEnteredFormat.verticalAlignment"}},
        {"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": 6, "endRowIndex": 14, "startColumnIndex": 2, "endColumnIndex": 3}, "cell": {"userEnteredFormat": {"horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE", "textFormat": {"bold": True}}}, "fields": "userEnteredFormat.horizontalAlignment,userEnteredFormat.verticalAlignment,userEnteredFormat.textFormat.bold"}},
        {"setDataValidation": {"range": {"sheetId": sheet_id, "startRowIndex": 6, "endRowIndex": 14, "startColumnIndex": 2, "endColumnIndex": 3}, "rule": {"condition": {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": value} for value in STATUS_VALUES]}, "strict": True, "showCustomUi": True}}},
        {"setBasicFilter": {"filter": {"range": {"sheetId": sheet_id, "startRowIndex": 5, "endRowIndex": 14, "startColumnIndex": 0, "endColumnIndex": 10}}}},
        {"updateDimensionProperties": {"range": {"sheetId": sheet_id, "dimension": "ROWS", "startIndex": 0, "endIndex": 1}, "properties": {"pixelSize": 42}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {"range": {"sheetId": sheet_id, "dimension": "ROWS", "startIndex": 5, "endIndex": 6}, "properties": {"pixelSize": 42}, "fields": "pixelSize"}},
    ]
    requests.extend(tracker_status_format_requests(sheet_id))
    requests.extend(tracker_column_width_requests(sheet_id))
    execute_request(
        sheets.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={"requests": requests}),
        "Format delivery tracker",
    )
    move_to_folder(drive, spreadsheet_id, folder_id)
    return {"id": spreadsheet_id, "url": sheet_url, "sheet_id": sheet_id}


def import_mail_request(
    gmail,
    account: str,
    sender: str,
    subject: str,
    body: str,
    seed_run_id: str,
    index: int,
    received_at: datetime,
    *,
    unread: bool,
    important: bool,
):
    message = EmailMessage()
    message["From"] = sender
    message["To"] = account
    message["Subject"] = subject
    message["Date"] = format_datetime(received_at)
    message["Message-ID"] = seeded_rfc_message_id(seed_run_id, index)
    message.set_content(body + f"\n\n[{MARKER}]")
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    labels = ["INBOX"]
    if unread:
        labels.append("UNREAD")
    if important:
        labels.append("IMPORTANT")
    return gmail.users().messages().import_(
        userId="me",
        body={"raw": raw, "labelIds": labels},
        internalDateSource="dateHeader",
        neverMarkSpam=True,
        processForCalendar=False,
    )


def seeded_rfc_message_id(seed_run_id: str, index: int) -> str:
    return f"<{MARKER}-{seed_run_id}-{index}@demo.example>"


def imported_mail_state(result: dict, role: str, received_at: datetime) -> dict:
    return {
        "id": result["id"],
        "thread_id": result.get("threadId", result["id"]),
        "url": f"https://mail.google.com/mail/u/0/#all/{result.get('threadId', result['id'])}",
        "role": role,
        "received_at": received_at.isoformat(),
    }


def resolve_imported_messages(gmail, seed_run_id: str, specs: list[dict], attempts: int = 3) -> dict[str, dict]:
    pending = {f"email-{spec['index']:03d}": spec for spec in specs}
    resolved: dict[str, dict] = {}
    for attempt in range(attempts):
        entries = [
            (
                request_id,
                gmail.users().messages().list(
                    userId="me",
                    q=f"rfc822msgid:{seeded_rfc_message_id(seed_run_id, spec['index'])}",
                    includeSpamTrash=True,
                    maxResults=2,
                ),
            )
            for request_id, spec in pending.items()
        ]

        def record_resolution(request_id: str, response: dict) -> None:
            matches = response.get("messages", [])
            if len(matches) == 1:
                resolved[request_id] = matches[0]

        execute_batch_requests(
            gmail,
            entries,
            "Gmail import verification",
            on_success=record_resolution,
            batch_size=GMAIL_BATCH_SIZE,
        )
        pending = {request_id: spec for request_id, spec in pending.items() if request_id not in resolved}
        if not pending:
            return resolved
        if attempt + 1 < attempts:
            time.sleep(1)
    raise RuntimeError(f"Gmail import verification could not resolve {len(pending)} messages")


def background_email_specs(reference_time: datetime) -> list[dict]:
    specs = []
    for index in range(BACKGROUND_EMAIL_COUNT):
        first = BACKGROUND_FIRST_NAMES[index // len(BACKGROUND_LAST_NAMES)]
        last = BACKGROUND_LAST_NAMES[index % len(BACKGROUND_LAST_NAMES)]
        subject, body = BACKGROUND_TOPICS[index]
        domain = BACKGROUND_DOMAINS[index % len(BACKGROUND_DOMAINS)]
        received_at = reference_time - timedelta(
            minutes=EMAIL_SPACING_MINUTES * (MEANINGFUL_EMAIL_COUNT + index),
        )
        specs.append({
            "sender": f"{first} {last} <{first.lower()}.{last.lower()}@{domain}>",
            "subject": subject,
            "body": body,
            "received_at": received_at,
            "unread": True,
            "important": False,
            "role": "background",
        })
    return specs


def create_emails(
    gmail,
    deck_url: str,
    sheet_url: str,
    doc_url: str,
    release_review_url: str,
    demo_day: date,
    created: list[dict] | None = None,
    seed_run_id: str | None = None,
) -> tuple[list[dict], dict[str, str]]:
    seed_run_id = seed_run_id or uuid.uuid4().hex
    account = execute_request(
        gmail.users().getProfile(userId="me"),
        "Read Gmail profile",
    )["emailAddress"]
    reference_time = email_reference_time(demo_day)
    follow_up_day = next_business_day(demo_day)
    data = [
        {
            "key": "bug",
            "sender": "Priya Shah <priya.shah@nvidia.example>",
            "subject": "BLOCKER: Agent Runtime duplicates tool-call completions",
            "body": (
                "P0 regression: tool-call completions duplicate in 8 of 10 runs. Postpone today's 2 PM release review.\n\n"
                "Hi,\n\nI reproduced the issue in the latest fictional RTX Spark Agent Runtime build. The release candidate should not advance until the patch passes the same matrix cleanly.\n\n"
                f"Please postpone the RTX Spark Agent Runtime release review scheduled for {display_date(demo_day)}.\n\n"
                f"Event: {release_review_url}\n"
                f"Tracker: {sheet_url}\n\n— Priya"
            ),
            "unread": True,
            "important": True,
        },
        {
            "key": "scheduling",
            "sender": "Daniel Cho <daniel.cho@nvidia.example>",
            "subject": "New slot for the Agent Runtime release review",
            "body": (
                f"Move the existing release review to the earliest non-conflicting one-hour slot on {display_date(follow_up_day)}. Reply in Priya's blocker thread with the confirmation and copy me; do not send it.\n\n"
                "Keep the event's current details and move it rather than creating a duplicate.\n\n"
                f"Event: {release_review_url}\n\n"
                "— Daniel"
            ),
            "unread": True,
            "important": True,
        },
        {
            "key": "evaluation",
            "sender": "Mateo Chen <mateo.chen@nvidia.example>",
            "subject": "READY: Agent Runtime latency evaluation",
            "body": (
                "The RTX Spark Agent Runtime latency evaluation is complete and ready for review. The report and methodology notes are in Drive. The delivery tracker still says In progress; please change that lane to Ready for review.\n\n"
                f"Evaluation report: {doc_url}\n"
                f"Delivery tracker: {sheet_url}\n\n— Mateo"
            ),
            "unread": True,
            "important": False,
        },
        {
            "key": "reliability",
            "sender": "Aisha Rahman <aisha.rahman@nvidia.example>",
            "subject": "READY: Reliability test matrix",
            "body": (
                "Noah completed the expanded reliability matrix and submitted the results for review. The tracker still says In review; change only the Reliability test matrix lane to Ready for review. Keep Noah as owner and leave the due date and notes unchanged.\n\n"
                f"Delivery tracker: {sheet_url}\n\n— Aisha"
            ),
            "unread": True,
            "important": False,
        },
        {
            "key": "copy",
            "sender": "Elena Torres <elena.torres@nvidia.example>",
            "subject": "For next week: approved Partner Readout headline",
            "body": (
                "Communications approved this exact replacement copy for slide 4: “Meet the RTX Spark Agent Runtime: a faster path from intent to completed work.” Replace the text APPROVED HEADLINE PLACEHOLDER and leave the rest of the slide unchanged. This is due next week and is not needed today.\n\n"
                f"Partner Readout: {deck_url}\n\n— Elena"
            ),
            "unread": True,
            "important": False,
        },
        {
            "key": "checklist",
            "sender": "Jordan Lee <jordan.lee@nvidia.example>",
            "subject": "ACTION: Partner demo checklist ready to start",
            "body": (
                "The partner demo checklist is finalized and execution can begin. Change only the Partner demo checklist lane from Not started to In progress; keep the owner, due date, and notes unchanged.\n\n"
                f"Delivery tracker: {sheet_url}\n"
                f"Partner Readout: {deck_url}\n\n— Jordan"
            ),
            "unread": True,
            "important": False,
        },
    ]
    created = created if created is not None else []
    evidence = {}
    mail_specs = []
    for index, spec in enumerate(data, 1):
        mail_specs.append({
            **spec,
            "index": index,
            "received_at": reference_time - timedelta(minutes=EMAIL_SPACING_MINUTES * (index - 1)),
            "role": "meaningful",
        })
    for index, spec in enumerate(background_email_specs(reference_time), MEANINGFUL_EMAIL_COUNT + 1):
        mail_specs.append({**spec, "index": index})

    # Gmail's list endpoint does not promise chronological ordering and, for
    # imported mail, commonly reflects recent import batches. Insert background
    # mail first and reserve the final batch for the six meaningful messages so
    # the dedicated demo inbox also presents the meaningful set near the top.
    import_specs = [spec for spec in mail_specs if spec["role"] == "background"]
    import_specs.extend(spec for spec in mail_specs if spec["role"] == "meaningful")
    entries_by_role = {"background": [], "meaningful": []}
    metadata = {}
    created_by_request = {}
    for spec in import_specs:
        request_id = f"email-{spec['index']:03d}"
        metadata[request_id] = spec
        request = import_mail_request(
            gmail,
            account,
            spec["sender"],
            spec["subject"],
            spec["body"],
            seed_run_id,
            spec["index"],
            spec["received_at"],
            unread=spec["unread"],
            important=spec["important"],
        )
        entries_by_role[spec["role"]].append((request_id, request))

    def record_import(request_id: str, response: dict) -> None:
        spec = metadata[request_id]
        item = imported_mail_state(response, spec["role"], spec["received_at"])
        created.append(item)
        created_by_request[request_id] = item

    for role in ("background", "meaningful"):
        execute_batch_requests(
            gmail,
            entries_by_role[role],
            f"Gmail {role} import",
            on_success=record_import,
            batch_size=GMAIL_BATCH_SIZE,
        )
    resolved = resolve_imported_messages(gmail, seed_run_id, mail_specs)
    for request_id, result in resolved.items():
        spec = metadata[request_id]
        item = created_by_request[request_id]
        item.update(imported_mail_state(result, spec["role"], spec["received_at"]))
        if spec.get("key"):
            evidence[spec["key"]] = item["url"]
    created.sort(key=lambda item: item["received_at"], reverse=True)
    return created, evidence


EVENTS = [
    ("08:00", "08:25", "RTX Spark engineering leads sync", "Routine team updates, planned work, and cross-functional dependencies."),
    ("09:00", "09:30", "Agent Runtime engineering stand-up", "Routine engineering progress, test coverage, and owner check-in."),
    ("10:00", "10:45", "RTX Spark integration sync", "Routine integration status and dependency review."),
    ("11:00", "12:00", "Engineering focus block", "Protected time for planned technical work."),
    ("12:00", "13:00", "Team lunch", "Optional team lunch; no preparation required."),
    ("15:15", "15:45", "Evaluation office hours", "Optional questions about completed evaluation methodology and results."),
    ("16:00", "16:30", "Partner demo checklist", "Routine readiness check for next week's partner work."),
    ("17:00", "17:20", "Developer guide editorial pass", "Review routine documentation edits and collect notes for the next planned revision."),
]

WEEKDAY_CODES = ("MO", "TU", "WE", "TH", "FR")
OVERLAP_EVENTS = [
    ((1, 3), "09:15", "10:15", "Agent Runtime design review", "Routine architecture review; decisions and notes stay with the engineering team."),
    ((2, 4), "11:30", "12:30", "Reliability test office hours", "Optional working session for routine test questions; no preparation is required."),
    ((0, 2), "15:30", "16:15", "Partner demo dry run", "Rehearsal for next week's partner demo; no action is needed today."),
]


def recurrence_for_days(day_offsets: tuple[int, ...]) -> str:
    days = ",".join(WEEKDAY_CODES[offset] for offset in day_offsets)
    return f"RRULE:FREQ=WEEKLY;BYDAY={days};COUNT={len(day_offsets)}"


def create_calendar(calendar, start_day: date, demo_day: date, deck_url: str, doc_url: str, sheet_url: str) -> list[dict]:
    created = []
    entries = []
    for index, (begin, end, title, description) in enumerate(EVENTS, 1):
        link = f"\nEvaluation report: {doc_url}" if title.startswith("Evaluation office hours") else f"\nPartner Readout: {deck_url}" if title.startswith("Partner demo") else ""
        request = calendar.events().insert(
            calendarId="primary",
            body={
                "summary": title,
                "description": f"{description}{link}\n[{MARKER}]",
                "start": {"dateTime": iso(start_day, begin), "timeZone": TZ_NAME},
                "end": {"dateTime": iso(start_day, end), "timeZone": TZ_NAME},
                "recurrence": ["RRULE:FREQ=DAILY;COUNT=5"],
            },
            sendUpdates="none",
        )
        entries.append((f"calendar-routine-{index:02d}", request))
    for index, (day_offsets, begin, end, title, description) in enumerate(OVERLAP_EVENTS, 1):
        first_day = start_day + timedelta(days=day_offsets[0])
        request = calendar.events().insert(
            calendarId="primary",
            body={
                "summary": title,
                "description": f"{description}\n[{MARKER}]",
                "start": {"dateTime": iso(first_day, begin), "timeZone": TZ_NAME},
                "end": {"dateTime": iso(first_day, end), "timeZone": TZ_NAME},
                "recurrence": [recurrence_for_days(day_offsets)],
            },
            sendUpdates="none",
        )
        entries.append((f"calendar-overlap-{index:02d}", request))
    release_review = calendar.events().insert(
        calendarId="primary",
        body={
            "summary": "RTX Spark Agent Runtime release review",
            "description": (
                "Release-gate review for the fictional Agent Runtime. If the duplicate-completion regression remains open, postpone this meeting rather than creating a second event.\n"
                f"Delivery tracker: {sheet_url}\n[{MARKER}]"
            ),
            "start": {"dateTime": iso(demo_day, "14:00"), "timeZone": TZ_NAME},
            "end": {"dateTime": iso(demo_day, "15:00"), "timeZone": TZ_NAME},
        },
        sendUpdates="none",
    )
    entries.append(("calendar-release-review", release_review))

    def record_event(request_id: str, response: dict) -> None:
        created.append({"key": request_id, "id": response["id"], "url": response.get("htmlLink", "")})

    execute_batch_requests(
        calendar,
        entries,
        "Calendar creation",
        on_success=record_event,
        batch_size=CALENDAR_BATCH_SIZE,
    )
    return created


def update_tracker_evidence(sheets, state: dict, evidence: dict[str, str]) -> None:
    sheet = state["sheet"]
    values = tracker_rows(
        state["slides"]["url"],
        state["doc"]["url"],
        sheet["url"],
        evidence,
        date.fromisoformat(state["demo_day"]),
    )
    execute_request(
        sheets.spreadsheets().values().update(spreadsheetId=sheet["id"], range="'Campaign Lanes'!A6:J14", valueInputOption="USER_ENTERED", body={"values": values}),
        "Update delivery tracker evidence",
    )


def resource_is_already_absent(exc: Exception) -> bool:
    return getattr(getattr(exc, "resp", None), "status", None) in {404, 410}


def cleanup(state: dict) -> dict[str, int]:
    svc = services()
    result = {"drafts_deleted": 0, "emails_deleted": 0, "events_deleted": 0, "folders_trashed": 0}
    failures = []
    for item in state.get("drafts", []):
        try:
            execute_request(
                svc["gmail"].users().drafts().delete(userId="me", id=item["id"]),
                "Delete tracked Gmail draft",
            )
            result["drafts_deleted"] += 1
        except Exception as exc:
            if resource_is_already_absent(exc):
                result["drafts_deleted"] += 1
            else:
                failures.append(f"Gmail draft {item['id']}: {exc}")
    email_entries = [
        (
            f"email-{item['id']}",
            svc["gmail"].users().messages().delete(userId="me", id=item["id"]),
        )
        for item in state.get("emails", [])
    ]

    def record_deleted_email(_request_id: str, _response) -> None:
        result["emails_deleted"] += 1

    try:
        execute_batch_requests(
            svc["gmail"],
            email_entries,
            "Gmail cleanup",
            on_success=record_deleted_email,
            accept_exception=resource_is_already_absent,
            batch_size=GMAIL_BATCH_SIZE,
        )
    except RuntimeError as exc:
        failures.append(str(exc))

    event_entries = [
        (
            f"calendar-{item['id']}",
            svc["calendar"].events().delete(calendarId="primary", eventId=item["id"], sendUpdates="none"),
        )
        for item in state.get("events", [])
    ]

    def record_deleted_event(_request_id: str, _response) -> None:
        result["events_deleted"] += 1

    try:
        execute_batch_requests(
            svc["calendar"],
            event_entries,
            "Calendar cleanup",
            on_success=record_deleted_event,
            accept_exception=resource_is_already_absent,
            batch_size=CALENDAR_BATCH_SIZE,
        )
    except RuntimeError as exc:
        failures.append(str(exc))
    if state.get("folder", {}).get("id"):
        try:
            execute_request(
                svc["drive"].files().update(fileId=state["folder"]["id"], body={"trashed": True}),
                "Trash seeded Drive folder",
            )
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
    today = local_now().date()
    demo_day = demo_day_for_week(week_of, today)
    state = {"schema": 3, "marker": MARKER, "seed_run_id": uuid.uuid4().hex, "week_of": week_of.isoformat(), "demo_day": demo_day.isoformat(), "events": [], "emails": [], "drafts": []}
    try:
        state["folder"] = create_folder(svc["drive"])
        state["doc"] = create_doc(svc["docs"], svc["drive"], state["folder"]["id"])
        state["slides"] = create_slides(svc["slides"], svc["drive"], state["folder"]["id"])
        state["sheet"] = create_sheet(
            svc["sheets"],
            svc["drive"],
            state["folder"]["id"],
            state["slides"]["url"],
            state["doc"]["url"],
            demo_day,
        )
        state["events"] = create_calendar(svc["calendar"], week_of, demo_day, state["slides"]["url"], state["doc"]["url"], state["sheet"]["url"])
        release_review_url = next(item["url"] for item in state["events"] if item["key"] == "calendar-release-review")
        state["emails"], evidence = create_emails(
            svc["gmail"],
            state["slides"]["url"],
            state["sheet"]["url"],
            state["doc"]["url"],
            release_review_url,
            demo_day,
            state["emails"],
            state["seed_run_id"],
        )
        update_tracker_evidence(svc["sheets"], state, evidence)
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
    parser.add_argument(
        "--week-of",
        help="Monday date (YYYY-MM-DD); defaults to the current week on weekdays or the upcoming week on weekends",
    )
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
    chosen_week = date.fromisoformat(args.week_of) if args.week_of else default_demo_week(local_now().date())
    if args.reset:
        if not path.exists(): raise SystemExit(f"No workspace state at {path}")
        previous = json.loads(path.read_text(encoding="utf-8"))
        chosen_week = date.fromisoformat(args.week_of) if args.week_of else default_demo_week(local_now().date())
        cleanup(previous)
        path.unlink(missing_ok=True)
    elif path.exists():
        raise SystemExit(f"Workspace already exists. Run reset or cleanup first: {path}")
    state = seed(chosen_week)
    print(json.dumps({"ok": True, "state": str(path), "week_of": state["week_of"], "demo_day": state["demo_day"], "folder": state["folder"], "sheet": state["sheet"], "doc": state["doc"], "slides": state["slides"], "emails": len(state["emails"]), "events": len(state["events"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
