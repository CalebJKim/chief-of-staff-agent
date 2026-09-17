from __future__ import annotations

import argparse
import importlib.util
import io
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import Mock, call, patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
spec = importlib.util.spec_from_file_location("tasks_ingest", SCRIPTS / "ingest.py")
ingest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ingest)


class GoogleTasksIngestTests(unittest.TestCase):
    def fetch(self, items, max_tasks=20, task_list="@default", next_page=None):
        api = Mock()
        api.tasks.return_value.list.return_value.execute.return_value = {
            "items": items, "nextPageToken": next_page,
        }
        result = ingest.fetch_tasks(api, max_tasks, task_list)
        # Exhaustive call check: one list/read, no mutations or follow-up pages.
        self.assertEqual(api.mock_calls, [
            call.tasks(),
            call.tasks().list(
                tasklist=task_list, maxResults=max_tasks, showCompleted=False,
                showDeleted=False, showHidden=False, showAssigned=True,
                fields="nextPageToken,items(id,title,status,due,notes,webViewLink,links,deleted,hidden)",
            ),
            call.tasks().list().execute(),
        ])
        return result

    def test_real_task_fields_source_links_and_date_are_preserved(self):
        tasks, more = self.fetch([{
            "id": "arbitrary-task", "title": "Publish the supplier checklist",
            "status": "needsAction", "due": "2026-05-11T00:00:00Z",
            "notes": "Confirm requirements.\nhttps://example.test/checklist",
            "webViewLink": "https://tasks.google.com/task/arbitrary-task",
            "links": [{"type": "email", "link": "https://mail.google.com/mail/u/0/#inbox/thread-7"}],
        }], task_list="custom-list")
        self.assertFalse(more)
        self.assertEqual(tasks[0]["due"], "2026-05-11")
        self.assertEqual(tasks[0]["status"], "needsAction")
        self.assertEqual(tasks[0]["title"], "Publish the supplier checklist")
        self.assertEqual(tasks[0]["url"], "https://tasks.google.com/task/arbitrary-task")
        self.assertEqual(tasks[0]["links"], [
            "https://example.test/checklist", "https://mail.google.com/mail/u/0/#inbox/thread-7",
        ])

    def test_completed_deleted_hidden_duplicate_and_missing_ids_are_excluded(self):
        base = {"id": "pending", "title": "Order supplies", "status": "needsAction"}
        tasks, _ = self.fetch([
            base, base.copy(), dict(base, id="done", status="completed"),
            dict(base, id="deleted", deleted=True), dict(base, id="hidden", hidden=True),
            {"title": "No identity", "status": "needsAction"}, dict(base, id="unknown", status="unknown"),
        ])
        self.assertEqual([task["id"] for task in tasks], ["pending"])

    def test_empty_success_missing_dates_and_fallback_link(self):
        self.assertEqual(self.fetch([]), ([], False))
        tasks, _ = self.fetch([{"id": "no-date", "status": "needsAction", "notes": None}])
        self.assertEqual(tasks[0]["due"], "")
        self.assertEqual(tasks[0]["url"], "https://tasks.google.com/")
        self.assertEqual(tasks[0]["links"], [])

    def test_bounds_redaction_and_late_source_link(self):
        note = "Verification code is 123456. " + "Context " * 200 + "https://example.test/source"
        tasks, more = self.fetch([
            {"id": str(i), "title": "Title " * 100, "status": "needsAction", "notes": note}
            for i in range(4)
        ], max_tasks=2, next_page="more-results")
        self.assertEqual(len(tasks), 2)
        self.assertTrue(more)
        self.assertLessEqual(len(tasks[0]["title"]), 200)
        self.assertLessEqual(len(tasks[0]["notes"]), 500)
        self.assertNotIn("123456", tasks[0]["notes"])
        self.assertIn("[REDACTED]", tasks[0]["notes"])
        self.assertEqual(tasks[0]["links"], ["https://example.test/source"])

    def test_invalid_bounds_never_call_api(self):
        for limit in (0, -1, 101):
            with self.subTest(limit=limit):
                api = Mock()
                with self.assertRaises(ValueError):
                    ingest.fetch_tasks(api, limit)
                self.assertEqual(api.mock_calls, [])

    def collect(self, error=None):
        api = Mock()
        api.tasks.return_value.list.return_value.execute.return_value = {
            "items": [{"id": "live-shaped-task", "title": "Finish a handoff", "status": "needsAction"}],
            "nextPageToken": "more-results",
        }
        if error:
            api.tasks.return_value.list.return_value.execute.side_effect = error
        args = argparse.Namespace(fixture=None, date="2026-05-12", days_ahead=2, days_back=30,
                                  max_events=10, max_messages=10, max_files=10, gmail_query=None,
                                  max_tasks=7, task_list="user-selected-list")
        with patch.object(ingest, "load_credentials", return_value=object()), \
                patch("googleapiclient.discovery.build", return_value=api), \
                patch.object(ingest, "_calendar_timezone", return_value="UTC"), \
                patch.object(ingest, "fetch_calendars", return_value=([{"id": "event"}], [])), \
                patch.object(ingest, "fetch_mail", return_value=([{"id": "email"}], {})), \
                patch.object(ingest, "fetch_drive", return_value=[{"id": "file"}]), \
                patch.object(ingest, "fetch_trackers", return_value=[]):
            return ingest.collect(args)

    def test_collection_adds_tasks_and_reports_partial_coverage(self):
        snapshot = self.collect()
        self.assertEqual(snapshot["tasks"][0]["id"], "live-shaped-task")
        self.assertEqual(snapshot["coverage"]["tasks"], 1)
        self.assertTrue(snapshot["coverage"]["tasks_has_more"])
        self.assertEqual(snapshot["coverage"]["errors"], [])

    def test_permission_or_timeout_failure_keeps_other_workspace_evidence(self):
        for error in (RuntimeError("403 insufficient permissions"), TimeoutError("Google request timed out")):
            with self.subTest(error=type(error).__name__):
                snapshot = self.collect(error)
                self.assertEqual(snapshot["tasks"], [])
                self.assertIn("tasks:", snapshot["coverage"]["errors"][0])
                self.assertIn(str(error), snapshot["coverage"]["errors"][0])
                self.assertEqual(snapshot["events"], [{"id": "event"}])
                self.assertEqual(snapshot["messages"], [{"id": "email"}])
                self.assertEqual(snapshot["files"], [{"id": "file"}])

    def test_cli_rejects_invalid_bounds_before_collecting(self):
        for limit in ("0", "101"):
            with self.subTest(limit=limit), patch.object(ingest.sys, "argv", ["ingest.py", "--max-tasks", limit]), \
                    patch.object(ingest, "collect") as collect, redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    ingest.main()
                self.assertEqual(error.exception.code, 2)
                collect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
