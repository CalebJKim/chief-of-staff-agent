from __future__ import annotations

import argparse
import base64
import email
import importlib.util
import io
import json
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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

    def test_live_collection_overlaps_independent_workspace_reads(self):
        barrier = threading.Barrier(3)
        drive_complete = threading.Event()

        def calendars(_api, _start, _end, _limit):
            barrier.wait(timeout=2)
            return ([{"id": "event-1"}], [])

        def mail(_api, _days_back, _max_messages, _query, _scan_limit):
            barrier.wait(timeout=2)
            return ([{"id": "message-1"}], {"email": "demo@example.test"})

        def drive(_api, _days_back, _max_files):
            barrier.wait(timeout=2)
            drive_complete.set()
            return [{"id": "sheet-1", "kind": "sheet"}]

        def sheets(_credentials, files):
            self.assertTrue(drive_complete.is_set())
            self.assertEqual("sheet-1", files[0]["id"])
            return [{"id": "sheet-1"}]

        args = argparse.Namespace(
            fixture=None,
            date="2026-08-25",
            days_ahead=2,
            days_back=30,
            max_events=60,
            max_messages=20,
            gmail_query=None,
            mail_scan_limit=120,
            max_files=30,
        )
        with patch.object(ingest, "load_credentials", return_value=object()), patch(
            "googleapiclient.discovery.build", side_effect=lambda name, *_args, **_kwargs: name
        ), patch.object(ingest, "_calendar_timezone", return_value="UTC"), patch.object(
            ingest, "fetch_calendars", side_effect=calendars
        ), patch.object(ingest, "fetch_mail", side_effect=mail), patch.object(
            ingest, "fetch_drive", side_effect=drive
        ), patch.object(ingest, "fetch_sheet_previews", side_effect=sheets):
            snapshot = ingest.collect(args)

        self.assertEqual(1, snapshot["coverage"]["events"])
        self.assertEqual(1, snapshot["coverage"]["messages"])
        self.assertEqual(1, snapshot["coverage"]["files"])
        self.assertEqual(1, snapshot["coverage"]["sheets"])
        self.assertEqual([], snapshot["coverage"]["errors"])

    def test_mail_output_stays_at_twenty_after_broader_scan(self):
        self.assertEqual(20, ingest.DEFAULT_MAX_MESSAGES)
        self.assertEqual(120, ingest.DEFAULT_MAIL_SCAN_LIMIT)

    def test_gmail_search_supports_generic_sender_and_subject_filters(self):
        captured = {}

        class Request:
            def execute(self):
                return {"messages": []}

        class Messages:
            def list(self, **kwargs):
                captured.update(kwargs)
                return Request()

        class Users:
            def messages(self):
                return Messages()

        class Api:
            def users(self):
                return Users()

        original_service = actions.service
        actions.service = lambda *_args: Api()
        try:
            args = argparse.Namespace(
                query="Agent Runtime",
                sender="@nvidia.example",
                subject='New "review" slot',
                max=10,
                max_chars=500,
            )
            output = io.StringIO()
            with redirect_stdout(output):
                actions.gmail_search(args)
        finally:
            actions.service = original_service

        expected = 'Agent Runtime from:@nvidia.example subject:"New \\"review\\" slot" -in:drafts'
        self.assertEqual(expected, captured["q"])
        self.assertEqual(expected, json.loads(output.getvalue())["query"])

        repeated, unknown = actions.build_parser().parse_known_args([
            "gmail", "search", "Agent Runtime", "--subject", "regression",
            "--from", "Priya", "--subject", "filter", "",
        ])
        self.assertEqual([""], unknown)
        self.assertEqual("filter", repeated.subject)

        reply = actions.build_parser().parse_args([
            "gmail", "reply-draft", "message-1", "--subject", "invented subject",
            "--body", "Here is the requested meeting update.", "--confirm",
        ])
        self.assertTrue(reply.confirm)
        original_service = actions.service
        actions.service = lambda *_args: object()
        try:
            with self.assertRaisesRegex(actions.DraftValidationError, "derive recipients"):
                actions.gmail_draft(reply)
        finally:
            actions.service = original_service

    def test_generic_gmail_draft_confirmation_uses_verified_fields(self):
        markdown = actions.gmail_draft_confirmation_markdown(
            "Maya Patel <maya@example.com>",
            "Daniel Cho <daniel@example.com>",
            "Re: Review prep",
            "https://mail.google.com/mail/u/0/#drafts/message-1",
        )

        self.assertIn("Maya Patel", markdown)
        self.assertIn("Daniel Cho", markdown)
        self.assertIn("saved (not sent)", markdown)
        self.assertIn("**Re: Review prep**", markdown)
        self.assertIn("[Draft](https://mail.google.com/mail/u/0/#drafts/message-1)", markdown)

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
        batch_sizes = []

        class Batch:
            def __init__(self):
                self.requests = []

            def add(self, request, callback, request_id):
                self.requests.append((request, callback, request_id))

            def execute(self):
                batch_sizes.append(len(self.requests))
                for request, callback, request_id in self.requests:
                    callback(request_id, request.execute(), None)

        class Users:
            def getProfile(self, **_kwargs):
                return Request({"emailAddress": "demo@example.test"})

            def messages(self):
                return messages

        class Api:
            def users(self):
                return Users()

            def new_batch_http_request(self):
                return Batch()

        result, identity = ingest.fetch_mail(Api(), 30, 2, None, scan_limit=4)

        self.assertEqual(["priority-1", "priority-2"], [item["id"] for item in result])
        self.assertEqual(4, identity["mail_scanned"])
        self.assertEqual([4], batch_sizes)

    def test_mail_metadata_batch_retries_only_rate_limited_messages(self):
        class Request:
            def __init__(self, value):
                self.value = value

            def execute(self):
                return self.value

        class RateLimited(Exception):
            def __init__(self):
                super().__init__("rate limited")
                self.resp = SimpleNamespace(status=429)

        attempts = {"message-1": 0, "message-2": 0}
        batch_sizes = []

        class Messages:
            def list(self, **_kwargs):
                return Request({"messages": [{"id": "message-1"}, {"id": "message-2"}]})

            def get(self, **kwargs):
                message_id = kwargs["id"]
                return Request({
                    "id": message_id,
                    "threadId": f"thread-{message_id}",
                    "internalDate": "1000",
                    "labelIds": ["INBOX"],
                    "payload": {"headers": [{"name": "Subject", "value": message_id}]},
                })

        messages = Messages()

        class Batch:
            def __init__(self):
                self.requests = []

            def add(self, request, callback, request_id):
                self.requests.append((request, callback, request_id))

            def execute(self):
                batch_sizes.append(len(self.requests))
                for request, callback, request_id in self.requests:
                    attempts[request_id] += 1
                    error = RateLimited() if request_id == "message-1" and attempts[request_id] == 1 else None
                    callback(request_id, None if error else request.execute(), error)

        class Users:
            def getProfile(self, **_kwargs):
                return Request({"emailAddress": "demo@example.test"})

            def messages(self):
                return messages

        class Api:
            def users(self):
                return Users()

            def new_batch_http_request(self):
                return Batch()

        with patch.object(ingest.time_module, "sleep") as sleep:
            result, _identity = ingest.fetch_mail(Api(), 30, 2, None, scan_limit=2)

        self.assertEqual({"message-1": 2, "message-2": 1}, attempts)
        self.assertEqual([2, 1], batch_sizes)
        self.assertEqual({"message-1", "message-2"}, {item["id"] for item in result})
        sleep.assert_called_once_with(1)

    def test_cloud_mutation_requires_confirmation(self):
        with self.assertRaisesRegex(RuntimeError, "without --confirm"):
            actions.require_confirm(argparse.Namespace(confirm=False), "test mutation")
        actions.require_confirm(argparse.Namespace(confirm=True), "test mutation")

    def test_sheet_ingest_returns_generic_structural_previews(self):
        captured = {}
        files = [{
            "id": "sheet-1",
            "name": "Weekly operations",
            "kind": "sheet",
            "url": "https://docs.google.com/spreadsheets/d/sheet-1/edit",
        }]
        expected = {
            "id": "sheet-1",
            "title": "Workbook title",
            "locale": "en_US",
            "timezone": "UTC",
            "tabs": [{
                "title": "Arbitrary tab",
                "table": {
                    "header_row": 3,
                    "columns": [{"column": "A", "name": "Signal"}],
                    "row_count": 1,
                    "representative_rows": [{"row": 4, "values": {"A": "Example"}}],
                },
                "validation_previews": [],
            }],
        }

        def preview(api, spreadsheet_id, max_rows, max_columns, max_sample_rows):
            captured.update({
                "api": api,
                "id": spreadsheet_id,
                "bounds": (max_rows, max_columns, max_sample_rows),
            })
            return dict(expected)

        api = object()
        module = SimpleNamespace(spreadsheet_preview=preview)
        with patch("googleapiclient.discovery.build", return_value=api), patch.object(
            ingest, "_workspace_actions_module", return_value=module
        ):
            previews = ingest.fetch_sheet_previews(object(), files)

        self.assertEqual("sheet-1", captured["id"])
        self.assertEqual((40, 20, 12), captured["bounds"])
        self.assertEqual("Weekly operations", previews[0]["name"])
        self.assertEqual(files[0]["url"], previews[0]["url"])
        self.assertNotIn("lane", json.dumps(previews).casefold())
        self.assertFalse(hasattr(ingest, "TRACKER_HEADER_ALIASES"))

    def test_spreadsheet_preview_discovers_structure_without_business_aliases(self):
        def cell(value="", validation=None):
            result = {"formattedValue": value} if value else {}
            if validation:
                result["dataValidation"] = validation
            return result

        allowed = {
            "condition": {
                "type": "ONE_OF_LIST",
                "values": [
                    {"userEnteredValue": "Alpha"},
                    {"userEnteredValue": "Beta"},
                ],
            },
            "strict": True,
            "showCustomUi": True,
        }
        rows = [
            [cell("Portfolio overview"), cell(), cell(), cell()],
            [cell(), cell(), cell(), cell()],
            [cell("Signal"), cell("Choice"), cell("Person"), cell("When")],
            [cell("Example one"), cell("Alpha", allowed), cell("Alex"), cell("Soon")],
            [cell("Example two"), cell("Beta", allowed), cell("Blair"), cell("Later")],
        ]
        workbook = {
            "spreadsheet_id": "sheet-1",
            "title": "Generic workbook",
            "locale": "en_US",
            "timezone": "UTC",
            "sheets": [{
                "sheet_id": 1,
                "title": "Arbitrary tab",
                "row_count": 100,
                "column_count": 10,
                "rows": rows,
                "protected_ranges": [],
                "merges": [],
                "truncated": True,
            }],
        }
        original_grid = actions._spreadsheet_grid
        actions._spreadsheet_grid = lambda *_args, **_kwargs: workbook
        try:
            result = actions.spreadsheet_preview(object(), "sheet-1", max_sample_rows=1)
        finally:
            actions._spreadsheet_grid = original_grid

        table = result["tabs"][0]["table"]
        self.assertEqual(3, table["header_row"])
        self.assertEqual(["Signal", "Choice", "Person", "When"], [item["name"] for item in table["columns"]])
        self.assertEqual(2, table["row_count"])
        self.assertEqual(1, len(table["representative_rows"]))
        validation = result["tabs"][0]["validation_previews"][0]
        self.assertEqual(["Alpha", "Beta"], validation["validation"]["allowed_values"])
        self.assertEqual(2, validation["cell_count"])

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
            def get(self, **kwargs):
                if kwargs["id"] == "message-2":
                    return Request({
                        "threadId": "thread-2",
                        "payload": {"headers": [
                            {"name": "From", "value": "Colleague <colleague@example.com>"},
                            {"name": "Subject", "value": "Other evidence"},
                            {"name": "Message-ID", "value": "<other@example.com>"},
                        ]},
                    })
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
                return Request({
                    "id": "draft-1",
                    "message": {
                        "id": "message-1",
                        "threadId": "thread-1",
                        "payload": {
                            "headers": [
                                {"name": "To", "value": "Person <person@example.com>"},
                                {"name": "Cc", "value": "Colleague <colleague@example.com>"},
                                {"name": "Subject", "value": "Re: Project update"},
                            ],
                            "mimeType": "text/plain",
                            "body": {"data": base64.urlsafe_b64encode(
                                b"Priya, Daniel,\n\nThe release review has moved.\n\nThanks"
                            ).decode("ascii")},
                        },
                    },
                })

        class Users:
            def getProfile(self, **_kwargs):
                return Request({"emailAddress": "demo@example.test"})

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
                body="Priya, Daniel,\\n\\nThe release review has moved.\\n\\nThanks, ",
                closing="Thanks",
                thread_id="",
                reply_to_message="message-0",
                include_sender_from_message=["message-2"],
            )
            output = io.StringIO()
            with redirect_stdout(output):
                actions.gmail_draft(args)
        finally:
            actions.service = original_service

        self.assertEqual(captured["message"]["threadId"], "thread-1")
        result = json.loads(output.getvalue())
        self.assertNotIn("draft_id", result)
        self.assertNotIn("message_id", result)
        self.assertNotIn("thread_id", result)
        raw = captured["message"]["raw"]
        parsed = email.message_from_bytes(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        self.assertEqual(parsed["To"], "Person <person@example.com>")
        self.assertEqual(parsed["Cc"], "Colleague <colleague@example.com>")
        self.assertEqual(parsed["Subject"], "Re: Project update")
        self.assertEqual(parsed["In-Reply-To"], "<original@example.com>")
        body = parsed.get_payload(decode=True).decode("utf-8")
        self.assertEqual("Priya, Daniel,\n\nThe release review has moved.\n\nThanks\n", body)
        self.assertNotIn("\\n", body)
        self.assertEqual(
            "Please update your calendars accordingly.\n\nThanks",
            actions.normalize_draft_body("Please update your calendars accordingly. Thanks", "Thanks"),
        )
        self.assertEqual(
            "The review has moved.\n\nThanks",
            actions.normalize_draft_body("The review has moved.\n\nBest", "Thanks"),
        )
        self.assertEqual(
            "The review has moved.\n\nThanks",
            actions.normalize_draft_body("The review has moved.\nThanks", "Thanks"),
        )
        self.assertEqual(
            "Hi Priya,\n\nThe review has moved.\n\nThanks",
            actions.normalize_draft_body(
                "Hi Priya,\n\n\nThe review has moved.\n\n\nThanks",
                "Thanks",
            ),
        )
        self.assertEqual(
            "Hi Priya,\n\nThe review has moved.\n\nThanks",
            actions.normalize_draft_body(
                "Hi Priya,\n\nThe review has moved.\n\nThanks\nDan",
                "Thanks",
                exact_final=True,
            ),
        )

    def test_reply_draft_rejects_draft_or_self_authored_source_before_writing(self):
        class Request:
            def __init__(self, value):
                self.value = value

            def execute(self):
                return self.value

        class Messages:
            def __init__(self, source):
                self.source = source

            def get(self, **_kwargs):
                return Request(self.source)

        class Drafts:
            def create(self, **_kwargs):
                self.fail("No draft may be written from invalid reply evidence")

        class Users:
            def __init__(self, source):
                self.source = source

            def getProfile(self, **_kwargs):
                return Request({"emailAddress": "demo@example.test"})

            def messages(self):
                return Messages(self.source)

            def drafts(self):
                return Drafts()

        class Api:
            def __init__(self, source):
                self.source = source

            def users(self):
                return Users(self.source)

        base = {
            "threadId": "thread-1",
            "payload": {"headers": [
                {"name": "From", "value": "Demo <demo@example.test>"},
                {"name": "Subject", "value": "Project update"},
            ]},
        }
        args = argparse.Namespace(
            to="", cc="", subject="", body="The review has moved.", closing="Thanks",
            thread_id="", reply_to_message="message-1", include_sender_from_message=[],
        )
        original_service = actions.service
        try:
            for source, expected in (
                ({**base, "labelIds": ["DRAFT"]}, "itself a draft"),
                (base, "signed-in Gmail account"),
            ):
                actions.service = lambda *_args, source=source: Api(source)
                with self.subTest(expected=expected), self.assertRaisesRegex(
                    actions.DraftValidationError, expected
                ):
                    actions.gmail_draft(args)
        finally:
            actions.service = original_service

    def test_reply_draft_rejects_blank_evidence_and_invented_recipient_override(self):
        with self.assertRaisesRegex(RuntimeError, "non-empty Gmail message ID"):
            actions._reply_evidence(object(), "")

        original_service = actions.service
        actions.service = lambda *_args: object()
        try:
            args = argparse.Namespace(
                to="invented@example.com",
                cc="",
                subject="",
                body="Here is the requested update.",
                closing="Thanks",
                thread_id="",
                reply_to_message="message-1",
                include_sender_from_message=[],
            )
            with self.assertRaisesRegex(RuntimeError, "derive recipients"):
                actions.gmail_draft(args)
        finally:
            actions.service = original_service

        self.assertFalse(actions._valid_email_address("priya@asnvdemo.m"))
        self.assertTrue(actions._valid_email_address("person@example.com"))

    def test_reply_draft_content_validation_happens_before_gmail_access(self):
        def unexpected_service(*_args):
            self.fail("Gmail must not be accessed when draft content is invalid")

        original_service = actions.service
        actions.service = unexpected_service
        try:
            for body in ("Thanks", "Hi Priya\n\nThanks", "Priya, Daniel,\n\nThanks"):
                args = argparse.Namespace(
                    to="",
                    cc="",
                    subject="",
                    body=body,
                    closing="Thanks",
                    thread_id="",
                    reply_to_message="message-1",
                    include_sender_from_message=[],
                    require_body_fact=[],
                )
                with self.subTest(body=body), self.assertRaisesRegex(RuntimeError, "no substantive message"):
                    actions.gmail_draft(args)
        finally:
            actions.service = original_service

    def test_inline_salutation_preserves_substantive_draft_content(self):
        body = actions.normalize_draft_body(
            "Hi Priya, I moved the review to Tuesday at 1:00 PM PDT. Thanks",
            "Thanks",
        )
        self.assertEqual(
            "Hi Priya, I moved the review to Tuesday at 1:00 PM PDT.\n\nThanks",
            body,
        )
        self.assertEqual([], actions.validate_draft_content(body, "Thanks", [], 4))
        with self.assertRaisesRegex(actions.DraftValidationError, "no substantive message"):
            actions.validate_draft_content("Hi Priya,\n\nThanks", "Thanks", [], 4)

    def test_calendar_confirmation_requires_live_event_verification_before_gmail_access(self):
        def unexpected_service(*_args):
            self.fail("No Google API may be accessed before calendar-confirmation validation")

        args = argparse.Namespace(
            to="",
            cc="",
            subject="",
            body=(
                "The release review is now Tuesday, August 25 from "
                "1:00-2:00 PM PDT.\n\nThanks"
            ),
            closing="Thanks",
            thread_id="",
            reply_to_message="message-1",
            include_sender_from_message=[],
            require_body_fact=[],
            verify_calendar_event="",
        )
        original_service = actions.service
        actions.service = unexpected_service
        try:
            with self.assertRaisesRegex(actions.DraftValidationError, "--verify-calendar-event is required"):
                actions.gmail_draft(args)
        finally:
            actions.service = original_service

        self.assertTrue(actions.looks_like_calendar_confirmation(
            "Moving the review to Tuesday August twenty fifth one PM PDT."
        ))
        self.assertFalse(actions.looks_like_calendar_confirmation(
            "Moving the review to Tuesday at one PM."
        ))

    def test_irrelevant_calendar_flag_is_ignored_for_completion_reply(self):
        body = (
            "All three preparation items are complete and everything is ready for 3 PM today."
            "\n\nThanks"
        )

        self.assertEqual(
            "",
            actions.calendar_verification_event_id(body, "unrelated-event-id"),
        )
        scheduled = "The review is now Tuesday, August 25 from 1:00-2:00 PM PDT.\n\nThanks"
        self.assertEqual(
            "event-1",
            actions.calendar_verification_event_id(scheduled, "event-1"),
        )

    def test_draft_content_requires_all_verified_facts(self):
        body = (
            "Priya, Daniel,\n\nThe RTX Spark Agent Runtime release review is now on "
            "2026-08-25 from 1:00 PM to 2:00 PM PDT.\n\nThanks"
        )
        facts = [
            "RTX Spark Agent Runtime release review",
            "2026-08-25",
            "1:00 PM",
            "2:00 PM",
            "PDT",
        ]
        self.assertEqual(facts, actions.validate_draft_content(body, "Thanks", facts, 4))
        self.assertEqual(
            ["1:00-2:00 PM"],
            actions.validate_draft_content(
                "The release review is now 1:00–2:00 PM.\n\nThanks",
                "Thanks",
                ["1:00-2:00 PM"],
                4,
            ),
        )
        with self.assertRaisesRegex(RuntimeError, "missing required verified fact 'PDT'"):
            actions.validate_draft_content(body.replace(" PDT", ""), "Thanks", facts, 4)

    def test_draft_content_rejects_empty_required_fact(self):
        with self.assertRaisesRegex(RuntimeError, "cannot be empty"):
            actions.validate_draft_content(
                "The release review has been moved.\n\nThanks",
                "Thanks",
                ["  "],
                4,
            )

    def test_calendar_confirmation_content_uses_live_event_facts(self):
        event = {
            "summary": "RTX Spark Agent Runtime release review",
            "start": {
                "dateTime": "2026-08-25T13:00:00-07:00",
                "timeZone": "America/Los_Angeles",
            },
            "end": {
                "dateTime": "2026-08-25T14:00:00-07:00",
                "timeZone": "America/Los_Angeles",
            },
        }
        body = (
            "The RTX Spark Agent Runtime release review is now Tuesday, August 25, 2026 "
            "from 1:00 PM to 2:00 PM PDT.\n\nThanks"
        )
        self.assertEqual(
            ["RTX Spark Agent Runtime release review", "2026-08-25", "1:00 PM", "2:00 PM", "PDT"],
            actions.validate_calendar_confirmation_content(
                body,
                event,
                actions.ZoneInfo("America/Los_Angeles"),
            ),
        )
        markdown = actions.calendar_draft_confirmation_markdown(
            {**event, "htmlLink": "https://calendar.example.test/event"},
            actions.ZoneInfo("America/Los_Angeles"),
            "Priya Shah <priya@example.com>",
            "Daniel Cho <daniel@example.com>",
            "https://mail.example.test/draft",
        )
        self.assertIn("Tuesday, August 25, 2026, 1:00–2:00 PM PDT", markdown)
        self.assertIn("[Calendar](https://calendar.example.test/event)", markdown)
        self.assertIn("draft to Priya Shah with Daniel Cho copied was saved (not sent)", markdown)
        self.assertIn("[Draft](https://mail.example.test/draft)", markdown)
        with self.assertRaisesRegex(RuntimeError, "missing the verified Calendar interval"):
            actions.validate_calendar_confirmation_content(
                body.replace("2:00 PM", "later"),
                event,
                actions.ZoneInfo("America/Los_Angeles"),
            )

        with self.assertRaisesRegex(RuntimeError, "missing the verified Calendar interval"):
            actions.validate_calendar_confirmation_content(
                (
                    "The RTX Spark Agent Runtime release review moved from Monday, August 24 at "
                    "2:00 PM PDT to Tuesday, August 25, 2026 at 1:00 PM PDT.\n\nThanks"
                ),
                event,
                actions.ZoneInfo("America/Los_Angeles"),
            )

        compact_body = (
            "The RTX Spark Agent Runtime release review is now Tuesday, August 25 "
            "from 1:00\\u20132:00 PM PDT.\n\nThanks"
        )
        normalized_compact_body = actions.normalize_draft_body(compact_body, "Thanks")
        self.assertNotIn(r"\u2013", normalized_compact_body)
        self.assertEqual(
            ["RTX Spark Agent Runtime release review", "2026-08-25", "1:00 PM", "2:00 PM", "PDT"],
            actions.validate_calendar_confirmation_content(
                normalized_compact_body,
                event,
                actions.ZoneInfo("America/Los_Angeles"),
            ),
        )

    def test_cli_reports_prewrite_content_rejection_without_a_command_failure(self):
        argv = ["actions.py", "gmail", "reply-draft", "message-1", "--body", "Thanks"]
        output = io.StringIO()
        with patch.object(actions.sys, "argv", argv), redirect_stdout(output):
            self.assertEqual(0, actions.main())
        result = json.loads(output.getvalue())
        self.assertEqual("rejected", result["status"])
        self.assertFalse(result["created"])
        self.assertFalse(result["content_validated"])

    def test_google_read_retries_one_transient_timeout_then_succeeds(self):
        class Request:
            attempts = 0

            def execute(self):
                self.attempts += 1
                if self.attempts == 1:
                    raise TimeoutError("read operation timed out")
                return {"ok": True}

        request = Request()
        with patch.object(actions.time_module, "sleep"):
            result = actions.execute_google_read(request, "Read test data")

        self.assertEqual({"ok": True}, result)
        self.assertEqual(2, request.attempts)

    def test_cli_reports_exhausted_timeout_as_google_side_issue(self):
        class Request:
            def execute(self):
                raise TimeoutError("read operation timed out")

        class Messages:
            def get(self, **_kwargs):
                return Request()

        class Users:
            def messages(self):
                return Messages()

        class Api:
            def users(self):
                return Users()

        argv = ["actions.py", "gmail", "get", "message-1"]
        output = io.StringIO()
        with patch.object(actions.sys, "argv", argv), patch.object(
            actions, "service", return_value=Api()
        ), patch.object(actions.time_module, "sleep"), redirect_stdout(output):
            self.assertEqual(0, actions.main())

        result = json.loads(output.getvalue())
        self.assertEqual("temporarily_unavailable", result["status"])
        self.assertTrue(result["google_side"])
        self.assertEqual(actions.GOOGLE_TEMPORARY_USER_MESSAGE, result["user_message"])

    def test_demo_draft_is_recorded_in_reference_workspace_state(self):
        class Request:
            def __init__(self, value):
                self.value = value

            def execute(self):
                return self.value

        class Drafts:
            raw = ""

            def create(self, **_kwargs):
                self.raw = _kwargs["body"]["message"]["raw"]
                return Request({"id": "draft-1", "message": {"id": "message-1"}})

            def get(self, **_kwargs):
                parsed = email.message_from_bytes(base64.urlsafe_b64decode(self.raw + "=" * (-len(self.raw) % 4)))
                body = parsed.get_payload(decode=True)
                return Request({
                    "id": "draft-1",
                    "message": {
                        "id": "message-1",
                        "payload": {
                            "headers": [
                                {"name": "To", "value": parsed["To"]},
                                {"name": "Subject", "value": parsed["Subject"]},
                            ],
                            "mimeType": "text/plain",
                            "body": {"data": base64.urlsafe_b64encode(body).decode("ascii")},
                        },
                    },
                })

        drafts = Drafts()

        class Users:
            def drafts(self):
                return drafts

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
            self.assertTrue(json.loads(output.getvalue())["tracked_demo_state"])

    def test_identical_tracked_draft_is_reused_without_creating_a_duplicate(self):
        class Request:
            def __init__(self, value):
                self.value = value

            def execute(self):
                return self.value

        payload = {
            "headers": [
                {"name": "To", "value": "Person <person@example.com>"},
                {"name": "Subject", "value": "Demo follow-up"},
            ],
            "mimeType": "text/plain",
            "body": {"data": base64.urlsafe_b64encode(
                b"Following up on the project.\n\nThanks"
            ).decode("ascii")},
        }

        class Drafts:
            def get(self, **_kwargs):
                return Request({
                    "id": "draft-existing",
                    "message": {
                        "id": "message-existing",
                        "threadId": "thread-existing",
                        "payload": payload,
                    },
                })

            def create(self, **_kwargs):
                raise AssertionError("An identical tracked draft must not be created again")

        class Users:
            def drafts(self):
                return Drafts()

        class Api:
            def users(self):
                return Users()

        with tempfile.TemporaryDirectory() as temp:
            profile = Path(temp)
            (profile / actions.REFERENCE_WORKSPACE_STATE_FILE).write_text(json.dumps({
                "schema": 3,
                "marker": actions.REFERENCE_WORKSPACE_MARKER,
                "drafts": [{"id": "draft-existing", "message_id": "message-existing"}],
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
                    body="Following up on the project. Thanks",
                    closing="Thanks",
                    thread_id="",
                    reply_to_message="",
                    include_sender_from_message=[],
                    require_body_fact=[],
                    verify_calendar_event="",
                    track_demo_state=True,
                )
                output = io.StringIO()
                with redirect_stdout(output):
                    actions.gmail_draft(args)
            finally:
                actions.hermes_home = original_home
                actions.service = original_service
        result = json.loads(output.getvalue())
        self.assertEqual("already_drafted", result["status"])
        self.assertFalse(result["created"])
        self.assertTrue(result["reused"])
        self.assertEqual("Person <person@example.com>", result["to"])
        self.assertEqual("Following up on the project.\n\nThanks", result["body"])

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

    def test_calendar_reschedule_uses_local_date_working_hours_and_reports_notifications(self):
        captured = {}

        class Request:
            def __init__(self, value):
                self.value = value

            def execute(self):
                return self.value

        current = {
            "id": "release-review",
            "summary": "Release review",
            "start": {"dateTime": "2026-08-24T14:00:00-07:00", "timeZone": "America/Los_Angeles"},
            "end": {"dateTime": "2026-08-24T15:00:00-07:00", "timeZone": "America/Los_Angeles"},
        }
        moved = {
            **current,
            "start": {"dateTime": "2026-08-25T13:00:00-07:00", "timeZone": "America/Los_Angeles"},
            "end": {"dateTime": "2026-08-25T14:00:00-07:00", "timeZone": "America/Los_Angeles"},
            "htmlLink": "https://calendar.google.com/event?eid=release-review",
        }

        class Events:
            gets = 0

            def get(self, **_kwargs):
                self.gets += 1
                return Request(current if self.gets == 1 else moved)

            def list(self, **_kwargs):
                return Request({"items": [{
                    "id": "busy",
                    "summary": "Morning block",
                    "start": {"dateTime": "2026-08-25T08:00:00-07:00"},
                    "end": {"dateTime": "2026-08-25T13:00:00-07:00"},
                }]})

            def patch(self, **kwargs):
                captured.update(kwargs)
                return Request(moved)

        events = Events()

        class Calendars:
            def get(self, **_kwargs):
                return Request({"timeZone": "America/Los_Angeles"})

        class Api:
            def events(self):
                return events

            def calendars(self):
                return Calendars()

        original_service = actions.service
        actions.service = lambda *_args: Api()
        try:
            args = argparse.Namespace(
                calendar="primary",
                event_id="release-review",
                query="Release review",
                date="2026-08-25",
                date_source_message="",
                user_directed_date=True,
                user_request_text="Please move it to Tuesday.",
                work_start="08:00",
                work_end="17:00",
                timezone="",
                step_minutes=15,
                lookup_days=14,
                send_updates="none",
                confirm=True,
            )
            output = io.StringIO()
            with redirect_stdout(output):
                actions.calendar_reschedule(args)
        finally:
            actions.service = original_service

        result = json.loads(output.getvalue())
        self.assertEqual("2026-08-25T13:00:00-07:00", result["start"]["dateTime"])
        self.assertEqual({"start": "08:00", "end": "17:00"}, result["working_hours"])
        self.assertEqual(
            {"date": "2026-08-24", "weekday": "Monday", "start_time": "2:00 PM", "end_time": "3:00 PM", "timezone": "America/Los_Angeles", "timezone_abbreviation": "PDT"},
            result["original_display"],
        )
        self.assertEqual(
            {"date": "2026-08-25", "weekday": "Tuesday", "start_time": "1:00 PM", "end_time": "2:00 PM", "timezone": "America/Los_Angeles", "timezone_abbreviation": "PDT"},
            result["new_display"],
        )
        self.assertNotIn("send_updates", result)
        self.assertNotIn("notifications_requested", result)
        self.assertNotIn("notification_delivery_verified", result)
        self.assertEqual("none", captured["sendUpdates"])

    def test_calendar_reschedule_rejects_weekday_date_mismatch_before_a_write(self):
        original_service = actions.service
        actions.service = lambda *_args: object()
        try:
            args = argparse.Namespace(
                calendar="primary",
                event_id="event-1",
                query="Release review",
                date="2026-08-24",
                date_source_message="",
                user_directed_date=True,
                user_request_text="Please move it to Monday.",
                expected_weekday="Tuesday",
                work_start="08:00",
                work_end="17:00",
                timezone="",
                step_minutes=15,
                lookup_days=14,
                send_updates="none",
                confirm=True,
            )
            with self.assertRaisesRegex(RuntimeError, "is Monday, not 'Tuesday'"):
                actions.calendar_reschedule(args)
        finally:
            actions.service = original_service

    def test_calendar_date_evidence_rejects_an_invented_target_date(self):
        class Request:
            def __init__(self, value):
                self.value = value

            def execute(self):
                return self.value

        payload = {
            "headers": [
                {"name": "From", "value": "Daniel <daniel@example.test>"},
                {"name": "Subject", "value": "New release-review slot"},
            ],
            "mimeType": "text/plain",
            "body": {"data": base64.urlsafe_b64encode(
                b"Move the review to Tuesday, August 25."
            ).decode("ascii")},
        }

        class Messages:
            def get(self, **kwargs):
                if kwargs["format"] == "metadata":
                    return Request({"threadId": "thread-1", "payload": payload})
                return Request({"threadId": "thread-1", "payload": payload})

        class Users:
            def getProfile(self, **_kwargs):
                return Request({"emailAddress": "demo@example.test"})

            def messages(self):
                return Messages()

        class Api:
            def users(self):
                return Users()

        actions.validate_calendar_date_evidence(Api(), "message-1", date(2026, 8, 25))
        with self.assertRaisesRegex(actions.CalendarValidationError, "does not contain target date"):
            actions.validate_calendar_date_evidence(Api(), "message-1", date(2026, 8, 27))

    def test_user_directed_date_must_appear_in_exact_current_request(self):
        actions.validate_user_directed_date("Move it to Tuesday.", date(2026, 8, 25))
        actions.validate_user_directed_date("Use 2026-08-25.", date(2026, 8, 25))
        with self.assertRaisesRegex(actions.CalendarValidationError, "current user request does not contain"):
            actions.validate_user_directed_date("Take action on the first item.", date(2026, 8, 25))

    def test_missing_calendar_date_authority_is_structured_feedback_not_a_shell_error(self):
        argv = [
            "actions.py", "calendar", "reschedule", "event-1",
            "--query", "Release review", "--date", "2026-08-25", "--confirm",
        ]
        output = io.StringIO()
        with patch.object(actions.sys, "argv", argv), redirect_stdout(output):
            self.assertEqual(0, actions.main())
        result = json.loads(output.getvalue())
        self.assertEqual("rejected", result["status"])
        self.assertFalse(result["moved"])
        self.assertIn("exactly one date authority", result["reason"])

    def test_stale_calendar_id_can_only_recover_from_one_live_query_match(self):
        class Missing(Exception):
            resp = type("Response", (), {"status": 404})()

        class Request:
            def __init__(self, value=None, error=None):
                self.value = value
                self.error = error

            def execute(self):
                if self.error:
                    raise self.error
                return self.value

        event = {
            "id": "live-id",
            "summary": "Release review",
            "start": {"dateTime": "2026-08-24T14:00:00-07:00"},
            "end": {"dateTime": "2026-08-24T15:00:00-07:00"},
        }

        class Events:
            def get(self, **_kwargs):
                return Request(error=Missing("gone"))

            def list(self, **_kwargs):
                return Request({"items": [event]})

        class Api:
            def events(self):
                return Events()

        resolved, recovered = actions._resolve_calendar_event(
            Api(),
            "primary",
            "stale-id",
            "Release review",
            date(2026, 8, 25),
            actions.ZoneInfo("America/Los_Angeles"),
            14,
        )
        self.assertEqual("live-id", resolved["id"])
        self.assertTrue(recovered)

    def test_live_calendar_id_must_match_the_bounded_title_query(self):
        class Request:
            def execute(self):
                return {
                    "id": "wrong-live-id",
                    "summary": "Evaluation office hours",
                    "start": {"dateTime": "2026-08-24T15:15:00-07:00"},
                    "end": {"dateTime": "2026-08-24T15:45:00-07:00"},
                }

        class Events:
            def get(self, **_kwargs):
                return Request()

        class Api:
            def events(self):
                return Events()

        with self.assertRaisesRegex(actions.CalendarValidationError, "does not match query"):
            actions._resolve_calendar_event(
                Api(),
                "primary",
                "wrong-live-id",
                "RTX Spark Agent Runtime release review",
                date(2026, 8, 25),
                actions.ZoneInfo("America/Los_Angeles"),
                14,
            )

    def _semantic_workbook(self, status="In progress", *, formula=False, protected=False):
        rows = [[{} for _ in range(6)] for _ in range(8)]
        rows[1][0] = {"effectiveValue": {"stringValue": "Status"}, "formattedValue": "Status"}
        rows[1][3] = {"effectiveValue": {"stringValue": "Workstream"}, "formattedValue": "Workstream"}
        rows[4][3] = {"effectiveValue": {"stringValue": "Evaluation"}, "formattedValue": "Evaluation"}
        rows[4][0] = {
            "effectiveValue": {"stringValue": status},
            "formattedValue": status,
            "dataValidation": {
                "condition": {
                    "type": "ONE_OF_LIST",
                    "values": [
                        {"userEnteredValue": "In progress"},
                        {"userEnteredValue": "Ready for review"},
                    ],
                },
                "strict": True,
                "showCustomUi": True,
            },
        }
        if formula:
            rows[4][0]["userEnteredValue"] = {"formulaValue": "=A1"}
        protected_ranges = []
        if protected:
            protected_ranges.append({
                "description": "Owner controlled",
                "range": {
                    "startRowIndex": 4,
                    "endRowIndex": 5,
                    "startColumnIndex": 0,
                    "endColumnIndex": 1,
                },
            })
        return {
            "spreadsheet_id": "sheet-1",
            "title": "Delivery",
            "locale": "en_US",
            "timezone": "America/Los_Angeles",
            "sheets": [{
                "sheet_id": 99,
                "title": "Roadmap",
                "row_count": 100,
                "column_count": 20,
                "rows": rows,
                "protected_ranges": protected_ranges,
                "merges": [],
                "truncated": False,
            }],
        }

    def test_semantic_cell_update_discovers_moved_columns_and_live_dropdown(self):
        captured = {}

        class Request:
            def execute(self):
                return {"updatedCells": 1}

        class Values:
            def update(self, **kwargs):
                captured.update(kwargs)
                return Request()

        class Spreadsheets:
            def values(self):
                return Values()

        class Api:
            def spreadsheets(self):
                return Spreadsheets()

        before = self._semantic_workbook()
        after = self._semantic_workbook("Ready for review")
        workbooks = iter([before, after])
        original_service = actions.service
        original_grid = actions._spreadsheet_grid
        actions.service = lambda *_args: Api()
        actions._spreadsheet_grid = lambda *_args, **_kwargs: next(workbooks)
        try:
            args = argparse.Namespace(
                spreadsheet_id="sheet-1",
                sheet="",
                row_match="Evaluation",
                column="Status",
                expected_current="In progress",
                value="Ready for review",
                max_rows=200,
                max_columns=50,
                confirm=True,
            )
            output = io.StringIO()
            with redirect_stdout(output):
                actions.sheets_set_cell(args)
        finally:
            actions.service = original_service
            actions._spreadsheet_grid = original_grid

        self.assertEqual("'Roadmap'!A5", captured["range"])
        self.assertEqual([["Ready for review"]], captured["body"]["values"])
        result = json.loads(output.getvalue())
        self.assertTrue(result["verified"])
        self.assertEqual("A5", result["cell"])
        self.assertEqual(
            "**Evaluation**: **Status** changed from **In progress** to **Ready for review**. "
            "[Sheet](https://docs.google.com/spreadsheets/d/sheet-1/edit)",
            result["confirmation_markdown"],
        )
        self.assertNotIn("A5", result["confirmation_markdown"])
        self.assertEqual(
            ["In progress", "Ready for review"],
            result["validation"]["allowed_values"],
        )

    def test_semantic_cell_resolution_accepts_only_an_unambiguous_partial_row_label(self):
        workbook = self._semantic_workbook()
        match = actions._resolve_semantic_cell(workbook, "Eval", "Status")
        self.assertEqual("unique_contains", match["match_mode"])
        self.assertEqual(4, match["row_index"])

        duplicate = self._semantic_workbook()
        duplicate["sheets"][0]["rows"][5][3] = {
            "effectiveValue": {"stringValue": "Evaluation follow-up"},
            "formattedValue": "Evaluation follow-up",
        }
        with self.assertRaisesRegex(RuntimeError, "ambiguous"):
            actions._resolve_semantic_cell(duplicate, "Eval", "Status")

    def test_semantic_cell_update_rejects_value_not_in_live_dropdown(self):
        workbook = self._semantic_workbook()
        original_service = actions.service
        original_grid = actions._spreadsheet_grid
        actions.service = lambda *_args: object()
        actions._spreadsheet_grid = lambda *_args, **_kwargs: workbook
        try:
            args = argparse.Namespace(
                spreadsheet_id="sheet-1",
                sheet="",
                row_match="Evaluation",
                column="Status",
                expected_current="In progress",
                value="Made up status",
                max_rows=200,
                max_columns=50,
                confirm=True,
            )
            with self.assertRaisesRegex(RuntimeError, "Ready for review"):
                actions.sheets_set_cell(args)
        finally:
            actions.service = original_service
            actions._spreadsheet_grid = original_grid

    def test_semantic_cell_update_rejects_formula_protection_and_stale_value(self):
        class Api:
            def spreadsheets(self):
                return self

        for workbook, expected, error in (
            (self._semantic_workbook(formula=True), "In progress", "formula cell"),
            (self._semantic_workbook(protected=True), "In progress", "protected cell"),
            (self._semantic_workbook(), "Not started", "changed since inspection"),
        ):
            with self.subTest(error=error):
                original_service = actions.service
                original_grid = actions._spreadsheet_grid
                actions.service = lambda *_args: Api()
                actions._spreadsheet_grid = lambda *_args, **_kwargs: workbook
                try:
                    args = argparse.Namespace(
                        spreadsheet_id="sheet-1",
                        sheet="",
                        row_match="Evaluation",
                        column="Status",
                        expected_current=expected,
                        value="Ready for review",
                        max_rows=200,
                        max_columns=50,
                        confirm=True,
                    )
                    with self.assertRaisesRegex(RuntimeError, error):
                        actions.sheets_set_cell(args)
                finally:
                    actions.service = original_service
                    actions._spreadsheet_grid = original_grid

    def test_range_backed_dropdown_is_resolved_from_sheet(self):
        class Request:
            def execute(self):
                return {"values": [["Queued"], ["Active"], ["Done"]]}

        class Values:
            def get(self, **_kwargs):
                return Request()

        class Spreadsheets:
            def values(self):
                return Values()

        class Api:
            def spreadsheets(self):
                return Spreadsheets()

        validation = actions._validation_description(Api(), "sheet-1", {
            "condition": {
                "type": "ONE_OF_RANGE",
                "values": [{"userEnteredValue": "='Options'!A1:A3"}],
            },
            "strict": True,
        })
        self.assertEqual(["Queued", "Active", "Done"], validation["allowed_values"])

    def test_sheet_parser_exposes_schema_inspection_and_guarded_cell_update(self):
        inspect = actions.build_parser().parse_args([
            "sheets", "inspect", "sheet-1",
            "--row-match", "Evaluation", "--column", "Status",
        ])
        update = actions.build_parser().parse_args([
            "sheets", "set-cell", "sheet-1",
            "--row-match", "Evaluation", "--column", "Status",
            "--expected-current", "In progress", "--value", "Ready for review", "--confirm",
        ])
        self.assertEqual("Evaluation", inspect.row_match)
        self.assertEqual("Status", inspect.column)
        self.assertEqual("In progress", update.expected_current)
        self.assertTrue(update.confirm)

    def test_docs_get_returns_the_live_source_url(self):
        class Request:
            def execute(self):
                return {
                    "title": "Product summary",
                    "body": {"content": [{"paragraph": {"elements": [
                        {"textRun": {"content": "Grounded text"}},
                    ]}}]},
                }

        class Documents:
            def get(self, **_kwargs):
                return Request()

        class Api:
            def documents(self):
                return Documents()

        args = argparse.Namespace(document_id="doc-1", max_chars=1000)
        original_service = actions.service
        actions.service = lambda *_args: Api()
        try:
            output = io.StringIO()
            with redirect_stdout(output):
                actions.docs_get(args)
        finally:
            actions.service = original_service

        result = json.loads(output.getvalue())
        self.assertEqual("https://docs.google.com/document/d/doc-1/edit", result["url"])
        self.assertEqual("Grounded text", result["text"])

    def test_slides_replace_returns_verified_user_facing_confirmation(self):
        class Request:
            def __init__(self, value):
                self.value = value

            def execute(self):
                return self.value

        class Presentations:
            def batchUpdate(self, **_kwargs):
                return Request({"replies": [{"replaceAllText": {"occurrencesChanged": 1}}]})

            def get(self, **_kwargs):
                return Request({
                    "title": "Launch deck",
                    "slides": [{"pageElements": [{"shape": {"text": {"textElements": [
                        {"textRun": {"content": "New wording"}},
                    ]}}}]}],
                })

        class Api:
            def presentations(self):
                return Presentations()

        args = argparse.Namespace(
            presentation_id="deck-1",
            find="Old wording",
            replace="New wording",
            match_case=False,
            confirm=True,
        )
        original_service = actions.service
        actions.service = lambda *_args: Api()
        try:
            output = io.StringIO()
            with redirect_stdout(output):
                actions.slides_replace(args)
        finally:
            actions.service = original_service
        result = json.loads(output.getvalue())
        self.assertTrue(result["verified"])
        self.assertEqual(
            "Updated **Launch deck** with the requested text change. "
            "[Slides](https://docs.google.com/presentation/d/deck-1/edit)",
            result["confirmation_markdown"],
        )

    def test_slides_get_recovers_only_a_strong_unique_live_id_match(self):
        class MissingPresentation(Exception):
            resp = type("Response", (), {"status": 404})()

        class Request:
            def __init__(self, value=None, error=None):
                self.value = value
                self.error = error

            def execute(self):
                if self.error:
                    raise self.error
                return self.value

        requested = "1examplePresentationIdentifiex"
        recovered = "1examplePresentationIdentifier"

        class Presentations:
            def get(self, presentationId):
                if presentationId == requested:
                    return Request(error=MissingPresentation("not found"))
                self.last_id = presentationId
                return Request({"title": "Live deck", "slides": []})

        presentations = Presentations()

        class SlidesApi:
            def presentations(self):
                return presentations

        class Files:
            def list(self, **_kwargs):
                return Request({"files": [
                    {"id": recovered, "name": "Live deck"},
                    {"id": "1unrelatedPresentationIdentifier", "name": "Another deck"},
                ]})

        class DriveApi:
            def files(self):
                return Files()

        original_service = actions.service
        actions.service = lambda name, *_args: SlidesApi() if name == "slides" else DriveApi()
        try:
            output = io.StringIO()
            with redirect_stdout(output):
                actions.slides_get(argparse.Namespace(presentation_id=requested, max_chars_per_slide=1000))
        finally:
            actions.service = original_service

        result = json.loads(output.getvalue())
        self.assertEqual(recovered, result["id"])
        self.assertEqual(recovered, presentations.last_id)
        self.assertEqual(f"https://docs.google.com/presentation/d/{recovered}/edit", result["url"])

    def test_workspace_text_normalization_renders_multiline_bullets(self):
        self.assertEqual(
            "• Product value\n• Pilot signal",
            actions.normalize_cli_text(r"\u2022 Product value\n\u2022 Pilot signal"),
        )

    def test_calendar_parser_exposes_focused_reads_and_safe_move(self):
        find = actions.build_parser().parse_args([
            "calendar", "find", "--query", "Release review",
        ])
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
        reschedule = actions.build_parser().parse_args([
            "calendar", "reschedule", "event-1",
            "--query", "Release review", "--date", "2026-08-25",
            "--date-source-message", "message-1", "--confirm",
        ])

        self.assertEqual(60, availability.duration_minutes)
        self.assertEqual("", find.start_date)
        self.assertEqual(14, find.days)
        self.assertEqual("event-1", availability.exclude_event)
        self.assertFalse(move.allow_conflict)
        self.assertTrue(move.confirm)
        self.assertEqual("08:00", reschedule.work_start)
        self.assertEqual("17:00", reschedule.work_end)
        self.assertEqual("2026-08-25", reschedule.date)
        self.assertEqual("message-1", reschedule.date_source_message)
        self.assertFalse(reschedule.user_directed_date)
        self.assertEqual("", reschedule.expected_weekday)


if __name__ == "__main__":
    unittest.main()
