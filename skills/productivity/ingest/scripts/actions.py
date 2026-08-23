#!/usr/bin/env python
"""Focused Google Workspace reads and guarded mutations for chief-of-staff workflows."""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Any


REFERENCE_WORKSPACE_MARKER = "chief-of-staff-reference-workspace-v1"
REFERENCE_WORKSPACE_STATE_FILE = "chief-of-staff-workspace-state.json"


def hermes_home() -> Path:
    override = os.environ.get("HERMES_HOME")
    if override:
        return Path(override).expanduser()
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "hermes"
    return Path.home() / ".hermes"


def credentials() -> Any:
    token = hermes_home() / "google_token.json"
    if not token.exists():
        raise RuntimeError(f"Google OAuth is not connected: {token} does not exist")
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    creds = Credentials.from_authorized_user_file(str(token))
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        payload = json.loads(creds.to_json())
        payload.setdefault("type", "authorized_user")
        token.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if not creds.valid:
        raise RuntimeError("Google OAuth token is invalid")
    return creds


def service(name: str, version: str) -> Any:
    from googleapiclient.discovery import build

    return build(name, version, credentials=credentials(), cache_discovery=False)


def emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def require_confirm(args: argparse.Namespace, action: str) -> None:
    if not getattr(args, "confirm", False):
        raise RuntimeError(f"Refusing {action} without --confirm after user approval")


def reference_workspace_state_path() -> Path:
    return hermes_home() / REFERENCE_WORKSPACE_STATE_FILE


def load_reference_workspace_state() -> tuple[Path, dict[str, Any]]:
    path = reference_workspace_state_path()
    if not path.exists():
        raise RuntimeError(f"No active reference workspace state at {path}; refusing untracked demo draft")
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("marker") != REFERENCE_WORKSPACE_MARKER:
        raise RuntimeError(f"Unexpected reference workspace marker in {path}")
    return path, state


def record_reference_workspace_draft(draft_id: str, message_id: str) -> Path:
    if not draft_id:
        raise RuntimeError("Gmail created a draft without returning a draft ID")
    path, state = load_reference_workspace_state()
    drafts = state.setdefault("drafts", [])
    if not any(item.get("id") == draft_id for item in drafts):
        drafts.append({"id": draft_id, "message_id": message_id})
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(temporary, path)
    return path


def decode_body(payload: dict[str, Any]) -> str:
    candidates: list[tuple[str, str]] = []

    def walk(part: dict[str, Any]) -> None:
        data = part.get("body", {}).get("data")
        if data:
            try:
                text = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")
                candidates.append((part.get("mimeType", ""), text))
            except Exception:
                pass
        for child in part.get("parts", []):
            walk(child)

    walk(payload)
    if not candidates:
        return ""
    plain = next((text for mime, text in candidates if mime == "text/plain"), None)
    text = plain if plain is not None else candidates[0][1]
    if plain is None:
        text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def headers(payload: dict[str, Any]) -> dict[str, str]:
    return {h.get("name", "").lower(): h.get("value", "") for h in payload.get("headers", [])}


def gmail_get(args: argparse.Namespace) -> None:
    api = service("gmail", "v1")
    msg = api.users().messages().get(userId="me", id=args.message_id, format="full").execute()
    hdr = headers(msg.get("payload", {}))
    emit({
        "id": msg.get("id"),
        "thread_id": msg.get("threadId"),
        "from": hdr.get("from", ""),
        "to": hdr.get("to", ""),
        "cc": hdr.get("cc", ""),
        "subject": hdr.get("subject", ""),
        "date": hdr.get("date", ""),
        "message_id_header": hdr.get("message-id", ""),
        "body": decode_body(msg.get("payload", {}))[: args.max_chars],
    })


def gmail_thread(args: argparse.Namespace) -> None:
    api = service("gmail", "v1")
    thread = api.users().threads().get(userId="me", id=args.thread_id, format="full").execute()
    output = []
    for msg in thread.get("messages", [])[-args.max_messages :]:
        hdr = headers(msg.get("payload", {}))
        output.append({
            "id": msg.get("id"),
            "from": hdr.get("from", ""),
            "to": hdr.get("to", ""),
            "subject": hdr.get("subject", ""),
            "date": hdr.get("date", ""),
            "body": decode_body(msg.get("payload", {}))[: args.max_chars],
        })
    emit({"thread_id": args.thread_id, "messages": output})


