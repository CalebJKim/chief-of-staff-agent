from __future__ import annotations

import base64
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


actions = load("preview_actions", "actions.py")
ingest = load("preview_ingest", "ingest.py")


def part(mime, text, **extra):
    return {"mimeType": mime, "body": {"data": base64.urlsafe_b64encode(text.encode()).decode()}, **extra}


class MailPreviewTests(unittest.TestCase):
    def fetch(self, payload, snippet="Gmail preview ends at 42"):
        api = Mock()
        users = api.users.return_value
        users.getProfile.return_value.execute.return_value = {"emailAddress": "owner@example.test"}
        messages = users.messages.return_value
        messages.list.return_value.execute.return_value = {
            "messages": [{"id": "one"}, {"id": "outside-budget"}],
        }
        messages.get.return_value.execute.return_value = {
            "id": "one", "threadId": "thread-one", "internalDate": "1",
            "snippet": snippet, "payload": payload, "labelIds": ["INBOX", "UNREAD"],
        }
        with patch.dict(sys.modules, {"actions": actions}):
            result, identity = ingest.fetch_mail(api, 7, 1, None)
        users.getProfile.assert_called_once_with(userId="me")
        messages.list.assert_called_once()
        messages.get.assert_called_once_with(userId="me", id="one", format="full")
        self.assertEqual(len(result), 1)
        self.assertEqual(identity["email"], "owner@example.test")
        return result[0]

    def test_body_preview_preserves_missing_units_without_extra_requests(self):
        text = "Cycle time is 17 seconds. Waste is 42% lower. No release decision yet."
        payload = part("text/plain", text, headers=[
            {"name": "From", "value": "Lina <lina@example.test>"},
            {"name": "To", "value": "owner@example.test"},
            {"name": "Cc", "value": "operations@example.test"},
            {"name": "Subject", "value": "Warehouse measurements"},
        ])
        result = self.fetch(payload)
        self.assertEqual(result["snippet"], text)
        self.assertEqual(result["from"], "Lina <lina@example.test>")
        self.assertEqual(result["cc"], "operations@example.test")

    def test_multipart_prefers_body_plain_text_over_html_and_attachment(self):
        payload = {"mimeType": "multipart/mixed", "parts": [
            part("text/plain", "Attachment is not the email body.", filename="readme.txt"),
            part("text/html", "<p>HTML alternative</p>"),
            part("text/plain", "Actual plain-text message."),
        ]}
        self.assertEqual(self.fetch(payload)["snippet"], "Actual plain-text message.")

    def test_html_entities_are_readable_and_codes_are_redacted(self):
        result = self.fetch(part("text/html", "<p>Research &amp; operations.</p><p>Your verification code is 836491.</p>"))
        self.assertIn("Research & operations.", result["snippet"])
        self.assertIn("[REDACTED]", result["snippet"])
        self.assertNotIn("836491", result["snippet"])

    def test_attachment_subtree_does_not_replace_message_body(self):
        payload = {"mimeType": "multipart/mixed", "parts": [
            {"mimeType": "message/rfc822", "filename": "attached.eml",
             "parts": [part("text/plain", "Old attachment: shipment approved.")]},
            part("text/html", "<p>Current body: shipment is not approved.</p>"),
        ]}
        self.assertEqual(self.fetch(payload)["snippet"], "Current body: shipment is not approved.")

    def test_nontext_and_attachment_only_mail_fall_back_to_gmail_preview(self):
        for payload in (
            part("application/pdf", "Binary content must not become the preview."),
            part("text/plain", "Attachment content.", filename="attachment.txt"),
            {"mimeType": "multipart/mixed", "parts": []},
        ):
            with self.subTest(payload=payload):
                self.assertEqual(self.fetch(payload, "Attached report for review.")["snippet"], "Attached report for review.")

    def test_nontext_does_not_hide_a_readable_html_body(self):
        payload = {"mimeType": "multipart/mixed", "parts": [
            part("application/octet-stream", "Binary data"),
            part("text/html", "<p>Readable &amp; useful.</p>"),
        ]}
        self.assertEqual(self.fetch(payload)["snippet"], "Readable & useful.")

    def test_long_preview_remains_bounded_and_visibly_truncated(self):
        result = self.fetch(part("text/plain", "Warehouse dependency details. " * 40))
        self.assertLessEqual(len(result["snippet"]), 500)
        self.assertTrue(result["snippet"].endswith("…"))
        self.assertNotIn("\n", result["snippet"])

    def test_plaintext_redaction_and_links_are_preserved(self):
        result = self.fetch(part("text/plain", "Your security code is 385192.\n\nSee https://example.test/report for details."))
        self.assertNotIn("385192", result["snippet"])
        self.assertIn("[REDACTED]", result["snippet"])
        self.assertEqual(result["links"], ["https://example.test/report"])


if __name__ == "__main__":
    unittest.main()
