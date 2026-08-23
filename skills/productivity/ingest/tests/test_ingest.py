from __future__ import annotations

import argparse
import base64
import email
import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).resolve().parents[2] / "chief-of-staff" / "tests" / "fixtures" / "workspace.json"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ingest = load("cos_ingest", ROOT / "scripts" / "ingest.py")
actions = load("cos_actions", ROOT / "scripts" / "actions.py")


class IngestTests(unittest.TestCase):
    def test_fixture_round_trip_is_bounded(self):
        args = argparse.Namespace(fixture=FIXTURE)
        snapshot = ingest.collect(args)
        self.assertEqual(snapshot["source"], "fixture")
        self.assertEqual(snapshot["coverage"]["events"], 4)
        self.assertLessEqual(len(snapshot["messages"]), ingest.DEFAULT_MAX_MESSAGES)

    def test_mail_output_stays_at_twenty_after_broader_scan(self):
        self.assertEqual(20, ingest.DEFAULT_MAX_MESSAGES)
        self.assertEqual(120, ingest.DEFAULT_MAIL_SCAN_LIMIT)

    def test_weekday_demo_date_uses_today_and_weekend_uses_next_monday(self):
        self.assertEqual(date(2026, 8, 20), ingest.next_demo_weekday(date(2026, 8, 20)))
        self.assertEqual(date(2026, 8, 24), ingest.next_demo_weekday(date(2026, 8, 22)))
        self.assertEqual(date(2026, 8, 24), ingest.next_demo_weekday(date(2026, 8, 23)))

    def test_mail_is_sorted_after_scanning_beyond_the_output_limit(self):
        class Request:
            def __init__(self, value):
                self.value = value

            def execute(self):
                return self.value

        metadata = {
            "background-1": 1000,
            "background-2": 2000,
            "priority-1": 5000,
            "priority-2": 4000,
        }

        class Messages:
            def list(self, **kwargs):
                if kwargs.get("pageToken") == "page-2":
                    return Request({"messages": [{"id": "priority-1"}, {"id": "priority-2"}]})
                return Request({
                    "messages": [{"id": "background-1"}, {"id": "background-2"}],
                    "nextPageToken": "page-2",
                })

            def get(self, **kwargs):
                message_id = kwargs["id"]
                return Request({
                    "id": message_id,
                    "threadId": f"thread-{message_id}",
                    "internalDate": str(metadata[message_id]),
                    "labelIds": ["INBOX"],
                    "payload": {"headers": [{"name": "Subject", "value": message_id}]},
                })

        messages = Messages()

        class Users:
            def getProfile(self, **_kwargs):
                return Request({"emailAddress": "demo@example.test"})

            def messages(self):
                return messages

        class Api:
            def users(self):
                return Users()

        result, identity = ingest.fetch_mail(Api(), 30, 2, None, scan_limit=4)

        self.assertEqual(["priority-1", "priority-2"], [item["id"] for item in result])
        self.assertEqual(4, identity["mail_scanned"])

    def test_cloud_mutation_requires_confirmation(self):
        with self.assertRaisesRegex(RuntimeError, "without --confirm"):
            actions.require_confirm(argparse.Namespace(confirm=False), "test mutation")
        actions.require_confirm(argparse.Namespace(confirm=True), "test mutation")

    def test_one_time_codes_are_redacted_before_model_context(self):
        text = "Your verification code is 865913. It expires soon."
        redacted = ingest.redact_sensitive(text)
        self.assertNotIn("865913", redacted)
        self.assertIn("[REDACTED]", redacted)

    def test_reply_draft_is_threaded(self):
        captured = {}

        class Request:
            def __init__(self, value):
                self.value = value

            def execute(self):
                return self.value

        class Messages:
            def get(self, **_kwargs):
                return Request({
                    "threadId": "thread-1",
                    "payload": {"headers": [
                        {"name": "From", "value": "Person <person@example.com>"},
                        {"name": "Subject", "value": "Project update"},
                        {"name": "Message-ID", "value": "<original@example.com>"},
                    ]},
                })

        class Drafts:
            def create(self, **kwargs):
                captured.update(kwargs["body"])
                return Request({"id": "draft-1", "message": {"id": "message-1"}})

            def get(self, **_kwargs):
                return Request({"id": "draft-1", "message": {"id": "message-1"}})

        class Users:
            def messages(self):
                return Messages()

            def drafts(self):
                return Drafts()

        class Api:
            def users(self):
                return Users()

        original_service = actions.service
        actions.service = lambda *_args: Api()
        try:
            args = argparse.Namespace(
                to="",
                cc="",
                subject="",
                body="Thanks — I will update it.",
                thread_id="",
                reply_to_message="message-0",
            )
            with redirect_stdout(io.StringIO()):
                actions.gmail_draft(args)
        finally:
            actions.service = original_service

        self.assertEqual(captured["message"]["threadId"], "thread-1")
        raw = captured["message"]["raw"]
        parsed = email.message_from_bytes(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        self.assertEqual(parsed["To"], "Person <person@example.com>")
        self.assertEqual(parsed["Subject"], "Re: Project update")
        self.assertEqual(parsed["In-Reply-To"], "<original@example.com>")

    def test_demo_draft_is_recorded_in_reference_workspace_state(self):
        class Request:
            def __init__(self, value):
                self.value = value

            def execute(self):
                return self.value

        class Drafts:
            def create(self, **_kwargs):
                return Request({"id": "draft-1", "message": {"id": "message-1"}})

            def get(self, **_kwargs):
                return Request({"id": "draft-1", "message": {"id": "message-1"}})

        class Users:
            def drafts(self):
                return Drafts()

        class Api:
            def users(self):
                return Users()

        with tempfile.TemporaryDirectory() as temp:
            profile = Path(temp)
            state_path = profile / actions.REFERENCE_WORKSPACE_STATE_FILE
            state_path.write_text(json.dumps({
                "schema": 2,
                "marker": actions.REFERENCE_WORKSPACE_MARKER,
                "drafts": [],
            }), encoding="utf-8")
            original_home = actions.hermes_home
            original_service = actions.service
            actions.hermes_home = lambda: profile
            actions.service = lambda *_args: Api()
            try:
                args = argparse.Namespace(
                    to="person@example.com",
                    cc="",
                    subject="Demo follow-up",
                    body="Checking in.",
                    thread_id="",
                    reply_to_message="",
                    track_demo_state=True,
                )
                output = io.StringIO()
                with redirect_stdout(output):
                    actions.gmail_draft(args)
            finally:
                actions.hermes_home = original_home
                actions.service = original_service

            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual([{"id": "draft-1", "message_id": "message-1"}], state["drafts"])
            self.assertEqual(str(state_path), json.loads(output.getvalue())["tracked_demo_state"])

    def test_demo_draft_requires_active_reference_workspace_state(self):
        with tempfile.TemporaryDirectory() as temp:
            original_home = actions.hermes_home
            actions.hermes_home = lambda: Path(temp)
            try:
                args = argparse.Namespace(
                    to="person@example.com",
                    cc="",
                    subject="Demo follow-up",
                    body="Checking in.",
                    thread_id="",
                    reply_to_message="",
                    track_demo_state=True,
                )
                with self.assertRaisesRegex(RuntimeError, "refusing untracked demo draft"):
                    actions.gmail_draft(args)
            finally:
                actions.hermes_home = original_home

    def test_calendar_move_preserves_event_and_verifies_time(self):
        captured = {}

        class Request:
            def __init__(self, value):
                self.value = value

            def execute(self):
                return self.value

        moved = {
            "id": "event-1",
            "summary": "Release review",
            "start": {"dateTime": "2026-08-24T11:00:00-07:00", "timeZone": "America/Los_Angeles"},
            "end": {"dateTime": "2026-08-24T12:00:00-07:00", "timeZone": "America/Los_Angeles"},
            "htmlLink": "https://calendar.google.com/event?eid=event-1",
        }

        class Events:
            calls = 0

            def get(self, **_kwargs):
                self.calls += 1
                if self.calls == 1:
                    return Request({
                        "id": "event-1",
                        "summary": "Release review",
                        "start": {"dateTime": "2026-08-21T14:00:00-07:00", "timeZone": "America/Los_Angeles"},
                        "end": {"dateTime": "2026-08-21T15:00:00-07:00", "timeZone": "America/Los_Angeles"},
                    })
                return Request(moved)

            def list(self, **_kwargs):
                return Request({"items": []})

            def patch(self, **kwargs):
                captured.update(kwargs)
                return Request(moved)

        events = Events()

        class Api:
            def events(self):
                return events

        original_service = actions.service
        actions.service = lambda *_args: Api()
        try:
            args = argparse.Namespace(
                calendar="primary",
                event_id="event-1",
                start="2026-08-24T11:00:00-07:00",
                end="2026-08-24T12:00:00-07:00",
                send_updates="none",
                allow_conflict=False,
                confirm=True,
            )
            output = io.StringIO()
            with redirect_stdout(output):
                actions.calendar_move(args)
        finally:
            actions.service = original_service

        self.assertEqual({"start", "end"}, set(captured["body"]))
        self.assertNotIn("summary", captured["body"])
        self.assertTrue(json.loads(output.getvalue())["verified"])

    def test_calendar_availability_returns_earliest_conflict_free_slot(self):
        class Request:
            def __init__(self, value):
                self.value = value

            def execute(self):
                return self.value

        class Events:
            def list(self, **_kwargs):
                return Request({"items": [
                    {
                        "id": "morning",
                        "summary": "Morning meetings",
                        "start": {"dateTime": "2026-08-25T09:00:00-07:00"},
                        "end": {"dateTime": "2026-08-25T11:00:00-07:00"},
                    },
                    {
                        "id": "focus",
                        "summary": "Engineering focus block",
                        "start": {"dateTime": "2026-08-25T11:00:00-07:00"},
                        "end": {"dateTime": "2026-08-25T12:00:00-07:00"},
                    },
                    {
                        "id": "lunch",
                        "summary": "Team lunch",
                        "start": {"dateTime": "2026-08-25T12:00:00-07:00"},
                        "end": {"dateTime": "2026-08-25T13:00:00-07:00"},
                    },
                ]})

        class Api:
            def events(self):
                return Events()

        original_service = actions.service
        actions.service = lambda *_args: Api()
        try:
            args = argparse.Namespace(
                calendar="primary",
                start="2026-08-25T09:00:00-07:00",
                end="2026-08-25T15:00:00-07:00",
                duration_minutes=60,
                step_minutes=15,
                limit=1,
                exclude_event="release-review",
            )
            output = io.StringIO()
            with redirect_stdout(output):
                actions.calendar_availability(args)
        finally:
            actions.service = original_service

        result = json.loads(output.getvalue())
        self.assertEqual(
            [{"start": "2026-08-25T13:00:00-07:00", "end": "2026-08-25T14:00:00-07:00"}],
            result["slots"],
        )
        self.assertEqual(
            ["Morning meetings", "Engineering focus block", "Team lunch"],
            [item["title"] for item in result["busy"]],
        )

    def test_calendar_move_rejects_an_existing_conflict(self):
        class Request:
            def __init__(self, value):
                self.value = value

            def execute(self):
                return self.value

        class Events:
            def get(self, **_kwargs):
                return Request({
                    "id": "release-review",
                    "summary": "Release review",
                    "start": {"dateTime": "2026-08-24T14:00:00-07:00"},
                    "end": {"dateTime": "2026-08-24T15:00:00-07:00"},
                })

            def list(self, **_kwargs):
                return Request({"items": [{
                    "id": "focus",
                    "summary": "Engineering focus block",
                    "start": {"dateTime": "2026-08-25T11:00:00-07:00"},
                    "end": {"dateTime": "2026-08-25T12:00:00-07:00"},
                }]})

            def patch(self, **_kwargs):
                raise AssertionError("A conflicting move must not be written")

        class Api:
            def events(self):
                return Events()

        original_service = actions.service
        actions.service = lambda *_args: Api()
        try:
            args = argparse.Namespace(
                calendar="primary",
                event_id="release-review",
                start="2026-08-25T11:00:00-07:00",
                end="2026-08-25T12:00:00-07:00",
                send_updates="none",
                allow_conflict=False,
                confirm=True,
            )
            with self.assertRaisesRegex(RuntimeError, "Engineering focus block"):
                actions.calendar_move(args)
        finally:
            actions.service = original_service

    def test_lane_update_preserves_unspecified_cells(self):
        captured = {}

        class Request:
            def __init__(self, value):
                self.value = value

            def execute(self):
                return self.value

        class Values:
            def get(self, **_kwargs):
                return Request({"values": [
                    ["Lane", "PIC", "Status", "Latest", "Next", "Due", "Blocker", "Evidence"],
                    ["Evaluation", "Mateo", "In progress", "Done", "Review", "Today", "None", "Mail"],
                ]})

            def batchUpdate(self, **kwargs):
                captured.update(kwargs["body"])
                return Request({"totalUpdatedRows": 1, "totalUpdatedCells": 6})

            def batchGet(self, **_kwargs):
                return Request({"valueRanges": [{"values": [["Ready for review", "Done", "Review", "Today", "None", "Mail"]]}]})

        values = Values()

        class Spreadsheets:
            def values(self):
                return values

        class Api:
            def spreadsheets(self):
                return Spreadsheets()

        original_service = actions.service
        actions.service = lambda *_args: Api()
        try:
            args = argparse.Namespace(
                spreadsheet_id="sheet-1",
                sheet="Campaign Lanes",
                updates='[{"lane":"Evaluation","status":"Ready for review"}]',
                lane=None,
                status=None,
                confirm=True,
            )
            with redirect_stdout(io.StringIO()):
                actions.sheets_update_lanes(args)
        finally:
            actions.service = original_service

        self.assertEqual(
            [["Ready for review", "Done", "Review", "Today", "None", "Mail"]],
            captured["data"][0]["values"],
        )

    def test_lane_update_accepts_single_lane_flags(self):
        args = actions.build_parser().parse_args([
            "sheets", "update-lanes", "sheet-1",
            "--lane", "Evaluation", "--status", "Ready for review", "--confirm",
        ])
        self.assertEqual("Evaluation", args.lane)
        self.assertEqual("Ready for review", args.status)
        self.assertIsNone(args.updates)

    def test_calendar_parser_exposes_focused_reads_and_safe_move(self):
        availability = actions.build_parser().parse_args([
            "calendar", "availability",
            "--start", "2026-08-25T08:00:00-07:00",
            "--end", "2026-08-25T18:00:00-07:00",
            "--duration-minutes", "60",
            "--exclude-event", "event-1",
        ])
        move = actions.build_parser().parse_args([
            "calendar", "move", "event-1",
            "--start", "2026-08-25T13:00:00-07:00",
            "--end", "2026-08-25T14:00:00-07:00",
            "--confirm",
        ])

        self.assertEqual(60, availability.duration_minutes)
        self.assertEqual("event-1", availability.exclude_event)
        self.assertFalse(move.allow_conflict)
        self.assertTrue(move.confirm)


if __name__ == "__main__":
    unittest.main()
