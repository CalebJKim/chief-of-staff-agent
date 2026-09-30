"""Offline regression tests for repeatable seeding and reset cleanup."""
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

DEMO = Path(__file__).parent
sys.path.insert(0, str(DEMO))
spec = importlib.util.spec_from_file_location("email_cleanup_seed", DEMO / "seed_workspace.py")
seed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed)


class EmailCleanupTests(unittest.TestCase):
    def test_headers_find_orphans_without_search_and_preserve_unrelated_mail(self):
        gmail = Mock()
        messages = gmail.users().messages()
        messages.list.return_value.execute.side_effect = [
            {"messages": [{"id": "tracked"}, {"id": "orphan"}], "nextPageToken": "page2"},
            {"messages": [{"id": "unrelated"}, {"id": "near-match"}, {"id": "no-header"}]},
        ]
        metadata = {
            "orphan": {"payload": {"headers": [{"name": "Message-Id", "value": f"<{seed.MARKER}-previous-5@demo.invalid>"}]}},
            "unrelated": {"payload": {"headers": [{"name": "Message-ID", "value": "<personal@example.com>"}]}},
            "near-match": {"payload": {"headers": [{"name": "Message-ID", "value": f"<{seed.MARKER}-1@other.example>"}]}},
            "no-header": {"payload": {}},
        }
        messages.get.side_effect = lambda **kwargs: metadata[kwargs["id"]]
        with patch.object(seed, "execute_batched", side_effect=lambda api, requests: requests):
            self.assertEqual({"tracked", "orphan"}, seed.seeded_gmail_message_ids(gmail, {"tracked", "missing"}))
        for call in messages.list.call_args_list:
            self.assertNotIn("q", call.kwargs)
            self.assertTrue(call.kwargs["includeSpamTrash"])
        for call in messages.get.call_args_list:
            self.assertEqual("metadata", call.kwargs["format"])
            self.assertEqual(["Message-ID"], call.kwargs["metadataHeaders"])
        self.assertEqual("page2", messages.list.call_args_list[1].kwargs["pageToken"])

    def test_header_read_failure_aborts_cleanup(self):
        gmail = Mock()
        gmail.users().messages().list.return_value.execute.return_value = {"messages": [{"id": "unknown"}]}
        with patch.object(seed, "execute_batched", side_effect=RuntimeError("metadata read failed")):
            with self.assertRaisesRegex(RuntimeError, "metadata read failed"):
                seed.remove_dynamic_items({"emails": []}, {"gmail": gmail})
        gmail.users().messages().batchDelete.assert_not_called()

    def reset_with_cleanup_failure(self, *, deletion_error=False):
        gmail = Mock()
        svc = {"gmail": gmail, "tasks": None, "slides": Mock(), "drive": Mock()}
        state = {"emails": [{"id": "old"}], "slides": {"id": "deck"}}
        if deletion_error:
            gmail.users().messages().batchDelete.return_value.execute.side_effect = RuntimeError("delete failed")
        with patch.object(seed, "services", return_value=svc), \
             patch.object(seed, "reset_deck_baseline"), \
             patch.object(seed, "clear_seeded_tasks"), \
             patch.object(seed, "clear_all_drafts"), \
             patch.object(seed, "seeded_gmail_message_ids", side_effect=[{"old"}, {"old"}]), \
             patch.object(seed, "create_emails") as create:
            with self.assertRaisesRegex(RuntimeError, "delete failed" if deletion_error else "remain after cleanup"):
                seed.reset_in_place(state, date(2026, 9, 28))
            create.assert_not_called()

    def test_reset_does_not_import_if_old_mail_remains(self):
        self.reset_with_cleanup_failure()

    def test_reset_does_not_import_if_delete_fails(self):
        self.reset_with_cleanup_failure(deletion_error=True)

    def test_cleanup_splits_large_delete_into_supported_batches(self):
        gmail, calendar = Mock(), Mock()
        calendar.events().list.return_value.execute.return_value = {"items": []}
        ids = {f"seed-{i}" for i in range(1001)}
        with patch.object(seed, "seeded_gmail_message_ids", side_effect=[ids, set()]):
            seed.remove_dynamic_items({"week_of": "2026-09-28"}, {"gmail": gmail, "calendar": calendar})
        batches = [c.kwargs["body"]["ids"] for c in gmail.users().messages().batchDelete.call_args_list]
        self.assertEqual([1000, 1], [len(batch) for batch in batches])
        self.assertEqual(ids, set(batches[0] + batches[1]))

    def test_fresh_seed_refuses_existing_mail_before_creating_files(self):
        with patch.object(seed, "services", return_value={"gmail": Mock()}), \
             patch.object(seed, "seeded_gmail_message_ids", return_value={"orphan"}), \
             patch.object(seed, "create_folder") as create, patch.object(seed, "cleanup") as cleanup:
            with self.assertRaisesRegex(RuntimeError, "Demo emails already exist"):
                seed.seed(date(2026, 9, 28))
        create.assert_not_called()
        cleanup.assert_not_called()

    def test_lock_blocks_other_process_and_releases_after_error(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(seed.tempfile, "gettempdir", return_value=directory):
            child = (
                f"import sys,tempfile; sys.path.insert(0,{str(DEMO)!r}); "
                f"tempfile.tempdir={directory!r}; import seed_workspace; "
                "\nwith seed_workspace.workspace_write_lock(): pass"
            )
            with self.assertRaisesRegex(ValueError, "simulated failure"):
                with seed.workspace_write_lock():
                    result = subprocess.run([sys.executable, "-c", child], capture_output=True, text=True, timeout=20)
                    self.assertNotEqual(0, result.returncode)
                    self.assertIn("Another demo seed/reset/cleanup is running", result.stderr)
                    raise ValueError("simulated failure")
            result = subprocess.run([sys.executable, "-c", child], capture_output=True, text=True, timeout=20)
            self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
