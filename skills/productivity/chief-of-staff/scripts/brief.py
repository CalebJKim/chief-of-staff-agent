#!/usr/bin/env python
"""Turn a bounded Workspace snapshot into a compact decision packet."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, time, timedelta
from email.utils import parseaddr
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

KEYWORDS = {
    "urgent": 8,
    "blocker": 8,
    "deadline": 7,
    "decision": 7,
    "approve": 6,
    "approval": 6,
    "customer": 6,
    "launch": 6,
    "exec": 6,
    "board": 7,
    "investor": 6,
    "follow up": 5,
    "action required": 7,
    "review": 3,
    "update": 2,
}
STOPWORDS = {
    "about", "after", "before", "could", "from", "have", "into", "meeting", "notes",
    "that", "their", "there", "these", "this", "today", "update", "with", "your",
}
STATUS_PRIORITY = {
    "blocked": 100,
    "awaiting update": 40,
    "in progress": 50,
    "not started": 30,
    "ready for review": 20,
    "in review": 10,
    "on track": 0,
    "complete": -100,
}
TRACKER_STATUSES = (
    "Not started", "In progress", "Ready for review", "On track",
    "In review", "Awaiting update", "Blocked", "Complete",
)
WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


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


def keyword_score(text: str) -> tuple[int, list[str]]:
    lowered = (text or "").casefold()
    matches = [word for word in KEYWORDS if word in lowered]
    return sum(KEYWORDS[word] for word in matches), matches


def event_score(event: dict[str, Any], self_email: str) -> tuple[int, list[str]]:
    text = f"{event.get('title', '')} {event.get('location', '')}"
    score, hits = keyword_score(text)
    reasons = [f"keyword:{hit}" for hit in hits]
    attendees = event.get("attendees", [])
    others = [a for a in attendees if not a.get("self")]
    if len(others) >= 5:
        score += 3
        reasons.append("many attendees")
    organizer = event.get("organizer", "").casefold()
    if organizer and self_email and self_email.casefold() == organizer:
        score += 2
        reasons.append("you organize")
    domains = {a.get("email", "").split("@")[-1].casefold() for a in others if "@" in a.get("email", "")}
    own_domain = self_email.split("@")[-1].casefold() if "@" in self_email else ""
    if any(domain and domain != own_domain for domain in domains):
        score += 4
        reasons.append("external attendees")
    if event.get("self_status") == "needsAction":
        reasons.append("invitation unanswered")
    return score, reasons


def mail_score(message: dict[str, Any], self_email: str) -> tuple[int, list[str]]:
    text = f"{message.get('subject', '')} {message.get('snippet', '')}"
    score, hits = keyword_score(text)
    reasons = [f"keyword:{hit}" for hit in hits]
    if message.get("unread"):
        score += 2
        reasons.append("unread")
    if message.get("important"):
        score += 4
        reasons.append("gmail-important")
    to_line = f"{message.get('to', '')} {message.get('cc', '')}".casefold()
    if self_email and self_email.casefold() in to_line and "," not in message.get("to", ""):
        score += 3
        reasons.append("directly addressed")
    return score, reasons


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

    output = []
    for group in groups:
        output.append({
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
        })
    return output


def focus_blocks(events: list[dict[str, Any]], tz: ZoneInfo, day_value: str, start_hour: int, end_hour: int, minimum: int) -> list[dict[str, Any]]:
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
            blocks.append({"start": cursor.isoformat(), "end": start.isoformat(), "minutes": int((start - cursor).total_seconds() // 60)})
        cursor = max(cursor, end)
    if work_end > cursor and (work_end - cursor) >= timedelta(minutes=minimum):
        blocks.append({"start": cursor.isoformat(), "end": work_end.isoformat(), "minutes": int((work_end - cursor).total_seconds() // 60)})
    return blocks


def linked_context(event: dict[str, Any], messages: list[dict[str, Any]], files: list[dict[str, Any]]) -> dict[str, Any]:
    event_tokens = tokens(f"{event.get('title', '')} {event.get('organizer', '')}")
    mail_matches = []
    for message in messages:
        overlap = sorted(event_tokens & tokens(f"{message.get('subject', '')} {message.get('from', '')} {message.get('snippet', '')}"))
        if len(overlap) >= 2 or (overlap and event.get("organizer", "") and event.get("organizer", "").casefold() in message.get("from", "").casefold()):
            mail_matches.append({"id": message.get("id"), "thread_id": message.get("thread_id"), "subject": message.get("subject"), "from": message.get("from"), "match": overlap[:5]})
    file_matches = []
    for item in files:
        overlap = sorted(event_tokens & tokens(f"{item.get('name', '')} {item.get('description', '')}"))
        if overlap:
            file_matches.append({"id": item.get("id"), "name": item.get("name"), "kind": item.get("kind"), "url": item.get("url"), "match": overlap[:5]})
    return {"mail": mail_matches[:2], "files": file_matches[:2]}


def resource_id(url: str) -> str:
    match = re.search(r"/(?:d|folders)/([^/?#]+)", url or "")
    return match.group(1) if match else ""


def scheduled_time(text: str, generated: datetime, tz: ZoneInfo) -> datetime | None:
    """Resolve a weekday-and-time instruction such as "Monday at 11 AM PT"."""
    match = re.search(
        r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b"
        r".*?\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    hour = int(match.group(2)) % 12
    if match.group(4).casefold() == "pm":
        hour += 12
    minute = int(match.group(3) or 0)
    target_weekday = WEEKDAYS[match.group(1).casefold()]
    days_ahead = (target_weekday - generated.weekday()) % 7
    target_date = generated.date() + timedelta(days=days_ahead)
    result = datetime.combine(target_date, time(hour=hour, minute=minute), tzinfo=tz)
    if result <= generated:
        result += timedelta(days=7)
    return result


def desired_tracker_status(text: str, current: str) -> str:
    lowered = text.casefold()
    return next(
        (status for status in TRACKER_STATUSES if status.casefold() != current.casefold() and status.casefold() in lowered),
        "",
    )


def slide_replacement(text: str) -> tuple[str, str] | None:
    match = re.search(
        r"\breplace\s+([A-Z][A-Z0-9 _-]{3,}?)\s+with\s+[\"“](.+?)[\"”](?:\s|[.;]|$)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    return match.group(1).strip(), match.group(2).strip()


def first_name(address: str) -> str:
    display, email = parseaddr(address or "")
    if display:
        return display.split()[0]
    return email.split("@", 1)[0].split(".", 1)[0].title()


def workstream_action(
    row: dict[str, Any],
    target: dict[str, Any],
    supporting: dict[str, Any] | None,
    related_mail: list[dict[str, Any]],
    generated: datetime,
    tz: ZoneInfo,
) -> dict[str, Any] | None:
    """Build exact, verified helper steps from the same evidence used to rank a row."""
    next_action = str(row.get("next") or "")
    next_lower = next_action.casefold()

    if target.get("label") == "Calendar" and "draft" in next_lower and supporting:
        evidence_text = " ".join(
            [next_action, str(row.get("latest") or "")]
            + [f"{item.get('subject', '')} {item.get('snippet', '')}" for item in related_mail]
        )
        new_start = scheduled_time(evidence_text, generated, tz)
        old_start = parse_dt(str(target.get("start") or ""), tz)
        old_end = parse_dt(str(target.get("end") or ""), tz)
        cc_message = next(
            (
                item for item in related_mail
                if item.get("id") != supporting.get("id")
                and ("new slot" in str(item.get("subject") or "").casefold() or "draft" in str(item.get("snippet") or "").casefold())
            ),
            None,
        )
        cc_address = parseaddr(str((cc_message or {}).get("from") or ""))[1]
        if new_start and old_start and old_end and cc_address and target.get("id") and supporting.get("id"):
            new_end = new_start + (old_end - old_start)
            recipients = " and ".join(filter(None, [first_name(str(supporting.get("from") or "")), first_name(str(cc_message.get("from") or ""))]))
            when = new_start.strftime("%A, %B %-d at %-I:%M %p") if os.name != "nt" else new_start.strftime("%A, %B %#d at %#I:%M %p")
            body = (
                f"Hi {recipients},\n\n"
                f"I moved the {target.get('name')} to {when} PT. "
                "The event details are unchanged.\n\nThanks"
            )
            return {
                "kind": "calendar_move_and_draft",
                "steps": [
                    ["calendar", "move", str(target["id"]), "--start", new_start.isoformat(), "--end", new_end.isoformat()],
                    ["gmail", "draft", "--reply-to-message", str(supporting["id"]), "--cc", cc_address, "--body", body],
                ],
            }

    if target.get("label") == "Tracker":
        status = desired_tracker_status(next_action, str(row.get("status") or ""))
        if status and target.get("id") and row.get("lane"):
            return {
                "kind": "tracker_status",
                "steps": [["sheets", "update-lanes", str(target["id"]), "--lane", str(row["lane"]), "--status", status]],
            }

    if target.get("label") == "Deck":
        evidence_text = " ".join(
            [next_action, str(row.get("latest") or "")]
            + [str(item.get("snippet") or "") for item in related_mail]
        )
        replacement = slide_replacement(evidence_text)
        if replacement and target.get("id"):
            old, new = replacement
            return {
                "kind": "slides_replace_text",
                "steps": [["slides", "replace-text", str(target["id"]), "--find", old, "--replace", new]],
            }
    return None


def build_workstreams(
    trackers: list[dict[str, Any]],
    mail: list[dict[str, Any]],
    meetings: list[dict[str, Any]],
    files: list[dict[str, Any]],
    generated: datetime,
    tz: ZoneInfo,
) -> list[dict[str, Any]]:
    """Rank actionable tracker rows and attach their supporting mail and write target."""
    candidates: list[tuple[int, int, int, dict[str, Any], dict[str, Any]]] = []
    for tracker_index, tracker in enumerate(trackers):
        for row_index, row in enumerate(tracker.get("rows", [])):
            status = str(row.get("status") or "").casefold()
            next_action = str(row.get("next") or "")
            if status == "complete" or not next_action or "no further action" in next_action.casefold():
                continue
            priority = STATUS_PRIORITY.get(status, 5)
            blocker = str(row.get("blocker") or "").casefold()
            if blocker and not blocker.startswith("none"):
                priority += 20
            candidates.append((priority, tracker_index, row_index, tracker, row))
    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))

    output = []
    for _, _, _, tracker, row in candidates[:3]:
        row_text = " ".join(str(row.get(key) or "") for key in ("lane", "pic", "latest", "next", "blocker"))
        row_tokens = tokens(row_text)
        evidence = str(row.get("evidence") or "")
        supporting = next((item for item in mail if evidence and item.get("url") == evidence), None)
        related_mail = sorted(
            mail,
            key=lambda item: -len(row_tokens & tokens(f"{item.get('subject', '')} {item.get('from', '')} {item.get('snippet', '')}")),
        )[:2]
        if supporting is None and related_mail:
            supporting = related_mail[0]

        next_lower = str(row.get("next") or "").casefold()
        target: dict[str, Any] | None = None
        if any(word in next_lower for word in ("move", "reschedule", "postpone", "cancel")):
            event = max(
                meetings,
                key=lambda item: len(row_tokens & tokens(str(item.get("title") or ""))),
                default=None,
            )
            if event and row_tokens & tokens(str(event.get("title") or "")):
                target = {
                    "label": "Calendar",
                    "id": event.get("id"),
                    "name": event.get("title"),
                    "url": event.get("calendar_url"),
                    "start": event.get("start"),
                    "end": event.get("end"),
                }
        if target is None and any(word in next_lower for word in ("status", "lane")):
            target = {"label": "Tracker", "id": tracker.get("id"), "name": tracker.get("name"), "url": tracker.get("url")}
        if target is None:
            artifact_id = resource_id(str(row.get("artifact") or ""))
            artifact = next((item for item in files if artifact_id and item.get("id") == artifact_id), None)
            if artifact:
                label = {"slides": "Deck", "sheet": "Tracker"}.get(str(artifact.get("kind") or ""), "Drive")
                target = {"label": label, "id": artifact.get("id"), "name": artifact.get("name"), "url": artifact.get("url")}
        if target is None:
            target = {"label": "Drive", "url": row.get("artifact")}

        action = workstream_action(row, target, supporting, related_mail, generated, tz)

        def compact_mail(item: dict[str, Any] | None) -> dict[str, Any]:
            if not item:
                return {}
            return {key: item.get(key) for key in ("id", "thread_id", "url", "from", "subject")}

        item = {
            "outcome": row.get("lane"),
            "status": row.get("status"),
            "latest": row.get("latest"),
            "next": row.get("next"),
            "supporting_mail": compact_mail(supporting),
            "related_mail": [
                compact_mail(item)
                for item in related_mail
                if not supporting or item.get("id") != supporting.get("id")
            ][:1],
            "target": target,
        }
        if action:
            item["_action"] = action
        output.append(item)
    return output


def prepare_action_plan(packet: dict[str, Any]) -> dict[str, Any]:
    """Extract private action details and leave only short executable commands in the packet."""
    plan = {
        "schema": 1,
        "generated_at": packet.get("freshness", {}).get("generated_at"),
        "workstreams": [],
    }
    for index, workstream in enumerate(packet.get("workstreams", []), start=1):
        action = workstream.pop("_action", None)
        plan["workstreams"].append({
            "outcome": workstream.get("outcome"),
            "target": workstream.get("target"),
            "action": action,
        })
        if action:
            workstream["action_command"] = f'bash "$HERMES_HOME/cos.sh" {index}'
    return plan


def write_action_plan(plan: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def render_initial_reply(packet: dict[str, Any]) -> str:
    """Render ranked workstreams without exposing action commands or internal IDs."""
    workstreams = packet.get("workstreams", [])[:3]
    if len(workstreams) != 3:
        raise ValueError("A preformatted brief requires exactly three ranked workstreams")

    def display_text(value: Any) -> str:
        return str(value).strip().replace("\u2018", "'").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')

    outcomes = [display_text(item.get("outcome") or "Untitled priority") for item in workstreams]
    lines = [f"Today's workload centers on {outcomes[0]}, {outcomes[1]}, and {outcomes[2]}."]
    for index, item in enumerate(workstreams, start=1):
        latest = display_text(item.get("latest") or "This priority needs attention")
        if latest[-1:] not in ".!?:":
            latest += "."
        next_action = display_text(item.get("next") or "Review the available evidence and choose the next action.")
        supporting_mail = item.get("supporting_mail") or {}
        target = item.get("target") or {}
        mail_url = supporting_mail.get("url")
        target_url = target.get("url")
        target_label = target.get("label")
        if not mail_url or not target_url or not target_label:
            raise ValueError(f"Workstream {index} is missing its supporting mail or action-target link")
        lines.extend([
            "",
            f"{index}. **{outcomes[index - 1]}**",
            f"   {latest} [Mail]({mail_url}) [{target_label}]({target_url})",
            f"   - **Recommended action item(s):** {next_action}",
        ])
    return "\n".join(lines)


def build_packet(snapshot: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    tz_name = snapshot.get("timezone") or "UTC"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")
        tz_name = "UTC"
    identity = snapshot.get("identity", {})
    self_email = identity.get("email", "")
    events = snapshot.get("events", [])
    messages = snapshot.get("messages", [])
    files = snapshot.get("files", [])
    trackers = [
        {
            "id": tracker.get("id"),
            "name": tracker.get("name"),
            "url": tracker.get("url"),
            "rows": [
                {key: row.get(key) for key in ("row", "lane", "pic", "status", "latest", "next", "blocker", "evidence", "artifact")}
                for row in tracker.get("rows", [])
            ],
        }
        for tracker in snapshot.get("trackers", [])
    ]
    generated = parse_dt(snapshot.get("generated_at", ""), tz) or datetime.now(tz)

    ranked_events = []
    for event in events:
        score, reasons = event_score(event, self_email)
        context = linked_context(event, messages, files)
        ranked_events.append({
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
            "signal_score": score,
            "signals": reasons,
            "related": context,
        })
    ranked_events.sort(key=lambda e: (-e["signal_score"], e.get("start") or ""))

    ranked_mail = []
    for message in messages:
        score, reasons = mail_score(message, self_email)
        internal_ms = int(message.get("internal_ms", 0) or 0)
        received = datetime.fromtimestamp(internal_ms / 1000, tz=tz) if internal_ms else None
        age_days = max(0, (generated.date() - received.date()).days) if received else None
        ranked_mail.append({
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
            "links": message.get("links", []),
            "signal_score": score,
            "signals": reasons,
        })
    ranked_mail.sort(key=lambda m: (-m["signal_score"], -next((x.get("internal_ms", 0) for x in messages if x.get("id") == m.get("id")), 0)))
    for item in ranked_events + ranked_mail:
        item.pop("signal_score", None)

    recent_files = [
        {k: item.get(k) for k in ("id", "name", "kind", "modified", "url", "starred", "last_editor")}
        for item in files[: args.max_files]
    ]
    window_start = snapshot.get("window", {}).get("start") or datetime.now(tz).isoformat()
    coverage = snapshot.get("coverage", {})
    error_text = " ".join(str(error).casefold() for error in coverage.get("errors", []))
    source_status = {
        "calendar": "error" if "calendar" in error_text else ("ok" if events else "ok_empty"),
        "gmail": "error" if "gmail" in error_text else ("ok" if messages else "ok_empty"),
        "drive": "error" if "drive" in error_text else ("ok" if files else "ok_empty"),
    }
    packet = {
        "schema": 1,
        "instruction": "When workstreams has three items, render workstreams[0:3] exactly once and in order; never split, merge, or re-rank them. Otherwise rank up to three distinct outcomes from the remaining evidence. Begin with a very short plain-text summary of today's workload in no more than three sentences and no heading. Then render exactly three numbered items. Each item must have a bold outcome line, one concise evidence sentence using latest and ending with exactly two inline links (supporting_mail as Mail and target with its supplied label), and an indented sub-bullet labeled exactly `Recommended action item(s):` using next. No tables, inbox inventory, extra sections, closing question, scores, browser launches, or more tools; end after item 3's action sub-bullet. stale_timing means historical timing: verify it and never call it due today. ok_empty means success with zero results.",
        "freshness": {"generated_at": snapshot.get("generated_at"), "timezone": tz_name, "window": snapshot.get("window")},
        "coverage": coverage,
        "source_status": source_status,
        "workstreams": build_workstreams(trackers, ranked_mail, ranked_events, recent_files, generated, tz),
        "conflicts": conflicts(events, tz),
        "focus_blocks": focus_blocks(events, tz, window_start, args.work_start, args.work_end, args.min_focus_minutes),
        "meetings": ranked_events[: args.max_meetings],
        "mail": ranked_mail[: args.max_mail],
        "recent_files": recent_files,
        "trackers": trackers,
    }
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

    def trim_tracker_rows(floor: int) -> None:
        while len(encode()) > max_chars:
            candidates = [tracker.get("rows", []) for tracker in packet.get("trackers", [])]
            target = max(candidates, key=len, default=[])
            if len(target) <= floor:
                break
            target.pop()

    encoded = encode()
    if len(encoded) <= max_chars:
        return encoded

    # Preserve the six highest-signal messages long enough for the reference
    # demo while shedding lower-value duplicates first. More aggressive stages
    # still guarantee unusually small caller budgets are honored.
    trim_list("recent_files", 4)
    trim_list("meetings", 5)
    trim_list("mail", 6)
    # Data-ranked workstreams already preserve the actionable tracker rows, so
    # prefer dropping their raw duplicates over losing meaningful mail.
    trim_tracker_rows(0 if packet.get("workstreams") else 6)
    trim_list("meetings", 3)
    trim_list("recent_files", 2)
    trim_tracker_rows(3)
    trim_list("conflicts", 3)
    trim_list("meetings", 1)
    trim_list("recent_files", 1)
    trim_tracker_rows(1)
    trim_list("conflicts", 1)
    trim_list("focus_blocks", 2)
    trim_list("mail", 3)
    trim_list("mail", 1)

    if len(encode()) > max_chars:
        for mail in packet.get("mail", []):
            mail["snippet"] = (mail.get("snippet") or "")[:160]

    for name in ("trackers", "recent_files", "meetings", "mail", "conflicts", "focus_blocks"):
        trim_list(name, 0)

    return encode()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a compact chief-of-staff decision packet")
    parser.add_argument("--snapshot", type=Path, default=default_snapshot())
    parser.add_argument("--max-meetings", type=int, default=15)
    parser.add_argument("--max-mail", type=int, default=12)
    parser.add_argument("--max-files", type=int, default=12)
    parser.add_argument("--max-chars", type=int, default=14000)
    parser.add_argument("--action-plan", type=Path, default=hermes_home() / "chief-of-staff" / "action-plan.json")
    parser.add_argument("--work-start", type=int, default=8)
    parser.add_argument("--work-end", type=int, default=18)
    parser.add_argument("--min-focus-minutes", type=int, default=30)
    parser.add_argument("--reply-only", action="store_true", help="Print the preformatted top-three reply")
    args = parser.parse_args()
    if not args.snapshot.exists():
        print(json.dumps({"ok": False, "error": f"Snapshot not found: {args.snapshot}"}), file=sys.stderr)
        return 1
    try:
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        packet = build_packet(snapshot, args)
        write_action_plan(prepare_action_plan(packet), args.action_plan)
        print(render_initial_reply(packet) if args.reply_only else fit_packet(packet, args.max_chars))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
