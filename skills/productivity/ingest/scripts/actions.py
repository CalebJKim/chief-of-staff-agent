#!/usr/bin/env python
"""Focused Google Workspace reads and guarded mutations for chief-of-staff workflows."""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import socket
import sys
import time as time_module
import unicodedata
from datetime import date, datetime, time, timedelta
from difflib import SequenceMatcher
from email.message import EmailMessage
from email.utils import getaddresses
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


REFERENCE_WORKSPACE_MARKER = "chief-of-staff-reference-workspace-v1"
REFERENCE_WORKSPACE_STATE_FILE = "chief-of-staff-workspace-state.json"
GOOGLE_HTTP_TIMEOUT_SECONDS = 30
GOOGLE_READ_ATTEMPTS = 2
GOOGLE_TRANSIENT_STATUSES = {408, 409, 425, 429, 500, 502, 503, 504}
GOOGLE_TEMPORARY_USER_MESSAGE = (
    "Google Workspace timed out. This is a temporary Google-side issue; please try again later."
)


class DraftValidationError(RuntimeError):
    """A recoverable content rejection that occurs before Gmail is mutated."""


class CalendarValidationError(RuntimeError):
    """A recoverable evidence rejection that occurs before Calendar is mutated."""


class GoogleTransientError(RuntimeError):
    """A bounded Google request exhausted its safe retries."""


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
    from google_auth_httplib2 import AuthorizedHttp
    import httplib2

    authorized_http = AuthorizedHttp(
        credentials(),
        http=httplib2.Http(timeout=GOOGLE_HTTP_TIMEOUT_SECONDS),
    )
    return build(name, version, http=authorized_http, cache_discovery=False)


def is_transient_google_error(exc: Exception) -> bool:
    status = getattr(getattr(exc, "resp", None), "status", None)
    if status in GOOGLE_TRANSIENT_STATUSES:
        return True
    if isinstance(exc, (TimeoutError, socket.timeout, ConnectionError)):
        return True
    message = str(exc).casefold()
    return any(
        marker in message
        for marker in (
            "timed out",
            "timeout",
            "temporarily unavailable",
            "connection reset",
            "remote end closed",
        )
    )


def execute_google_read(request: Any, operation: str) -> Any:
    """Execute an idempotent Google read with a small, bounded retry budget."""
    for attempt in range(GOOGLE_READ_ATTEMPTS):
        try:
            return request.execute()
        except Exception as exc:
            if not is_transient_google_error(exc):
                raise
            if attempt == GOOGLE_READ_ATTEMPTS - 1:
                raise GoogleTransientError(
                    f"{operation} failed after {GOOGLE_READ_ATTEMPTS} attempts: {exc}"
                ) from exc
            time_module.sleep(1)
    raise GoogleTransientError(f"{operation} failed without returning a response")


def temporary_google_result(exc: Exception) -> dict[str, Any]:
    return {
        "status": "temporarily_unavailable",
        "ok": False,
        "retryable": True,
        "google_side": True,
        "user_message": GOOGLE_TEMPORARY_USER_MESSAGE,
        "reason": str(exc),
    }


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
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def headers(payload: dict[str, Any]) -> dict[str, str]:
    return {h.get("name", "").lower(): h.get("value", "") for h in payload.get("headers", [])}


def gmail_get(args: argparse.Namespace) -> None:
    api = service("gmail", "v1")
    msg = execute_google_read(
        api.users().messages().get(userId="me", id=args.message_id, format="full"),
        "Read Gmail message",
    )
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
    thread = execute_google_read(
        api.users().threads().get(userId="me", id=args.thread_id, format="full"),
        "Read Gmail thread",
    )
    output = []
    for msg in thread.get("messages", [])[-args.max_messages :]:
        if "DRAFT" in msg.get("labelIds", []):
            continue
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


def gmail_search(args: argparse.Namespace) -> None:
    api = service("gmail", "v1")
    query_parts = [args.query.strip()]
    sender = getattr(args, "sender", "").strip()
    subject = getattr(args, "subject", "").strip()
    if sender:
        query_parts.append(f"from:{sender}")
    if subject:
        escaped_subject = subject.replace('"', r'\"')
        query_parts.append(f'subject:"{escaped_subject}"')
    query_parts.extend(str(value).strip() for value in getattr(args, "extra", []) if str(value).strip())
    query_parts.append("-in:drafts")
    query = " ".join(part for part in query_parts if part)
    if not query:
        raise RuntimeError("Gmail search requires a query, sender, or subject")
    result = execute_google_read(
        api.users().messages().list(
            userId="me",
            q=query,
            maxResults=args.max,
        ),
        "Search Gmail",
    )
    messages = []
    for item in result.get("messages", []):
        message = execute_google_read(
            api.users().messages().get(
                userId="me",
                id=item.get("id", ""),
                format="metadata",
                metadataHeaders=["From", "To", "Cc", "Subject", "Date", "Message-ID"],
            ),
            "Read Gmail search result",
        )
        if "DRAFT" in message.get("labelIds", []):
            continue
        message_headers = headers(message.get("payload", {}))
        messages.append({
            "id": message.get("id", ""),
            "thread_id": message.get("threadId", ""),
            "from": message_headers.get("from", ""),
            "to": message_headers.get("to", ""),
            "cc": message_headers.get("cc", ""),
            "subject": message_headers.get("subject", ""),
            "date": message_headers.get("date", ""),
            "snippet": message.get("snippet", "")[: args.max_chars],
        })
    emit({"query": query, "messages": messages})


def _valid_email_address(address: str) -> bool:
    return bool(re.fullmatch(r"[^@\s<>]+@(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,63}", address.strip()))


def _validated_recipients(value: str, label: str) -> list[tuple[str, str]]:
    parsed = [(name.strip(), address.strip()) for name, address in getaddresses([value]) if name.strip() or address.strip()]
    if not parsed or any(not _valid_email_address(address) for _name, address in parsed):
        raise RuntimeError(f"{label} contains an invalid email address")
    return parsed


def _format_recipient(name: str, address: str) -> str:
    return f"{name} <{address}>" if name else address


def _reply_evidence(api: Any, message_id: str) -> dict[str, Any]:
    if not message_id.strip():
        raise RuntimeError("A reply draft requires a non-empty Gmail message ID")
    original = execute_google_read(
        api.users().messages().get(
            userId="me",
            id=message_id,
            format="metadata",
            metadataHeaders=["From", "Reply-To", "Subject", "Message-ID", "References"],
        ),
        "Read Gmail reply evidence",
    )
    if "DRAFT" in original.get("labelIds", []):
        raise DraftValidationError(
            f"Gmail message {message_id} is itself a draft; choose a received source message. "
            "No draft was created."
        )
    original_headers = headers(original.get("payload", {}))
    recipient = original_headers.get("reply-to") or original_headers.get("from", "")
    _validated_recipients(recipient, f"Sender on Gmail message {message_id}")
    subject = original_headers.get("subject", "").strip()
    if not subject:
        raise RuntimeError(f"Gmail message {message_id} has no subject")
    return {
        "message_id": message_id,
        "thread_id": original.get("threadId", ""),
        "recipient": recipient,
        "subject": subject if subject.casefold().startswith("re:") else f"Re: {subject}",
        "message_id_header": original_headers.get("message-id", ""),
        "references": original_headers.get("references", ""),
    }


def _gmail_profile_address(api: Any) -> str:
    profile = execute_google_read(
        api.users().getProfile(userId="me"),
        "Read Gmail profile",
    )
    address = str(profile.get("emailAddress", "")).strip()
    if not _valid_email_address(address):
        raise RuntimeError("Gmail profile did not return a valid signed-in account address")
    return address.casefold()


def _require_external_reply_recipient(
    evidence: dict[str, Any],
    signed_in_address: str,
    label: str,
) -> None:
    recipients = _validated_recipients(str(evidence["recipient"]), label)
    if any(address.casefold() == signed_in_address for _name, address in recipients):
        raise DraftValidationError(
            f"{label} resolves to the signed-in Gmail account; choose a received message from the "
            "intended external recipient. No draft was created."
        )


def validate_calendar_date_evidence(
    api: Any,
    message_id: str,
    target_day: date,
) -> None:
    """Require a received Gmail message to contain the requested target date."""
    try:
        evidence = _reply_evidence(api, message_id)
        _require_external_reply_recipient(
            evidence,
            _gmail_profile_address(api),
            "Calendar date evidence",
        )
    except DraftValidationError as exc:
        raise CalendarValidationError(str(exc)) from exc
    message = execute_google_read(
        api.users().messages().get(userId="me", id=message_id, format="full"),
        "Read Gmail calendar evidence",
    )
    message_headers = headers(message.get("payload", {}))
    evidence_text = "\n".join(
        (message_headers.get("subject", ""), decode_body(message.get("payload", {})))
    )
    month_day = f"{target_day.strftime('%B')} {target_day.day}"
    weekday = target_day.strftime("%A")
    accepted = (
        target_day.isoformat(),
        f"{month_day}, {target_day.year}",
        f"{weekday}, {month_day}",
        f"{weekday}, {month_day}, {target_day.year}",
        f"{target_day.month}/{target_day.day}/{target_day.year}",
    )
    comparison = _draft_comparison_text(evidence_text)
    if not any(_draft_comparison_text(value) in comparison for value in accepted):
        raise CalendarValidationError(
            f"Gmail date evidence does not contain target date {target_day.isoformat()}; "
            "choose the scheduling message that states the requested date. No event was moved."
        )


def validate_user_directed_date(request_text: str, target_day: date) -> None:
    """Require the current user request to state the target date or weekday."""
    if not request_text.strip():
        raise CalendarValidationError(
            "--user-directed-date requires --user-request-text containing the current user request. "
            "No event was moved."
        )
    month_day = f"{target_day.strftime('%B')} {target_day.day}"
    weekday = target_day.strftime("%A")
    accepted = (
        target_day.isoformat(),
        f"{month_day}, {target_day.year}",
        f"{weekday}, {month_day}",
        f"{weekday}, {month_day}, {target_day.year}",
        f"{target_day.month}/{target_day.day}/{target_day.year}",
        weekday,
    )
    comparison = _draft_comparison_text(request_text)
    if not any(_draft_comparison_text(value) in comparison for value in accepted):
        raise CalendarValidationError(
            f"The current user request does not contain target date {target_day.isoformat()} "
            f"or weekday {weekday}; use Gmail date evidence instead. No event was moved."
        )