def normalize_draft_body(value: str, closing: str = "") -> str:
    """Accept shell-friendly escaped line breaks and apply an optional exact closing."""
    normalized = value.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\r", "\n")
    lines = [line.rstrip() for line in normalized.splitlines()]
    while lines and not lines[-1]:
        lines.pop()
    if closing:
        exact_closing = closing.strip()
        common_closings = {"thanks", "thank you", "best regards", "regards", "sincerely"}
        replaced = False
        for index in range(len(lines) - 1, max(-1, len(lines) - 4), -1):
            candidate = lines[index].strip().casefold().rstrip(",.!:")
            if candidate in common_closings:
                lines[index] = exact_closing
                replaced = True
                break
        if not replaced:
            if lines:
                lines.append("")
            lines.append(exact_closing)
    return "\n".join(lines)


def gmail_draft(args: argparse.Namespace) -> None:
    track_demo_state = getattr(args, "track_demo_state", False)
    if track_demo_state:
        load_reference_workspace_state()
    api = service("gmail", "v1")
    message = EmailMessage()
    to = args.to
    subject = args.subject
    thread_id = args.thread_id
    if args.reply_to_message:
        original = api.users().messages().get(
            userId="me",
            id=args.reply_to_message,
            format="metadata",
            metadataHeaders=["From", "Reply-To", "Subject", "Message-ID", "References"],
        ).execute()
        original_headers = headers(original.get("payload", {}))
        to = to or original_headers.get("reply-to") or original_headers.get("from", "")
        original_subject = original_headers.get("subject", "")
        subject = subject or (original_subject if original_subject.casefold().startswith("re:") else f"Re: {original_subject}")
        message_id = original_headers.get("message-id", "")
        references = " ".join(filter(None, [original_headers.get("references", ""), message_id]))
        if message_id:
            message["In-Reply-To"] = message_id
        if references:
            message["References"] = references
        thread_id = original.get("threadId", thread_id)
    if not to or not subject:
        raise RuntimeError("A draft needs recipients and a subject")
    message["To"] = to
    if args.cc:
        message["Cc"] = args.cc
    message["Subject"] = subject
    message.set_content(normalize_draft_body(args.body, getattr(args, "closing", "")))
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    body: dict[str, Any] = {"message": {"raw": raw}}
    if thread_id:
        body["message"]["threadId"] = thread_id
    result = api.users().drafts().create(userId="me", body=body).execute()
    draft_id = result.get("id", "")
    message_id = result.get("message", {}).get("id", "")
    verified = api.users().drafts().get(userId="me", id=draft_id, format="minimal").execute()
    if verified.get("id") != draft_id:
        raise RuntimeError(f"Gmail draft {draft_id} could not be verified")
    tracked_state = ""
    if track_demo_state:
        try:
            tracked_state = str(record_reference_workspace_draft(draft_id, message_id))
        except Exception as tracking_error:
            try:
                api.users().drafts().delete(userId="me", id=draft_id).execute()
            except Exception as rollback_error:
                raise RuntimeError(
                    f"Draft {draft_id} was created but could not be tracked ({tracking_error}) "
                    f"or rolled back ({rollback_error})"
                ) from tracking_error
            raise RuntimeError(f"Draft tracking failed and draft {draft_id} was rolled back: {tracking_error}") from tracking_error
    emit({
        "status": "drafted",
        "draft_id": draft_id,
        "message_id": message_id,
        "url": f"https://mail.google.com/mail/u/0/#drafts/{message_id}",
        "verified": True,
        "tracked_demo_state": tracked_state,
    })


def drive_search(args: argparse.Namespace) -> None:
    safe = args.query.replace("'", "\\'")
    query = args.query if args.raw_query else f"trashed = false and fullText contains '{safe}'"
    result = service("drive", "v3").files().list(
        q=query,
        orderBy="modifiedTime desc",
        pageSize=args.max,
        fields="files(id,name,mimeType,modifiedTime,webViewLink,owners(displayName,emailAddress),description)",
    ).execute()
    emit(result.get("files", []))


