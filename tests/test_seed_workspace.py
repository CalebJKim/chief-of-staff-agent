from __future__ import annotations

import base64
import importlib.util
import unittest
from datetime import datetime
from email import message_from_bytes
from email.utils import parsedate_to_datetime
from pathlib import Path
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("seed_workspace", ROOT / "demo" / "seed_workspace.py")
assert SPEC and SPEC.loader
seed_workspace = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(seed_workspace)


class FakeBatch:
    def __init__(self) -> None:
        self.entries = []

    def add(self, request, callback=None, request_id=None) -> None:
        self.entries.append((request, callback, request_id))

    def execute(self) -> None:
        for request, callback, request_id in self.entries:
            try:
                response = request.execute()
            except Exception as exc:
                callback(request_id, None, exc)
            else:
                callback(request_id, response, None)


class SeedWorkspaceTests(unittest.TestCase):
    def test_background_mail_is_low_signal_unread_and_on_one_day(self) -> None:
        reference = datetime(2026, 8, 21, 12, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
        background = seed_workspace.background_email_specs(reference)

        self.assertEqual(100, len(background))
        self.assertEqual(100, len({item["sender"] for item in background}))
        self.assertEqual(100, len({item["subject"] for item in background}))
        self.assertTrue(all(item["received_at"] < reference for item in background))
        self.assertEqual({reference.date()}, {item["received_at"].date() for item in background})
        self.assertEqual(100, len({item["received_at"] for item in background}))
        self.assertTrue(all(item["unread"] and not item["important"] for item in background))
        prohibited = (
            "urgent", "blocker", "deadline", "decision", "approve", "approval",
            "customer", "launch", "exec", "board", "investor", "follow up",
            "action required", "review", "update",
        )
        for item in background:
            text = f"{item['subject']} {item['body']}".casefold()
            self.assertFalse(any(term in text for term in prohibited), text)

    def test_all_seeded_mail_is_unread_with_unique_times_on_demo_day(self) -> None:
        gmail = Mock()
        gmail.new_batch_http_request.side_effect = FakeBatch
        gmail.users().getProfile.return_value.execute.return_value = {"emailAddress": "demo@example.test"}
        gmail.users().messages().import_.return_value.execute.side_effect = [
            {"id": f"message-{index}", "threadId": f"thread-{index}"}
            for index in range(seed_workspace.MEANINGFUL_EMAIL_COUNT + seed_workspace.BACKGROUND_EMAIL_COUNT)
        ]
        demo_day = datetime(2026, 8, 21).date()

        created, _ = seed_workspace.create_emails(
            gmail,
            "https://example.test/deck",
            "https://example.test/sheet",
            "https://example.test/doc",
            demo_day,
        )

        calls = gmail.users().messages().import_.call_args_list
        dates = []
        for call in calls:
            body = call.kwargs["body"]
            labels = body["labelIds"]
            message = message_from_bytes(base64.urlsafe_b64decode(body["raw"]))
            dates.append(parsedate_to_datetime(message["Date"]))
            self.assertIn("INBOX", labels)
            self.assertIn("UNREAD", labels)

        self.assertEqual(106, len(created))
        self.assertEqual(106, len(dates))
        self.assertEqual({demo_day}, {item.date() for item in dates})
        self.assertEqual(106, len(set(dates)))
        self.assertGreater(min(dates[:6]), max(dates[6:]))
        self.assertEqual(6, gmail.new_batch_http_request.call_count)

    @patch.object(seed_workspace.time, "sleep")
    def test_batch_retries_only_rate_limited_requests(self, mock_sleep: Mock) -> None:
        class RateLimited(Exception):
            resp = type("Response", (), {"status": 429})()

        service = Mock()
        service.new_batch_http_request.side_effect = FakeBatch
        request = Mock()
        request.execute.side_effect = [RateLimited("slow down"), {"id": "created-1"}]
        recorded = []

        seed_workspace.execute_batch_requests(
            service,
            [("item-1", request)],
            "test operation",
            on_success=lambda request_id, response: recorded.append((request_id, response["id"])),
        )

        self.assertEqual([("item-1", "created-1")], recorded)
        self.assertEqual(2, service.new_batch_http_request.call_count)
        mock_sleep.assert_called_once_with(1)

    def test_campaign_lanes_match_tracker_row_contract(self) -> None:
        sheets = Mock()
        drive = Mock()
        sheets.spreadsheets().create.return_value.execute.return_value = {
            "spreadsheetId": "sheet-1",
            "sheets": [{"properties": {"sheetId": 123}}],
        }
        drive.files().get.return_value.execute.return_value = {"parents": []}

        result = seed_workspace.create_sheet(
            sheets,
            drive,
            "folder-1",
            "https://example.test/slides",
            "https://example.test/doc",
        )

        self.assertEqual("sheet-1", result["id"])
        update = sheets.spreadsheets().values().update.call_args.kwargs
        self.assertEqual("'Campaign Lanes'!A1:J14", update["range"])
        self.assertEqual(14, len(update["body"]["values"]))
        validation_request = next(
            request["setDataValidation"]
            for request in sheets.spreadsheets().batchUpdate.call_args.kwargs["body"]["requests"]
            if "setDataValidation" in request
        )
        validation = validation_request["range"]
        self.assertEqual(
            {
                "sheetId": 123,
                "startRowIndex": 6,
                "endRowIndex": 14,
                "startColumnIndex": 2,
                "endColumnIndex": 3,
            },
            validation,
        )
        drive.files().update.assert_called_once_with(
            fileId="sheet-1",
            addParents="folder-1",
            removeParents="",
            fields="id,parents",
        )

    def test_calendar_uses_recurring_weekday_series_in_bounded_batches(self) -> None:
        calendar = Mock()
        calendar.new_batch_http_request.side_effect = FakeBatch
        calendar.events().insert.return_value.execute.side_effect = [
            {"id": f"event-{index}", "htmlLink": f"https://example.test/event-{index}"}
            for index in range(len(seed_workspace.EVENTS) + 1)
        ]

        created = seed_workspace.create_calendar(
            calendar,
            datetime(2026, 8, 17).date(),
            datetime(2026, 8, 21).date(),
            "https://example.test/deck",
            "https://example.test/doc",
            "https://example.test/sheet",
        )

        calls = calendar.events().insert.call_args_list
        self.assertEqual(9, len(created))
        self.assertEqual(9, len(calls))
        self.assertEqual(2, calendar.new_batch_http_request.call_count)
        for call in calls[:8]:
            self.assertEqual(["RRULE:FREQ=DAILY;COUNT=5"], call.kwargs["body"]["recurrence"])
        self.assertNotIn("recurrence", calls[8].kwargs["body"])

    @patch.object(seed_workspace, "services")
    def test_cleanup_uses_supported_trash_operations_and_reports_counts(self, mock_services: Mock) -> None:
        gmail = Mock()
        calendar = Mock()
        drive = Mock()
        gmail.new_batch_http_request.side_effect = FakeBatch
        calendar.new_batch_http_request.side_effect = FakeBatch
        mock_services.return_value = {"gmail": gmail, "calendar": calendar, "drive": drive}
        state = {
            "drafts": [{"id": "draft-1"}],
            "emails": [{"id": "message-1"}],
            "events": [{"id": "event-1"}],
            "folder": {"id": "folder-1"},
        }

        result = seed_workspace.cleanup(state)

        self.assertEqual({"drafts_deleted": 1, "emails_trashed": 1, "events_deleted": 1, "folders_trashed": 1}, result)
        gmail.users().drafts().delete.assert_called_once_with(userId="me", id="draft-1")
        gmail.users().messages().trash.assert_called_once_with(userId="me", id="message-1")
        gmail.users().messages().delete.assert_not_called()
        self.assertEqual(1, gmail.new_batch_http_request.call_count)
        calendar.events().delete.assert_called_once_with(
            calendarId="primary",
            eventId="event-1",
            sendUpdates="none",
        )
        self.assertEqual(1, calendar.new_batch_http_request.call_count)
        drive.files().update.assert_called_once_with(fileId="folder-1", body={"trashed": True})

    @patch.object(seed_workspace, "services")
    def test_cleanup_raises_when_any_resource_cannot_be_removed(self, mock_services: Mock) -> None:
        gmail = Mock()
        calendar = Mock()
        drive = Mock()
        gmail.new_batch_http_request.side_effect = FakeBatch
        mock_services.return_value = {"gmail": gmail, "calendar": calendar, "drive": drive}
        gmail.users().messages().trash.return_value.execute.side_effect = RuntimeError("denied")

        with self.assertRaisesRegex(RuntimeError, "email-message-1: denied"):
            seed_workspace.cleanup({"emails": [{"id": "message-1"}]})

    @patch.object(seed_workspace, "services")
    def test_cleanup_retry_accepts_resources_that_are_already_absent(self, mock_services: Mock) -> None:
        class MissingResource(Exception):
            resp = type("Response", (), {"status": 404})()

        gmail = Mock()
        calendar = Mock()
        drive = Mock()
        gmail.new_batch_http_request.side_effect = FakeBatch
        mock_services.return_value = {"gmail": gmail, "calendar": calendar, "drive": drive}
        gmail.users().messages().trash.return_value.execute.side_effect = MissingResource("not found")

        result = seed_workspace.cleanup({"emails": [{"id": "message-1"}]})

        self.assertEqual(1, result["emails_trashed"])


if __name__ == "__main__":
    unittest.main()
