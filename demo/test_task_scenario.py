import json
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from xml.etree import ElementTree
from zipfile import ZipFile
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent))
import seed_workspace as seed
import task_scenario as scenario


class TaskScenarioTests(unittest.TestCase):
    def resources(self):
        return {key: {"id": key, "url": f"https://drive.google.com/{key}"} for key in scenario.RESOURCES}

    def test_relative_dates_and_decision_stays_open(self):
        resources = self.resources()
        for today in (date(2026, 9, 30), date(2026, 12, 29)):
            mail = scenario.email_specs(resources, today)
            bodies = list(scenario.task_bodies(resources, {t["key"]: "mail-link" for t in scenario.TASKS}, today, seed.MARKER))
            self.assertEqual(3, len(bodies))
            self.assertTrue(all(b["due"] == today.isoformat() + "T00:00:00Z" for b in bodies))
            self.assertTrue(all(len(t["notes"]) <= 240 for t in scenario.TASKS))
            self.assertIn("whether you’d be available", mail[1][2])
            self.assertIn("A yes or no", mail[1][2])
            self.assertIn("your proposed design", mail[2][2])
            self.assertIn("outline today", mail[2][2])
            self.assertNotIn("ETA", mail[2][2])
            self.assertIn("rough design", bodies[2]["title"])
            self.assertIn("tradeoffs", bodies[2]["notes"])
        self.assertIn("Wednesday, September 23, 2026", scenario.email_specs(resources, date(2026, 9, 30))[1][2])

    def test_design_outline_leaves_decisions_open(self):
        with ZipFile(Path(__file__).parent / "templates/local-meeting-notes-overview.docx") as doc:
            root = ElementTree.fromstring(doc.read("word/document.xml"))
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        text = "\n".join("".join(p.itertext()) for p in root.findall("w:body/w:p", ns))
        self.assertNotIn("ETA", text)
        self.assertNotIn("How it works", text)
        self.assertIn("Design Outline", text)
        self.assertEqual(4, text.count("TODO:"))
        self.assertIn("TODO: Diagram of the user experience", text)
        self.assertIn("keeping processing on the device", text)
        self.assertIn("main tradeoffs", text)

    def test_refresh_deletes_only_marked_task_mail_and_preserves_other_state(self):
        state = {"folder": {"id": "folder"}, "slides": {"id": "deck"}, "sheet": {"id": "sheet"},
                 "events": [{"id": "meeting"}], "task_resources": self.resources(),
                 "emails": [{"id": key} for key in ("old-task", "rtx", "personal", "missing")], "tasks": []}
        gmail, drive, tasks = Mock(), Mock(), Mock()
        drive.files().get.return_value.execute.return_value = {"id": "folder", "trashed": False}
        gmail.users().getProfile.return_value.execute.return_value = {"emailAddress": "user@example.com"}
        def meta(subject, marker=True):
            return {"payload": {"headers": [{"name": "Subject", "value": subject}, {"name": "Message-ID", "value": f"<{seed.MARKER}-run-1@demo.invalid>" if marker else "<personal@example.com>"}]}}
        metadata = [meta("Publish a customer demo FAQ"), meta("NeoAgent V2 Exec Review"), meta("Publish a customer demo FAQ", False), None]
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(seed, "state_path", return_value=Path(temp) / "state.json"), \
             patch.object(seed, "services", return_value={"gmail": gmail, "drive": drive, "tasks": tasks}), \
             patch.object(seed, "local_now", return_value=datetime(2026, 9, 30, 12, tzinfo=ZoneInfo(seed.TZ_NAME))), \
             patch.object(scenario, "ensure_resources") as resources, \
             patch.object(scenario, "tracked_mail_metadata", return_value=metadata), \
             patch.object(seed, "mail_import_request") as imported, \
             patch.object(seed, "clear_seeded_tasks") as clear, patch.object(seed, "create_tasks") as create:
            imported.side_effect = [Mock(execute=Mock(return_value={"id": f"new-{i}"})) for i in range(3)]
            scenario.refresh(seed, state)
            saved = json.loads(seed.state_path().read_text())
        gmail.users().messages().batchDelete.assert_called_once_with(userId="me", body={"ids": ["old-task"]})
        gmail.users().drafts.assert_not_called()
        self.assertEqual(["rtx", "personal", "new-0", "new-1", "new-2"], [m["id"] for m in saved["emails"]])
        self.assertEqual({"id": "deck"}, saved["slides"])
        self.assertEqual({"id": "sheet"}, saved["sheet"])
        self.assertEqual([{"id": "meeting"}], saved["events"])
        self.assertNotIn("restore", resources.call_args.kwargs)
        clear.assert_called_once_with(tasks, state)
        self.assertEqual({t["key"] for t in scenario.TASKS}, set(create.call_args.args[2]))

    def test_metadata_ignores_only_not_found(self):
        class Batch:
            def __init__(self, error): self.error = error
            def add(self, request, callback, request_id): self.callback, self.key = callback, request_id
            def execute(self): self.callback(self.key, None, self.error)
        api = Mock()
        for status in (404, 403):
            error = RuntimeError("Google failure")
            error.resp = SimpleNamespace(status=status)
            api.new_batch_http_request.return_value = Batch(error)
            if status == 404:
                self.assertEqual([None], scenario.tracked_mail_metadata(api, [{"id": "gone"}]))
            else:
                with self.assertRaisesRegex(RuntimeError, "Google failure"):
                    scenario.tracked_mail_metadata(api, [{"id": "blocked"}])


if __name__ == "__main__":
    unittest.main()
