from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("tasks_brief", ROOT / "scripts" / "brief.py")
brief = importlib.util.module_from_spec(spec)
spec.loader.exec_module(brief)


class GoogleTasksBriefTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = json.loads((ROOT / "tests/fixtures/workspace.json").read_text(encoding="utf-8"))
        self.args = argparse.Namespace(max_files=12, max_meetings=15, max_mail=12, max_tasks=8,
                                       work_start=8, work_end=18, min_focus_minutes=30)

    def task(self, task_id="task-any", **extra):
        return dict({"id": task_id, "title": "Complete the field handbook", "status": "needsAction",
                     "due": "2026-05-12", "notes": "Required work is still pending.",
                     "url": "https://tasks.google.com/task/" + task_id, "links": []}, **extra)

    def test_tasks_are_additive_and_existing_google_evidence_is_preserved(self):
        original = brief.build_packet(self.snapshot, self.args)
        self.snapshot["tasks"] = [self.task()]
        before = copy.deepcopy(self.snapshot)
        packet = brief.build_packet(self.snapshot, self.args)
        for key in ("mail", "meetings", "recent_files", "conflicts", "focus_blocks"):
            self.assertEqual(packet[key], original[key])
        self.assertEqual(packet["tasks"][0]["title"], "Complete the field handbook")
        self.assertEqual(packet["source_status"]["tasks"], "ok")
        self.assertIn("describe the same work once", packet["instruction"])
        self.assertEqual(self.snapshot, before)

    def test_exact_source_thread_link_connects_task_to_email(self):
        for route in ("all", "inbox", "sent", "search/handbook"):
            with self.subTest(route=route):
                tasks = [self.task(links=[f"https://mail.google.com/mail/u/1/#{route}/thread-urgent"])]
                result = brief.task_context(tasks, self.snapshot["messages"], 8)
                self.assertEqual(result[0]["related_mail_ids"], ["msg-urgent"])

    def test_shared_file_titles_or_partial_thread_ids_do_not_create_matches(self):
        tasks = [self.task(title=self.snapshot["messages"][0]["subject"], links=[
            "https://files.example.test/shared-project", "https://mail.google.com/mail/#all/thread-urgent-extra",
            "https://mail.google.com.example.test/mail/#all/thread-urgent", "https://[bad-url",
        ])]
        self.assertEqual(brief.task_context(tasks, self.snapshot["messages"], 8)[0]["related_mail_ids"], [])

    def test_task_links_remain_available_when_email_is_outside_packet(self):
        self.args.max_mail = 1
        self.snapshot["messages"].append({"id": "not-selected", "thread_id": "quiet-thread", "subject": "FYI"})
        source = "https://mail.google.com/mail/u/0/#all/quiet-thread"
        self.snapshot["tasks"] = [self.task(links=[source])]
        packet = brief.build_packet(self.snapshot, self.args)
        self.assertEqual(packet["tasks"][0]["related_mail_ids"], [])
        self.assertEqual(packet["tasks"][0]["links"], [source])

    def test_distinct_tasks_sharing_an_email_are_not_collapsed(self):
        link = "https://mail.google.com/mail/u/0/#all/thread-urgent"
        tasks = [self.task("handbook", title="Publish the handbook", links=[link]),
                 self.task("training", title="Run staff training", links=[link])]
        result = brief.task_context(tasks, self.snapshot["messages"], 8)
        self.assertEqual(len(result), 2)
        self.assertTrue(all(task["related_mail_ids"] == ["msg-urgent"] for task in result))

    def test_pending_filter_date_order_bounds_and_short_notes(self):
        tasks = [self.task("undated", due=""), self.task("later", due="2026-06-01"),
                 self.task("earlier", due="2026-04-09", notes="Background " * 100),
                 self.task("finished", status="completed"), self.task("hidden", hidden=True),
                 self.task("removed", deleted=True)]
        result = brief.task_context(tasks, [], 2)
        self.assertEqual([task["id"] for task in result], ["earlier", "later"])
        self.assertLessEqual(len(result[0]["notes"]), 240)
        self.assertEqual(brief.task_context(tasks, [], 8)[-1]["id"], "undated")

    def test_missing_source_empty_success_and_error_are_distinct(self):
        legacy = brief.build_packet(self.snapshot, self.args)
        self.assertNotIn("tasks", legacy)
        self.assertNotIn("tasks", legacy["source_status"])
        self.snapshot["tasks"] = []
        self.assertEqual(brief.build_packet(self.snapshot, self.args)["source_status"]["tasks"], "ok_empty")
        self.snapshot["coverage"]["errors"] = ["tasks: insufficient permissions"]
        packet = brief.build_packet(self.snapshot, self.args)
        self.assertEqual(packet["source_status"]["tasks"], "error")
        self.assertEqual(packet["source_status"]["gmail"], "ok")

    def test_tasks_participate_in_existing_packet_budget(self):
        self.snapshot["tasks"] = [self.task(str(i), notes="Background " * 100) for i in range(30)]
        packet = brief.build_packet(self.snapshot, self.args)
        self.assertEqual(len(packet["tasks"]), 8)
        fitted = json.loads(brief.fit_packet(packet, 5000))
        self.assertLessEqual(len(json.dumps(fitted, ensure_ascii=False, separators=(",", ":"))), 5000)
        for key in ("tasks", "mail", "meetings", "recent_files"):
            self.assertTrue(fitted[key], key)


if __name__ == "__main__":
    unittest.main()
