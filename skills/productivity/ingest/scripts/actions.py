#!/usr/bin/env python
"""Focused Google Workspace reads and guarded mutations for chief-of-staff workflows."""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from email.message import EmailMessage
from pathlib import Path
from typing import Any


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


def gmail_draft(args: argparse.Namespace) -> None:
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
    message.set_content(args.body)
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    body: dict[str, Any] = {"message": {"raw": raw}}
    if thread_id:
        body["message"]["threadId"] = thread_id
    result = api.users().drafts().create(userId="me", body=body).execute()
    emit({"status": "drafted", "draft_id": result.get("id"), "message_id": result.get("message", {}).get("id")})


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


TRACKER_STATUSES = {"On track", "In review", "Awaiting update", "Blocked", "Complete"}


def sheets_update_lanes(args: argparse.Namespace) -> None:
    """Update tracker lanes by name with validated, named fields."""
    require_confirm(args, "tracker lane update")
    updates = json.loads(args.updates)
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
    row_by_lane = {row[0]: index for index, row in enumerate(current[1:], start=7) if row}
    missing = [lane for lane in lanes if lane not in row_by_lane]
    if missing:
        raise RuntimeError(f"Tracker lane(s) not found: {missing}")

    data = []
    for item in updates:
        row = row_by_lane[item["lane"]]
        values = [[
            item["status"], item.get("latest", ""), item.get("next", ""),
            item.get("due", ""), item.get("blocker", ""), item.get("evidence", ""),
        ]]
        data.append({"range": f"'{args.sheet}'!C{row}:H{row}", "values": values})
    result = api.spreadsheets().values().batchUpdate(
        spreadsheetId=args.spreadsheet_id,
        body={"valueInputOption": "USER_ENTERED", "data": data},
    ).execute()
    emit({"status": "updated", "spreadsheet_id": args.spreadsheet_id, "lanes": lanes, "updated_rows": result.get("totalUpdatedRows", 0), "updated_cells": result.get("totalUpdatedCells", 0)})


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
    result = service("slides", "v1").presentations().batchUpdate(
        presentationId=args.presentation_id,
        body={"requests": [{"replaceAllText": {"containsText": {"text": args.find, "matchCase": args.match_case}, "replaceText": args.replace}}]},
    ).execute()
    replies = result.get("replies", [])
    occurrences = sum(r.get("replaceAllText", {}).get("occurrencesChanged", 0) for r in replies)
    emit({"status": "updated", "presentation_id": args.presentation_id, "occurrences_changed": occurrences})


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
    p.add_argument("--thread-id", default="")
    p.add_argument("--reply-to-message", default="", help="Build a correctly threaded reply draft")
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
    p.add_argument("--updates", required=True, help="JSON array of named lane updates")
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
    p = calendar.add_parser("create")
    p.add_argument("--title", required=True)
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--description", default="")
    p.add_argument("--attendees", default="")
    p.add_argument("--calendar", default="primary")
    p.add_argument("--confirm", action="store_true")
    p.set_defaults(func=calendar_create)
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
