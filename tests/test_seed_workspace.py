from __future__ import annotations

import base64
import importlib.util
import unittest
from datetime import date, datetime
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
    def test_default_demo_week_uses_current_weekday_and_next_monday_on_weekends(self) -> None:
        self.assertEqual(date(2026, 8, 17), seed_workspace.default_demo_week(date(2026, 8, 20)))
        self.assertEqual(date(2026, 8, 24), seed_workspace.default_demo_week(date(2026, 8, 22)))
        self.assertEqual(date(2026, 8, 24), seed_workspace.default_demo_week(date(2026, 8, 23)))

    def test_demo_day_is_each_current_weekday_or_next_monday_on_weekends(self) -> None:
        week_of = date(2026, 8, 17)
        for offset in range(5):
            current = date(2026, 8, 17 + offset)
            with self.subTest(current=current):
                self.assertEqual(current, seed_workspace.demo_day_for_week(week_of, current))

        upcoming_week = date(2026, 8, 24)
        self.assertEqual(upcoming_week, seed_workspace.demo_day_for_week(upcoming_week, date(2026, 8, 22)))
        self.assertEqual(upcoming_week, seed_workspace.demo_day_for_week(upcoming_week, date(2026, 8, 23)))

    def test_email_reference_time_uses_current_day_for_a_future_demo_day(self) -> None:
        now = datetime(2026, 8, 22, 13, 5, tzinfo=ZoneInfo("America/Los_Angeles"))

        result = seed_workspace.email_reference_time(date(2026, 8, 24), now)

        self.assertEqual(
            datetime(2026, 8, 22, 13, 0, tzinfo=ZoneInfo("America/Los_Angeles")),
            result,
        )

    def test_email_reference_time_never_uses_a_future_time_today(self) -> None:
        now = datetime(2026, 8, 20, 9, 37, 42, tzinfo=ZoneInfo("America/Los_Angeles"))

        result = seed_workspace.email_reference_time(date(2026, 8, 20), now)

        self.assertEqual(
            datetime(2026, 8, 20, 9, 37, tzinfo=ZoneInfo("America/Los_Angeles")),
            result,
        )

    def test_tracker_reschedules_to_the_next_business_day(self) -> None:
        thursday = seed_workspace.tracker_rows("slides", "doc", "sheet", {}, date(2026, 8, 20))
        friday = seed_workspace.tracker_rows("slides", "doc", "sheet", {}, date(2026, 8, 21))

        self.assertIn("earliest non-conflicting one-hour slot on Friday", thursday[1][4])
        self.assertIn("earliest non-conflicting one-hour slot on Monday", friday[1][4])

    def test_background_mail_is_low_signal_unread_and_on_one_day(self) -> None:
        reference = datetime(2026, 8, 21, 12, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
        background = seed_workspace.background_email_specs(reference)

        self.assertEqual(seed_workspace.BACKGROUND_EMAIL_COUNT, len(background))
        self.assertEqual(seed_workspace.BACKGROUND_EMAIL_COUNT, len({item["sender"] for item in background}))
        self.assertEqual(seed_workspace.BACKGROUND_EMAIL_COUNT, len({item["subject"] for item in background}))
        self.assertTrue(all("note " not in item["subject"].casefold() for item in background))
        self.assertTrue(all(item["received_at"] < reference for item in background))
        self.assertEqual({reference.date()}, {item["received_at"].date() for item in background})
        self.assertEqual(seed_workspace.BACKGROUND_EMAIL_COUNT, len({item["received_at"] for item in background}))
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
        gmail.users().messages().list.return_value.execute.side_effect = [
            {"messages": [{"id": f"live-message-{index}", "threadId": f"live-thread-{index}"}]}
            for index in range(seed_workspace.MEANINGFUL_EMAIL_COUNT + seed_workspace.BACKGROUND_EMAIL_COUNT)
        ]
        demo_day = datetime(2026, 8, 21).date()

        created, evidence = seed_workspace.create_emails(
            gmail,
            "https://example.test/deck",
            "https://example.test/sheet",
            "https://example.test/doc",
            "https://calendar.example.test/release-review",
            demo_day,
        )

        calls = gmail.users().messages().import_.call_args_list
        dates = []
        message_ids = []
        messages = []
        for call in calls:
            body = call.kwargs["body"]
            labels = body["labelIds"]
            message = message_from_bytes(base64.urlsafe_b64decode(body["raw"]))
            messages.append((message, labels))
            dates.append(parsedate_to_datetime(message["Date"]))
            message_ids.append(message["Message-ID"])
            self.assertIn("INBOX", labels)
            self.assertIn("UNREAD", labels)

        total_messages = seed_workspace.MEANINGFUL_EMAIL_COUNT + seed_workspace.BACKGROUND_EMAIL_COUNT
        self.assertEqual(total_messages, len(created))
        self.assertEqual("live-message-0", created[0]["id"])
        self.assertEqual("live-thread-0", created[0]["thread_id"])
        self.assertEqual(total_messages, len(dates))
        self.assertEqual({demo_day}, {item.date() for item in dates})
        self.assertEqual(total_messages, len(set(dates)))
        self.assertEqual(total_messages, len(set(message_ids)))
        self.assertTrue(all(message_id.startswith(f"<{seed_workspace.MARKER}-") for message_id in message_ids))
        self.assertTrue(all(message_id.endswith("@demo.example>") for message_id in message_ids))
        meaningful_subjects = {
            "BLOCKER: Agent Runtime duplicates tool-call completions",
            "New slot for the Agent Runtime release review",
            "READY: Agent Runtime latency evaluation",
            "READY: Reliability test matrix",
            "For next week: approved Partner Readout headline",
            "ACTION: Partner demo checklist ready to start",
        }
        self.assertEqual({"bug", "scheduling", "evaluation", "reliability", "copy", "checklist"}, set(evidence))
        meaningful_positions = [
            index for index, (message, _labels) in enumerate(messages)
            if message["Subject"] in meaningful_subjects
        ]
        self.assertEqual(
            list(range(seed_workspace.BACKGROUND_EMAIL_COUNT, total_messages)),
            meaningful_positions,
        )
        meaningful_dates = [dates[index] for index in meaningful_positions]
        background_dates = [item for index, item in enumerate(dates) if index not in meaningful_positions]
        self.assertGreater(min(meaningful_dates), max(background_dates))
        labels_by_subject = {message["Subject"]: labels for message, labels in messages}
        bodies_by_subject = {
            message["Subject"]: message.get_payload(decode=True).decode("utf-8")
            for message, _labels in messages
        }
        priya_body = bodies_by_subject["BLOCKER: Agent Runtime duplicates tool-call completions"]
        daniel_body = bodies_by_subject["New slot for the Agent Runtime release review"]
        self.assertNotIn("Daniel is checking the next available slot.", priya_body)
        self.assertIn("Please postpone the RTX Spark Agent Runtime release review scheduled for", priya_body)
        self.assertIn("Reply in Priya's blocker thread with the confirmation and copy me", daniel_body)
        self.assertIn("IMPORTANT", labels_by_subject["BLOCKER: Agent Runtime duplicates tool-call completions"])
        self.assertIn("IMPORTANT", labels_by_subject["New slot for the Agent Runtime release review"])
        self.assertTrue(all(
            "IMPORTANT" not in labels
            for subject, labels in labels_by_subject.items()
            if subject not in {
                "BLOCKER: Agent Runtime duplicates tool-call completions",
                "New slot for the Agent Runtime release review",
            }
        ))
        for message, _ in messages[
            seed_workspace.BACKGROUND_EMAIL_COUNT:seed_workspace.BACKGROUND_EMAIL_COUNT + 2
        ]:
            text = message.get_payload(decode=True).decode("utf-8")
            self.assertGreater(text.index("https://calendar.example.test/release-review"), 200)
        batches = lambda count: (count + seed_workspace.GMAIL_BATCH_SIZE - 1) // seed_workspace.GMAIL_BATCH_SIZE
        expected_batches = (
            batches(seed_workspace.BACKGROUND_EMAIL_COUNT)
            + batches(seed_workspace.MEANINGFUL_EMAIL_COUNT)
            + batches(total_messages)
        )
        self.assertEqual(expected_batches, gmail.new_batch_http_request.call_count)

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

    @patch.object(seed_workspace.time, "sleep")
    def test_individual_request_retries_service_unavailable(self, mock_sleep: Mock) -> None:
        class ServiceUnavailable(Exception):
            resp = type("Response", (), {"status": 503})()

        request = Mock()
        request.execute.side_effect = [
            ServiceUnavailable("temporarily unavailable"),
            {"spreadsheetId": "sheet-1"},
        ]

        result = seed_workspace.execute_request(request, "Create delivery tracker")

        self.assertEqual({"spreadsheetId": "sheet-1"}, result)
        self.assertEqual(2, request.execute.call_count)
        mock_sleep.assert_called_once_with(1)

    def test_evaluation_doc_uses_structured_report_formatting(self) -> None:
        docs = Mock()
        drive = Mock()
        docs.documents().create.return_value.execute.return_value = {"documentId": "doc-1"}
        drive.files().get.return_value.execute.return_value = {"parents": []}

        result = seed_workspace.create_doc(docs, drive, "folder-1")

        self.assertEqual("doc-1", result["id"])
        requests = docs.documents().batchUpdate.call_args.kwargs["body"]["requests"]
        self.assertIn("insertText", requests[0])
        document_text = requests[0]["insertText"]["text"]
        self.assertIn("EVALUATION REPORT  •  INTERNAL", document_text)
        self.assertIn("Complete — ready for review.", document_text)
        self.assertNotIn("- Interactive tool-call latency", document_text)
        self.assertEqual(1, sum("createParagraphBullets" in request for request in requests))
        named_styles = {
            request["updateParagraphStyle"]["paragraphStyle"].get("namedStyleType")
            for request in requests
            if "updateParagraphStyle" in request
            and request["updateParagraphStyle"]["paragraphStyle"].get("namedStyleType")
        }
        self.assertEqual({"TITLE", "HEADING_2"}, named_styles)
        callout_styles = [
            request["updateTextStyle"]["textStyle"]
            for request in requests
            if "updateTextStyle" in request
            and "backgroundColor" in request["updateTextStyle"]["textStyle"]
        ]
        self.assertEqual(2, len(callout_styles))
        self.assertTrue(all(style["bold"] for style in callout_styles))
        drive.files().update.assert_called_once_with(
            fileId="doc-1",
            addParents="folder-1",
            removeParents="",
            fields="id,parents",
        )

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
            date(2026, 8, 20),
        )

        self.assertEqual("sheet-1", result["id"])
        update = sheets.spreadsheets().values().update.call_args.kwargs
        self.assertEqual("'Campaign Lanes'!A1:J14", update["range"])
        self.assertEqual(14, len(update["body"]["values"]))
        partner_row = next(row for row in update["body"]["values"] if row and row[0] == "Partner Readout Deck")
        self.assertIn("APPROVED HEADLINE PLACEHOLDER", partner_row[4])
        self.assertIn("Meet the RTX Spark Agent Runtime", partner_row[4])
        reliability_row = next(row for row in update["body"]["values"] if row and row[0] == "Reliability test matrix")
        checklist_row = next(row for row in update["body"]["values"] if row and row[0] == "Partner demo checklist")
        self.assertEqual("In review", reliability_row[2])
        self.assertIn("status to Ready for review", reliability_row[4])
        self.assertEqual("Not started", checklist_row[2])
        self.assertIn("status to In progress", checklist_row[4])
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
        format_requests = sheets.spreadsheets().batchUpdate.call_args.kwargs["body"]["requests"]
        conditional_rules = [
            request["addConditionalFormatRule"]
            for request in format_requests
            if "addConditionalFormatRule" in request
        ]
        self.assertEqual(len(seed_workspace.STATUS_VALUES), len(conditional_rules))
        self.assertEqual(
            set(seed_workspace.STATUS_VALUES),
            {
                rule["rule"]["booleanRule"]["condition"]["values"][0]["userEnteredValue"]
                for rule in conditional_rules
            },
        )
        for rule in conditional_rules:
            cell_format = rule["rule"]["booleanRule"]["format"]
            self.assertIn("backgroundColor", cell_format)
            self.assertTrue(cell_format["textFormat"]["bold"])
        column_widths = [
            request["updateDimensionProperties"]["properties"]["pixelSize"]
            for request in format_requests
            if request.get("updateDimensionProperties", {}).get("range", {}).get("dimension") == "COLUMNS"
        ]
        self.assertEqual(seed_workspace.TRACKER_COLUMN_WIDTHS, column_widths)
        drive.files().update.assert_called_once_with(
            fileId="sheet-1",
            addParents="folder-1",
            removeParents="",
            fields="id,parents",
        )

    def test_partner_readout_uses_reusable_slide_template(self) -> None:
        slides = Mock()
        drive = Mock()
        slides.presentations().create.return_value.execute.return_value = {
            "presentationId": "slides-1",
            "slides": [{"objectId": "default-slide"}],
        }
        drive.files().get.return_value.execute.return_value = {"parents": []}

        result = seed_workspace.create_slides(slides, drive, "folder-1")

        self.assertEqual("slides-1", result["id"])
        requests = slides.presentations().batchUpdate.call_args.kwargs["body"]["requests"]
        self.assertEqual(6, sum("createSlide" in request for request in requests))
        self.assertEqual(6, sum("updatePageProperties" in request for request in requests))
        shape_ids = {
            request["createShape"]["objectId"]
            for request in requests
            if "createShape" in request
        }
        for index in range(1, 7):
            self.assertIn(f"rtx_accent_{index}", shape_ids)
            self.assertIn(f"rtx_card_{index}", shape_ids)
            self.assertIn(f"rtx_footer_{index}", shape_ids)
            self.assertIn(f"rtx_page_{index}", shape_ids)
        inserted_text = {
            request["insertText"]["objectId"]: request["insertText"]["text"]
            for request in requests
            if "insertText" in request
        }
        self.assertIn("APPROVED HEADLINE PLACEHOLDER", inserted_text["rtx_body_4"])
        emphasized_ranges = [
            request["updateTextStyle"]["textRange"]
            for request in requests
            if request.get("updateTextStyle", {}).get("objectId") == "rtx_body_4"
            and request["updateTextStyle"]["textRange"].get("type") == "FIXED_RANGE"
        ]
        self.assertEqual(1, len(emphasized_ranges))
        drive.files().update.assert_called_once_with(
            fileId="slides-1",
            addParents="folder-1",
            removeParents="",
            fields="id,parents",
        )

    def test_calendar_uses_recurring_weekday_series_in_bounded_batches(self) -> None:
        calendar = Mock()
        calendar.new_batch_http_request.side_effect = FakeBatch
        calendar.events().insert.return_value.execute.side_effect = [
            {"id": f"event-{index}", "htmlLink": f"https://example.test/event-{index}"}
            for index in range(len(seed_workspace.EVENTS) + len(seed_workspace.OVERLAP_EVENTS) + 1)
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
        self.assertEqual(12, len(created))
        self.assertEqual(12, len(calls))
        self.assertEqual(3, calendar.new_batch_http_request.call_count)
        for call in calls[:8]:
            self.assertEqual(["RRULE:FREQ=DAILY;COUNT=5"], call.kwargs["body"]["recurrence"])
        for call, (day_offsets, *_rest) in zip(calls[8:11], seed_workspace.OVERLAP_EVENTS):
            self.assertEqual([seed_workspace.recurrence_for_days(day_offsets)], call.kwargs["body"]["recurrence"])
        self.assertNotIn("recurrence", calls[11].kwargs["body"])

    def test_added_meeting_series_overlap_at_three_distinct_times(self) -> None:
        def minutes(value: str) -> int:
            hour, minute = (int(part) for part in value.split(":"))
            return hour * 60 + minute

        routine = [(minutes(begin), minutes(end)) for begin, end, *_rest in seed_workspace.EVENTS]
        start_times = set()
        added_by_day = [0, 0, 0, 0, 0]
        for day_offsets, begin, end, *_rest in seed_workspace.OVERLAP_EVENTS:
            start = minutes(begin)
            finish = minutes(end)
            start_times.add(start)
            self.assertGreater(len(day_offsets), 0)
            self.assertLess(len(day_offsets), 5)
            self.assertTrue(any(start < routine_end and routine_start < finish for routine_start, routine_end in routine))
            for offset in day_offsets:
                added_by_day[offset] += 1

        self.assertEqual(3, len(seed_workspace.OVERLAP_EVENTS))
        self.assertEqual(3, len(start_times))
        self.assertEqual([1, 1, 2, 1, 1], added_by_day)

    @patch.object(seed_workspace, "services")
    def test_cleanup_permanently_deletes_tracked_mail_and_reports_counts(self, mock_services: Mock) -> None:
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

        self.assertEqual({"drafts_deleted": 1, "emails_deleted": 1, "events_deleted": 1, "folders_trashed": 1}, result)
        gmail.users().drafts().delete.assert_called_once_with(userId="me", id="draft-1")
        gmail.users().messages().delete.assert_called_once_with(userId="me", id="message-1")
        gmail.users().messages().trash.assert_not_called()
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
        gmail.users().messages().delete.return_value.execute.side_effect = RuntimeError("denied")

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
        gmail.users().messages().delete.return_value.execute.side_effect = MissingResource("not found")

        result = seed_workspace.cleanup({"emails": [{"id": "message-1"}]})

        self.assertEqual(1, result["emails_deleted"])


if __name__ == "__main__":
    unittest.main()