def docs_get(args: argparse.Namespace) -> None:
    doc = service("docs", "v1").documents().get(documentId=args.document_id).execute()
    chunks: list[str] = []
    for block in doc.get("body", {}).get("content", []):
        for element in block.get("paragraph", {}).get("elements", []):
            chunks.append(element.get("textRun", {}).get("content", ""))
    emit({"id": args.document_id, "title": doc.get("title", ""), "text": "".join(chunks)[: args.max_chars]})


def docs_append(args: argparse.Namespace) -> None:
    require_confirm(args, "Docs append")
    api = service("docs", "v1")
    doc = api.documents().get(documentId=args.document_id).execute()
    end_index = max(1, doc.get("body", {}).get("content", [{}])[-1].get("endIndex", 1) - 1)
    api.documents().batchUpdate(
        documentId=args.document_id,
        body={"requests": [{"insertText": {"location": {"index": end_index}, "text": args.text}}]},
    ).execute()
    emit({"status": "appended", "document_id": args.document_id, "characters": len(args.text)})


def docs_replace(args: argparse.Namespace) -> None:
    require_confirm(args, "Docs text replacement")
    result = service("docs", "v1").documents().batchUpdate(
        documentId=args.document_id,
        body={
            "requests": [
                {
                    "replaceAllText": {
                        "containsText": {"text": args.find, "matchCase": args.match_case},
                        "replaceText": args.replace,
                    }
                }
            ]
        },
    ).execute()
    occurrences = sum(
        reply.get("replaceAllText", {}).get("occurrencesChanged", 0)
        for reply in result.get("replies", [])
    )
    emit({"status": "updated", "document_id": args.document_id, "occurrences_changed": occurrences})


def sheets_get(args: argparse.Namespace) -> None:
    result = service("sheets", "v4").spreadsheets().values().get(
        spreadsheetId=args.spreadsheet_id,
        range=args.range,
    ).execute()
    emit({"spreadsheet_id": args.spreadsheet_id, "range": result.get("range"), "values": result.get("values", [])})


def sheets_update(args: argparse.Namespace) -> None:
    require_confirm(args, "Sheets update")
    values = json.loads(args.values)
    if not isinstance(values, list):
        raise RuntimeError("--values must be a JSON array of rows")
    result = service("sheets", "v4").spreadsheets().values().update(
        spreadsheetId=args.spreadsheet_id,
        range=args.range,
        valueInputOption="USER_ENTERED",
        body={"values": values},
    ).execute()
    emit({"status": "updated", **result})


TRACKER_STATUSES = {
    "Not started", "In progress", "Ready for review", "On track",
    "In review", "Awaiting update", "Blocked", "Complete",
}


def sheets_update_lanes(args: argparse.Namespace) -> None:
    """Update tracker lanes by name with validated, named fields."""
    require_confirm(args, "tracker lane update")
    if args.updates:
        updates = json.loads(args.updates)
    elif args.lane and args.status:
        updates = [{"lane": args.lane, "status": args.status}]
    else:
        raise RuntimeError("Use --updates, or use --lane with --status for one lane")
    if not isinstance(updates, list) or not updates:
        raise RuntimeError("--updates must be a non-empty JSON array")
    lanes = [str(item.get("lane", "")).strip() for item in updates if isinstance(item, dict)]
    if len(lanes) != len(updates) or any(not lane for lane in lanes):
        raise RuntimeError("Every tracker update needs a lane")
    if len(set(lanes)) != len(lanes):
        raise RuntimeError("Each tracker lane may be updated only once")
    for item in updates:
        if item.get("status") not in TRACKER_STATUSES:
            raise RuntimeError(f"Invalid status for {item['lane']!r}; use one of {sorted(TRACKER_STATUSES)}")

    api = service("sheets", "v4")
    current = api.spreadsheets().values().get(
        spreadsheetId=args.spreadsheet_id,
        range=f"'{args.sheet}'!A6:H100",
    ).execute().get("values", [])
    row_by_lane = {row[0]: (index, row) for index, row in enumerate(current[1:], start=7) if row}
    missing = [lane for lane in lanes if lane not in row_by_lane]
    if missing:
        raise RuntimeError(f"Tracker lane(s) not found: {missing}")

    data = []
    for item in updates:
        row, existing = row_by_lane[item["lane"]]
        preserved = existing + [""] * (8 - len(existing))
        values = [[
            item["status"], item.get("latest", preserved[3]), item.get("next", preserved[4]),
            item.get("due", preserved[5]), item.get("blocker", preserved[6]), item.get("evidence", preserved[7]),
        ]]
        data.append({"range": f"'{args.sheet}'!C{row}:H{row}", "values": values})
    result = api.spreadsheets().values().batchUpdate(
        spreadsheetId=args.spreadsheet_id,
        body={"valueInputOption": "USER_ENTERED", "data": data},
    ).execute()
    verified = api.spreadsheets().values().batchGet(
        spreadsheetId=args.spreadsheet_id,
        ranges=[item["range"] for item in data],
    ).execute().get("valueRanges", [])
    emit({
        "status": "updated",
        "spreadsheet_id": args.spreadsheet_id,
        "lanes": lanes,
        "updated_rows": result.get("totalUpdatedRows", 0),
        "updated_cells": result.get("totalUpdatedCells", 0),
        "verified_values": [item.get("values", []) for item in verified],
    })


