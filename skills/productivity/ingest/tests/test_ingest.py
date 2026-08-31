from __future__ import annotations

import argparse
import base64
import email
import importlib.util
import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
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
        self.assertLessEqual(len(snapshot["messages"]), 50)

    def test_cloud_mutation_requires_confirmation(self):
        with self.assertRaisesRegex(RuntimeError, "without --confirm"):
            actions.require_confirm(argparse.Namespace(confirm=False), "test mutation")
        actions.require_confirm(argparse.Namespace(confirm=True), "test mutation")

    def test_gmail_draft_requires_confirmation(self):
        with (
            patch.object(actions, "service") as mock_service,
            self.assertRaisesRegex(RuntimeError, "without --confirm"),
        ):
            actions.gmail_draft(argparse.Namespace(confirm=False))

        mock_service.assert_not_called()

    def test_tracker_updates_can_be_read_from_standard_input(self):
        payload = '[{"lane":"Exec Review deck","status":"In review","latest":"Aisha\'s review is complete."}]'
        args = argparse.Namespace(updates=None, updates_file="-")

        with patch.object(actions.sys, "stdin", io.StringIO(payload)):
            updates = actions._load_tracker_updates(args)

        self.assertEqual("Aisha's review is complete.", updates[0]["latest"])

    def test_inline_tracker_updates_remain_supported(self):
        payload = '[{"lane":"Exec Review deck","status":"In review"}]'
        args = argparse.Namespace(updates=payload, updates_file=None)

        self.assertEqual("Exec Review deck", actions._load_tracker_updates(args)[0]["lane"])

    def test_one_time_codes_are_redacted_before_model_context(self):
        text = "Your verification code is 865913. It expires soon."
        redacted = ingest.redact_sensitive(text)
        self.assertNotIn("865913", redacted)
        self.assertIn("[REDACTED]", redacted)

    def test_gmail_search_is_metadata_only_and_bounded(self):
        calls = {}

        class Request:
            def __init__(self, value):
                self.value = value

            def execute(self):
                return self.value

        class Messages:
            def list(self, **kwargs):
                calls["list"] = kwargs
                return Request({"messages": [{"id": "message-1"}]})

            def get(self, **kwargs):
                calls["get"] = kwargs
                return Request({
                    "id": "message-1",
                    "threadId": "thread-1",
                    "payload": {"headers": [
                        {"name": "From", "value": "Person <person@example.com>"},
                        {"name": "Subject", "value": "Project update"},
                    ]},
                })

        class Users:
            def messages(self):
                return Messages()

        class Api:
            def users(self):
                return Users()

        original_service = actions.service
        actions.service = lambda *_args: Api()
        output = io.StringIO()
        try:
            with redirect_stdout(output):
                actions.gmail_search(argparse.Namespace(query="Person project", max=50))
        finally:
            actions.service = original_service

        result = json.loads(output.getvalue())
        self.assertEqual(10, calls["list"]["maxResults"])
        self.assertEqual("metadata", calls["get"]["format"])
        self.assertEqual("Person <person@example.com>", result["matches"][0]["from"])
        self.assertNotIn("body", result["matches"][0])

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
                confirm=True,
                to="Person <person@example.com>",
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

    def test_reply_draft_requires_verified_expected_recipient(self):
        with (
            patch.object(actions, "service") as mock_service,
            self.assertRaisesRegex(RuntimeError, "require --to"),
        ):
            actions.gmail_draft(argparse.Namespace(
                confirm=True,
                to="",
                cc="",
                subject="",
                body="Can you share an update?\n\nThanks",
                thread_id="",
                reply_to_message="message-0",
            ))

        mock_service.assert_not_called()

    def test_reply_draft_rejects_mismatched_recipient_before_create(self):
        api = unittest.mock.Mock()
        api.users().messages().get.return_value.execute.return_value = {
            "threadId": "thread-1",
            "payload": {"headers": [
                {"name": "From", "value": "Person <person@example.com>"},
                {"name": "Subject", "value": "Project update"},
            ]},
        }
        args = argparse.Namespace(
            confirm=True,
            to="Different Person <different@example.com>",
            cc="",
            subject="",
            body="Can you share an update?\n\nThanks",
            thread_id="",
            reply_to_message="message-0",
        )

        with patch.object(actions, "service", return_value=api), self.assertRaisesRegex(RuntimeError, "does not match"):
            actions.gmail_draft(args)

        api.users().drafts().create.assert_not_called()

    def test_name_only_draft_recipient_is_rejected_before_create(self):
        api = unittest.mock.Mock()
        args = argparse.Namespace(
            confirm=True,
            to="Grant Walker",
            cc="",
            subject="Retail demo ownership",
            body="Can you take ownership?\n\nThanks",
            thread_id="",
            reply_to_message="",
        )

        with patch.object(actions, "service", return_value=api), self.assertRaisesRegex(RuntimeError, "complete email address"):
            actions.gmail_draft(args)

        api.users().drafts().create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
