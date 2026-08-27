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
STATUS_VALUES = ["Not started", "In progress", "Ready for review", "On track", "In review", "Awaiting update", "Blocked", "Done"]
STATUS_STYLES = {
    "Not started": ({"red": 0.91, "green": 0.93, "blue": 0.95}, {"red": 0.28, "green": 0.32, "blue": 0.38}),
    "In progress": ({"red": 0.82, "green": 0.90, "blue": 1.00}, {"red": 0.07, "green": 0.27, "blue": 0.52}),
    "Ready for review": ({"red": 0.90, "green": 0.84, "blue": 0.98}, {"red": 0.31, "green": 0.15, "blue": 0.50}),
    "On track": ({"red": 0.82, "green": 0.95, "blue": 0.86}, {"red": 0.06, "green": 0.36, "blue": 0.17}),
    "In review": ({"red": 0.80, "green": 0.94, "blue": 0.94}, {"red": 0.02, "green": 0.35, "blue": 0.37}),
    "Awaiting update": ({"red": 1.00, "green": 0.91, "blue": 0.76}, {"red": 0.51, "green": 0.27, "blue": 0.02}),
    "Blocked": ({"red": 1.00, "green": 0.82, "blue": 0.82}, {"red": 0.58, "green": 0.06, "blue": 0.06}),
    "Done": ({"red": 0.75, "green": 0.91, "blue": 0.80}, {"red": 0.03, "green": 0.29, "blue": 0.12}),
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
            body={"name": "RTX AI Assistant Executive Review Demo", "mimeType": "application/vnd.google-apps.folder", "description": MARKER},
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


def product_summary_doc_requests(text: str) -> list[dict]:
    """Build the reusable formatting layer for the seeded product brief."""
    title = "RTX AI Assistant Product Summary"
    eyebrow = "PRODUCT BRIEF  •  EXECUTIVE REVIEW"
    status = "Ready for today's executive review."
    decision = (
        "Decision requested: approve an expanded partner pilot focused on everyday coordination work, "
        "with the same user-control and verification safeguards."
    )
    scope = (
        "Understands a plain-language request and gathers the relevant Workspace context\n"
        "Shows the intended change before carrying out consequential work\n"
        "Completes approved Gmail, Calendar, and Drive actions and verifies the result\n"
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
    for heading in (
        "Status",
        "Product at a glance",
        "Customer value",
        "How it works",
        "Pilot signals",
        "Guardrails",
        "Decision for today",
    ):
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
            decision,
            {
                "bold": True,
                "foregroundColor": {"color": {"rgbColor": DOC_THEME["navy"]}},
                "backgroundColor": {"color": {"rgbColor": DOC_THEME["action_fill"]}},
            },
            "bold,foregroundColor,backgroundColor",
        ),
        _doc_paragraph_style(
            text,
            decision,
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
        docs.documents().create(body={"title": "RTX AI Assistant Product Summary"}),
        "Create product summary",
    )
    doc_id = result["documentId"]
    text = (
        "RTX AI Assistant Product Summary\n\n"
        "PRODUCT BRIEF  •  EXECUTIVE REVIEW\n\n"
        "Status\n"
        "Ready for today's executive review.\n\n"
        "Product at a glance\n"
        "RTX AI Assistant helps people complete everyday work across Gmail, Calendar, and Drive from one conversational request. It gathers the right context, proposes a clear next step, and keeps the user in control before anything is changed.\n\n"
        "Customer value\n"
        "Early pilot users spent less time switching between apps for routine coordination work. They could move from a request to a reviewed result while still seeing what the assistant planned to do.\n\n"
        "How it works\n"
        "Understands a plain-language request and gathers the relevant Workspace context\n"
        "Shows the intended change before carrying out consequential work\n"
        "Completes approved Gmail, Calendar, and Drive actions and verifies the result\n\n"
        "Pilot signals\n"
        "The strongest feedback was about convenience, clarity, and reduced follow-up work. Participants especially valued having related email, meeting, and file context brought together in one place.\n\n"
        "Guardrails\n"
        "The assistant drafts rather than sends email, verifies file and calendar changes, and uses live document structure instead of assuming fixed locations or allowed values.\n\n"
        "Decision for today\n"
        "Decision requested: approve an expanded partner pilot focused on everyday coordination work, with the same user-control and verification safeguards.\n"
    )
    execute_request(
        docs.documents().batchUpdate(documentId=doc_id, body={"requests": product_summary_doc_requests(text)}),
        "Populate and format product summary",
    )
    move_to_folder(drive, doc_id, folder_id)
    return {"id": doc_id, "url": f"https://docs.google.com/document/d/{doc_id}/edit"}


SLIDES = [
    ("RTX AI Assistant\nExecutive Review", "From everyday requests to completed work — with the user in control\nExecutive discussion"),
    ("Introduction", "INTRODUCTION BULLETS PLACEHOLDER"),
    ("Product experience", "Ask in plain language\nBring together the relevant work context\nReview the proposed next step\nComplete and verify the approved action"),
    ("Pilot signals", "Less time switching between apps\nClearer handoffs and follow-up\nStrongest interest in everyday coordination workflows"),
    ("Trust and control", "Draft before send\nVerify every Workspace write\nUse live document structure and allowed values"),
    ("Decision", "Approve an expanded partner pilot focused on everyday coordination work while preserving the current user-control safeguards."),
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
        {"insertText": {"objectId": kicker_id, "text": "RTX AI ASSISTANT  /  EXECUTIVE REVIEW"}},
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
    if "INTRODUCTION BULLETS PLACEHOLDER" in body:
        start = body.index("INTRODUCTION BULLETS PLACEHOLDER")
        requests.append(
            _slide_text_style(
                body_id,
                19,
                SLIDE_THEME["accent"],
                bold=True,
                text_range={"type": "FIXED_RANGE", "startIndex": start, "endIndex": start + len("INTRODUCTION BULLETS PLACEHOLDER")},
            )
        )
    requests.extend(_solid_slide_shape(footer_rule_id, slide_id, "RECTANGLE", 628, 1, 46, 365, SLIDE_THEME["muted"]))
    requests.extend([
        {"createShape": _slide_element(footer_id, slide_id, 520, 16, 46, 374)},
        {"insertText": {"objectId": footer_id, "text": "EXECUTIVE REVIEW  •  SEEDED DEMO"}},
        _slide_text_style(footer_id, 8, SLIDE_THEME["muted"], bold=True),
        {"createShape": _slide_element(page_id, slide_id, 35, 16, 638, 374)},
        {"insertText": {"objectId": page_id, "text": f"{index:02d}"}},
        _slide_text_style(page_id, 8, SLIDE_THEME["accent"], bold=True),
    ])
    return requests


def create_slides(slides, drive, folder_id: str) -> dict:
    result = execute_request(
        slides.presentations().create(body={"title": "RTX AI Assistant Executive Review"}),
        "Create executive review deck",
    )
    presentation_id = result["presentationId"]
    requests = []
    if result.get("slides"):
        requests.append({"deleteObject": {"objectId": result["slides"][0]["objectId"]}})
    for index, (title, body) in enumerate(SLIDES, 1):
        requests.extend(slide_template_requests(index, title, body))
    execute_request(
        slides.presentations().batchUpdate(presentationId=presentation_id, body={"requests": requests}),
        "Populate executive review deck",
    )
    move_to_folder(drive, presentation_id, folder_id)
    return {"id": presentation_id, "url": f"https://docs.google.com/presentation/d/{presentation_id}/edit"}


def tracker_rows(
    slides_url: str,
    doc_url: str,
    sheet_url: str,
    evidence: dict[str, str],
    demo_day: date,
    executive_review_url: str | None = None,
) -> list[list[str]]:
    return [
        ["Work item", "Owner", "Status", "Latest update", "Next step", "Due", "Dependency / blocker", "Source", "Artifact", "Notes"],
        ["Executive Review Deck", "Alex Morgan", "In progress", "The executive review moved to today; the Introduction slide still needs its product overview.", "Read the product summary, update the Introduction slide, then set this status to Done.", "Today", "Finish before the executive review.", evidence.get("executive_review", "Maya's meeting-prep email"), slides_url, "Change this status only after the Introduction slide is updated."],
        ["Product Summary", "Sam Rivera", "Done", "The concise product brief is ready for meeting preparation.", "Use it as the source for the Introduction slide.", "Today", "None", evidence.get("executive_review", "Maya's meeting-prep email"), doc_url, "Source material; no edit is requested."],
        ["Pilot Metrics", "Priya Shah", "Ready for review", "The latest customer-pilot signals are compiled.", "Review the decision points before the pilot check-in.", "Today", "Two customer comments still need categorization.", evidence.get("pilot", "Priya's pilot email"), sheet_url, "Keep the metric definitions unchanged."],
        ["Partner Briefing", "Elena Torres", "In review", "The partner narrative is ready for a short owner review.", "Confirm the plain-language framing.", "Today", "None", evidence.get("partner", "Elena's briefing email"), slides_url, "Separate from the executive-review deck update."],
        ["Executive Demo Environment", "Jordan Lee", "On track", "The demo environment passed the morning check.", "Run the final check before the meeting.", "Today", "None", evidence.get("environment", "Jordan's environment email"), sheet_url, "Routine readiness work."],
        ["Partner Pilot Scope", "Noah Williams", "Awaiting update", "The proposed partner list is being refined.", "Wait for regional feedback.", "Next week", "Regional feedback is pending.", "Routine team update", doc_url, "No action needed today."],
        ["Customer Quotes", "Aisha Rahman", "Not started", "The quote review is scheduled for later this week.", "Begin after approvals arrive.", "This week", "Approval is pending.", "Routine team update", doc_url, "Lower priority."],
        ["Meeting Logistics", "Sofia Martin", "Done", "Room, video link, and attendee list are confirmed.", "No further action.", "Done", "None", executive_review_url or sheet_url, executive_review_url or sheet_url, "Closed."],
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
        sheets.spreadsheets().create(body={"properties": {"title": "RTX AI Assistant Exec Review Prep Tracker"}, "sheets": [{"properties": {"title": "Pre-Exec Review", "gridProperties": {"rowCount": 100, "columnCount": 12, "frozenRowCount": 6, "hideGridlines": True}}}]}),
        "Create executive review prep tracker",
    )
    spreadsheet_id = result["spreadsheetId"]
    sheet_id = result["sheets"][0]["properties"]["sheetId"]
    sheet_url = result.get("spreadsheetUrl", f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit")
    rows = [["RTX AI Assistant Exec Review Prep Tracker"], ["Decision-ready view of pre-meeting work"], ["In progress", "1", "", "Ready for review", "1", "", "Open work items", "6", "Last refreshed", demo_day.isoformat()], ["Statuses come from current owner evidence; use the Artifact column to open the working file or source."], [], *tracker_rows(slides_url, doc_url, sheet_url, {}, demo_day)]
    execute_request(
        sheets.spreadsheets().values().update(spreadsheetId=spreadsheet_id, range="'Pre-Exec Review'!A1:J14", valueInputOption="USER_ENTERED", body={"values": rows}),
        "Populate executive review prep tracker",
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
    executive_review_url: str,
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
    data = [
        {
            "key": "executive_review",
            "sender": "Maya Patel <maya.patel@nvidia.example>",
            "subject": "Executive review prep for today",
            "body": (
                "Hi,\n\n"
                f"The executive team moved the RTX AI Assistant review up from Friday to today, {display_date(demo_day)}, at 3:00 PM. "
                "Before we meet, please read the product summary so you have the latest positioning, customer value, and pilot signals in mind. "
                "Then use that material to replace the placeholder on the deck's Introduction slide. "
                "Once the slide is updated, mark the Executive Review Deck as Done in the prep tracker.\n\n"
                "The links below are the current working versions:\n"
                f"Product summary: {doc_url}\n"
                f"Executive review deck: {deck_url}\n"
                f"Prep tracker: {sheet_url}\n"
                f"Meeting: {executive_review_url}\n\n"
                "Thanks,\nMaya"
            ),
            "unread": True,
            "important": True,
        },
        {
            "key": "pilot",
            "sender": "Priya Shah <priya.shah@nvidia.example>",
            "subject": "Customer pilot feedback needs a decision",
            "body": (
                "Hi,\n\nWe have enough feedback from the customer pilot to decide which everyday workflows should be included in the next round. "
                "Please review the open decision points before this afternoon's pilot check-in so we can close the scope.\n\n"
                f"Prep tracker: {sheet_url}\n\nThanks,\nPriya"
            ),
            "unread": True,
            "important": True,
        },
        {
            "key": "partner",
            "sender": "Elena Torres <elena.torres@nvidia.example>",
            "subject": "Partner briefing ready for your review",
            "body": (
                "Hi,\n\nThe partner briefing now uses the plain-language framing we discussed and is ready for a quick owner review. "
                "Please confirm that the story stays focused on useful everyday work rather than implementation details.\n\n"
                f"Executive review deck: {deck_url}\n\nThanks,\nElena"
            ),
            "unread": True,
            "important": True,
        },
        {
            "key": "environment",
            "sender": "Jordan Lee <jordan.lee@nvidia.example>",
            "subject": "Morning demo environment check passed",
            "body": (
                "Hi,\n\nThe morning environment check passed. Please run the short final check before the executive review so the demo account and shared files are ready when the meeting begins.\n\n"
                f"Prep tracker: {sheet_url}\n\nThanks,\nJordan"
            ),
            "unread": True,
            "important": False,
        },
        {
            "key": "research",
            "sender": "Mateo Chen <mateo.chen@nvidia.example>",
            "subject": "Creator workshop notes for later this week",
            "body": (
                "Hi,\n\nI consolidated the notes from the creator workshop. They will be useful when we refine the next pilot, but there is no action needed before the executive review.\n\n"
                f"Product summary: {doc_url}\n\nThanks,\nMateo"
            ),
            "unread": True,
            "important": False,
        },
        {
            "key": "community",
            "sender": "Aisha Rahman <aisha.rahman@nvidia.example>",
            "subject": "Community demo recap available",
            "body": (
                "Hi,\n\nThe community demo recap is available for background reading. Nothing in it changes today's executive-review preparation.\n\n"
                f"Product summary: {doc_url}\n\nThanks,\nAisha"
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
    ("08:00", "08:30", "Executive staff sync", "Leadership updates, decisions, and cross-functional dependencies."),
    ("08:30", "09:15", "Daily planning and decisions", "Review planned work, decisions, and owner handoffs."),
    ("09:15", "10:00", "Customer pilot check-in", "Review customer feedback and open pilot decisions."),
    ("10:00", "11:00", "Product strategy review", "Review product direction, customer value, and open decisions."),
    ("11:00", "12:00", "Operating review", "Review execution risks, milestones, and cross-functional follow-ups."),
    ("12:00", "13:00", "Leadership working lunch", "Working lunch for leadership updates and decisions."),
    ("13:00", "14:00", "Product feedback office hours", "Questions and decisions about product and pilot feedback."),
    ("15:00", "16:00", "Customer success review", "Review customer health, escalations, and upcoming commitments."),
    ("16:00", "17:00", "Partner briefing check-in", "Routine review of partner briefing work."),
    ("17:00", "17:30", "Daily wrap-up", "Review completed work and capture tomorrow's follow-ups."),
]

WEEKDAY_CODES = ("MO", "TU", "WE", "TH", "FR")
OVERLAP_EVENTS = [
    ((1, 3), "09:15", "10:15", "Product experience review", "Routine review of the customer experience."),
    ((2, 4), "11:30", "12:30", "Customer research office hours", "Optional working session for research questions."),
    ((1, 2, 4), "14:00", "15:00", "Executive materials review", "Review materials and decisions for upcoming executive meetings."),
]


def recurrence_for_days(day_offsets: tuple[int, ...]) -> str:
    days = ",".join(WEEKDAY_CODES[offset] for offset in day_offsets)
    return f"RRULE:FREQ=WEEKLY;BYDAY={days};COUNT={len(day_offsets)}"


def create_calendar(calendar, start_day: date, demo_day: date, deck_url: str, doc_url: str, sheet_url: str) -> list[dict]:
    created = []
    entries = []
    for index, (begin, end, title, description) in enumerate(EVENTS, 1):
        link = f"\nProduct summary: {doc_url}" if title.startswith("Product feedback") else f"\nExecutive review deck: {deck_url}" if title.startswith("Partner briefing") else ""
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
    executive_review = calendar.events().insert(
        calendarId="primary",
        body={
            "summary": "RTX AI Assistant Executive Review",
            "description": (
                "Executive product review moved up from Friday to today. Review the product context, updated Introduction slide, and prep status.\n"
                f"Product summary: {doc_url}\n"
                f"Executive review deck: {deck_url}\n"
                f"Prep tracker: {sheet_url}\n[{MARKER}]"
            ),
            "start": {"dateTime": iso(demo_day, "15:00"), "timeZone": TZ_NAME},
            "end": {"dateTime": iso(demo_day, "16:00"), "timeZone": TZ_NAME},
        },
        sendUpdates="none",
    )
    entries.append(("calendar-executive-review", executive_review))

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
    executive_review_url = next(
        item["url"] for item in state["events"] if item["key"] == "calendar-executive-review"
    )
    values = tracker_rows(
        state["slides"]["url"],
        state["doc"]["url"],
        sheet["url"],
        evidence,
        date.fromisoformat(state["demo_day"]),
        executive_review_url,
    )
    execute_request(
        sheets.spreadsheets().values().update(spreadsheetId=sheet["id"], range="'Pre-Exec Review'!A6:J14", valueInputOption="USER_ENTERED", body={"values": values}),
        "Update executive review tracker evidence",
    )


def resource_is_already_absent(exc: Exception) -> bool:
    return getattr(getattr(exc, "resp", None), "status", None) in {404, 410}


def seeded_calendar_event_ids(calendar) -> set[str]:
    """Find only Calendar resources carrying this seeder's ownership marker."""
    event_ids: set[str] = set()
    page_token = None
    while True:
        kwargs = {
            "calendarId": "primary",
            "q": MARKER,
            "showDeleted": False,
            "singleEvents": False,
            "maxResults": 2500,
        }
        if page_token:
            kwargs["pageToken"] = page_token
        page = execute_request(
            calendar.events().list(**kwargs),
            "Find seeded Calendar resources",
        )
        for item in page.get("items", []):
            event_id = str(item.get("id", "")).strip()
            description = str(item.get("description", ""))
            if event_id and f"[{MARKER}]" in description:
                event_ids.add(event_id)
        page_token = page.get("nextPageToken")
        if not page_token:
            return event_ids


def seeded_drive_folder_ids(drive) -> set[str]:
    """Find only Drive folders carrying this seeder's exact ownership marker."""
    safe_marker = MARKER.replace("'", "\\'")
    page_token = None
    folder_ids: set[str] = set()
    while True:
        kwargs = {
            "q": (
                "trashed = false and "
                "mimeType = 'application/vnd.google-apps.folder' and "
                f"fullText contains '{safe_marker}'"
            ),
            "pageSize": 100,
            "fields": "nextPageToken,files(id,description)",
        }
        if page_token:
            kwargs["pageToken"] = page_token
        page = execute_request(
            drive.files().list(**kwargs),
            "Find seeded Drive folders",
        )
        for item in page.get("files", []):
            folder_id = str(item.get("id", "")).strip()
            if folder_id and str(item.get("description", "")).strip() == MARKER:
                folder_ids.add(folder_id)
        page_token = page.get("nextPageToken")
        if not page_token:
            return folder_ids


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

    tracked_event_ids = {
        str(item.get("id", "")).strip()
        for item in state.get("events", [])
        if str(item.get("id", "")).strip()
    }
    try:
        tracked_event_ids.update(seeded_calendar_event_ids(svc["calendar"]))
    except Exception as exc:
        failures.append(f"Calendar marker lookup: {exc}")
    event_entries = [
        (
            f"calendar-{event_id}",
            svc["calendar"].events().delete(calendarId="primary", eventId=event_id, sendUpdates="none"),
        )
        for event_id in sorted(tracked_event_ids)
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
    folder_ids = {
        str(state.get("folder", {}).get("id", "")).strip()
    } - {""}
    try:
        folder_ids.update(seeded_drive_folder_ids(svc["drive"]))
    except Exception as exc:
        failures.append(f"Drive marker lookup: {exc}")
    folder_entries = [
        (
            f"drive-folder-{folder_id}",
            svc["drive"].files().update(fileId=folder_id, body={"trashed": True}),
        )
        for folder_id in sorted(folder_ids)
    ]

    def record_trashed_folder(_request_id: str, _response) -> None:
        result["folders_trashed"] += 1

    try:
        execute_batch_requests(
            svc["drive"],
            folder_entries,
            "Drive folder cleanup",
            on_success=record_trashed_folder,
            accept_exception=resource_is_already_absent,
            batch_size=API_BATCH_SIZE,
        )
    except RuntimeError as exc:
        failures.append(str(exc))
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
        executive_review_url = next(item["url"] for item in state["events"] if item["key"] == "calendar-executive-review")
        state["emails"], evidence = create_emails(
            svc["gmail"],
            state["slides"]["url"],
            state["sheet"]["url"],
            state["doc"]["url"],
            executive_review_url,
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
