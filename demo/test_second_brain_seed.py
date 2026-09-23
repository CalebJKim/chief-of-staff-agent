"""Local reset tests: temporary vaults only; no live Google requests."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).parent))
import seed_workspace as seed
from second_brain_seed import check_reset, reset_second_brain


class SecondBrainResetTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.profile = self.root / "profile"
        self.profile.mkdir()
        self.vault = self.root / "demo" / "CoS_SecondBrain"
        self.vault.mkdir(parents=True)
        self.archive = self.root / "demo" / "templates" / "CoS_SecondBrain.zip"
        self.archive.parent.mkdir()
        self.baseline = {"index.md": b"# Index\n", "projects/project.md": b"Original facts\n"}
        with ZipFile(self.archive, "w") as archive:
            for name, content in self.baseline.items():
                archive.writestr(name, content)
        self.state = {"week_of": "2026-09-21", "folder": {}, "sheet": {}, "doc": {},
                      "slides": {}, "emails": [], "events": [], "tasks": []}
        self.state_path = self.profile / "state.json"
        self.state_path.write_text(json.dumps(self.state))

    def assert_baseline(self):
        for name, content in self.baseline.items():
            self.assertEqual(content, (self.vault / name).read_bytes())

    def test_restores_changed_missing_notes_and_backs_up_extra_files(self):
        (self.vault / "index.md").write_text("Changed facts")
        (self.vault / "job-note.md").write_text("New note")
        settings = self.vault / ".obsidian"
        settings.mkdir()
        (settings / "workspace.json").write_text('{"local": true}')
        personal = self.root / "personal"
        personal.mkdir()
        (personal / "note.md").write_text("Personal note")
        (self.profile / "second-brain.json").write_text(json.dumps({"vault_path": str(personal)}))
        connection_before = (self.profile / "second-brain.json").read_bytes()

        result = reset_second_brain(self.root, self.profile)

        self.assert_baseline()
        self.assertFalse((self.vault / "job-note.md").exists())
        backup = Path(result["backup"])
        self.assertEqual("Changed facts", (backup / "index.md").read_text())
        self.assertEqual("New note", (backup / "job-note.md").read_text())
        self.assertEqual('{"local": true}', (settings / "workspace.json").read_text())
        self.assertEqual("Personal note", (personal / "note.md").read_text())
        self.assertEqual(connection_before, (self.profile / "second-brain.json").read_bytes())
        again = reset_second_brain(self.root, self.profile)
        self.assert_baseline()
        self.assertNotEqual(result["backup"], again["backup"])

    def test_recreates_missing_vault(self):
        self.vault.rmdir()
        result = reset_second_brain(self.root, self.profile)
        self.assertIsNone(result["backup"])
        self.assert_baseline()

    def test_rejects_unsafe_or_nonportable_baselines_without_changing_notes(self):
        for name in ("../escape.md", "/absolute.md", "C:/escape.md", "..\\escape.md", ".obsidian/workspace.json"):
            with self.subTest(name=name):
                with ZipFile(self.archive, "w") as archive:
                    archive.writestr("index.md", "Original")
                    archive.writestr(name, "Unsafe")
                with self.assertRaises(RuntimeError):
                    reset_second_brain(self.root, self.profile)
                self.assertEqual([], list(self.vault.iterdir()))
                self.assertFalse((self.root / "demo" / ".second-brain-backups").exists())

    def test_rejects_linked_vault(self):
        original = Path.resolve
        def resolve(path, *args, **kwargs):
            return self.root / "personal" if path == self.vault else original(path, *args, **kwargs)
        with patch.object(Path, "resolve", resolve):
            with self.assertRaisesRegex(RuntimeError, "linked path"):
                check_reset(self.root, self.profile)

    def run_reset(self, arguments=None, failure=None):
        with patch.object(seed, "ROOT", self.root), patch.object(seed, "hermes_home", return_value=self.profile), \
             patch.object(seed, "state_path", return_value=self.state_path), \
             patch.object(seed, "reset_in_place", return_value=self.state, side_effect=failure) as google_reset, \
             patch.object(sys, "argv", ["seed_workspace.py", *(arguments or ["--reset", "--confirm"])]), \
             patch("builtins.print"):
            try:
                result = seed.main()
            finally:
                self.google_reset_calls = google_reset.call_count
        return result

    def test_same_confirmed_reset_runs_google_and_local_reset(self):
        (self.vault / "index.md").write_text("Changed")
        self.assertEqual(0, self.run_reset())
        self.assertEqual(1, self.google_reset_calls)
        self.assert_baseline()

    def test_confirmation_still_required(self):
        with self.assertRaisesRegex(SystemExit, "without --confirm"):
            self.run_reset(["--reset"])
        self.assertEqual(0, self.google_reset_calls)
        self.assertEqual([], list(self.vault.iterdir()))

    def test_running_job_prevents_both_resets(self):
        cron = self.profile / "cron"
        cron.mkdir()
        (cron / "jobs.json").write_text(json.dumps({"jobs": [{"fire_claim": {"run": "active"}}]}))
        with self.assertRaisesRegex(RuntimeError, "cron job is running"):
            self.run_reset()
        self.assertEqual(0, self.google_reset_calls)
        self.assertEqual([], list(self.vault.iterdir()))

    def test_bad_baseline_prevents_google_reset(self):
        self.archive.unlink()
        with self.assertRaises(FileNotFoundError):
            self.run_reset()
        self.assertEqual(0, self.google_reset_calls)

    def test_google_failure_leaves_local_notes_untouched(self):
        (self.vault / "index.md").write_text("Keep my notes")
        with self.assertRaisesRegex(RuntimeError, "Google unavailable"):
            self.run_reset(failure=RuntimeError("Google unavailable"))
        self.assertEqual("Keep my notes", (self.vault / "index.md").read_text())
        self.assertFalse((self.root / "demo" / ".second-brain-backups").exists())

    def test_bundled_archive_is_valid_and_excludes_settings(self):
        # Test the reset source independently of mutable working notes.
        root = Path(__file__).resolve().parents[1]
        check_reset(root, self.profile)
        with ZipFile(root / "demo" / "templates" / "CoS_SecondBrain.zip") as archive:
            names = [item.filename for item in archive.infolist() if not item.is_dir()]
            self.assertIn("index.md", names)
            self.assertTrue(all(not name.startswith(".obsidian/") for name in names))


if __name__ == "__main__":
    unittest.main()
