import base64
import importlib.util
import sys
import unittest
import zipfile
from datetime import date, datetime
from email import message_from_bytes
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

MODULE = Path(__file__).with_name("seed_workspace.py")
sys.path.insert(0, str(Path(__file__).parent))
spec = importlib.util.spec_from_file_location("workspace_seed", MODULE)
seed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed)
from baseline import PRE_EMAIL_ROWS

class WorkspaceSeedTests(unittest.TestCase):
    def test_reference_names_and_no_private_labels(self):
        source = MODULE.read_text(encoding="utf-8")
        self.assertIn("RTX Spark Campaign Tracker", source)
        self.assertIn("RTX Spark Campaign Plan", source)
        self.assertIn("RTX Spark Exec Review", source)
        self.assertNotIn("Public Demo", source)
        self.assertNotIn("August", source)

    def test_exact_templates_are_present_and_valid(self):
        templates = Path(__file__).with_name("templates")
        expected = {
            "rtx-spark-campaign-tracker.xlsx": "xl/workbook.xml",
            "rtx-spark-exec-review.pptx": "ppt/presentation.xml",
            "rtx-spark-campaign-plan.docx": "word/document.xml",
        }
        for filename, member in expected.items():
            path = templates / filename
            self.assertTrue(path.exists(), filename)
            with zipfile.ZipFile(path) as archive:
                self.assertIn(member, archive.namelist())

    def test_reference_email_and_calendar_shape(self):
        self.assertEqual(len(seed.EVENTS), 16)
        self.assertTrue(any(x[2].startswith("RTX Spark Exec Review") for x in seed.EVENTS))
        self.assertIn("Mike Chen", MODULE.read_text(encoding="utf-8"))
        self.assertIn("2.1x faster", MODULE.read_text(encoding="utf-8"))

    def test_main_emails_are_preserved_with_diverse_background_mail_and_today_times(self):
        gmail = Mock()
        gmail.users().getProfile.return_value.execute.return_value = {"emailAddress": "demo@example.test"}
        total = seed.MEANINGFUL_EMAIL_COUNT + seed.BACKGROUND_EMAIL_COUNT + seed.CONTACT_EMAIL_COUNT
        results = [
            {"id": f"message-{index}", "threadId": f"thread-{index}"}
            for index in range(total)
        ]
        now = datetime(2026, 8, 27, 14, 30, tzinfo=ZoneInfo("America/Los_Angeles"))

        with patch.object(seed, "local_now", return_value=now), patch.object(seed, "execute_batched", return_value=results) as batched:
            created, evidence = seed.create_emails(gmail, "deck", "sheet", "doc")

        imported = []
        labels = []
        for call in gmail.users().messages().import_.call_args_list:
            payload = call.kwargs["body"]
            imported.append(message_from_bytes(base64.urlsafe_b64decode(payload["raw"])))
            labels.append(payload["labelIds"])

        self.assertEqual(total, len(created))
        self.assertEqual(total, len(batched.call_args.args[1]))
        self.assertEqual(
            [
                "URGENT: RTX Spark Exec Review moved to 5 PM today",
                "APPROVED: RTX Spark inference numbers for slide 4",
                "Exec Review deck pass: cut slide 6; protect slide 10",
                "Legal scope: RTX Spark wording cleared for leadership review",
                "Decision by 4:30 PM today: marketing shoot venue hold",
                "Agent Security PRD needs to reach Engineering today",
            ],
            [message["Subject"] for message in imported[:seed.MEANINGFUL_EMAIL_COUNT]],
        )
        self.assertEqual({"elena", "mike", "aisha", "daniel", "priya", "prd"}, set(evidence))
        received_at = [parsedate_to_datetime(message["Date"]) for message in imported]
        self.assertEqual({date(2026, 8, 27)}, {value.date() for value in received_at})
        self.assertEqual(total, len(set(received_at)))
        self.assertTrue(all("IMPORTANT" in value for value in labels[:seed.MEANINGFUL_EMAIL_COUNT]))
        self.assertTrue(all("IMPORTANT" not in value for value in labels[seed.MEANINGFUL_EMAIL_COUNT:]))
        background_end = seed.MEANINGFUL_EMAIL_COUNT + seed.BACKGROUND_EMAIL_COUNT
        background = imported[seed.MEANINGFUL_EMAIL_COUNT:background_end]
        self.assertEqual(seed.BACKGROUND_EMAIL_COUNT, len({message["From"] for message in background}))
        self.assertEqual(seed.BACKGROUND_EMAIL_COUNT, len({message["Subject"] for message in background}))
        self.assertTrue(all("no action is required" in message.get_payload().casefold() for message in background))
        contacts = imported[background_end:]
        self.assertEqual(seed.CONTACT_EMAIL_COUNT, len(contacts))
        self.assertEqual(
            {
                "Grant Walker <grant.walker@nvidia.example>": "Retail demo coordination contact",
                "Rafael Costa <rafael.costa@nvidia.example>": "Social rollout coordination contact",
            },
            {message["From"]: message["Subject"] for message in contacts},
        )

        seeded_addresses = {
            name: address
            for message in imported
            for name, address in [parseaddr(message["From"])]
            if name and address
        }
        tracker_people = {row[1] for row in PRE_EMAIL_ROWS if row[1] != "Workspace Owner"}
        self.assertEqual(set(), tracker_people - seeded_addresses.keys())
        self.assertTrue(all("@" in seeded_addresses[name] for name in tracker_people))

    def test_google_requests_are_executed_in_bounded_batches(self):
        batches = []

        class Batch:
            def __init__(self):
                self.items = []

            def add(self, request, callback, request_id):
                self.items.append((request, callback, request_id))

            def execute(self):
                for request, callback, request_id in self.items:
                    callback(request_id, {"value": request}, None)

        class Api:
            def new_batch_http_request(self):
                batch = Batch()
                batches.append(batch)
                return batch

        requests = list(range(seed.BATCH_SIZE + 1))
        results = seed.execute_batched(Api(), requests)

        self.assertEqual(2, len(batches))
        self.assertEqual(seed.BATCH_SIZE, len(batches[0].items))
        self.assertEqual({"value": requests[-1]}, results[-1])

    def test_seeded_email_times_stay_unique_and_on_today_even_just_after_midnight(self):
        now = datetime(2026, 8, 27, 0, 0, 10, tzinfo=ZoneInfo("America/Los_Angeles"))

        values = seed.seeded_email_times(
            seed.MEANINGFUL_EMAIL_COUNT + seed.BACKGROUND_EMAIL_COUNT + seed.CONTACT_EMAIL_COUNT,
            now,
        )

        self.assertEqual({now.date()}, {value.date() for value in values})
        self.assertEqual(len(values), len(set(values)))

    def test_cleanup_permanently_deletes_seeded_mail_including_trash(self):
        gmail = Mock()
        gmail.users().messages().list.return_value.execute.side_effect = [
            {"messages": [{"id": "tracked"}, {"id": "trashed-orphan"}], "nextPageToken": "next"},
            {"messages": [{"id": "older-orphan"}]},
        ]
        calendar = Mock()
        calendar.events().list.return_value.execute.return_value = {"items": []}

        seed.remove_dynamic_items(
            {"week_of": "2026-08-24", "emails": [{"id": "tracked"}], "events": []},
            {"gmail": gmail, "calendar": calendar},
        )

        self.assertEqual(
            {"ids": ["older-orphan", "tracked", "trashed-orphan"]},
            gmail.users().messages().batchDelete.call_args.kwargs["body"],
        )
        self.assertEqual(
            [
                {"userId": "me", "q": f'"{seed.MARKER}"', "includeSpamTrash": True, "maxResults": 500},
                {"userId": "me", "q": f'"{seed.MARKER}"', "includeSpamTrash": True, "maxResults": 500, "pageToken": "next"},
            ],
            [call.kwargs for call in gmail.users().messages().list.call_args_list],
        )
        gmail.users().messages().delete.assert_not_called()
        gmail.users().messages().trash.assert_not_called()

    def test_reset_draft_cleanup_lists_and_batches_all_drafts(self):
        gmail = Mock()
        gmail.users().drafts().list.return_value.execute.side_effect = [
            {"drafts": [{"id": "draft-1"}], "nextPageToken": "next"},
            {"drafts": [{"id": "draft-2"}]},
        ]

        with patch.object(seed, "execute_batched", return_value=[{}, {}]) as batched:
            removed = seed.clear_all_drafts(gmail)

        self.assertEqual(2, removed)
        self.assertEqual(2, len(batched.call_args.args[1]))
        self.assertEqual(
            [
                {"userId": "me", "maxResults": 500},
                {"userId": "me", "maxResults": 500, "pageToken": "next"},
            ],
            [call.kwargs for call in gmail.users().drafts().list.call_args_list],
        )
        self.assertEqual(
            ["draft-1", "draft-2"],
            [call.kwargs["id"] for call in gmail.users().drafts().delete.call_args_list],
        )

    def test_sheet_baseline_uses_one_values_batch(self):
        sheets = Mock()
        state = {
            "sheet": {"id": "sheet-1", "url": "sheet-url"},
            "slides": {"url": "deck-url"},
            "doc": {"url": "doc-url"},
        }
        evidence = {"priya": "priya-url", "aisha": "aisha-url"}

        seed.reset_sheet_baseline(sheets, state, evidence, "2026-08-28")

        sheets.spreadsheets().values().update.assert_not_called()
        call = sheets.spreadsheets().values().batchUpdate.call_args
        self.assertEqual("sheet-1", call.kwargs["spreadsheetId"])
        self.assertEqual(
            ["'Campaign Lanes'!A7:J14", "'Campaign Lanes'!A3:J3"],
            [item["range"] for item in call.kwargs["body"]["data"]],
        )

if __name__ == "__main__":
    unittest.main()
