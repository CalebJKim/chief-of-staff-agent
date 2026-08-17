#!/usr/bin/env python
"""Verify authorized Workspace APIs without printing private content."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

MIMES = {
    "docs": "application/vnd.google-apps.document",
    "sheets": "application/vnd.google-apps.spreadsheet",
    "slides": "application/vnd.google-apps.presentation",
}


def home() -> Path:
    if os.environ.get("HERMES_HOME"):
        return Path(os.environ["HERMES_HOME"]).expanduser()
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "hermes"
    return Path.home() / ".hermes"


def main() -> int:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    token = home() / "google_token.json"
    creds = Credentials.from_authorized_user_file(str(token))
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    results: dict[str, Any] = {}

    def check(name: str, fn: Any) -> Any:
        try:
            value = fn()
            results[name] = {"ok": True, **value}
            return value
        except Exception as exc:
            results[name] = {"ok": False, "error_type": type(exc).__name__, "error": str(exc)[:400]}
            return None

    gmail = build("gmail", "v1", credentials=creds, cache_discovery=False)
    check("gmail", lambda: {"sample_count": len(gmail.users().messages().list(userId="me", maxResults=1).execute().get("messages", []))})

    calendar = build("calendar", "v3", credentials=creds, cache_discovery=False)
    calendars: list[dict[str, Any]] = []

    def calendar_check() -> dict[str, int]:
        response = calendar.calendarList().list(showHidden=False).execute()
        calendars.extend(response.get("items", []))
        now = datetime.now(timezone.utc)
        count = 0
        for item in calendars:
            events = calendar.events().list(
                calendarId=item["id"],
                timeMin=now.isoformat(),
                timeMax=(now + timedelta(days=30)).isoformat(),
                singleEvents=True,
                showDeleted=False,
                maxResults=50,
            ).execute()
            count += len(events.get("items", []))
        return {"calendar_count": len(calendars), "next_30d_event_count": count}

    check("calendar", calendar_check)

    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    check("drive", lambda: {"sample_count": len(drive.files().list(q="trashed = false", pageSize=10, fields="files(id)").execute().get("files", []))})

    for api_name, mime in MIMES.items():
        found = drive.files().list(
            q=f"trashed = false and mimeType = '{mime}'",
            pageSize=1,
            fields="files(id)",
        ).execute().get("files", [])
        if not found:
            results[api_name] = {"ok": True, "sample": "no_file_available"}
            continue
        file_id = found[0]["id"]
        if api_name == "docs":
            api = build("docs", "v1", credentials=creds, cache_discovery=False)
            check(api_name, lambda: {"sample": "read", "structural_items": len(api.documents().get(documentId=file_id).execute().get("body", {}).get("content", []))})
        elif api_name == "sheets":
            api = build("sheets", "v4", credentials=creds, cache_discovery=False)
            check(api_name, lambda: {"sample": "read", "tab_count": len(api.spreadsheets().get(spreadsheetId=file_id, fields="sheets.properties.sheetId").execute().get("sheets", []))})
        else:
            api = build("slides", "v1", credentials=creds, cache_discovery=False)
            check(api_name, lambda: {"sample": "read", "slide_count": len(api.presentations().get(presentationId=file_id, fields="slides.objectId").execute().get("slides", []))})

    ok = all(item.get("ok") for item in results.values())
    print(json.dumps({"ok": ok, "services": results}, separators=(",", ":")))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
