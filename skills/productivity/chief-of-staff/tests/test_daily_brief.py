from __future__ import annotations

import contextlib
import copy
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import brief
import daily_brief

FIXTURE = ROOT / "tests/fixtures/workspace.json"


class DailyBriefTests(unittest.TestCase):
    def invoke(self, home):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, {"COS_STATE_DIR": str(home)}), patch.object(
            sys, "argv", ["daily_brief.py", "--fixture", str(FIXTURE)]
        ), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = daily_brief.main()
        return code, stdout.getvalue(), stderr.getvalue()

    def test_fixture_pipeline_runs_each_script_once_and_saves_exact_packet(self):
        with tempfile.TemporaryDirectory() as home, patch.object(
            daily_brief, "run", wraps=daily_brief.run
        ) as run:
            code, output, error = self.invoke(home)
            self.assertEqual(code, 0, error)
            self.assertEqual([call.args[0].name for call in run.call_args_list], ["ingest.py", "brief.py"])
            receipt, encoded = output.splitlines()
            saved = Path(json.loads(receipt)["packet_path"])
            self.assertTrue(saved.is_relative_to(Path(home).resolve()))
            self.assertEqual(saved.read_bytes(), (encoded + "\n").encode("utf-8"))
            self.assertLessEqual(len(encoded), 14000)
            self.assertIn("source_status", json.loads(encoded))

    def test_failed_ingest_does_not_run_brief_retry_or_return_old_packet(self):
        with tempfile.TemporaryDirectory() as home, patch.object(
            daily_brief, "run", side_effect=subprocess.CalledProcessError(1, "ingest.py", stderr="fixture failure")
        ) as run:
            code, output, error = self.invoke(home)
            self.assertEqual(code, 1)
            self.assertEqual(output, "")
            self.assertEqual(json.loads(error)["stage"], "ingest")
            run.assert_called_once()
            self.assertEqual(list(Path(home).rglob("packet.json")), [])

    def test_failed_brief_does_not_retry_or_publish_a_packet(self):
        with tempfile.TemporaryDirectory() as home, patch.object(
            daily_brief, "run", side_effect=["", subprocess.CalledProcessError(1, "brief.py", stderr="fixture failure")]
        ) as run:
            code, output, error = self.invoke(home)
            self.assertEqual(code, 1)
            self.assertEqual(output, "")
            self.assertEqual(json.loads(error)["stage"], "brief")
            self.assertEqual(run.call_count, 2)
            self.assertEqual(list(Path(home).rglob("packet.json")), [])

    def test_final_budget_reduces_background_before_live_work(self):
        packet = {"instruction": "Use this evidence", "mail": [{"id": "manager", "snippet": "Decision due today"}],
                  "tasks": [{"id": "task", "title": "Prepare proposal"}],
                  "focus_blocks": [{"start": "09:30", "end": "10:30"}],
                  "source_status": {"gmail": "ok", "tasks": "ok"}}
        baseline = copy.deepcopy(packet)
        packet["second_brain"] = {"status": "ok", "notes": [
            {"title": f"Background {i}", "excerpt": "Long background context " * 100} for i in range(5)]}
        encoded = brief.fit_packet(packet, 600)
        self.assertLessEqual(len(encoded), 600)
        final = json.loads(encoded)
        for key, value in baseline.items():
            self.assertEqual(final[key], value)
        self.assertTrue(final["second_brain"]["truncated"])

    def test_impossible_budget_fails_instead_of_returning_oversized_json(self):
        with self.assertRaises(ValueError):
            brief.fit_packet({"instruction": "Required instructions" * 100}, 100)


if __name__ == "__main__":
    unittest.main()
