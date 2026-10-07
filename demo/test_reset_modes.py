"""Reset contract tests with fake Google APIs and disposable local workspaces."""
import copy
import json
from datetime import date, datetime
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent))
import reset_modes as modes
import seed_workspace as seed
from evidence_cache import clear_evidence_cache
from second_brain_links import refresh_links


class ResetModesTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.state_file = self.root / "state.json"
        self.state = {
            "week_of": "2026-10-05",
            **{k: {"id": k, "url": f"https://drive.google.com/{k}"} for k in ("folder", "slides", "sheet", "doc", "original_sheet")},
            "task_resources": {k: {"id": k, "url": f"https://drive.google.com/{k}"} for k in seed.task_scenario.RESOURCES},
            "emails": [{"id": str(i), "url": f"https://mail.google.com/mail/u/0/#all/{i}"} for i in range(6)],
            "tasks": [{"id": str(i), "url": f"https://tasks.google.com/task/{i}"} for i in range(3)],
            "task_list": {"id": "list"},
            "events": [{"id": "event", "url": "event-url", "seed_key": "Review#1", "baseline": {"summary": "Review"}}],
        }
        for item in seed.task_scenario.TASKS:
            self.state["emails"].append({"id": item["key"], "task_key": item["key"], "url": "https://mail.google.com/mail/u/0/#all/" + item["key"]})
        self.svc = {k: Mock(name=k) for k in ("gmail", "calendar", "tasks", "drive", "slides", "sheets")}
        self.svc["gmail"].users().messages().list.return_value.execute.return_value = {"messages": self.state["emails"]}
        self.svc["calendar"].events().list.return_value.execute.return_value = {"items": [{"id": "event", "summary": "Review", "description": seed.MARKER}]}
        self.svc["tasks"].tasks().list.return_value.execute.return_value = {"items": self.state["tasks"]}
        self.svc["gmail"].users().drafts().list.return_value.execute.return_value = {}
        self.context = SimpleNamespace(**vars(seed))
        self.context.ROOT = self.root
        self.context.services = Mock(return_value=self.svc)
        self.context.execute_batched = Mock(side_effect=lambda api, requests, **kw: [{} for _ in requests])
        self.context.state_path = lambda: self.state_file
        self.context.local_now = lambda: datetime(2026, 10, 6, 10, tzinfo=ZoneInfo(seed.TZ_NAME))

    def test_preflight_missing_email_stops_before_writes(self):
        self.svc["gmail"].users().messages().list.return_value.execute.return_value = {"messages": []}
        with self.assertRaisesRegex(RuntimeError, "--full-reset"):
            modes.reset_in_place(self.context, self.state, date(2026, 10, 5))
        self.svc["gmail"].users().messages().batchModify.assert_not_called()
        self.svc["drive"].files().update.assert_not_called()
        self.assertFalse(self.state_file.exists())

    def test_missing_task_or_deleted_event_prevents_quick_reset(self):
        self.svc["tasks"].tasks().list.return_value.execute.return_value = {"items": []}
        with self.assertRaisesRegex(RuntimeError, "Google Tasks"):
            modes.preflight(self.context, self.svc, self.state, full_reset=False)
        self.svc["tasks"].tasks().list.return_value.execute.return_value = {"items": self.state["tasks"]}
        self.svc["calendar"].events().list.return_value.execute.return_value = {}
        self.svc["calendar"].events().get.return_value.execute.return_value = {"status": "cancelled"}
        with self.assertRaisesRegex(RuntimeError, "calendar events"):
            modes.preflight(self.context, self.svc, self.state, full_reset=False)

    def test_quick_reset_rejects_week_change_or_incomplete_prior_reset(self):
        with self.assertRaisesRegex(RuntimeError, "another workweek"):
            modes.reset_in_place(self.context, self.state, date(2026, 10, 12))
        self.state["reset_incomplete"] = True
        with self.assertRaisesRegex(RuntimeError, "interrupted reset"):
            modes.preflight(self.context, self.svc, self.state, full_reset=False)

    def test_saved_stale_email_or_task_link_requires_full_reset(self):
        folder = self.root / "CoS_Workspace/DailyBriefs"
        folder.mkdir(parents=True)
        brief = folder / "2026-10-06.md"
        for url in ("https://mail.google.com/mail/u/0/#all/stale", "https://tasks.google.com/task/stale?sa=6"):
            brief.write_text(f"[Source]({url})")
            with self.assertRaisesRegex(RuntimeError, "saved daily brief"):
                modes.validate_saved_brief(self.root, self.state)
            self.assertTrue(brief.exists())
        brief.write_text("[Current](https://mail.google.com/mail/u/0/#all/0)")
        modes.validate_saved_brief(self.root, self.state)

    def test_mail_labels_restored_without_message_recreation(self):
        modes.restore_mail_labels(self.context, self.svc, self.state)
        bodies = [c.kwargs["body"] for c in self.svc["gmail"].users().messages().batchModify.call_args_list]
        self.assertEqual(set(sum([b["ids"] for b in bodies], [])), {m["id"] for m in self.state["emails"]})
        self.assertTrue(all("INBOX" in b["addLabelIds"] and "UNREAD" in b["addLabelIds"] for b in bodies))
        self.svc["gmail"].users().messages().batchDelete.assert_not_called()
        self.svc["gmail"].users().messages().import_.assert_not_called()

    def test_stale_import_id_recovered_by_exact_rfc_header(self):
        rfc = f"<{seed.MARKER}-{'a' * 32}-1@demo.invalid>"
        state = {"emails": [{"id": "stale", "rfc_message_id": rfc}]}
        self.context.execute_batched.return_value = None
        self.context.execute_batched.side_effect = lambda *a: [{"id": "canonical", "threadId": "thread", "payload": {"headers": [{"name": "Message-ID", "value": rfc}]}}]
        modes.reconcile_email_ids(self.context, self.svc["gmail"], state, {"canonical"})
        self.assertEqual(state["emails"][0]["id"], "canonical")
        self.assertEqual(state["emails"][0]["url"], "https://mail.google.com/mail/u/0/#all/thread")
        self.svc["gmail"].users().messages().import_.assert_not_called()
        self.svc["gmail"].users().messages().batchDelete.assert_not_called()

    def test_rfc_recovery_rejects_wrong_run_or_ambiguous_match(self):
        rfc = f"<{seed.MARKER}-{'a' * 32}-1@demo.invalid>"
        message = {"id": "canonical", "threadId": "thread", "payload": {"headers": [{"name": "Message-ID", "value": rfc}]}}
        for results in ([], [message, message]):
            state = {"emails": [{"id": "stale", "rfc_message_id": rfc}]}
            self.context.execute_batched.side_effect = None
            self.context.execute_batched.return_value = results
            with self.assertRaisesRegex(RuntimeError, "missing or ambiguous"):
                modes.reconcile_email_ids(self.context, self.svc["gmail"], state, {"canonical", "unrelated"})
            self.assertEqual(state["emails"][0]["id"], "stale")

    def test_legacy_rfc_recovery_verifies_run_and_ordinal(self):
        run = "a" * 32
        state = {"emails": [{"id": "anchor"}, {"id": "stale"}]}
        self.svc["gmail"].users().messages().get.return_value.execute.return_value = {"payload": {"headers": [{"name": "Message-ID", "value": f"<{seed.MARKER}-{run}-1@demo.invalid>"}]}}
        self.context.execute_batched.side_effect = None
        self.context.execute_batched.return_value = [{"id": "canonical", "threadId": "thread", "payload": {"headers": [{"name": "Message-ID", "value": f"<{seed.MARKER}-{run}-2@demo.invalid>"}]}}]
        modes.reconcile_email_ids(self.context, self.svc["gmail"], state, {"anchor", "canonical"})
        self.assertEqual(state["emails"][1]["id"], "canonical")

    def test_calendar_restores_edited_event_using_same_id(self):
        self.context.execute_batched.side_effect = lambda api, requests, **kw: [{"id": "event", "htmlLink": "event-url"} for _ in requests]
        modes.restore_calendar(self.context, self.svc, self.state, {"event": {"summary": "Changed"}}, date(2026, 10, 5), full_reset=False)
        self.svc["calendar"].events().update.assert_called_once_with(calendarId="primary", eventId="event", body={"summary": "Review"}, sendUpdates="none")
        self.svc["calendar"].events().insert.assert_not_called()
        self.assertEqual(self.state["events"][0]["id"], "event")

    def test_unchanged_calendar_skips_writes(self):
        modes.restore_calendar(self.context, self.svc, self.state, {"event": {"summary": "Review"}}, date(2026, 10, 5), full_reset=False)
        self.svc["calendar"].events().update.assert_not_called()
        self.svc["calendar"].events().insert.assert_not_called()

    def test_full_calendar_reuses_ids_and_recreates_missing_events(self):
        desired = [{"seed_key": "Review#1", "baseline": {"summary": "Review", "description": "new date"}},
                   {"seed_key": "New#1", "baseline": {"summary": "New"}}]
        self.context.execute_batched.side_effect = [[{"id": "event"}, {"id": "new-event"}], []]
        with patch.object(modes, "calendar_baseline", return_value=desired):
            modes.restore_calendar(self.context, self.svc, self.state, {"event": {"summary": "Review"}}, date(2026, 10, 12), full_reset=True)
        self.assertEqual([e["id"] for e in self.state["events"]], ["event", "new-event"])
        self.svc["calendar"].events().update.assert_called_once()
        self.svc["calendar"].events().insert.assert_called_once()

    def test_legacy_calendar_uses_original_email_date_not_today(self):
        self.state["events"] = [{"id": "event"}]
        self.svc["gmail"].users().messages().get.return_value.execute.return_value = {"internalDate": str(int(datetime(2026, 10, 5, 8, tzinfo=ZoneInfo(seed.TZ_NAME)).timestamp() * 1000))}
        with patch.object(modes, "calendar_baseline", return_value=[{"seed_key": "Review#1", "baseline": {"summary": "Review"}}]) as baseline:
            modes.preflight(self.context, self.svc, self.state, full_reset=False)
        self.assertEqual(baseline.call_args.args[-1], date(2026, 10, 5))
        self.assertEqual(self.state["events"][0]["id"], "event")

    def test_only_demo_drafts_deleted(self):
        self.svc["gmail"].users().drafts().list.return_value.execute.return_value = {"drafts": [{"id": "demo"}, {"id": "personal"}]}
        self.context.execute_batched.side_effect = [[
            {"message": {"payload": {"headers": [{"name": "Subject", "value": "Re: NeoAgent V2"}]}}},
            {"message": {"payload": {"headers": [{"name": "Subject", "value": "Family dinner"}]}}},
        ], []]
        modes.clear_demo_drafts(self.context, self.svc["gmail"])
        self.svc["gmail"].users().drafts().delete.assert_called_once_with(userId="me", id="demo")

    def test_quick_orchestration_preserves_ids_and_tasks(self):
        original = copy.deepcopy(self.state)
        for name in ("reset_deck_baseline", "reset_sheet_baseline", "reset_original_sheet", "clear_seeded_tasks", "create_tasks", "create_emails", "clear_evidence_cache"):
            setattr(self.context, name, Mock())
        self.context.deck_template_hash = lambda: "hash"
        self.context.task_scenario = SimpleNamespace(RESOURCES=seed.task_scenario.RESOURCES, TASKS=seed.task_scenario.TASKS, ensure_resources=Mock())
        with patch.object(modes, "restore_calendar"), patch("googleapiclient.http.MediaFileUpload"):
            result = modes.reset_in_place(self.context, self.state, date(2026, 10, 5))
        self.context.clear_seeded_tasks.assert_not_called()
        self.context.create_tasks.assert_not_called()
        self.context.create_emails.assert_not_called()
        self.context.clear_evidence_cache.assert_not_called()
        self.assertEqual(original["tasks"], result["tasks"])
        self.assertTrue(all(not change["added"] and not change["removed"] for change in result["last_reset"]["changed_ids"].values()))
        self.assertTrue(json.loads(self.state_file.read_text())["reset_incomplete"])  # cleared only after local restore succeeds

    def test_full_reset_invalidates_brief_before_id_changes(self):
        order = []
        self.context.clear_evidence_cache = Mock(side_effect=lambda *a, **kw: order.append("clear brief"))
        self.context.deck_template_hash = lambda: "hash"
        self.context.reset_deck_baseline = Mock(side_effect=RuntimeError("simulated later failure"))
        with self.assertRaisesRegex(RuntimeError, "simulated later failure"):
            modes.reset_in_place(self.context, self.state, date(2026, 10, 5), full_reset=True)
        self.assertEqual(order, ["clear brief"])
        self.context.clear_evidence_cache.assert_called_once_with(self.root, preserve_latest_brief=False)
        self.assertTrue(json.loads(self.state_file.read_text())["reset_incomplete"])

    def test_full_reset_recreates_mail_tasks_and_reports_changed_ids(self):
        old = copy.deepcopy(self.state)
        for name in ("reset_deck_baseline", "reset_sheet_baseline", "reset_original_sheet", "clear_seeded_tasks", "clear_evidence_cache"):
            setattr(self.context, name, Mock())
        self.context.deck_template_hash = lambda: "hash"
        self.context.task_scenario = SimpleNamespace(ensure_resources=Mock())
        self.context.seeded_gmail_message_ids = Mock(return_value={"orphan"})
        self.context.create_emails = Mock(return_value=([{"id": "new-mail", "url": "new-mail-url"}], {"elena": "new-mail-url"}))
        self.context.create_tasks = Mock(side_effect=lambda api, state, evidence: state.update(tasks=[{"id": "new-task"}]))
        with patch.object(modes, "restore_calendar"), patch("googleapiclient.http.MediaFileUpload"):
            result = modes.reset_in_place(self.context, self.state, date(2026, 10, 12), full_reset=True)
        self.context.clear_seeded_tasks.assert_called_once()
        self.context.create_emails.assert_called_once()
        self.context.create_tasks.assert_called_once()
        self.assertEqual(result["events"], old["events"])
        self.assertEqual(result["week_of"], "2026-10-12")
        self.assertEqual(result["last_reset"]["changed_ids"]["emails"]["added"], ["new-mail"])
        self.assertEqual(result["last_reset"]["changed_ids"]["tasks"]["added"], ["new-task"])
        self.assertIn("orphan", self.svc["gmail"].users().messages().batchDelete.call_args.kwargs["body"]["ids"])

    def test_calendar_duplicate_summary_keys_are_distinct_and_stable(self):
        result = modes.calendar_baseline(self.context, self.state, date(2026, 10, 5), date(2026, 10, 6))
        self.assertEqual(len(result), len({item["seed_key"] for item in result}))
        again = modes.calendar_baseline(self.context, self.state, date(2026, 10, 12), date(2026, 10, 13))
        self.assertEqual([item["seed_key"] for item in result], [item["seed_key"] for item in again])

    def test_all_google_links_in_real_baseline_have_explicit_bindings(self):
        import re
        from zipfile import ZipFile
        templates = Path(__file__).parent / "templates"
        bindings = json.loads((templates / "second-brain-links.json").read_text())
        with ZipFile(templates / "CoS_SecondBrain.zip") as archive:
            for name in archive.namelist():
                if name.endswith(".md"):
                    text = archive.read(name).decode("utf-8")
                    links = re.findall(r'https://(?:mail|docs|drive|calendar|tasks)\.google\.com/[^\s)\]"<>]+', text)
                    self.assertTrue(set(links) <= bindings.keys(), (name, links))

    def test_full_cleanup_removes_saved_briefs_quick_preserves_latest(self):
        folder = self.root / "CoS_Workspace/DailyBriefs"
        folder.mkdir(parents=True)
        brief = folder / "2026-10-06.md"
        brief.write_text("brief")
        clear_evidence_cache(self.root)
        self.assertTrue(brief.exists())
        clear_evidence_cache(self.root, preserve_latest_brief=False)
        self.assertFalse(folder.exists())

    def test_baseline_links_use_current_ids_without_altering_other_text(self):
        demo = self.root / "demo"
        (demo / "templates").mkdir(parents=True)
        vault = self.root / "vault"
        vault.mkdir()
        (demo / "templates/second-brain-links.json").write_text(json.dumps({"https://old/email": ["email", "leah_ramp_up"], "https://old/doc": ["task_resources", "notes_overview"]}))
        note = vault / "note.md"
        note.write_text('[Leah](https://old/email) [Doc](https://old/doc)\n[[Other note]] and https://example.com')
        self.assertEqual(refresh_links(vault, demo, self.state), 2)
        self.assertIn("#all/leah_ramp_up", note.read_text())
        self.assertIn(self.state["task_resources"]["notes_overview"]["url"], note.read_text())
        self.assertIn("[[Other note]] and https://example.com", note.read_text())
        self.assertEqual(refresh_links(vault, demo, self.state), 0)


if __name__ == "__main__":
    unittest.main()
