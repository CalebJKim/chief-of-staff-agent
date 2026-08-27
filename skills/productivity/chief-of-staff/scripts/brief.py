#!/usr/bin/env python
"""Turn a bounded Workspace snapshot into a compact decision packet."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, time, timedelta
from email.utils import getaddresses
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

STOPWORDS = {
    "about", "after", "before", "could", "from", "have", "into", "meeting", "notes",
    "that", "their", "there", "these", "this", "today", "update", "with", "your",
}
GOOGLE_TEMPORARY_USER_MESSAGE = (
    "Google Workspace timed out. This is a temporary Google-side issue; please try again later."
)


def hermes_home() -> Path:
    override = os.environ.get("HERMES_HOME")
    if override:
        return Path(override).expanduser()
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "hermes"
    return Path.home() / ".hermes"


def default_snapshot() -> Path:
    return hermes_home() / "chief-of-staff" / "snapshot.json"


def parse_dt(value: str, tz: ZoneInfo) -> datetime | None:
    if not value or "T" not in value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=tz)
        return parsed.astimezone(tz)
    except ValueError:
        return None


def tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9_-]{3,}", (text or "").casefold())
        if token not in STOPWORDS and not token.isdigit()
    }


def is_directly_addressed(message: dict[str, Any], self_email: str) -> bool:
    """Return true when the account is the message's sole primary recipient."""
    if not self_email:
        return False
    recipients = [
        address.casefold()
        for _, address in getaddresses([str(message.get("to", ""))])
        if address
    ]
    return len(recipients) == 1 and recipients[0] == self_email.casefold()


def deterministic_mail_priority(message: dict[str, Any], self_email: str) -> tuple[int, int, int, int, str]:
    """Generic, stable priority policy with no content or workspace-specific rules."""
    return (
        -int(bool(message.get("important"))),
        -int(is_directly_addressed(message, self_email)),
        -int(bool(message.get("unread"))),
        -int(message.get("internal_ms", 0) or 0),
        str(message.get("id", "")),
    )


def sheet_row_contexts(sheet_evidence: list[dict[str, Any]]) -> list[tuple[str, set[str]]]:
    """Return schema-agnostic row identities and their visible value tokens."""
    contexts: list[tuple[str, set[str]]] = []
    for sheet_index, sheet in enumerate(sheet_evidence):
        for tab_index, tab in enumerate(sheet.get("tabs", [])):
            for row in tab.get("row_units", []):
                visible_values = " ".join(
                    str(cell.get("value", ""))
                    for cell in row.get("cells", [])
                    if not str(cell.get("value", "")).casefold().startswith(("http://", "https://"))
                )
                row_tokens = tokens(visible_values)
                if row_tokens:
                    key = f"sheet:{sheet_index}:{tab_index}:{row.get('source_order', 0)}"
                    contexts.append((key, row_tokens))
    return contexts


def event_contexts(events: list[dict[str, Any]]) -> list[tuple[str, set[str]]]:
    """Return event identities and title tokens without interpreting event meaning."""
    return [
        (f"event:{event.get('id')}", event_tokens)
        for event in events
        if event.get("id") and (event_tokens := tokens(str(event.get("title", ""))))
    ]


def uniquely_matching_context(
    message_tokens: set[str],
    contexts: list[tuple[str, set[str]]],
    minimum_overlap: int,
    minimum_margin: int,
) -> str | None:
    """Choose a context only when one live candidate is a clear lexical winner."""
    scored = sorted(
        ((len(message_tokens & context_tokens), key) for key, context_tokens in contexts),
        key=lambda item: (-item[0], item[1]),
    )
    if not scored or scored[0][0] < minimum_overlap:
        return None
    runner_up = scored[1][0] if len(scored) > 1 else 0
    if scored[0][0] - runner_up < minimum_margin:
        return None
    return scored[0][1]


def mail_task_signals(
    message: dict[str, Any],
    rows: list[tuple[str, set[str]]],
    events: list[tuple[str, set[str]]],
) -> dict[str, str | None]:
    """Derive conservative task-identity signals only from live message/context data."""
    message_tokens = tokens(f"{message.get('subject', '')} {message.get('snippet', '')}")
    return {
        "thread": str(message.get("thread_id", "")) or None,
        "sheet_row": uniquely_matching_context(message_tokens, rows, minimum_overlap=4, minimum_margin=2),
        "event": uniquely_matching_context(message_tokens, events, minimum_overlap=3, minimum_margin=1),
    }