def normalize_cli_text(value: str) -> str:
    """Render common shell-friendly escapes used in multi-line Workspace text."""
    normalized = value.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\r", "\n")
    for escaped, character in {
        r"\u2011": "‑",
        r"\u2012": "‒",
        r"\u2013": "–",
        r"\u2014": "—",
        r"\u2212": "−",
        r"\u00a0": " ",
        r"\u2022": "•",
    }.items():
        normalized = normalized.replace(escaped, character)
    return normalized


def normalize_draft_body(value: str, closing: str = "", exact_final: bool = False) -> str:
    """Accept shell-friendly escaped line breaks and apply an optional exact closing."""
    normalized = normalize_cli_text(value)
    lines = [line.rstrip() for line in normalized.splitlines()]
    while lines and not lines[-1]:
        lines.pop()
    if closing:
        exact_closing = closing.strip()
        common_closings = {"thanks", "thank you", "best", "best regards", "regards", "sincerely"}
        replaced = False
        for index in range(len(lines) - 1, max(-1, len(lines) - 4), -1):
            candidate = lines[index].strip().casefold().rstrip(",.!:")
            if candidate in common_closings:
                lines[index] = exact_closing
                if exact_final:
                    lines = lines[: index + 1]
                if index > 0 and lines[index - 1]:
                    lines.insert(index, "")
                replaced = True
                break
        if not replaced and lines:
            inline_closing = re.search(
                r"(?i)(?:^|\s+)(?:thanks|thank you|best|best regards|regards|sincerely)\s*[,.!:]?\s*$",
                lines[-1],
            )
            if inline_closing:
                preceding_text = lines[-1][: inline_closing.start()].rstrip()
                if preceding_text:
                    lines[-1] = preceding_text
                    lines.append("")
                    lines.append(exact_closing)
                else:
                    lines[-1] = exact_closing
                replaced = True
        if not replaced:
            if lines:
                lines.append("")
            lines.append(exact_closing)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines))


def _draft_comparison_text(value: str) -> str:
    """Normalize harmless typography differences for required-fact checks."""
    for escaped in (r"\u2011", r"\u2012", r"\u2013", r"\u2014", r"\u2212"):
        value = value.replace(escaped, "-")
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"[\u2010-\u2015\u2212]", "-", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def validate_draft_content(
    body: str,
    closing: str = "",
    required_facts: list[str] | None = None,
    minimum_words: int = 1,
) -> list[str]:
    """Reject empty/closing-only drafts and verify caller-supplied evidence facts."""
    if minimum_words < 1:
        raise RuntimeError("Draft minimum word count must be positive")

    nonempty_lines = [line.strip() for line in body.splitlines() if line.strip()]
    common_closings = {"thanks", "thank you", "best", "best regards", "regards", "sincerely"}
    if closing.strip():
        common_closings.add(closing.strip().casefold().rstrip(",.!:"))
    if nonempty_lines and nonempty_lines[-1].casefold().rstrip(",.!:") in common_closings:
        nonempty_lines.pop()

    if nonempty_lines:
        first_line = nonempty_lines[0]
        first_words = re.findall(r"[^\W_]+(?:['’-][^\W_]+)*", first_line, flags=re.UNICODE)
        inline_salutation = re.match(
            r"(?i)^(?:hi|hello|dear)\s+[^,:.!?]{1,80}[,:]\s*(.*)$",
            first_line,
        )
        standalone_salutation = bool(re.fullmatch(
            r"(?i)(?:hi|hello|dear)(?:\s+[^\s,:.!?]+){1,4}[,:]?",
            first_line,
        ))
        looks_like_name_greeting = (
            first_line.endswith((',', ':'))
            and len(first_words) <= 8
            and not re.search(r"[.!?]", first_line)
        )
        if inline_salutation and inline_salutation.group(1).strip():
            nonempty_lines[0] = inline_salutation.group(1).strip()
        elif inline_salutation or standalone_salutation or looks_like_name_greeting:
            nonempty_lines.pop(0)

    substantive_text = " ".join(nonempty_lines)
    substantive_words = re.findall(
        r"[^\W_]+(?:['’-][^\W_]+)*",
        substantive_text,
        flags=re.UNICODE,
    )
    if len(substantive_words) < minimum_words:
        raise DraftValidationError(
            "Draft body has no substantive message before its closing; "
            f"include at least {minimum_words} content words. No draft was created."
        )

    checked_facts: list[str] = []
    comparison_body = _draft_comparison_text(body)
    for fact in required_facts or []:
        fact = fact.strip()
        if not fact:
            raise DraftValidationError("A required draft fact cannot be empty; no draft was created")
        if _draft_comparison_text(fact) not in comparison_body:
            raise DraftValidationError(
                f"Draft body is missing required verified fact {fact!r}; no draft was created"
            )
        checked_facts.append(fact)
    return checked_facts


def _clock_expression(expected: str, *, optional_meridiem: bool = False) -> str:
    match = re.fullmatch(r"(\d{1,2}):(\d{2})\s*(AM|PM)", expected.strip().upper())
    if not match:
        return re.escape(_draft_comparison_text(expected).upper())
    hour, minute, meridiem = match.groups()
    minute_expression = rf"(?::{minute})?" if minute == "00" else rf":{minute}"
    meridiem_expression = rf"(?:\s*{meridiem})?" if optional_meridiem else rf"\s*{meridiem}"
    return rf"(?<!\d){int(hour)}{minute_expression}{meridiem_expression}(?!\w)"


def _body_mentions_interval(body: str, start: str, end: str) -> bool:
    """Require the live start and end to be expressed as one interval."""
    comparison_body = _draft_comparison_text(body).upper()
    start_meridiem = start.strip().upper().rsplit(" ", 1)[-1]
    end_meridiem = end.strip().upper().rsplit(" ", 1)[-1]
    start_expression = _clock_expression(
        start,
        optional_meridiem=start_meridiem == end_meridiem,
    )
    end_expression = _clock_expression(end)
    connector = (
        r"(?:\s*(?:-|TO|UNTIL|THROUGH)\s*|"
        r"\s*(?:,?\s*AND\s+)?(?:ENDS?|ENDING)\s+AT\s*)"
    )
    return bool(re.search(start_expression + connector + end_expression, comparison_body))


def validate_calendar_confirmation_content(
    body: str,
    event: dict[str, Any],
    zone: ZoneInfo,
) -> list[str]:
    """Require a draft to contain the material facts from one live timed event."""
    title = str(event.get("summary", "")).strip()
    start_value = str(event.get("start", {}).get("dateTime", "")).strip()
    end_value = str(event.get("end", {}).get("dateTime", "")).strip()
    if not title or not start_value or not end_value:
        raise RuntimeError(
            "Calendar confirmation verification requires a titled, timed event; no draft was created"
        )
    display = _calendar_interval_display(start_value, end_value, zone)
    event_day = _parse_date(display["date"], "Calendar confirmation date")
    month_day = f"{event_day.strftime('%B')} {event_day.day}"
    date_alternatives = [
        display["date"],
        month_day,
        f"{month_day}, {event_day.year}",
        f"{display['weekday']}, {month_day}",
        f"{display['weekday']}, {month_day}, {event_day.year}",
    ]
    requirements = [
        ("title", [title], title),
        ("date", date_alternatives, display["date"]),
    ]
    comparison_body = _draft_comparison_text(body)
    checked: list[str] = []
    for label, alternatives, reported_value in requirements:
        matched = any(_draft_comparison_text(value) in comparison_body for value in alternatives if value)
        if not matched:
            raise DraftValidationError(
                f"Draft body is missing verified Calendar {label} {reported_value!r}; no draft was created"
            )
        checked.append(reported_value)
    start_time = display["start_time"]
    end_time = display["end_time"]
    if not _body_mentions_interval(body, start_time, end_time):
        raise DraftValidationError(
            "Draft body is missing the verified Calendar interval "
            f"{start_time!r} through {end_time!r}; express the new start and end together. "
            "No draft was created"
        )
    checked.extend([start_time, end_time])
    timezone_values = [display["timezone_abbreviation"], display["timezone"]]
    if not any(_draft_comparison_text(value) in comparison_body for value in timezone_values if value):
        raise DraftValidationError(
            "Draft body is missing verified Calendar timezone "
            f"{display['timezone_abbreviation']!r}; no draft was created"
        )
    checked.append(display["timezone_abbreviation"])
    return checked


def looks_like_calendar_confirmation(body: str) -> bool:
    """Detect a dated, timed calendar confirmation without relying on workspace terms."""
    has_date = bool(re.search(
        r"\b(?:\d{4}-\d{2}-\d{2}|"
        r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)|"
        r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)(?:,)?\s+"
        r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}|"
        r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2})\b",
        body,
        flags=re.IGNORECASE,
    ))
    has_time = bool(re.search(
        r"\b(?:\d{1,2}(?::\d{2})?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
        r"\s*(?:AM|PM)\b",
        body,
        flags=re.IGNORECASE,
    ))
    timezone_tokens = re.findall(r"\b[A-Z]{2,5}\b", body)
    has_timezone = any(token not in {"AM", "PM"} for token in timezone_tokens)
    return has_date and has_time and has_timezone


def calendar_verification_event_id(body: str, requested_event_id: str) -> str:
    """Use Calendar verification only for a body that actually confirms a schedule."""
    event_id = requested_event_id.strip()
    if not looks_like_calendar_confirmation(body):
        return ""
    if not event_id:
        raise DraftValidationError(
            "This looks like a Calendar confirmation, so --verify-calendar-event is required "
            "to check the live title, date, times, and timezone before drafting. No draft was created."
        )
    return event_id


