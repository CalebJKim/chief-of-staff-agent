import base64
import importlib.util
import sys
import unittest
import zipfile
from datetime import date, datetime, timedelta
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
    def test_tasks_without_permission_skip_unless_previous_tasks_need_reset(self):
        creds = Mock()
        creds.has_scopes.return_value = False
        with patch.object(seed, "build") as build, patch("sys.stderr"):
            self.assertIsNone(seed.task_service(creds))
            with self.assertRaisesRegex(RuntimeError, "No workspace reset or cleanup was started"):
                seed.task_service(creds, required=True)
        build.assert_not_called()

    def test_tasks_api_unavailable_is_detected_before_workspace_mutations(self):
        creds = Mock()
        creds.has_scopes.return_value = True
        api = Mock()
        api.tasklists().list.return_value.execute.side_effect = seed.HttpError(
            Mock(status=403, reason="Forbidden"), b'{"error":{"message":"API disabled"}}'
        )
        state = {"task_list": {"id": "demo-list"}}
        with patch.object(seed, "credentials", return_value=creds), patch.object(seed, "build", return_value=api), patch.object(seed, "remove_dynamic_items") as remove:
            with self.assertRaisesRegex(RuntimeError, "Google Tasks API access is unavailable"):
                seed.reset_in_place(state, date(2026, 9, 7))
        remove.assert_not_called()
        api.tasks().delete.assert_not_called()
        api.tasklists().delete.assert_not_called()

    def test_tasks_use_default_list_and_link_to_source_emails_and_files(self):
        api = Mock()
        api.tasklists().get.return_value.execute.return_value = {"id": "default-list", "title": "My Tasks"}
        state = {
            "task_list": {"id": "demo-list"},
            "slides": {"url": "https://docs.google.com/presentation/d/deck"},
            "sheet": {"url": "https://docs.google.com/spreadsheets/d/sheet"},
            "doc": {"url": "https://docs.google.com/document/d/doc"},
        }
        evidence = {key: f"https://mail.google.com/mail/u/0/#all/{key}" for key in ("elena", "mike", "aisha", "daniel", "priya", "prd")}
        evidence.update({item["key"]: f"https://mail.google.com/mail/u/0/#all/{item['key']}" for item in seed.BACKLOG_TASKS})
        results = [{"id": f"task-{i}", "title": f"Task {i}", "webViewLink": f"https://tasks.google.com/task/{i}"} for i in range(3 + len(seed.BACKLOG_TASKS))]
        now = datetime(2026, 9, 10, 10, 30, tzinfo=ZoneInfo("America/Los_Angeles"))
        with patch.object(seed, "execute_batched", return_value=results), patch.object(seed, "local_now", return_value=now):
            seed.create_tasks(api, state, evidence)
        api.tasklists().insert.assert_not_called()
        api.tasklists().get.assert_called_once_with(tasklist="@default")
        self.assertEqual({"id": "default-list", "title": "My Tasks"}, state["task_list"])
        bodies = [call.kwargs["body"] for call in api.tasks().insert.call_args_list]
        self.assertEqual(3 + len(seed.BACKLOG_TASKS), len(bodies))
        notes = "\n".join(body["notes"] for body in bodies)
        self.assertTrue(all(url in notes for url in evidence.values()))
        self.assertTrue(all(state[key]["url"] in notes for key in ("slides", "sheet", "doc")))
        self.assertTrue(all(body["due"] == "2026-09-10T00:00:00Z" for body in bodies[:3]))
        self.assertTrue(all(body["status"] == "needsAction" for body in bodies))
        for item, body in zip(seed.BACKLOG_TASKS, bodies[3:]):
            requested = now.date() - timedelta(days=item["requested_days_ago"])
            due = date.fromisoformat(body["due"][:10])
            self.assertLess(requested, due)
            self.assertLess(due, now.date())
            self.assertIn(requested.isoformat(), body["notes"])
            self.assertIn("still unfinished", body["notes"])
            self.assertIn(evidence[item["key"]], body["notes"])
            self.assertNotIn("Working file:", body["notes"])
        self.assertTrue(all(call.kwargs["tasklist"] == "default-list" for call in api.tasks().insert.call_args_list))
        self.assertEqual(len(bodies), len(state["tasks"]))

    def test_task_reset_preserves_unrelated_tasks_and_finds_completed_orphans(self):
        api = Mock()
        state = {"task_list": {"id": "demo-list"}, "tasks": [{"id": "tracked"}]}
        api.tasks().list.return_value.execute.side_effect = [
            {"items": [{"id": "tracked"}, {"id": "personal", "notes": "Keep this"}], "nextPageToken": "next"},
            {"items": [{"id": "orphan", "notes": seed.MARKER, "status": "completed", "hidden": True}]},
        ]
        with patch.object(seed, "execute_batched"):
            seed.clear_seeded_tasks(api, state)
        self.assertEqual(["tracked", "orphan"], [call.kwargs["task"] for call in api.tasks().delete.call_args_list])
        self.assertTrue(all(call.kwargs["tasklist"] == "demo-list" for call in api.tasks().delete.call_args_list))
        self.assertTrue(all(call.kwargs["showHidden"] and call.kwargs["showCompleted"] for call in api.tasks().list.call_args_list))
        self.assertEqual("demo-list", state["task_list"]["id"])
        self.assertEqual([], state["tasks"])
        api.tasklists().delete.assert_not_called()

    def test_tasks_cleanup_preserves_default_list_and_personal_tasks(self):
        api = Mock()
        state = {"task_list": {"id": "default-list"}, "tasks": [{"id": "tracked"}]}
        api.tasks().list.return_value.execute.return_value = {
            "items": [{"id": "tracked"}, {"id": "personal", "notes": "Keep this"}]
        }
        with patch.object(seed, "services", return_value={"tasks": api}), patch.object(seed, "remove_dynamic_items"), patch.object(seed, "execute_batched"):
            seed.cleanup(state)
        api.tasks().delete.assert_called_once_with(tasklist="default-list", task="tracked")
        api.tasklists().delete.assert_not_called()
        self.assertEqual("default-list", state["task_list"]["id"])
        self.assertEqual([], state["tasks"])

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
        monday = date(2026, 8, 24)
        specs = seed.calendar_event_specs(monday, "deck", "doc", "sheet", reference_day=monday + timedelta(days=3))
        events_by_day = {
            day: [title for event_day, _, _, title, _ in specs if event_day == day]
            for day in (monday + timedelta(days=offset) for offset in range(5))
        }
        self.assertEqual(89, len(specs))
        self.assertEqual(5, len({tuple(titles) for titles in events_by_day.values()}))
        for day in events_by_day:
            periods = sorted(
                (begin, end)
                for event_day, begin, end, _, _ in specs
                if event_day == day
            )
            self.assertTrue(any(next_begin < end for (_, end), (next_begin, _) in zip(periods, periods[1:])))
        exec_reviews = [item for item in specs if item[3].startswith("RTX Spark Exec Review")]
        self.assertEqual(1, len(exec_reviews))
        self.assertEqual(monday + timedelta(days=3), exec_reviews[0][0])
        self.assertIn(seed.EXEC_REVIEW_ROLES, exec_reviews[0][4])
        self.assertIn("You will present", seed.EXEC_REVIEW_ROLES)
        self.assertIn("Planned attendees:", seed.EXEC_REVIEW_ROLES)
        self.assertIn("Mike Chen", MODULE.read_text(encoding="utf-8"))
        self.assertIn("2.1x faster", MODULE.read_text(encoding="utf-8"))

    def test_main_emails_are_preserved_with_diverse_background_mail_and_fixed_times(self):
        gmail = Mock()
        gmail.users().getProfile.return_value.execute.return_value = {"emailAddress": "demo@example.test"}
        today_count = seed.MEANINGFUL_EMAIL_COUNT + seed.BACKGROUND_EMAIL_COUNT + seed.CONTACT_EMAIL_COUNT
        total = today_count + len(seed.BACKLOG_TASKS)
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
        self.assertEqual({"elena", "mike", "aisha", "daniel", "priya", "prd"} | {item["key"] for item in seed.BACKLOG_TASKS}, set(evidence))
        review_feedback = imported[2].get_payload(decode=True).decode("utf-8")
        self.assertIn(seed.EXEC_REVIEW_ROLES, imported[0].get_payload(decode=True).decode("utf-8"))
        for phrase in ("I have not edited the deck", "proposed customer-use example", "Customer Example section of slide 7",
                       "then remove slide 6", "not customer validation", "owners still need a decision"):
            self.assertIn(phrase, review_feedback)
        received_at = [parsedate_to_datetime(message["Date"]) for message in imported]
        self.assertEqual({now.date()}, {value.date() for value in received_at[:seed.MEANINGFUL_EMAIL_COUNT]})
        self.assertEqual({now.date(), now.date() - timedelta(days=1)}, {value.date() for value in received_at[:today_count]})
        self.assertEqual(seed.seeded_email_times(today_count, now), received_at[:today_count])
        for index, item in enumerate(seed.BACKLOG_TASKS, today_count):
            due = now.date() - timedelta(days=item["due_days_ago"])
            self.assertLess(received_at[index].date(), due)
            self.assertLess(due, now.date())
            self.assertIn(due.isoformat(), imported[index].get_payload())
            self.assertEqual(created[index]["url"], evidence[item["key"]])
        self.assertEqual(total, len(set(received_at)))
        self.assertTrue(all("IMPORTANT" in value for value in labels[:seed.MEANINGFUL_EMAIL_COUNT]))
        self.assertTrue(all("IMPORTANT" not in value for value in labels[seed.MEANINGFUL_EMAIL_COUNT:]))
        background_end = seed.MEANINGFUL_EMAIL_COUNT + seed.BACKGROUND_EMAIL_COUNT
        background = imported[seed.MEANINGFUL_EMAIL_COUNT:background_end]
        self.assertEqual(seed.BACKGROUND_EMAIL_COUNT, len({message["From"] for message in background}))
        self.assertEqual(seed.BACKGROUND_EMAIL_COUNT, len({message["Subject"] for message in background}))
        self.assertTrue(all("no action is required" in message.get_payload().casefold() for message in background))
        contacts = imported[background_end:today_count]
        self.assertEqual(seed.CONTACT_EMAIL_COUNT, len(contacts))
        self.assertEqual(
            {
                "Rafael Costa <rafael.example@nvidia.com>": "REFERENCE CONTACT ONLY - Social rollout",
            },
            {message["From"]: message["Subject"] for message in contacts},
        )

        seeded_addresses = {
            name: address
            for message in imported
            for name, address in [parseaddr(message["From"])]
            if name and address
        }
        tracker_people = {row[1] for row in PRE_EMAIL_ROWS if row[1] not in {"Workspace Owner", "Unassigned"}}
        self.assertEqual(set(), tracker_people - seeded_addresses.keys())
        self.assertTrue(all("@" in seeded_addresses[name] for name in tracker_people))
        self.assertTrue(all(address.endswith(".example@nvidia.com") for address in seeded_addresses.values()))

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

    def test_seeded_email_clock_times_are_independent_of_reset_time(self):
        tz = ZoneInfo(seed.TZ_NAME)
        count = seed.MEANINGFUL_EMAIL_COUNT + seed.BACKGROUND_EMAIL_COUNT + seed.CONTACT_EMAIL_COUNT
        expected = seed.seeded_email_times(count, datetime(2026, 8, 27, 0, 0, tzinfo=tz))
        self.assertEqual((9, 12), (expected[0].hour, expected[0].minute))
        gaps = [a - b for a, b in zip(expected, expected[1:])]
        self.assertTrue(all(gap > timedelta(0) for gap in gaps))
        self.assertGreater(len(set(gaps)), 10)
        for hour in (6, 8, 12, 16, 23):
            with self.subTest(hour=hour):
                self.assertEqual(expected, seed.seeded_email_times(count, datetime(2026, 8, 27, hour, 37, tzinfo=tz)))

    def test_seeded_email_date_advances_but_clock_times_stay_fixed(self):
        tz = ZoneInfo(seed.TZ_NAME)
        today = datetime(2026, 8, 27, 9, 0, tzinfo=tz)
        tomorrow = today + timedelta(days=1)
        count = seed.MEANINGFUL_EMAIL_COUNT + seed.BACKGROUND_EMAIL_COUNT + seed.CONTACT_EMAIL_COUNT
        first = seed.seeded_email_times(count, today)
        second = seed.seeded_email_times(count, tomorrow)
        self.assertEqual([value.time() for value in first], [value.time() for value in second])
        self.assertEqual([value + timedelta(days=1) for value in first], second)

    def test_seeded_email_times_span_today_and_previous_day_even_after_midnight(self):
        now = datetime(2026, 8, 27, 0, 0, 10, tzinfo=ZoneInfo("America/Los_Angeles"))

        values = seed.seeded_email_times(
            seed.MEANINGFUL_EMAIL_COUNT + seed.BACKGROUND_EMAIL_COUNT + seed.CONTACT_EMAIL_COUNT,
            now,
        )

        self.assertEqual({now.date(), now.date() - timedelta(days=1)}, {value.date() for value in values})
        self.assertEqual(len(values), len(set(values)))
        self.assertTrue(any(value.date() < now.date() and 12 <= value.hour < 18 for value in values))
        self.assertTrue(any(value.date() < now.date() and value.hour >= 18 for value in values))

    def test_seeded_email_times_handle_empty_and_single_message(self):
        now = datetime(2026, 8, 27, 16, 0, tzinfo=ZoneInfo(seed.TZ_NAME))
        self.assertEqual([], seed.seeded_email_times(0, now))
        self.assertEqual([now.replace(hour=9, minute=12)], seed.seeded_email_times(1, now))

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
            ["'Campaign Lanes'!A7:J14", "'Campaign Lanes'!A3:J3", "'Campaign Lanes'!A4"],
            [item["range"] for item in call.kwargs["body"]["data"]],
        )

    def test_deck_reset_restores_every_demo_mutation_surface(self):
        slides = Mock()
        presentation = {
            "slides": [
                {
                    "pageElements": [
                        {"objectId": f"title-{number}", "shape": {"text": {"textElements": [{"textRun": {"content": "Old title"}}]}}},
                        {"objectId": f"body-{number}", "shape": {"text": {"textElements": [{"textRun": {"content": "Old body"}}]}}},
                    ]
                }
                for number in range(1, 11)
            ]
        }
        slides.presentations().get.return_value.execute.return_value = presentation

        seed.reset_deck_baseline(slides, "deck-1")

        call = slides.presentations().batchUpdate.call_args
        requests = call.kwargs["body"]["requests"]
        inserted = [item["insertText"]["text"] for item in requests if "insertText" in item]
        self.assertEqual(32, len(requests))
        self.assertTrue(any("Performance to go here" in text for text in inserted))
        self.assertTrue(any("Two decisions to leave with" in text for text in inserted))
        self.assertFalse(any("Retail demo owner" in text for text in inserted))

if __name__ == "__main__":
    unittest.main()