def same_task(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Return true only when conservative live-evidence identities agree."""
    left_signals = left["_task_signals"]
    right_signals = right["_task_signals"]
    if left_signals["thread"] and left_signals["thread"] == right_signals["thread"]:
        return True

    left_row = left_signals["sheet_row"]
    right_row = right_signals["sheet_row"]
    if left_row and right_row:
        return left_row == right_row

    left_event = left_signals["event"]
    right_event = right_signals["event"]
    return bool(left_event and left_event == right_event)


def group_ranked_mail(ranked_mail: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Preserve priority order while grouping messages with the same live task identity."""
    groups: list[list[dict[str, Any]]] = []
    for message in ranked_mail:
        matching_group = next(
            (group for group in groups if any(same_task(message, member) for member in group)),
            None,
        )
        if matching_group is None:
            groups.append([message])
        else:
            matching_group.append(message)
    return groups


def conflicts(events: list[dict[str, Any]], tz: ZoneInfo) -> list[dict[str, Any]]:
    timed: list[tuple[datetime, datetime, dict[str, Any]]] = []
    for event in events:
        start = parse_dt(event.get("start", ""), tz)
        end = parse_dt(event.get("end", ""), tz)
        if start and end:
            timed.append((start, end, event))
    timed.sort(key=lambda item: item[0])
    groups: list[list[tuple[datetime, datetime, dict[str, Any]]]] = []
    current: list[tuple[datetime, datetime, dict[str, Any]]] = []
    max_end: datetime | None = None
    for item in timed:
        if current and max_end and item[0] < max_end:
            current.append(item)
            max_end = max(max_end, item[1])
        else:
            if len(current) > 1:
                groups.append(current)
            current = [item]
            max_end = item[1]
    if len(current) > 1:
        groups.append(current)

    return [
        {
            "start": min(item[0] for item in group).isoformat(),
            "end": max(item[1] for item in group).isoformat(),
            "events": [
                {
                    "id": item[2].get("id"),
                    "title": item[2].get("title"),
                    "start": item[2].get("start"),
                    "end": item[2].get("end"),
                }
                for item in group
            ],
        }
        for group in groups
    ]


def focus_blocks(
    events: list[dict[str, Any]],
    tz: ZoneInfo,
    day_value: str,
    start_hour: int,
    end_hour: int,
    minimum: int,
) -> list[dict[str, Any]]:
    target = datetime.fromisoformat(day_value).astimezone(tz).date()
    cursor = datetime.combine(target, time(hour=start_hour), tzinfo=tz)
    work_end = datetime.combine(target, time(hour=end_hour), tzinfo=tz)
    intervals: list[tuple[datetime, datetime]] = []
    for event in events:
        start = parse_dt(event.get("start", ""), tz)
        end = parse_dt(event.get("end", ""), tz)
        if start and end and start.date() == target and end > cursor and start < work_end:
            intervals.append((max(start, cursor), min(end, work_end)))
    intervals.sort()
    merged: list[tuple[datetime, datetime]] = []
    for start, end in intervals:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    blocks: list[dict[str, Any]] = []
    for start, end in merged:
        if start > cursor and (start - cursor) >= timedelta(minutes=minimum):
            blocks.append({
                "start": cursor.isoformat(),
                "end": start.isoformat(),
                "minutes": int((start - cursor).total_seconds() // 60),
            })
        cursor = max(cursor, end)
    if work_end > cursor and (work_end - cursor) >= timedelta(minutes=minimum):
        blocks.append({
            "start": cursor.isoformat(),
            "end": work_end.isoformat(),
            "minutes": int((work_end - cursor).total_seconds() // 60),
        })
    return blocks


def linked_context(
    event: dict[str, Any],
    messages: list[dict[str, Any]],
    files: list[dict[str, Any]],
) -> dict[str, Any]:
    """Attach generic lexical matches without scoring or selecting outcomes."""
    event_tokens = tokens(f"{event.get('title', '')} {event.get('organizer', '')}")
    mail_matches = []
    for message in messages:
        overlap = sorted(event_tokens & tokens(
            f"{message.get('subject', '')} {message.get('from', '')} {message.get('snippet', '')}"
        ))
        organizer = event.get("organizer", "")
        if len(overlap) >= 2 or (
            overlap and organizer and organizer.casefold() in message.get("from", "").casefold()
        ):
            mail_matches.append({
                "id": message.get("id"),
                "thread_id": message.get("thread_id"),
                "subject": message.get("subject"),
                "from": message.get("from"),
                "match": overlap[:5],
            })
    file_matches = []
    for item in files:
        overlap = sorted(event_tokens & tokens(f"{item.get('name', '')} {item.get('description', '')}"))
        if overlap:
            file_matches.append({
                "id": item.get("id"),
                "name": item.get("name"),
                "kind": item.get("kind"),
                "url": item.get("url"),
                "match": overlap[:5],
            })
    return {"mail": mail_matches[:2], "files": file_matches[:2]}


def compact_sheet_evidence(previews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Make structural row boundaries explicit without mapping headers to business fields."""
    output = []
    source_order = 0
    for sheet in previews:
        compact_tabs = []
        for tab in sheet.get("tabs", []):
            table = tab.get("table", {})
            headers = {
                str(item.get("column", "")): str(item.get("name", ""))
                for item in table.get("columns", [])
            }
            row_units = []
            for row in table.get("representative_rows", []):
                source_order += 1
                row_units.append({
                    "source_order": source_order,
                    "cells": [
                        {
                            "column": column,
                            "header": headers.get(column, column),
                            "value": value,
                        }
                        for column, value in row.get("values", {}).items()
                    ],
                })
            compact_tabs.append({
                "title": tab.get("title"),
                "schema": table.get("columns", []),
                "row_count": table.get("row_count", 0),
                "row_units": row_units,
                "validation_previews": tab.get("validation_previews", []),
            })
        output.append({
            "id": sheet.get("id"),
            "name": sheet.get("name") or sheet.get("title"),
            "url": sheet.get("url"),
            "tabs": compact_tabs,
        })
    return output


def build_packet(snapshot: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    top_n = max(1, int(getattr(args, "top_n", 3)))
    tz_name = snapshot.get("timezone") or "UTC"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")
        tz_name = "UTC"
    events = snapshot.get("events", [])
    messages = snapshot.get("messages", [])
    files = snapshot.get("files", [])
    sheet_previews = snapshot.get("sheets", [])
    sheet_evidence = compact_sheet_evidence(sheet_previews)
    generated = parse_dt(snapshot.get("generated_at", ""), tz) or datetime.now(tz)
    self_email = str(snapshot.get("identity", {}).get("email", ""))
    row_contexts = sheet_row_contexts(sheet_evidence)
    calendar_contexts = event_contexts(events)

    meetings = []
    for event in events:
        meetings.append({
            "id": event.get("id"),
            "title": event.get("title"),
            "start": event.get("start"),
            "end": event.get("end"),
            "all_day": event.get("all_day"),
            "organizer": event.get("organizer"),
            "self_status": event.get("self_status"),
            "attendee_count": len(event.get("attendees", [])),
            "meeting_url": event.get("meeting_url"),
            "calendar_url": event.get("html_link"),
            "links": event.get("links", []),
            "related": linked_context(event, messages, files),
        })

    recent_mail = []
    for message in messages:
        internal_ms = int(message.get("internal_ms", 0) or 0)
        received = datetime.fromtimestamp(internal_ms / 1000, tz=tz) if internal_ms else None
        age_days = max(0, (generated.date() - received.date()).days) if received else None
        recent_mail.append({
            "id": message.get("id"),
            "thread_id": message.get("thread_id"),
            "url": f"https://mail.google.com/mail/u/0/#all/{message.get('thread_id')}",
            "from": message.get("from"),
            "subject": message.get("subject"),
            "date": message.get("date"),
            "age_days": age_days,
            "stale_timing": age_days is not None and age_days > 1,
            "snippet": message.get("snippet"),
            "unread": message.get("unread"),
            "important": message.get("important"),
            "links": message.get("links", []),
            "_priority": deterministic_mail_priority(message, self_email),
            "_task_signals": mail_task_signals(message, row_contexts, calendar_contexts),
        })
    recent_mail.sort(key=lambda message: message["_priority"])
    ordering = "gmail_metadata_priority_then_recency"
    selection_basis = "important_then_direct_then_unread_then_newest_distinct_live_tasks"
    mail_groups = group_ranked_mail(recent_mail)
    selected_groups = mail_groups[:top_n]
    selected_item_count = len(selected_groups)
    selected_event_ids = {
        signal.removeprefix("event:")
        for group in selected_groups
        for message in group
        if (signal := message.get("_task_signals", {}).get("event"))
    }
    meetings.sort(key=lambda meeting: meeting.get("id") not in selected_event_ids)

    required_ids: set[str] = set()
    for selection_order, group in enumerate(selected_groups, 1):
        primary = group[0]
        primary["selected_for_output"] = True
        primary["selection_order"] = selection_order
        required_ids.add(str(primary.get("id", "")))
        # One bounded supporting message is enough to preserve distinct evidence
        # without expanding the existing packet or response shape.
        for supporting in group[1:2]:
            supporting["selected_for_output"] = False
            supporting["supports_selection_order"] = selection_order
            required_ids.add(str(supporting.get("id", "")))

    for item in recent_mail:
        item.setdefault("selected_for_output", False)

    max_mail = max(1, int(args.max_mail))
    required_mail = [item for item in recent_mail if str(item.get("id", "")) in required_ids]
    remaining_mail = [item for item in recent_mail if str(item.get("id", "")) not in required_ids]
    bounded_mail = required_mail + remaining_mail[:max(0, max_mail - len(required_mail))]
    for item in bounded_mail:
        item.pop("_priority", None)
        item.pop("_task_signals", None)

    recent_files = [
        {k: item.get(k) for k in ("id", "name", "kind", "modified", "url", "starred", "last_editor")}
        for item in files[:args.max_files]
    ]
    window_start = snapshot.get("window", {}).get("start") or datetime.now(tz).isoformat()
    coverage = snapshot.get("coverage", {})
    error_text = " ".join(str(error).casefold() for error in coverage.get("errors", []))
    source_status = {
        "calendar": "error" if "calendar" in error_text else ("ok" if events else "ok_empty"),
        "gmail": "error" if "gmail" in error_text else ("ok" if messages else "ok_empty"),
        "drive": "error" if "drive" in error_text else ("ok" if files else "ok_empty"),
        "sheets": "error" if "sheets" in error_text else ("ok" if sheet_previews else "ok_empty"),
    }
    temporary_markers = (
        "timed out",
        "timeout",
        "temporarily unavailable",
        "connection reset",
        "remote end closed",
    )
    if any(marker in error_text for marker in temporary_markers):
        return {
            "schema": 3,
            "temporary_google_error": True,
            "instruction": f"Return exactly this sentence: {GOOGLE_TEMPORARY_USER_MESSAGE}",
            "user_message": GOOGLE_TEMPORARY_USER_MESSAGE,
            "coverage": coverage,
            "source_status": source_status,
            "response_contract": {
                "item_count": 0,
                "rule": "Do not render priorities or use partial Workspace data. Return user_message exactly.",
            },
        }
    packet = {
        "schema": 3,
        "instruction": f"Render {selected_item_count} pre-ranked distinct items. selected_for_output marks each primary; supports_selection_order attaches mail evidence. Do not rank or regroup.",
        "ordering_contract": [
            "Python grouped mail by live identity and ranked it with generic Gmail metadata.",
            "Render one item per selected_for_output primary in selection_order. Do not score, rank, regroup, reorder, merge, replace, or skip items.",
            "Mail with supports_selection_order N is context for item N, not a separate item.",
            "Other Workspace data may enrich a clearly related item but cannot change the selected items or order.",
            "Use only live values; never use remembered or repository-defined mappings.",
            "Name pending work without implying it is complete. Use past tense only for facts already completed.",
        ],
        "response_contract": {
            "summary": "Begin with exactly one unnumbered sentence and then item 1 when items exist; write no heading, preamble, or second summary sentence.",
            "item_count": selected_item_count,
            "item_template": [
                "N. **WORK ITEM NAME**",
                "   - **Context:** One or two high-level sentences explaining what needs attention and why it matters now. [RESOURCE_KIND](MATCHING_RESOURCE_URL) [Mail — SENDER](GMAIL_URL)",
            ],
            "item_identity_rule": "Item N uses the selected primary with selection_order N. Mail with supports_selection_order N belongs only to item N.",
            "link_rule": "Include primary and assigned supporting [Mail — SENDER](URL) links with exact sender names. Add one clearly related Calendar, Sheet, Doc, Slides, or Drive target. Never invent or link an unrelated resource.",
            "self_check": [
                "The response has one opening sentence, exactly item_count items in selection_order, and exactly two lines per item.",
                "Each item is anchored to its matching selected primary mail entry and includes the primary and all assigned supporting Mail links with exact sender names.",
                "Any Calendar or Drive link is supported by the packet and belongs to that selected item's outcome.",
                "Titles name pending work and do not claim that requested work is already complete.",
                "The response ends with the final Context line and contains none of the forbidden content.",
            ],
            "forbidden": [
                "raw IDs, helper names, flags, commands, row numbers, cell coordinates, scores, JSON, or schema commentary",
                "action checklists, conflict/focus sections, horizontal rules, closing questions, offers, or text after the last Context line",
            ],
            "forbidden_tokens": ["`", "--", "calendar find", "calendar reschedule", "sheets inspect", "sheets set-cell", "slides replace-text"],
        },
        "requested_top_n": top_n,
        "selected_item_count": selected_item_count,
        "ordering": ordering,
        "selection_basis": selection_basis,
        "freshness": {"generated_at": snapshot.get("generated_at"), "timezone": tz_name, "window": snapshot.get("window")},
        "coverage": coverage,
        "source_status": source_status,
        "conflicts": conflicts(events, tz),
        "focus_blocks": focus_blocks(events, tz, window_start, args.work_start, args.work_end, args.min_focus_minutes),
        "meetings": meetings[:args.max_meetings],
        "mail": bounded_mail,
        "recent_files": recent_files,
        "sheet_evidence": sheet_evidence,
    }
    # Keep the strict presentation contract last so local models see it after
    # the evidence they must interpret.
    packet["response_contract"] = packet.pop("response_contract")
    return packet


def fit_packet(packet: dict[str, Any], max_chars: int) -> str:
    for mail in packet.get("mail", []):
        mail["snippet"] = (mail.get("snippet") or "")[:320]

    def encode() -> str:
        return json.dumps(packet, ensure_ascii=False, separators=(",", ":"))

    def trim_list(name: str, floor: int) -> None:
        items = packet.get(name, [])
        while len(items) > floor and len(encode()) > max_chars:
            items.pop()

    def trim_sheet_samples(floor: int) -> None:
        while len(encode()) > max_chars:
            candidates = [
                tab.get("row_units", [])
                for sheet in packet.get("sheet_evidence", [])
                for tab in sheet.get("tabs", [])
            ]
            target = max(candidates, key=len, default=[])
            if len(target) <= floor:
                break
            target.pop()

    encoded = encode()
    if len(encoded) <= max_chars:
        return encoded

    selected_item_count = max(0, int(packet.get("selected_item_count") or 0))
    minimum_sheet_rows = max(3, selected_item_count)
    protected_mail_count = sum(
        1
        for mail in packet.get("mail", [])
        if mail.get("selected_for_output") or mail.get("supports_selection_order")
    )

    # Preserve selected anchors while trimming lower-value supporting context first.
    trim_list("recent_files", 4)
    trim_list("meetings", 5)
    trim_list("mail", max(6, protected_mail_count))
    trim_sheet_samples(minimum_sheet_rows)
    trim_list("meetings", 3)
    trim_list("recent_files", 2)
    trim_list("conflicts", 3)
    trim_sheet_samples(minimum_sheet_rows)
    trim_list("meetings", 1)
    trim_list("recent_files", 1)
    trim_list("conflicts", 1)
    trim_list("focus_blocks", 2)
    trim_sheet_samples(minimum_sheet_rows)
    trim_list("mail", max(3, protected_mail_count))
    trim_list("mail", max(1, protected_mail_count))

    if len(encode()) > max_chars:
        for mail in packet.get("mail", []):
            mail["snippet"] = (mail.get("snippet") or "")[:160]

    for name in ("sheet_evidence", "recent_files", "meetings", "conflicts", "focus_blocks"):
        trim_list(name, 0)

    if len(encode()) > max_chars:
        for mail in packet.get("mail", []):
            mail["snippet"] = (mail.get("snippet") or "")[:96]
            for field in ("id", "thread_id", "age_days", "stale_timing", "unread", "important", "links"):
                mail.pop(field, None)

    return encode()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a compact chief-of-staff decision packet")
    parser.add_argument("--snapshot", type=Path, default=default_snapshot())
    parser.add_argument("--max-meetings", type=int, default=15)
    parser.add_argument("--max-mail", type=int, default=12)
    parser.add_argument("--max-files", type=int, default=12)
    parser.add_argument("--max-chars", type=int, default=14000)
    parser.add_argument("--top", dest="top_n", type=int, default=3, help="Number of selected mail anchors to return")
    parser.add_argument("--work-start", type=int, default=8)
    parser.add_argument("--work-end", type=int, default=18)
    parser.add_argument("--min-focus-minutes", type=int, default=30)
    args = parser.parse_args()
    if args.top_n < 1:
        parser.error("--top must be a positive integer")
    if not args.snapshot.exists():
        print(json.dumps({"ok": False, "error": f"Snapshot not found: {args.snapshot}"}), file=sys.stderr)
        return 1
    try:
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        packet = build_packet(snapshot, args)
        print(fit_packet(packet, args.max_chars))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