def matching_tracked_draft(
    api: Any,
    tracked_drafts: list[dict[str, Any]],
    to: str,
    cc: str,
    subject: str,
    body: str,
    thread_id: str,
) -> dict[str, Any] | None:
    """Return an identical tracked Gmail draft so retries remain idempotent."""
    expected_to = {
        address.casefold()
        for _name, address in _validated_recipients(to, "Expected To header")
    }
    expected_cc = (
        {
            address.casefold()
            for _name, address in _validated_recipients(cc, "Expected Cc header")
        }
        if cc else set()
    )
    for tracked in tracked_drafts:
        draft_id = str(tracked.get("id", "")).strip()
        if not draft_id:
            continue
        try:
            draft = execute_google_read(
                api.users().drafts().get(
                    userId="me",
                    id=draft_id,
                    format="full",
                ),
                "Read tracked Gmail draft",
            )
        except Exception as exc:
            status = getattr(getattr(exc, "resp", None), "status", None)
            if status in {404, 410}:
                continue
            raise
        message = draft.get("message", {})
        message_headers = headers(message.get("payload", {}))
        try:
            actual_to = {
                address.casefold()
                for _name, address in _validated_recipients(
                    message_headers.get("to", ""),
                    "Saved To header",
                )
            }
            actual_cc = (
                {
                    address.casefold()
                    for _name, address in _validated_recipients(
                        message_headers.get("cc", ""),
                        "Saved Cc header",
                    )
                }
                if message_headers.get("cc") else set()
            )
        except RuntimeError:
            continue
        if (
            expected_to == actual_to
            and expected_cc == actual_cc
            and message_headers.get("subject", "") == subject
            and decode_body(message.get("payload", {})) == body.strip()
            and (not thread_id or message.get("threadId") == thread_id)
        ):
            return draft
    return None


def calendar_draft_confirmation_markdown(
    event: dict[str, Any],
    zone: ZoneInfo,
    to: str,
    cc: str,
    draft_url: str,
) -> str:
    """Build a generic final response from verified Calendar and Gmail state."""
    display = _calendar_interval_display(
        str(event.get("start", {}).get("dateTime", "")),
        str(event.get("end", {}).get("dateTime", "")),
        zone,
    )
    event_day = _parse_date(display["date"], "Calendar confirmation date")
    date_label = f"{display['weekday']}, {event_day.strftime('%B')} {event_day.day}, {event_day.year}"
    start_time = display["start_time"]
    end_time = display["end_time"]
    start_meridiem = start_time.rsplit(" ", 1)[-1]
    end_meridiem = end_time.rsplit(" ", 1)[-1]
    compact_start = start_time.rsplit(" ", 1)[0] if start_meridiem == end_meridiem else start_time
    time_label = f"{compact_start}–{end_time} {display['timezone_abbreviation']}"

    def names(value: str) -> str:
        recipients = [name or address for name, address in _validated_recipients(value, "Confirmation recipient")]
        return ", ".join(recipients)

    copied = f" with {names(cc)} copied" if cc else ""
    title = str(event.get("summary", "")).strip()
    event_url = str(event.get("htmlLink", "")).strip()
    calendar_link = f" [Calendar]({event_url})" if event_url else ""
    return (
        f"**{title}** was rescheduled to **{date_label}, {time_label}**.{calendar_link} "
        f"A confirmation draft to {names(to)}{copied} was saved (not sent). [Draft]({draft_url})"
    )


def gmail_draft_confirmation_markdown(to: str, cc: str, subject: str, draft_url: str) -> str:
    """Build a concise final response from verified Gmail draft state."""

    def names(value: str) -> str:
        recipients = [name or address for name, address in _validated_recipients(value, "Confirmation recipient")]
        return ", ".join(recipients)

    copied = f" with {names(cc)} copied" if cc else ""
    return (
        f"Draft to {names(to)}{copied} was saved (not sent) with subject "
        f"**{subject}**. [Draft]({draft_url})"
    )


def gmail_draft(args: argparse.Namespace) -> None:
    track_demo_state = getattr(args, "track_demo_state", False)
    reference_state: dict[str, Any] | None = None
    if track_demo_state:
        _state_path, reference_state = load_reference_workspace_state()
    expected_body = normalize_draft_body(
        args.body,
        getattr(args, "closing", ""),
        exact_final=bool(args.reply_to_message),
    )
    minimum_words = getattr(args, "minimum_body_words", 4 if args.reply_to_message else 1)
    checked_facts = validate_draft_content(
        expected_body,
        getattr(args, "closing", ""),
        getattr(args, "require_body_fact", []) or [],
        minimum_words,
    )
    verified_calendar_event = False
    calendar_confirmation: tuple[dict[str, Any], ZoneInfo] | None = None
    calendar_event_id = calendar_verification_event_id(
        expected_body,
        getattr(args, "verify_calendar_event", ""),
    )
    if calendar_event_id:
        calendar_api = service("calendar", "v3")
        calendar_id = getattr(args, "calendar", "primary")
        event = execute_google_read(
            calendar_api.events().get(calendarId=calendar_id, eventId=calendar_event_id),
            "Read Calendar event for draft validation",
        )
        zone = _calendar_zone(calendar_api, calendar_id, "", event)
        checked_facts.extend(validate_calendar_confirmation_content(expected_body, event, zone))
        verified_calendar_event = True
        calendar_confirmation = (event, zone)
    api = service("gmail", "v1")
    message = EmailMessage()
    to = args.to
    cc = args.cc
    subject = args.subject
    thread_id = args.thread_id
    reply_evidence: dict[str, Any] | None = None
    if args.reply_to_message:
        if any((args.to, args.cc, args.subject, args.thread_id)):
            raise DraftValidationError(
                "Reply drafts derive recipients, subject, and thread from Gmail evidence; "
                "use --include-sender-from-message for additional recipients"
            )
        signed_in_address = _gmail_profile_address(api)
        reply_evidence = _reply_evidence(api, args.reply_to_message)
        _require_external_reply_recipient(
            reply_evidence,
            signed_in_address,
            "Primary reply evidence",
        )
        to = reply_evidence["recipient"]
        subject = reply_evidence["subject"]
        thread_id = reply_evidence["thread_id"]
        message_id = reply_evidence["message_id_header"]
        references = " ".join(filter(None, [reply_evidence["references"], message_id]))
        if message_id:
            message["In-Reply-To"] = message_id
        if references:
            message["References"] = references
        extra_recipients = []
        seen = {address.casefold() for _name, address in _validated_recipients(to, "Derived To header")}
        additional_sources = getattr(args, "include_sender_from_message", []) or []
        for source_message_id in additional_sources:
            if source_message_id.strip() == args.reply_to_message.strip():
                raise RuntimeError("An additional-recipient message ID must differ from the primary reply message ID")
            evidence = _reply_evidence(api, source_message_id)
            _require_external_reply_recipient(
                evidence,
                signed_in_address,
                "Additional-recipient evidence",
            )
            for name, address in _validated_recipients(evidence["recipient"], "Derived additional recipient"):
                if address.casefold() not in seen:
                    seen.add(address.casefold())
                    extra_recipients.append(_format_recipient(name, address))
        if additional_sources and not extra_recipients:
            raise RuntimeError("Additional Gmail evidence did not supply a distinct recipient; no draft was created")
        cc = ", ".join(extra_recipients)
    if not to or not subject:
        raise RuntimeError("A draft needs recipients and a subject")
    _validated_recipients(to, "To header")
    if cc:
        _validated_recipients(cc, "Cc header")
    existing = matching_tracked_draft(
        api,
        (reference_state or {}).get("drafts", []),
        to,
        cc,
        subject,
        expected_body,
        thread_id,
    ) if track_demo_state else None
    if existing:
        existing_message = existing.get("message", {})
        existing_headers = headers(existing_message.get("payload", {}))
        existing_message_id = str(existing_message.get("id", "")).strip()
        draft_url = f"https://mail.google.com/mail/u/0/#drafts/{existing_message_id}"
        confirmation_markdown = gmail_draft_confirmation_markdown(
            existing_headers.get("to", ""),
            existing_headers.get("cc", ""),
            existing_headers.get("subject", ""),
            draft_url,
        )
        if calendar_confirmation:
            confirmation_markdown = calendar_draft_confirmation_markdown(
                calendar_confirmation[0],
                calendar_confirmation[1],
                existing_headers.get("to", ""),
                existing_headers.get("cc", ""),
                draft_url,
            )
        emit({
            "status": "already_drafted",
            "created": False,
            "reused": True,
            "url": draft_url,
            "verified": True,
            "to": existing_headers.get("to", ""),
            "cc": existing_headers.get("cc", ""),
            "subject": existing_headers.get("subject", ""),
            "body": decode_body(existing_message.get("payload", {})),
            "content_validated": True,
            "required_body_facts": checked_facts,
            "calendar_event_verified": verified_calendar_event,
            "confirmation_markdown": confirmation_markdown,
            "sent": False,
            "tracked_demo_state": True,
        })
        return
    message["To"] = to
    if cc:
        message["Cc"] = cc
    message["Subject"] = subject
    message.set_content(expected_body)
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    body: dict[str, Any] = {"message": {"raw": raw}}
    if thread_id:
        body["message"]["threadId"] = thread_id
    result = api.users().drafts().create(userId="me", body=body).execute()
    draft_id = result.get("id", "")
    message_id = result.get("message", {}).get("id", "")
    verified = execute_google_read(
        api.users().drafts().get(userId="me", id=draft_id, format="full"),
        "Verify saved Gmail draft",
    )
    verified_message = verified.get("message", {})
    verified_headers = headers(verified_message.get("payload", {}))
    verified_body = decode_body(verified_message.get("payload", {}))
    expected_to = {address.casefold() for _name, address in _validated_recipients(to, "Expected To header")}
    actual_to = {address.casefold() for _name, address in _validated_recipients(verified_headers.get("to", ""), "Saved To header")}
    expected_cc = {address.casefold() for _name, address in _validated_recipients(cc, "Expected Cc header")} if cc else set()
    actual_cc = {address.casefold() for _name, address in _validated_recipients(verified_headers.get("cc", ""), "Saved Cc header")} if verified_headers.get("cc") else set()
    verified_ok = (
        verified.get("id") == draft_id
        and expected_to == actual_to
        and expected_cc == actual_cc
        and verified_headers.get("subject", "") == subject
        and verified_body == expected_body.strip()
        and (not thread_id or verified_message.get("threadId") == thread_id)
    )
    if not verified_ok:
        try:
            api.users().drafts().delete(userId="me", id=draft_id).execute()
        except Exception:
            pass
        raise RuntimeError(f"Gmail draft {draft_id} could not be verified")
    tracked_state = False
    if track_demo_state:
        try:
            record_reference_workspace_draft(draft_id, message_id)
            tracked_state = True
        except Exception as tracking_error:
            try:
                api.users().drafts().delete(userId="me", id=draft_id).execute()
            except Exception as rollback_error:
                raise RuntimeError(
                    f"Draft {draft_id} was created but could not be tracked ({tracking_error}) "
                    f"or rolled back ({rollback_error})"
                ) from tracking_error
            raise RuntimeError(f"Draft tracking failed and draft {draft_id} was rolled back: {tracking_error}") from tracking_error
    draft_url = f"https://mail.google.com/mail/u/0/#drafts/{message_id}"
    confirmation_markdown = gmail_draft_confirmation_markdown(
        verified_headers.get("to", ""),
        verified_headers.get("cc", ""),
        verified_headers.get("subject", ""),
        draft_url,
    )
    if calendar_confirmation:
        confirmation_markdown = calendar_draft_confirmation_markdown(
            calendar_confirmation[0],
            calendar_confirmation[1],
            verified_headers.get("to", ""),
            verified_headers.get("cc", ""),
            draft_url,
        )
    emit({
        "status": "drafted",
        "url": draft_url,
        "verified": True,
        "to": verified_headers.get("to", ""),
        "cc": verified_headers.get("cc", ""),
        "subject": verified_headers.get("subject", ""),
        "body": verified_body,
        "content_validated": True,
        "required_body_facts": checked_facts,
        "calendar_event_verified": verified_calendar_event,
        "confirmation_markdown": confirmation_markdown,
        "sent": False,
        "tracked_demo_state": tracked_state,
    })