def _slide_text(slide: dict[str, Any]) -> str:
    chunks: list[str] = []
    for element in slide.get("pageElements", []):
        for item in element.get("shape", {}).get("text", {}).get("textElements", []):
            chunks.append(item.get("textRun", {}).get("content", ""))
        for row in element.get("table", {}).get("tableRows", []):
            for cell in row.get("tableCells", []):
                for item in cell.get("text", {}).get("textElements", []):
                    chunks.append(item.get("textRun", {}).get("content", ""))
    return re.sub(r"\n{3,}", "\n\n", "".join(chunks)).strip()


def slides_get(args: argparse.Namespace) -> None:
    deck = service("slides", "v1").presentations().get(presentationId=args.presentation_id).execute()
    slides = [
        {"number": index, "object_id": slide.get("objectId"), "text": _slide_text(slide)[: args.max_chars_per_slide]}
        for index, slide in enumerate(deck.get("slides", []), start=1)
    ]
    emit({"id": args.presentation_id, "title": deck.get("title", ""), "url": f"https://docs.google.com/presentation/d/{args.presentation_id}/edit", "slides": slides})


def slides_replace(args: argparse.Namespace) -> None:
    require_confirm(args, "Slides text replacement")
    api = service("slides", "v1")
    result = api.presentations().batchUpdate(
        presentationId=args.presentation_id,
        body={"requests": [{"replaceAllText": {"containsText": {"text": args.find, "matchCase": args.match_case}, "replaceText": args.replace}}]},
    ).execute()
    replies = result.get("replies", [])
    occurrences = sum(r.get("replaceAllText", {}).get("occurrencesChanged", 0) for r in replies)
    if occurrences < 1:
        raise RuntimeError(f"Slides text was not found: {args.find!r}")
    deck = api.presentations().get(presentationId=args.presentation_id).execute()
    text = "\n".join(_slide_text(slide) for slide in deck.get("slides", []))
    verified = args.replace in text and args.find not in text
    if not verified:
        raise RuntimeError("Slides replacement could not be verified")
    emit({"status": "updated", "presentation_id": args.presentation_id, "occurrences_changed": occurrences, "verified": True})


