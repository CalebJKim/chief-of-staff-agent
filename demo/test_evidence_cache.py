"""Evidence cleanup tests use disposable workspaces, never live demo data."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parent))
from evidence_cache import check_evidence_cache, clear_evidence_cache


class EvidenceCacheTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.workspace = self.root / "CoS_Workspace"
        self.state = self.workspace / ".chief-of-staff-state"
        self.state.mkdir(parents=True)

    def write(self, path, text="saved evidence"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_clears_current_and_legacy_cache_but_preserves_other_files(self):
        runs = [self.state / "chief-of-staff" / ("daily-brief-" + "a" * 32),
                self.state / "daily-brief-f0zd281p"]
        for run in runs:
            self.write(run / "packet.json")
            self.write(run / "snapshot.json")
        incomplete = self.state / "chief-of-staff" / ("daily-brief-" + "b" * 32)
        incomplete.mkdir()
        standalone = [self.state / "snapshot.json",
                      self.state / "chief-of-staff/snapshot.json",
                      self.state / "chief-of-staff/packet.json"]
        for path in standalone:
            self.write(path)
        preserved = [self.state / name for name in (
            "google_token.json", "google_client_secret.json", "second-brain.json",
            "chief-of-staff-workspace-state.json", "other.json")]
        preserved += [self.workspace / "CoS_SecondBrain/index.md",
                      self.workspace / "my-report.md",
                      self.workspace / "snapshot.json",
                      self.state / "chief-of-staff/daily-brief-notes/notes.md",
                      self.root / "checkpoints/checkpoint-4/packet.json"]
        before = {path: self.write(path, "keep this").read_bytes() for path in preserved}

        result = clear_evidence_cache(self.root)

        self.assertEqual(result, {"run_folders_removed": 3, "files_removed": 7})
        self.assertTrue(all(not path.exists() for path in [*runs, incomplete, *standalone]))
        self.assertEqual(before, {path: path.read_bytes() for path in preserved})
        self.assertEqual(clear_evidence_cache(self.root),
                         {"run_folders_removed": 0, "files_removed": 0})

    def test_preflight_does_not_delete_or_create_files(self):
        packet = self.write(self.state / "chief-of-staff" / ("daily-brief-" + "c" * 32) / "packet.json")
        before = {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        check_evidence_cache(self.root)
        self.assertEqual(before, {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()})
        self.assertTrue(packet.exists())
        absent = self.root / "unused-checkout"
        self.assertEqual(clear_evidence_cache(absent),
                         {"run_folders_removed": 0, "files_removed": 0})
        self.assertFalse(absent.exists())

    def link_directory(self, link, target):
        link.parent.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            shell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
            quote = lambda path: "'" + str(path).replace("'", "''") + "'"
            result = subprocess.run(
                [str(shell), "-NoProfile", "-NonInteractive", "-Command",
                 f"$ErrorActionPreference='Stop'; New-Item -ItemType Junction -Path {quote(link)} -Target {quote(target)} | Out-Null"],
                capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            link.symlink_to(target, target_is_directory=True)

    def test_refuses_linked_cache_root(self):
        outside = self.root / "another-workspace"
        evidence = self.write(outside / "snapshot.json", "do not delete")
        self.link_directory(self.state / "chief-of-staff", outside)
        with self.assertRaisesRegex(RuntimeError, "linked path"):
            clear_evidence_cache(self.root)
        self.assertEqual(evidence.read_text(), "do not delete")

    def test_nested_link_aborts_before_deleting_any_cache(self):
        first = self.write(self.state / "chief-of-staff" / ("daily-brief-" + "1" * 32) / "packet.json")
        outside = self.root / "another-workspace"
        evidence = self.write(outside / "snapshot.json", "do not delete")
        self.link_directory(self.state / "chief-of-staff" / ("daily-brief-" + "2" * 32) / "linked", outside)
        with self.assertRaisesRegex(RuntimeError, "linked path"):
            clear_evidence_cache(self.root)
        self.assertTrue(first.exists())
        self.assertEqual(evidence.read_text(), "do not delete")


if __name__ == "__main__":
    unittest.main()