def drive_search(args: argparse.Namespace) -> None:
    safe = args.query.replace("'", "\\'")
    query = args.query if args.raw_query else f"trashed = false and fullText contains '{safe}'"
    result = execute_google_read(
        service("drive", "v3").files().list(
            q=query,
            orderBy="modifiedTime desc",
            pageSize=args.max,
            fields="files(id,name,mimeType,modifiedTime,webViewLink,owners(displayName,emailAddress),description)",
        ),
        "Search Google Drive",
    )
    emit(result.get("files", []))


def docs_get(args: argparse.Namespace) -> None:
    doc = execute_google_read(
        service("docs", "v1").documents().get(documentId=args.document_id),
        "Read Google Doc",
    )
    chunks: list[str] = []
    for block in doc.get("body", {}).get("content", []):
        for element in block.get("paragraph", {}).get("elements", []):
            chunks.append(element.get("textRun", {}).get("content", ""))
    emit({
        "id": args.document_id,
        "title": doc.get("title", ""),
        "url": f"https://docs.google.com/document/d/{args.document_id}/edit",
        "text": "".join(chunks)[: args.max_chars],
    })


def docs_append(args: argparse.Namespace) -> None:
    require_confirm(args, "Docs append")
    api = service("docs", "v1")
    doc = execute_google_read(
        api.documents().get(documentId=args.document_id),
        "Read Google Doc before append",
    )
    end_index = max(1, doc.get("body", {}).get("content", [{}])[-1].get("endIndex", 1) - 1)
    api.documents().batchUpdate(
        documentId=args.document_id,
        body={"requests": [{"insertText": {"location": {"index": end_index}, "text": args.text}}]},
    ).execute()
    emit({"status": "appended", "document_id": args.document_id, "characters": len(args.text)})


