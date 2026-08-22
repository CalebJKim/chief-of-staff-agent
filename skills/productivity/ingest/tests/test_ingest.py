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

    def test_default_mail_scan_is_twenty_messages(self):
        self.assertEqual(20, ingest.DEFAULT_MAX_MESSAGES)

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


if __name__ == "__main__":
    unittest.main()