def _calendar_time(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeError(f"{label} must be an ISO date-time") from exc
    if parsed.tzinfo is None:
        raise RuntimeError(f"{label} must include a UTC offset")
    return parsed


def _event_time(event: dict[str, Any], key: str, fallback: datetime) -> datetime | None:
    value = event.get(key, {})
    if value.get("dateTime"):
        try:
            return datetime.fromisoformat(value["dateTime"].replace("Z", "+00:00"))
        except ValueError:
            return None
    if value.get("date"):
        try:
            return datetime.fromisoformat(value["date"]).replace(tzinfo=fallback.tzinfo)
        except ValueError:
            return None
    return None


def _excluded_event(event: dict[str, Any], event_id: str) -> bool:
    return bool(event_id) and event_id in {event.get("id"), event.get("recurringEventId")}


def _event_blocks_time(event: dict[str, Any]) -> bool:
    return event.get("status") != "cancelled" and event.get("transparency") != "transparent"


def _calendar_window(
    api: Any,
    calendar_id: str,
    start: datetime,
    end: datetime,
    query: str = "",
    max_results: int = 250,
) -> list[dict[str, Any]]:
    if end <= start:
        raise RuntimeError("Calendar window end must be after start")
    request = {
        "calendarId": calendar_id,
        "timeMin": start.isoformat(),
        "timeMax": end.isoformat(),
        "singleEvents": True,
        "orderBy": "startTime",
        "maxResults": max_results,
    }
    if query:
        request["q"] = query
    return api.events().list(**request).execute().get("items", [])


def _calendar_item(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": event.get("id"),
        "recurring_event_id": event.get("recurringEventId"),
        "title": event.get("summary", ""),
        "start": event.get("start", {}),
        "end": event.get("end", {}),
        "status": event.get("status"),
        "transparency": event.get("transparency"),
        "url": event.get("htmlLink", ""),
    }


def calendar_get(args: argparse.Namespace) -> None:
    event = service("calendar", "v3").events().get(
        calendarId=args.calendar,
        eventId=args.event_id,
    ).execute()
    emit(_calendar_item(event))


def calendar_list(args: argparse.Namespace) -> None:
    start = _calendar_time(args.start, "--start")
    end = _calendar_time(args.end, "--end")
    events = _calendar_window(
        service("calendar", "v3"),
        args.calendar,
        start,
        end,
        query=args.query,
        max_results=args.max,
    )
    emit({
        "start": start.isoformat(),
        "end": end.isoformat(),
        "events": [
            _calendar_item(event)
            for event in events
            if not _excluded_event(event, args.exclude_event)
        ],
    })


def _blocking_intervals(
    events: list[dict[str, Any]],
    start: datetime,
    end: datetime,
    exclude_event: str = "",
) -> list[tuple[datetime, datetime, dict[str, Any]]]:
    intervals = []
    for event in events:
        if _excluded_event(event, exclude_event) or not _event_blocks_time(event):
            continue
        event_start = _event_time(event, "start", start)
        event_end = _event_time(event, "end", start)
        if event_start and event_end and event_start < end and event_end > start:
            intervals.append((max(start, event_start), min(end, event_end), event))
    return sorted(intervals, key=lambda item: item[0])


def _ceil_to_minutes(value: datetime, step_minutes: int) -> datetime:
    value = value.replace(second=0, microsecond=0)
    remainder = value.minute % step_minutes
    return value if remainder == 0 else value + timedelta(minutes=step_minutes - remainder)


def calendar_availability(args: argparse.Namespace) -> None:
    start = _calendar_time(args.start, "--start")
    end = _calendar_time(args.end, "--end")
    if args.duration_minutes < 1 or args.step_minutes < 1 or args.limit < 1:
        raise RuntimeError("Duration, step, and limit must be positive")
    api = service("calendar", "v3")
    events = _calendar_window(api, args.calendar, start, end)
    intervals = _blocking_intervals(events, start, end, args.exclude_event)

    merged: list[tuple[datetime, datetime]] = []
    for busy_start, busy_end, _event in intervals:
        if merged and busy_start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], busy_end))
        else:
            merged.append((busy_start, busy_end))

    duration = timedelta(minutes=args.duration_minutes)
    step = timedelta(minutes=args.step_minutes)
    slots = []
    cursor = _ceil_to_minutes(start, args.step_minutes)

    def add_slots(gap_end: datetime) -> None:
        nonlocal cursor
        while cursor + duration <= gap_end and len(slots) < args.limit:
            slots.append({"start": cursor.isoformat(), "end": (cursor + duration).isoformat()})
            cursor += step

    for busy_start, busy_end in merged:
        add_slots(busy_start)
        cursor = _ceil_to_minutes(max(cursor, busy_end), args.step_minutes)
        if len(slots) >= args.limit:
            break
    if len(slots) < args.limit:
        add_slots(end)

    emit({
        "start": start.isoformat(),
        "end": end.isoformat(),
        "duration_minutes": args.duration_minutes,
        "slots": slots,
        "busy": [
            {**_calendar_item(event), "start": busy_start.isoformat(), "end": busy_end.isoformat()}
            for busy_start, busy_end, event in intervals
        ],
    })


