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
        self.assertLessEqual(len(snapshot["messages"]), 50)

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


if __name__ == "__main__":
    unittest.main()