def docs_replace(args: argparse.Namespace) -> None:
    require_confirm(args, "Docs text replacement")
    find = normalize_cli_text(args.find)
    replacement = normalize_cli_text(args.replace)
    result = service("docs", "v1").documents().batchUpdate(
        documentId=args.document_id,
        body={
            "requests": [
                {
                    "replaceAllText": {
                        "containsText": {"text": find, "matchCase": args.match_case},
                        "replaceText": replacement,
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
    result = execute_google_read(
        service("sheets", "v4").spreadsheets().values().get(
            spreadsheetId=args.spreadsheet_id,
            range=args.range,
        ),
        "Read Google Sheet values",
    )
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


def _sheet_title_a1(title: str) -> str:
    return "'" + title.replace("'", "''") + "'"


def _column_name(index: int) -> str:
    if index < 0:
        raise ValueError("Column index cannot be negative")
    result = ""
    value = index + 1
    while value:
        value, remainder = divmod(value - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _grid_cell_value(cell: dict[str, Any]) -> Any:
    effective = cell.get("effectiveValue", {})
    for key in ("stringValue", "numberValue", "boolValue"):
        if key in effective:
            return effective[key]
    entered = cell.get("userEnteredValue", {})
    for key in ("stringValue", "numberValue", "boolValue"):
        if key in entered:
            return entered[key]
    return ""


def _grid_cell_display(cell: dict[str, Any]) -> str:
    if "formattedValue" in cell:
        return str(cell["formattedValue"])
    value = _grid_cell_value(cell)
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    return "" if value is None else str(value)


def _grid_cell_kind(cell: dict[str, Any]) -> str:
    if cell.get("userEnteredValue", {}).get("formulaValue"):
        return "formula"
    condition_type = cell.get("dataValidation", {}).get("condition", {}).get("type")
    if condition_type == "BOOLEAN":
        return "checkbox"
    format_type = cell.get("userEnteredFormat", {}).get("numberFormat", {}).get("type", "")
    if format_type in {"DATE", "DATE_TIME", "TIME"}:
        return format_type.casefold()
    effective = cell.get("effectiveValue", {})
    if "boolValue" in effective:
        return "boolean"
    if "numberValue" in effective:
        return "number"
    if "stringValue" in effective:
        return "text"
    return "blank"


def _grid_rows(sheet: dict[str, Any], max_rows: int, max_columns: int) -> list[list[dict[str, Any]]]:
    rows: list[list[dict[str, Any]]] = [[{} for _ in range(max_columns)] for _ in range(max_rows)]
    for block in sheet.get("data", []):
        start_row = int(block.get("startRow", 0))
        start_column = int(block.get("startColumn", 0))
        for row_offset, row_data in enumerate(block.get("rowData", [])):
            row_index = start_row + row_offset
            if row_index >= max_rows:
                break
            for column_offset, cell in enumerate(row_data.get("values", [])):
                column_index = start_column + column_offset
                if column_index >= max_columns:
                    break
                rows[row_index][column_index] = cell
    return rows


def _grid_range_contains(grid_range: dict[str, Any], row_index: int, column_index: int) -> bool:
    return (
        int(grid_range.get("startRowIndex", 0)) <= row_index < int(grid_range.get("endRowIndex", row_index + 1))
        and int(grid_range.get("startColumnIndex", 0)) <= column_index < int(grid_range.get("endColumnIndex", column_index + 1))
    )


def _cell_protections(sheet: dict[str, Any], row_index: int, column_index: int) -> list[dict[str, Any]]:
    protections = []
    for item in sheet.get("protectedRanges", []):
        grid_range = item.get("range", {})
        if not _grid_range_contains(grid_range, row_index, column_index):
            continue
        if any(_grid_range_contains(unprotected, row_index, column_index) for unprotected in item.get("unprotectedRanges", [])):
            continue
        protections.append({
            "description": item.get("description", ""),
            "warning_only": bool(item.get("warningOnly", False)),
        })
    return protections


def _condition_values(condition: dict[str, Any]) -> list[str]:
    return [
        str(item.get("userEnteredValue", ""))
        for item in condition.get("values", [])
        if "userEnteredValue" in item
    ]


def _validation_description(
    api: Any,
    spreadsheet_id: str,
    validation: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not validation:
        return None
    condition = validation.get("condition", {})
    condition_type = condition.get("type", "")
    values = _condition_values(condition)
    result: dict[str, Any] = {
        "condition_type": condition_type,
        "strict": bool(validation.get("strict", False)),
        "show_dropdown": bool(validation.get("showCustomUi", False)),
    }
    if condition_type == "ONE_OF_LIST":
        result["allowed_values"] = values
    elif condition_type == "ONE_OF_RANGE":
        reference = values[0] if values else ""
        result["source_range"] = reference
        if reference:
            resolved = execute_google_read(
                api.spreadsheets().values().get(
                    spreadsheetId=spreadsheet_id,
                    range=reference.removeprefix("="),
                ),
                "Read Google Sheet validation values",
            ).get("values", [])
            result["allowed_values"] = [
                str(value)
                for row in resolved
                for value in row
                if str(value).strip()
            ]
    elif condition_type == "BOOLEAN":
        result["allowed_values"] = values or ["TRUE", "FALSE"]
    elif values:
        result["condition_values"] = values
    return result


def _spreadsheet_grid(
    api: Any,
    spreadsheet_id: str,
    sheet_title: str = "",
    max_rows: int = 200,
    max_columns: int = 50,
) -> dict[str, Any]:
    if max_rows < 1 or max_columns < 1:
        raise RuntimeError("Spreadsheet inspection bounds must be positive")
    metadata = execute_google_read(
        api.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            includeGridData=False,
            fields=(
                "properties(title,locale,timeZone),"
                "sheets(properties(sheetId,title,gridProperties(rowCount,columnCount)),"
                "protectedRanges(description,warningOnly,range,unprotectedRanges),merges)"
            ),
        ),
        "Inspect Google Sheet metadata",
    )
    selected = [
        item for item in metadata.get("sheets", [])
        if not sheet_title or item.get("properties", {}).get("title", "").casefold() == sheet_title.casefold()
    ]
    if sheet_title and not selected:
        raise RuntimeError(f"Spreadsheet sheet not found: {sheet_title!r}")
    ranges = []
    bounds: dict[int, tuple[int, int]] = {}
    for item in selected:
        properties = item.get("properties", {})
        grid = properties.get("gridProperties", {})
        row_limit = min(max_rows, int(grid.get("rowCount", max_rows)))
        column_limit = min(max_columns, int(grid.get("columnCount", max_columns)))
        bounds[int(properties.get("sheetId", 0))] = (row_limit, column_limit)
        ranges.append(
            f"{_sheet_title_a1(properties.get('title', ''))}!A1:{_column_name(column_limit - 1)}{row_limit}"
        )
    detailed = execute_google_read(
        api.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            ranges=ranges,
            includeGridData=True,
            fields=(
                "sheets(properties(sheetId,title),data(startRow,startColumn,rowData(values("
                "effectiveValue,formattedValue,userEnteredValue,userEnteredFormat.numberFormat,"
                "dataValidation,note))))"
            ),
        ),
        "Inspect Google Sheet grid",
    )
    details_by_id = {
        int(item.get("properties", {}).get("sheetId", 0)): item
        for item in detailed.get("sheets", [])
    }
    output_sheets = []
    for item in selected:
        properties = item.get("properties", {})
        sheet_id = int(properties.get("sheetId", 0))
        row_limit, column_limit = bounds[sheet_id]
        detail = details_by_id.get(sheet_id, {"properties": properties, "data": []})
        detail["protectedRanges"] = item.get("protectedRanges", [])
        detail["merges"] = item.get("merges", [])
        output_sheets.append({
            "sheet_id": sheet_id,
            "title": properties.get("title", ""),
            "row_count": int(properties.get("gridProperties", {}).get("rowCount", 0)),
            "column_count": int(properties.get("gridProperties", {}).get("columnCount", 0)),
            "rows": _grid_rows(detail, row_limit, column_limit),
            "protected_ranges": item.get("protectedRanges", []),
            "merges": item.get("merges", []),
            "truncated": (
                row_limit < int(properties.get("gridProperties", {}).get("rowCount", 0))
                or column_limit < int(properties.get("gridProperties", {}).get("columnCount", 0))
            ),
        })
    return {
        "spreadsheet_id": spreadsheet_id,
        "title": metadata.get("properties", {}).get("title", ""),
        "locale": metadata.get("properties", {}).get("locale", ""),
        "timezone": metadata.get("properties", {}).get("timeZone", ""),
        "sheets": output_sheets,
    }


def _header_candidates(rows: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    candidates = []
    inside_detected_table = False
    for row_index, row in enumerate(rows):
        cells = [(column_index, _grid_cell_display(cell).strip()) for column_index, cell in enumerate(row)]
        nonempty = [(column_index, value) for column_index, value in cells if value]
        if not nonempty:
            inside_detected_table = False
            continue
        if inside_detected_table:
            continue
        if len(nonempty) < 2 or not all(_grid_cell_kind(row[column_index]) in {"text", "blank"} for column_index, _ in nonempty):
            continue
        following = rows[row_index + 1 : row_index + 4]
        if not any(sum(bool(_grid_cell_display(next_row[column]).strip()) for column, _ in nonempty) >= 2 for next_row in following):
            continue
        candidates.append({
            "row": row_index + 1,
            "columns": [
                {"column": _column_name(column_index), "name": value}
                for column_index, value in nonempty
            ],
        })
        inside_detected_table = True
    return candidates


def _resolve_semantic_cell(
    workbook: dict[str, Any],
    row_match: str,
    column_name: str,
) -> dict[str, Any]:
    wanted_row = row_match.strip().casefold()
    wanted_column = column_name.strip().casefold()
    if not wanted_row or not wanted_column:
        raise RuntimeError("Both a row match and column name are required")
    exact_occurrences = []
    containing_occurrences = []
    for sheet in workbook.get("sheets", []):
        for row_index, row in enumerate(sheet["rows"]):
            for column_index, cell in enumerate(row):
                cell_value = _grid_cell_display(cell).strip().casefold()
                if cell_value == wanted_row:
                    exact_occurrences.append((sheet, row_index, column_index))
                elif wanted_row in cell_value:
                    containing_occurrences.append((sheet, row_index, column_index))
    occurrences = exact_occurrences or containing_occurrences
    match_mode = "exact" if exact_occurrences else "unique_contains"
    matches = []
    for sheet, row_index, matching_column in occurrences:
        rows = sheet["rows"]
        if row_index > 0:
            matching_columns = [matching_column]
            for matching_column in matching_columns:
                header_matches = []
                for header_row in range(row_index - 1, -1, -1):
                    columns = [
                        column_index for column_index, cell in enumerate(rows[header_row])
                        if _grid_cell_display(cell).strip().casefold() == wanted_column
                    ]
                    if columns:
                        header_matches = [(header_row, column_index) for column_index in columns]
                        break
                for header_row, target_column in header_matches:
                    matches.append({
                        "sheet": sheet,
                        "row_index": row_index,
                        "row_match_column": matching_column,
                        "header_row_index": header_row,
                        "column_index": target_column,
                        "match_mode": match_mode,
                    })
    if not matches:
        scope = ", ".join(sheet["title"] for sheet in workbook.get("sheets", []))
        raise RuntimeError(
            f"Could not resolve row {row_match!r} under column {column_name!r} in inspected sheet(s): {scope}"
        )
    unique = {
        (item["sheet"]["sheet_id"], item["row_index"], item["column_index"]): item
        for item in matches
    }
    if len(unique) != 1:
        cells = [
            f"{item['sheet']['title']}!{_column_name(item['column_index'])}{item['row_index'] + 1}"
            for item in unique.values()
        ]
        raise RuntimeError(f"Semantic cell match is ambiguous: {cells}")
    return next(iter(unique.values()))


def _semantic_cell_description(api: Any, workbook: dict[str, Any], match: dict[str, Any]) -> dict[str, Any]:
    sheet = match["sheet"]
    row_index = match["row_index"]
    column_index = match["column_index"]
    cell = sheet["rows"][row_index][column_index]
    coordinate = f"{_column_name(column_index)}{row_index + 1}"
    header_row = sheet["rows"][match["header_row_index"]]
    row_values = {
        _grid_cell_display(header_cell).strip(): _grid_cell_display(sheet["rows"][row_index][header_column])
        for header_column, header_cell in enumerate(header_row)
        if _grid_cell_display(header_cell).strip()
    }
    return {
        "sheet": sheet["title"],
        "cell": coordinate,
        "a1_range": f"{_sheet_title_a1(sheet['title'])}!{coordinate}",
        "current_value": _grid_cell_display(cell),
        "row_match_mode": match.get("match_mode", "exact"),
        "value_kind": _grid_cell_kind(cell),
        "formula": cell.get("userEnteredValue", {}).get("formulaValue", ""),
        "number_format": cell.get("userEnteredFormat", {}).get("numberFormat", {}),
        "validation": _validation_description(
            api,
            workbook["spreadsheet_id"],
            cell.get("dataValidation"),
        ),
        "protected_by": _cell_protections(
            {"protectedRanges": sheet.get("protected_ranges", [])},
            row_index,
            column_index,
        ),
        "row": row_values,
    }


def _inspectable_sheet(sheet: dict[str, Any], api: Any, spreadsheet_id: str) -> dict[str, Any]:
    visible_rows = []
    constraints: dict[str, dict[str, Any]] = {}
    for row_index, row in enumerate(sheet["rows"]):
        values = {
            _column_name(column_index): _grid_cell_display(cell)
            for column_index, cell in enumerate(row)
            if _grid_cell_display(cell) != ""
        }
        if values:
            visible_rows.append({"row": row_index + 1, "values": values})
        for column_index, cell in enumerate(row):
            validation = _validation_description(api, spreadsheet_id, cell.get("dataValidation"))
            protections = _cell_protections(
                {"protectedRanges": sheet.get("protected_ranges", [])},
                row_index,
                column_index,
            )
            formula = cell.get("userEnteredValue", {}).get("formulaValue", "")
            if not validation and not protections and not formula:
                continue
            signature = json.dumps(
                {"value_kind": _grid_cell_kind(cell), "validation": validation, "protected_by": protections, "formula": formula},
                ensure_ascii=False,
                sort_keys=True,
            )
            group = constraints.setdefault(signature, {
                "cells": [],
                "value_kind": _grid_cell_kind(cell),
                "validation": validation,
                "protected_by": protections,
                "formula": formula,
            })
            group["cells"].append(f"{_column_name(column_index)}{row_index + 1}")
    return {
        "title": sheet["title"],
        "sheet_id": sheet["sheet_id"],
        "grid_size": {"rows": sheet["row_count"], "columns": sheet["column_count"]},
        "inspection_truncated": sheet["truncated"],
        "header_candidates": _header_candidates(sheet["rows"]),
        "rows": visible_rows,
        "constraints": list(constraints.values()),
    }


def spreadsheet_preview(
    api: Any,
    spreadsheet_id: str,
    max_rows: int = 40,
    max_columns: int = 20,
    max_sample_rows: int = 12,
) -> dict[str, Any]:
    """Return bounded structural evidence without assigning business meaning to columns."""
    if max_sample_rows < 1:
        raise RuntimeError("Spreadsheet preview sample bound must be positive")
    workbook = _spreadsheet_grid(api, spreadsheet_id, max_rows=max_rows, max_columns=max_columns)
    tabs = []
    for sheet in workbook["sheets"]:
        inspected = _inspectable_sheet(sheet, api, spreadsheet_id)
        candidates = inspected["header_candidates"]
        header = max(
            candidates,
            key=lambda item: (len(item.get("columns", [])), -int(item.get("row", 0))),
            default=None,
        )
        visible_rows = inspected["rows"]
        if header:
            header_row = int(header["row"])
            column_names = [str(column["column"]) for column in header["columns"]]
            table_rows = [
                {
                    "row": int(row["row"]),
                    "values": {
                        column: row["values"][column]
                        for column in column_names
                        if column in row["values"]
                    },
                }
                for row in visible_rows
                if int(row["row"]) > header_row
                and any(column in row["values"] for column in column_names)
            ]
            preamble = [row for row in visible_rows if int(row["row"]) < header_row][-4:]
        else:
            header_row = None
            column_names = []
            table_rows = visible_rows
            preamble = []
        if len(table_rows) > max_sample_rows:
            samples = table_rows[: max_sample_rows - 1] + [table_rows[-1]]
        else:
            samples = table_rows
        constraints = []
        for item in inspected["constraints"][:12]:
            cells = list(item.get("cells", []))
            constraints.append({
                **{key: value for key, value in item.items() if key != "cells"},
                "cells": cells[:12],
                "cell_count": len(cells),
            })
        tabs.append({
            "title": inspected["title"],
            "grid_size": inspected["grid_size"],
            "inspection_truncated": inspected["inspection_truncated"],
            "preamble": preamble,
            "table": {
                "header_row": header_row,
                "columns": header.get("columns", []) if header else [],
                "row_count": len(table_rows),
                "representative_rows": samples,
            },
            "validation_previews": constraints,
        })
    return {
        "id": spreadsheet_id,
        "title": workbook["title"],
        "locale": workbook["locale"],
        "timezone": workbook["timezone"],
        "tabs": tabs,
    }


def sheets_inspect(args: argparse.Namespace) -> None:
    api = service("sheets", "v4")
    workbook = _spreadsheet_grid(
        api,
        args.spreadsheet_id,
        args.sheet,
        args.max_rows,
        args.max_columns,
    )
    output = {
        key: workbook[key]
        for key in ("spreadsheet_id", "title", "locale", "timezone")
    }
    output["sheets"] = [
        _inspectable_sheet(sheet, api, args.spreadsheet_id)
        for sheet in workbook["sheets"]
    ]
    if args.row_match or args.column:
        if not args.row_match or not args.column:
            raise RuntimeError("Use --row-match and --column together")
        match = _resolve_semantic_cell(workbook, args.row_match, args.column)
        output["target"] = _semantic_cell_description(api, workbook, match)
    emit(output)


def _parse_number(value: str, label: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise RuntimeError(f"{label} must be numeric") from exc


def _validate_requested_cell_value(value: str, target: dict[str, Any]) -> None:
    if value.startswith("="):
        raise RuntimeError("Formula writes are not supported by the guarded cell updater")
    if target.get("formula"):
        raise RuntimeError(f"Refusing to overwrite formula cell {target['a1_range']}")
    if target.get("protected_by"):
        raise RuntimeError(f"Refusing to update protected cell {target['a1_range']}")
    validation = target.get("validation")
    if validation:
        condition_type = validation.get("condition_type", "")
        allowed = [str(item) for item in validation.get("allowed_values", [])]
        if condition_type in {"ONE_OF_LIST", "ONE_OF_RANGE", "BOOLEAN"}:
            if value not in allowed:
                raise RuntimeError(
                    f"Value {value!r} is not allowed for {target['a1_range']}; use one of {allowed}"
                )
            return
        operands = validation.get("condition_values", [])
        if condition_type.startswith("NUMBER_"):
            number = _parse_number(value, "Requested value")
            thresholds = [_parse_number(item, "Validation operand") for item in operands]
            valid = {
                "NUMBER_GREATER": lambda: number > thresholds[0],
                "NUMBER_GREATER_THAN_EQ": lambda: number >= thresholds[0],
                "NUMBER_LESS": lambda: number < thresholds[0],
                "NUMBER_LESS_THAN_EQ": lambda: number <= thresholds[0],
                "NUMBER_EQ": lambda: number == thresholds[0],
                "NUMBER_NOT_EQ": lambda: number != thresholds[0],
                "NUMBER_BETWEEN": lambda: thresholds[0] <= number <= thresholds[1],
                "NUMBER_NOT_BETWEEN": lambda: not thresholds[0] <= number <= thresholds[1],
            }.get(condition_type)
            if not valid or not valid():
                raise RuntimeError(f"Value {value!r} violates {condition_type} validation for {target['a1_range']}")
            return
        if condition_type.startswith("DATE_"):
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise RuntimeError(f"Value for {target['a1_range']} must be an ISO date (YYYY-MM-DD)") from exc
            return
        if condition_type == "TEXT_IS_EMAIL":
            addresses = getaddresses([value])
            if len(addresses) != 1 or not _valid_email_address(addresses[0][1]):
                raise RuntimeError(f"Value for {target['a1_range']} must be a valid email address")
            return
        if condition_type == "TEXT_IS_URL":
            if not re.match(r"^https?://[^\s]+$", value, flags=re.IGNORECASE):
                raise RuntimeError(f"Value for {target['a1_range']} must be an HTTP(S) URL")
            return
        if validation.get("strict"):
            raise RuntimeError(
                f"Strict validation {condition_type!r} on {target['a1_range']} cannot be evaluated safely"
            )
    kind = target.get("value_kind")
    if kind == "number":
        _parse_number(value, f"Value for {target['a1_range']}")
    elif kind == "boolean" and value not in {"TRUE", "FALSE"}:
        raise RuntimeError(f"Value for {target['a1_range']} must be TRUE or FALSE")
    elif kind in {"date", "date_time"}:
        try:
            datetime.fromisoformat(value)
        except ValueError as exc:
            raise RuntimeError(f"Value for {target['a1_range']} must be ISO-formatted") from exc
    elif kind == "time":
        try:
            time.fromisoformat(value)
        except ValueError as exc:
            raise RuntimeError(f"Value for {target['a1_range']} must be an ISO time") from exc


def _equivalent_cell_values(actual: str, requested: str, kind: str) -> bool:
    if actual == requested:
        return True
    if kind == "number":
        try:
            return float(actual.replace(",", "")) == float(requested)
        except ValueError:
            return False
    if kind in {"boolean", "checkbox"}:
        return actual.casefold() == requested.casefold()
    return False


def sheets_set_cell(args: argparse.Namespace) -> None:
    require_confirm(args, "guarded Sheets cell update")
    api = service("sheets", "v4")
    workbook = _spreadsheet_grid(
        api,
        args.spreadsheet_id,
        args.sheet,
        args.max_rows,
        args.max_columns,
    )
    match = _resolve_semantic_cell(workbook, args.row_match, args.column)
    if match["column_index"] == match["row_match_column"]:
        raise RuntimeError("Refusing to update the row-identifier cell used to resolve the target")
    target = _semantic_cell_description(api, workbook, match)
    if target["current_value"] != args.expected_current:
        raise RuntimeError(
            f"Cell {target['a1_range']} changed since inspection: expected {args.expected_current!r}, "
            f"found {target['current_value']!r}"
        )
    _validate_requested_cell_value(args.value, target)
    api.spreadsheets().values().update(
        spreadsheetId=args.spreadsheet_id,
        range=target["a1_range"],
        valueInputOption="USER_ENTERED",
        body={"values": [[args.value]]},
    ).execute()
    verified_workbook = _spreadsheet_grid(
        api,
        args.spreadsheet_id,
        args.sheet,
        args.max_rows,
        args.max_columns,
    )
    verified_match = _resolve_semantic_cell(verified_workbook, args.row_match, args.column)
    verified = _semantic_cell_description(api, verified_workbook, verified_match)
    if verified["a1_range"] != target["a1_range"]:
        raise RuntimeError("Spreadsheet structure changed while the cell update was in progress")
    if not _equivalent_cell_values(verified["current_value"], args.value, verified["value_kind"]):
        raise RuntimeError(
            f"Sheets update could not be verified: expected {args.value!r}, found {verified['current_value']!r}"
        )
    emit({
        "status": "updated",
        "spreadsheet_id": args.spreadsheet_id,
        "sheet": verified["sheet"],
        "cell": verified["cell"],
        "old_value": target["current_value"],
        "new_value": verified["current_value"],
        "validation": verified["validation"],
        "verified": True,
        "url": f"https://docs.google.com/spreadsheets/d/{args.spreadsheet_id}/edit#gid={match['sheet']['sheet_id']}&range={verified['cell']}",
        "confirmation_markdown": (
            f"**{args.row_match}**: **{args.column}** changed from "
            f"**{target['current_value']}** to **{verified['current_value']}**. "
            f"[Sheet](https://docs.google.com/spreadsheets/d/{args.spreadsheet_id}/edit)"
        ),
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


def _recover_presentation_id(requested_id: str) -> str | None:
    """Recover only a strong, unique near-match among live presentation IDs."""
    result = execute_google_read(
        service("drive", "v3").files().list(
            q="trashed = false and mimeType = 'application/vnd.google-apps.presentation'",
            orderBy="modifiedTime desc",
            pageSize=50,
            fields="files(id,name,mimeType,modifiedTime)",
        ),
        "Find a uniquely matching Google Slides presentation",
    )
    ranked = sorted(
        (
            (SequenceMatcher(None, requested_id, str(item.get("id", ""))).ratio(), str(item.get("id", "")))
            for item in result.get("files", [])
            if str(item.get("id", "")) and str(item.get("id", "")) != requested_id
        ),
        reverse=True,
    )
    if not ranked:
        return None
    best_score, best_id = ranked[0]
    runner_up = ranked[1][0] if len(ranked) > 1 else 0.0
    if best_score < 0.92 or best_score - runner_up < 0.05:
        return None
    return best_id


def slides_get(args: argparse.Namespace) -> None:
    api = service("slides", "v1")
    presentation_id = args.presentation_id
    try:
        deck = execute_google_read(
            api.presentations().get(presentationId=presentation_id),
            "Read Google Slides presentation",
        )
    except Exception as exc:
        if _api_status(exc) not in {404, 410}:
            raise
        recovered_id = _recover_presentation_id(presentation_id)
        if not recovered_id:
            raise RuntimeError(
                f"Google Slides presentation ID {presentation_id!r} does not resolve and no strong unique live match exists"
            ) from exc
        presentation_id = recovered_id
        deck = execute_google_read(
            api.presentations().get(presentationId=presentation_id),
            "Read recovered Google Slides presentation",
        )
    slides = [
        {"number": index, "object_id": slide.get("objectId"), "text": _slide_text(slide)[: args.max_chars_per_slide]}
        for index, slide in enumerate(deck.get("slides", []), start=1)
    ]
    emit({"id": presentation_id, "title": deck.get("title", ""), "url": f"https://docs.google.com/presentation/d/{presentation_id}/edit", "slides": slides})


def slides_replace(args: argparse.Namespace) -> None:
    require_confirm(args, "Slides text replacement")
    api = service("slides", "v1")
    find = normalize_cli_text(args.find)
    replacement = normalize_cli_text(args.replace)
    result = api.presentations().batchUpdate(
        presentationId=args.presentation_id,
        body={"requests": [{"replaceAllText": {"containsText": {"text": find, "matchCase": args.match_case}, "replaceText": replacement}}]},
    ).execute()
    replies = result.get("replies", [])
    occurrences = sum(r.get("replaceAllText", {}).get("occurrencesChanged", 0) for r in replies)
    if occurrences < 1:
        raise RuntimeError(f"Slides text was not found: {find!r}")
    deck = execute_google_read(
        api.presentations().get(presentationId=args.presentation_id),
        "Verify Google Slides replacement",
    )
    text = "\n".join(_slide_text(slide) for slide in deck.get("slides", []))
    verified = replacement in text and find not in text
    if not verified:
        raise RuntimeError("Slides replacement could not be verified")
    title = str(deck.get("title", "")).strip() or "Google Slides presentation"
    url = f"https://docs.google.com/presentation/d/{args.presentation_id}/edit"
    emit({
        "status": "updated",
        "presentation_id": args.presentation_id,
        "title": title,
        "occurrences_changed": occurrences,
        "verified": True,
        "url": url,
        "confirmation_markdown": f"Updated **{title}** with the requested text change. [Slides]({url})",
    })


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
    return execute_google_read(
        api.events().list(**request),
        "Read Google Calendar events",
    ).get("items", [])


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
    try:
        event = execute_google_read(
            service("calendar", "v3").events().get(
                calendarId=args.calendar,
                eventId=args.event_id,
            ),
            "Read Google Calendar event",
        )
    except Exception as exc:
        if _api_status(exc) in {404, 410}:
            raise RuntimeError(
                f"Calendar event ID {args.event_id!r} does not resolve. "
                "Use calendar find with evidence-backed title terms and literal dates; never derive an ID from a Calendar URL."
            ) from exc
        raise
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


def _availability(
    events: list[dict[str, Any]],
    start: datetime,
    end: datetime,
    duration_minutes: int,
    step_minutes: int,
    limit: int,
    exclude_event: str = "",
) -> tuple[list[dict[str, str]], list[tuple[datetime, datetime, dict[str, Any]]]]:
    if duration_minutes < 1 or step_minutes < 1 or limit < 1:
        raise RuntimeError("Duration, step, and limit must be positive")
    intervals = _blocking_intervals(events, start, end, exclude_event)

    merged: list[tuple[datetime, datetime]] = []
    for busy_start, busy_end, _event in intervals:
        if merged and busy_start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], busy_end))
        else:
            merged.append((busy_start, busy_end))

    duration = timedelta(minutes=duration_minutes)
    step = timedelta(minutes=step_minutes)
    slots = []
    cursor = _ceil_to_minutes(start, step_minutes)

    def add_slots(gap_end: datetime) -> None:
        nonlocal cursor
        while cursor + duration <= gap_end and len(slots) < limit:
            slots.append({"start": cursor.isoformat(), "end": (cursor + duration).isoformat()})
            cursor += step

    for busy_start, busy_end in merged:
        add_slots(busy_start)
        cursor = _ceil_to_minutes(max(cursor, busy_end), step_minutes)
        if len(slots) >= limit:
            break
    if len(slots) < limit:
        add_slots(end)
    return slots, intervals


def calendar_availability(args: argparse.Namespace) -> None:
    start = _calendar_time(args.start, "--start")
    end = _calendar_time(args.end, "--end")
    api = service("calendar", "v3")
    events = _calendar_window(api, args.calendar, start, end)
    slots, intervals = _availability(
        events,
        start,
        end,
        args.duration_minutes,
        args.step_minutes,
        args.limit,
        args.exclude_event,
    )

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


def _parse_date(value: str, label: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise RuntimeError(f"{label} must be an ISO date (YYYY-MM-DD)") from exc


def _parse_clock(value: str, label: str) -> time:
    try:
        parsed = time.fromisoformat(value)
    except ValueError as exc:
        raise RuntimeError(f"{label} must be an ISO local time (HH:MM)") from exc
    if parsed.tzinfo is not None:
        raise RuntimeError(f"{label} must be a local clock time without a UTC offset")
    return parsed


def _calendar_zone(api: Any, calendar_id: str, explicit: str = "", event: dict[str, Any] | None = None) -> ZoneInfo:
    zone_name = explicit.strip()
    if not zone_name and event:
        zone_name = event.get("start", {}).get("timeZone", "") or event.get("end", {}).get("timeZone", "")
    if not zone_name:
        zone_name = execute_google_read(
            api.calendars().get(calendarId=calendar_id),
            "Read Google Calendar timezone",
        ).get("timeZone", "")
    if not zone_name:
        raise RuntimeError("Calendar timezone could not be determined")
    try:
        return ZoneInfo(zone_name)
    except Exception as exc:
        raise RuntimeError(f"Unknown calendar timezone: {zone_name!r}") from exc


def _local_day_window(day: date, start_value: str, end_value: str, zone: ZoneInfo) -> tuple[datetime, datetime]:
    start = datetime.combine(day, _parse_clock(start_value, "--work-start"), tzinfo=zone)
    end = datetime.combine(day, _parse_clock(end_value, "--work-end"), tzinfo=zone)
    if end <= start:
        raise RuntimeError("Working-hours end must be after start")
    return start, end


def _calendar_interval_display(start_value: str, end_value: str, zone: ZoneInfo) -> dict[str, str]:
    start = _calendar_time(start_value, "Calendar display start").astimezone(zone)
    end = _calendar_time(end_value, "Calendar display end").astimezone(zone)

    def clock(value: datetime) -> str:
        return value.strftime("%I:%M %p").lstrip("0")

    return {
        "date": start.date().isoformat(),
        "weekday": start.strftime("%A"),
        "start_time": clock(start),
        "end_time": clock(end),
        "timezone": str(zone),
        "timezone_abbreviation": start.tzname() or str(zone),
    }


def _api_status(exc: Exception) -> int | None:
    return getattr(getattr(exc, "resp", None), "status", None)


def _calendar_title_matches_query(title: str, query: str) -> bool:
    """Require every bounded query term to describe the resolved event title."""
    title_terms = set(re.findall(r"[a-z0-9]+", title.casefold()))
    query_terms = set(re.findall(r"[a-z0-9]+", query.casefold()))
    return bool(title_terms and query_terms and query_terms.issubset(title_terms))


def _resolve_calendar_event(
    api: Any,
    calendar_id: str,
    event_id: str,
    query: str,
    target_day: date,
    zone: ZoneInfo,
    lookup_days: int,
) -> tuple[dict[str, Any], bool]:
    if event_id.strip():
        try:
            resolved = execute_google_read(
                api.events().get(calendarId=calendar_id, eventId=event_id),
                "Resolve Google Calendar event",
            )
            if query.strip() and not _calendar_title_matches_query(str(resolved.get("summary", "")), query):
                raise CalendarValidationError(
                    f"Calendar event ID resolves to {resolved.get('summary', 'an untitled event')!r}, "
                    f"which does not match query {query!r}. No event was moved. "
                    "Run a focused Calendar find and retry with its returned event ID."
                )
            return resolved, False
        except Exception as exc:
            if isinstance(exc, CalendarValidationError):
                raise
            if _api_status(exc) not in {404, 410}:
                raise
            if not query.strip():
                raise RuntimeError(
                    f"Calendar event ID {event_id!r} no longer resolves; provide --query to perform a bounded live lookup"
                ) from exc
    if not query.strip():
        raise RuntimeError("Calendar rescheduling requires a live event ID or a unique --query fallback")
    if lookup_days < 1:
        raise RuntimeError("--lookup-days must be positive")
    lookup_start = datetime.combine(target_day - timedelta(days=lookup_days), time.min, tzinfo=zone)
    lookup_end = datetime.combine(target_day + timedelta(days=lookup_days + 1), time.min, tzinfo=zone)
    candidates = [
        item for item in _calendar_window(api, calendar_id, lookup_start, lookup_end, query=query)
        if _event_blocks_time(item) and item.get("start", {}).get("dateTime")
    ]
    exact = [item for item in candidates if item.get("summary", "").strip().casefold() == query.strip().casefold()]
    resolved = exact or candidates
    unique = {str(item.get("id", "")): item for item in resolved if item.get("id")}
    if len(unique) != 1:
        descriptions = [
            f"{item.get('summary', 'Untitled')} at {item.get('start', {}).get('dateTime', '')}"
            for item in unique.values()
        ]
        raise RuntimeError(
            f"Calendar lookup for {query!r} returned {len(unique)} possible events; "
            f"refusing an ambiguous move: {descriptions}"
        )
    return next(iter(unique.values())), True


def calendar_find(args: argparse.Namespace) -> None:
    api = service("calendar", "v3")
    zone = _calendar_zone(api, args.calendar, args.timezone)
    start_value = args.start_date.strip()
    end_value = args.end_date.strip()
    if start_value:
        start_day = _parse_date(start_value, "--start-date")
        end_day = _parse_date(end_value or start_value, "--end-date")
    else:
        if end_value:
            raise RuntimeError("--end-date requires --start-date")
        if args.days < 1:
            raise RuntimeError("--days must be positive")
        start_day = datetime.now(zone).date()
        end_day = start_day + timedelta(days=args.days)
    if end_day < start_day:
        raise RuntimeError("--end-date must be on or after --start-date")
    start = datetime.combine(start_day, time.min, tzinfo=zone)
    end = datetime.combine(end_day + timedelta(days=1), time.min, tzinfo=zone)
    events = _calendar_window(api, args.calendar, start, end, query=args.query, max_results=args.max)
    emit({
        "query": args.query,
        "start_date": start_day.isoformat(),
        "end_date": end_day.isoformat(),
        "timezone": str(zone),
        "events": [_calendar_item(event) for event in events if _event_blocks_time(event)],
    })


def calendar_reschedule(args: argparse.Namespace) -> None:
    """Move an event to the first conflict-free slot in a literal local-day window."""
    require_confirm(args, "Calendar event reschedule")
    target_day = _parse_date(args.date, "--date")
    date_source_message = getattr(args, "date_source_message", "").strip()
    user_directed_date = getattr(args, "user_directed_date", False)
    if bool(date_source_message) == bool(user_directed_date):
        raise CalendarValidationError(
            "Calendar reschedule needs exactly one date authority: use --date-source-message when "
            "Gmail states the target date, or --user-directed-date only when the user's request "
            "literally states it. No event was moved."
        )
    if date_source_message:
        validate_calendar_date_evidence(service("gmail", "v1"), date_source_message, target_day)
    else:
        validate_user_directed_date(getattr(args, "user_request_text", ""), target_day)
    expected_weekday = getattr(args, "expected_weekday", "")
    if expected_weekday and target_day.strftime("%A").casefold() != expected_weekday.strip().casefold():
        raise RuntimeError(
            f"Date {target_day.isoformat()} is {target_day.strftime('%A')}, not {expected_weekday!r}; refusing the move"
        )
    api = service("calendar", "v3")
    preliminary_zone = _calendar_zone(api, args.calendar, args.timezone)
    current, recovered_by_query = _resolve_calendar_event(
        api,
        args.calendar,
        args.event_id,
        args.query,
        target_day,
        preliminary_zone,
        args.lookup_days,
    )
    zone = _calendar_zone(api, args.calendar, args.timezone, current)
    window_start, window_end = _local_day_window(target_day, args.work_start, args.work_end, zone)
    current_start = _event_time(current, "start", window_start)
    current_end = _event_time(current, "end", window_start)
    if not current_start or not current_end or current_end <= current_start:
        raise RuntimeError("The selected Calendar event does not have a valid timed duration")
    duration_minutes = int((current_end - current_start).total_seconds() // 60)
    if duration_minutes < 1:
        raise RuntimeError("The selected Calendar event duration is invalid")
    events = _calendar_window(api, args.calendar, window_start, window_end)
    slots, intervals = _availability(
        events,
        window_start,
        window_end,
        duration_minutes,
        args.step_minutes,
        1,
        str(current.get("id", "")),
    )
    if not slots:
        raise RuntimeError(
            f"No conflict-free {duration_minutes}-minute slot exists on {target_day.isoformat()} "
            f"between {args.work_start} and {args.work_end} in {zone}"
        )
    selected = slots[0]
    moved_start = _calendar_time(selected["start"], "selected start")
    moved_end = _calendar_time(selected["end"], "selected end")
    event_id = str(current.get("id", ""))
    api.events().patch(
        calendarId=args.calendar,
        eventId=event_id,
        body={
            "start": {"dateTime": moved_start.isoformat(), "timeZone": str(zone)},
            "end": {"dateTime": moved_end.isoformat(), "timeZone": str(zone)},
        },
        sendUpdates=args.send_updates,
    ).execute()
    verified = execute_google_read(
        api.events().get(calendarId=args.calendar, eventId=event_id),
        "Verify rescheduled Google Calendar event",
    )
    actual_start = verified.get("start", {}).get("dateTime", "")
    actual_end = verified.get("end", {}).get("dateTime", "")
    if not actual_start or not actual_end or not _same_instant(actual_start, selected["start"]) or not _same_instant(actual_end, selected["end"]):
        raise RuntimeError("Calendar reschedule could not be verified")
    emit({
        "status": "moved",
        "id": event_id,
        "title": verified.get("summary", ""),
        "original_start": current.get("start", {}),
        "original_end": current.get("end", {}),
        "original_display": _calendar_interval_display(
            current.get("start", {}).get("dateTime", ""),
            current.get("end", {}).get("dateTime", ""),
            zone,
        ),
        "start": verified.get("start", {}),
        "end": verified.get("end", {}),
        "new_display": _calendar_interval_display(actual_start, actual_end, zone),
        "timezone": str(zone),
        "working_hours": {"start": args.work_start, "end": args.work_end},
        "duration_minutes": duration_minutes,
        "busy": [
            {**_calendar_item(event), "start": busy_start.isoformat(), "end": busy_end.isoformat()}
            for busy_start, busy_end, event in intervals
        ],
        "recovered_by_query": recovered_by_query,
        "url": verified.get("htmlLink", ""),
        "verified": True,
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
    send_updates = "all" if args.attendees else "none"
    emit({
        "status": "created",
        "id": result.get("id"),
        "url": result.get("htmlLink"),
        "send_updates": send_updates,
        "notifications_requested": send_updates != "none",
        "notification_delivery_verified": False,
    })


def _same_instant(actual: str, expected: str) -> bool:
    return datetime.fromisoformat(actual.replace("Z", "+00:00")) == datetime.fromisoformat(expected.replace("Z", "+00:00"))


def calendar_move(args: argparse.Namespace) -> None:
    """Move one existing event while preserving all other event details."""
    require_confirm(args, "Calendar event move")
    api = service("calendar", "v3")
    current = execute_google_read(
        api.events().get(calendarId=args.calendar, eventId=args.event_id),
        "Read Google Calendar event before move",
    )
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
    verified = execute_google_read(
        api.events().get(calendarId=args.calendar, eventId=args.event_id),
        "Verify moved Google Calendar event",
    )
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
        "send_updates": args.send_updates,
        "notifications_requested": args.send_updates != "none",
        "notification_delivery_verified": False,
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
    p = gmail.add_parser("search")
    p.add_argument("query")
    p.add_argument("extra", nargs="*", help=argparse.SUPPRESS)
    p.add_argument("--from", dest="sender", default="", help="Optional Gmail sender filter")
    p.add_argument("--subject", default="", help="Optional Gmail subject filter")
    p.add_argument("--max", type=int, default=10)
    p.add_argument("--max-chars", type=int, default=500)
    p.set_defaults(func=gmail_search)
    p = gmail.add_parser("draft")
    p.add_argument("--to", default="")
    p.add_argument("--cc", default="")
    p.add_argument("--subject", default="")
    p.add_argument("--body", required=True)
    p.add_argument("--closing", default="", help="Ensure an exact final closing while preserving any following signature")
    p.add_argument(
        "--require-body-fact",
        action="append",
        default=[],
        help="Require an evidence-derived fact to appear in the body before creating the draft; repeat as needed",
    )
    p.add_argument(
        "--verify-calendar-event",
        default="",
        help="Read a live event and require its title, date, start/end times, and timezone in the body before drafting",
    )
    p.add_argument("--thread-id", default="")
    p.add_argument("--reply-to-message", default="", help="Build a correctly threaded reply draft")
    p.add_argument(
        "--include-sender-from-message",
        action="append",
        default=[],
        help="Add a Cc recipient derived from another real Gmail message; repeat as needed",
    )
    p.add_argument("--track-demo-state", action="store_true", help="Record this draft for reference-workspace cleanup")
    p.set_defaults(func=gmail_draft)
    p = gmail.add_parser("reply-draft")
    p.add_argument("reply_to_message", help="Real Gmail message ID that supplies the thread, To recipient, and subject")
    p.add_argument("--to", default="", help=argparse.SUPPRESS)
    p.add_argument("--cc", default="", help=argparse.SUPPRESS)
    p.add_argument("--subject", default="", help=argparse.SUPPRESS)
    p.add_argument("--thread-id", default="", help=argparse.SUPPRESS)
    p.add_argument(
        "--include-sender-from-message",
        action="append",
        default=[],
        help="Add a Cc recipient derived from another real Gmail message; repeat as needed",
    )
    p.add_argument("--body", required=True)
    p.add_argument("--closing", default="", help="Ensure an exact final closing")
    p.add_argument(
        "--require-body-fact",
        action="append",
        default=[],
        help="Require an evidence-derived fact to appear in the body before creating the draft; repeat as needed",
    )
    p.add_argument(
        "--verify-calendar-event",
        default="",
        help="Read a live event and require its title, date, start/end times, and timezone in the body before drafting",
    )
    p.add_argument("--track-demo-state", action="store_true", help="Record this draft for reference-workspace cleanup")
    p.add_argument("--confirm", action="store_true", help=argparse.SUPPRESS)
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
    p = sheets.add_parser("inspect")
    p.add_argument("spreadsheet_id")
    p.add_argument("--sheet", default="", help="Optional sheet title; inspect all sheets when omitted")
    p.add_argument("--row-match", default="", help="Exact existing cell value identifying the target row")
    p.add_argument("--column", default="", help="Exact header identifying the target column")
    p.add_argument("--max-rows", type=int, default=200)
    p.add_argument("--max-columns", type=int, default=50)
    p.set_defaults(func=sheets_inspect)
    p = sheets.add_parser("set-cell")
    p.add_argument("spreadsheet_id")
    p.add_argument("--sheet", default="", help="Optional sheet title; search all sheets when omitted")
    p.add_argument("--row-match", required=True, help="Exact existing cell value identifying the target row")
    p.add_argument("--column", required=True, help="Exact header identifying the target column")
    p.add_argument("--expected-current", required=True, help="Current value returned by the immediately preceding inspection")
    p.add_argument("--value", required=True, help="New scalar value")
    p.add_argument("--max-rows", type=int, default=200)
    p.add_argument("--max-columns", type=int, default=50)
    p.add_argument("--confirm", action="store_true")
    p.set_defaults(func=sheets_set_cell)

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
    p = calendar.add_parser("find")
    p.add_argument("--query", required=True)
    p.add_argument("--start-date", default="", help="Optional literal local date, YYYY-MM-DD; defaults to today")
    p.add_argument("--end-date", default="", help="Inclusive literal local date; requires --start-date")
    p.add_argument("--days", type=int, default=14, help="Default bounded look-ahead when dates are omitted")
    p.add_argument("--timezone", default="", help="IANA timezone; defaults to the Calendar timezone")
    p.add_argument("--max", type=int, default=50)
    p.add_argument("--calendar", default="primary")
    p.set_defaults(func=calendar_find)
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
    p = calendar.add_parser("reschedule")
    p.add_argument("event_id", nargs="?", default="", help="Live Calendar event ID; may be recovered with a unique --query")
    p.add_argument("--query", default="", help="Exact event title or bounded fallback search terms")
    p.add_argument("--date", required=True, help="Literal target local date, YYYY-MM-DD")
    p.add_argument("--expected-weekday", default="", help="Optional weekday named by the request/evidence; must match --date")
    authority = p.add_mutually_exclusive_group()
    authority.add_argument(
        "--date-source-message",
        default="",
        help="Received Gmail message ID whose content must state the target date",
    )
    authority.add_argument(
        "--user-directed-date",
        action="store_true",
        help="Assert that the user's current request literally states the target date",
    )
    p.add_argument(
        "--user-request-text",
        default="",
        help="Exact current user request; required with --user-directed-date and validated before any move",
    )
    p.add_argument("--work-start", default="08:00", help="Earliest local start, HH:MM")
    p.add_argument("--work-end", default="17:00", help="Latest local end, HH:MM")
    p.add_argument("--timezone", default="", help="IANA timezone; defaults to event or Calendar timezone")
    p.add_argument("--step-minutes", type=int, default=15)
    p.add_argument("--lookup-days", type=int, default=14)
    p.add_argument("--calendar", default="primary")
    p.add_argument("--send-updates", choices=("none", "all", "externalOnly"), default="none")
    p.add_argument("--confirm", action="store_true")
    p.set_defaults(func=calendar_reschedule)
    return parser


def main() -> int:
    parser = build_parser()
    args, unknown = parser.parse_known_args()
    unexpected = [value for value in unknown if value]
    if unexpected:
        parser.error(f"unrecognized arguments: {' '.join(unexpected)}")
    try:
        args.func(args)
        return 0
    except DraftValidationError as exc:
        emit({
            "status": "rejected",
            "created": False,
            "content_validated": False,
            "reason": str(exc),
        })
        return 0
    except CalendarValidationError as exc:
        emit({
            "status": "rejected",
            "moved": False,
            "date_validated": False,
            "reason": str(exc),
        })
        return 0
    except GoogleTransientError as exc:
        emit(temporary_google_result(exc))
        return 0
    except Exception as exc:
        if is_transient_google_error(exc):
            emit(temporary_google_result(exc))
            return 0
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
