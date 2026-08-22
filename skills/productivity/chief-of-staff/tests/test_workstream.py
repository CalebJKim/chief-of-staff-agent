from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("cos_workstream", ROOT / "scripts" / "workstream.py")
assert SPEC and SPEC.loader
workstream = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(workstream)


class WorkstreamTests(unittest.TestCase):
    def test_execute_dispatches_exact_steps_and_confirmation_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            helper = home / "skills" / "productivity" / "ingest" / "scripts" / "actions.py"
            helper.parent.mkdir(parents=True)
            helper.write_text(
                "import json, sys\nprint(json.dumps({'verified': True, 'url': 'https://example.test', 'argv': sys.argv[1:]}))\n",
                encoding="utf-8",
            )
            (home / "chief-of-staff-workspace-state.json").touch()
            plan_path = home / "chief-of-staff" / "action-plan.json"
            plan_path.parent.mkdir()
            plan_path.write_text(
                json.dumps({
                    "workstreams": [{
                        "outcome": "Demo work",
                        "target": {"label": "Tracker", "url": "https://tracker.example.test"},
                        "action": {
                            "kind": "test",
                            "steps": [
                                ["sheets", "update-lanes", "sheet-1", "--lane", "Demo", "--status", "Ready for review"],
                                ["gmail", "draft", "--reply-to-message", "message-1", "--body", "Done"],
                            ],
                        },
                    }],
                }),
                encoding="utf-8",
            )

            result = workstream.execute(1, plan_path, home, True)

            self.assertTrue(result["verified"])
            self.assertEqual(["https://example.test", "https://tracker.example.test"], result["urls"])
            self.assertIn("--confirm", result["results"][0]["argv"])
            self.assertIn("--track-demo-state", result["results"][1]["argv"])
            self.assertNotIn("--confirm", result["results"][1]["argv"])


if __name__ == "__main__":
    unittest.main()