def calendar_create(args: argparse.Namespace) -> None:
    require_confirm(args, "Calendar event creation")
    event: dict[str, Any] = {
        "summary": args.title,
        "start": {"dateTime": args.start},
        "end": {"dateTime": args.end},
    }
    if args.description:
        event["description"] = args.description
    if args.attendees:
        event["attendees"] = [{"email": email.strip()} for email in args.attendees.split(",") if email.strip()]
    result = service("calendar", "v3").events().insert(
        calendarId=args.calendar,
        body=event,
        sendUpdates="all" if args.attendees else "none",
    ).execute()
    emit({"status": "created", "id": result.get("id"), "url": result.get("htmlLink")})


def _same_instant(actual: str, expected: str) -> bool:
    return datetime.fromisoformat(actual.replace("Z", "+00:00")) == datetime.fromisoformat(expected.replace("Z", "+00:00"))


def calendar_move(args: argparse.Namespace) -> None:
    """Move one existing event while preserving all other event details."""
    require_confirm(args, "Calendar event move")
    api = service("calendar", "v3")
    current = api.events().get(calendarId=args.calendar, eventId=args.event_id).execute()
    requested_start = _calendar_time(args.start, "--start")
    requested_end = _calendar_time(args.end, "--end")
    if requested_end <= requested_start:
        raise RuntimeError("Calendar move end must be after start")
    if not getattr(args, "allow_conflict", False):
        events = _calendar_window(api, args.calendar, requested_start, requested_end)
        conflicts = _blocking_intervals(events, requested_start, requested_end, args.event_id)
        if conflicts:
            detail = "; ".join(
                f"{event.get('summary', 'Untitled event')} ({busy_start.isoformat()} to {busy_end.isoformat()})"
                for busy_start, busy_end, event in conflicts
            )
            raise RuntimeError(f"Calendar move conflicts with existing event(s): {detail}")
    start = {"dateTime": args.start}
    end = {"dateTime": args.end}
    if current.get("start", {}).get("timeZone"):
        start["timeZone"] = current["start"]["timeZone"]
    if current.get("end", {}).get("timeZone"):
        end["timeZone"] = current["end"]["timeZone"]
    api.events().patch(
        calendarId=args.calendar,
        eventId=args.event_id,
        body={"start": start, "end": end},
        sendUpdates=args.send_updates,
    ).execute()
    verified = api.events().get(calendarId=args.calendar, eventId=args.event_id).execute()
    actual_start = verified.get("start", {}).get("dateTime", "")
    actual_end = verified.get("end", {}).get("dateTime", "")
    if not actual_start or not actual_end or not _same_instant(actual_start, args.start) or not _same_instant(actual_end, args.end):
        raise RuntimeError("Calendar move could not be verified")
    emit({
        "status": "moved",
        "id": verified.get("id"),
        "title": verified.get("summary"),
        "start": verified.get("start"),
        "end": verified.get("end"),
        "url": verified.get("htmlLink"),
        "verified": True,
    })


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Focused Google Workspace actions")
    groups = parser.add_subparsers(dest="resource", required=True)

    gmail = groups.add_parser("gmail").add_subparsers(dest="action", required=True)
    p = gmail.add_parser("get")
    p.add_argument("message_id")
    p.add_argument("--max-chars", type=int, default=12000)
    p.set_defaults(func=gmail_get)
    p = gmail.add_parser("thread")
    p.add_argument("thread_id")
    p.add_argument("--max-messages", type=int, default=12)
    p.add_argument("--max-chars", type=int, default=8000)
    p.set_defaults(func=gmail_thread)
    p = gmail.add_parser("draft")
    p.add_argument("--to", default="")
    p.add_argument("--cc", default="")
    p.add_argument("--subject", default="")
    p.add_argument("--body", required=True)
    p.add_argument("--closing", default="", help="Ensure an exact final closing while preserving any following signature")
    p.add_argument("--thread-id", default="")
    p.add_argument("--reply-to-message", default="", help="Build a correctly threaded reply draft")
    p.add_argument("--track-demo-state", action="store_true", help="Record this draft for reference-workspace cleanup")
    p.set_defaults(func=gmail_draft)

    drive = groups.add_parser("drive").add_subparsers(dest="action", required=True)
    p = drive.add_parser("search")
    p.add_argument("query")
    p.add_argument("--max", type=int, default=10)
    p.add_argument("--raw-query", action="store_true")
    p.set_defaults(func=drive_search)

    docs = groups.add_parser("docs").add_subparsers(dest="action", required=True)
    p = docs.add_parser("get")
    p.add_argument("document_id")
    p.add_argument("--max-chars", type=int, default=30000)
    p.set_defaults(func=docs_get)
    p = docs.add_parser("append")
    p.add_argument("document_id")
    p.add_argument("--text", required=True)
    p.add_argument("--confirm", action="store_true")
    p.set_defaults(func=docs_append)
    p = docs.add_parser("replace-text")
    p.add_argument("document_id")
    p.add_argument("--find", required=True)
    p.add_argument("--replace", required=True)
    p.add_argument("--match-case", action="store_true")
    p.add_argument("--confirm", action="store_true")
    p.set_defaults(func=docs_replace)

    sheets = groups.add_parser("sheets").add_subparsers(dest="action", required=True)
    p = sheets.add_parser("get")
    p.add_argument("spreadsheet_id")
    p.add_argument("range")
    p.set_defaults(func=sheets_get)
    p = sheets.add_parser("update")
    p.add_argument("spreadsheet_id")
    p.add_argument("range")
    p.add_argument("--values", required=True)
    p.add_argument("--confirm", action="store_true")
    p.set_defaults(func=sheets_update)
    p = sheets.add_parser("update-lanes")
    p.add_argument("spreadsheet_id")
    p.add_argument("--sheet", default="Campaign Lanes")
    p.add_argument("--updates", help="JSON array of named lane updates")
    p.add_argument("--lane", help="Lane name for a single update")
    p.add_argument("--status", help="Status for a single update")
    p.add_argument("--confirm", action="store_true")
    p.set_defaults(func=sheets_update_lanes)

    slides = groups.add_parser("slides").add_subparsers(dest="action", required=True)
    p = slides.add_parser("get")
    p.add_argument("presentation_id")
    p.add_argument("--max-chars-per-slide", type=int, default=4000)
    p.set_defaults(func=slides_get)
    p = slides.add_parser("replace-text")
    p.add_argument("presentation_id")
    p.add_argument("--find", required=True)
    p.add_argument("--replace", required=True)
    p.add_argument("--match-case", action="store_true")
    p.add_argument("--confirm", action="store_true")
    p.set_defaults(func=slides_replace)

    calendar = groups.add_parser("calendar").add_subparsers(dest="action", required=True)
    p = calendar.add_parser("get")
    p.add_argument("event_id")
    p.add_argument("--calendar", default="primary")
    p.set_defaults(func=calendar_get)
    p = calendar.add_parser("list")
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--query", default="")
    p.add_argument("--exclude-event", default="")
    p.add_argument("--max", type=int, default=250)
    p.add_argument("--calendar", default="primary")
    p.set_defaults(func=calendar_list)
    p = calendar.add_parser("availability")
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--duration-minutes", type=int, required=True)
    p.add_argument("--step-minutes", type=int, default=15)
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--exclude-event", default="")
    p.add_argument("--calendar", default="primary")
    p.set_defaults(func=calendar_availability)
    p = calendar.add_parser("create")
    p.add_argument("--title", required=True)
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--description", default="")
    p.add_argument("--attendees", default="")
    p.add_argument("--calendar", default="primary")
    p.add_argument("--confirm", action="store_true")
    p.set_defaults(func=calendar_create)
    p = calendar.add_parser("move")
    p.add_argument("event_id")
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--calendar", default="primary")
    p.add_argument("--send-updates", choices=("none", "all", "externalOnly"), default="none")
    p.add_argument("--allow-conflict", action="store_true", help="Permit an explicitly requested overlapping move")
    p.add_argument("--confirm", action="store_true")
    p.set_defaults(func=calendar_move)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        args.func(args)
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
