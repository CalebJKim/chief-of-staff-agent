import importlib.util
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch


script_dir = Path(__file__).resolve().parents[2] / "chief-of-staff" / "scripts"
sys.path.insert(0, str(script_dir))
spec = importlib.util.spec_from_file_location("tracker_read_actions", script_dir / "actions.py")
actions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(actions)


class TrackerReadTests(unittest.TestCase):
    def read(self, values):
        api = Mock()
        get = api.spreadsheets.return_value.values.return_value.get
        get.return_value.execute.return_value = {"range": "'Delivery'!A1:J80", "values": values}
        output = io.StringIO()
        args = actions.build_parser().parse_args(["sheets", "get", "test-sheet"])
        with patch.object(actions, "service", return_value=api), redirect_stdout(output):
            args.func(args)
        self.assertEqual([call[0] for call in api.mock_calls if call[0].endswith("execute")], [
            "spreadsheets().values().get().execute",
        ])
        return json.loads(output.getvalue()), output.getvalue()

    def test_lane_scope_empty_blockers_and_links_survive_read(self):
        context = [["Delivery tracker"], [], ["Status guide: Complete means the deliverable is done."]]
        result, text = self.read(context + [
            ["Lane", "PIC", "Status", "Latest update", "Next action", "Due", "Dependency / blocker", "Evidence", "Artifact", "Notes"],
            ["Research approval", "Alex", "Awaiting update", "Approval pending", "Obtain approval", "2026-10-05", "", "mail-link", "doc-link", "Implementation is tracked separately."],
            ["Implementation", "Sam", "Blocked", "Access pending", "Obtain access", "", "Access is not available."],
        ])
        self.assertEqual(result["context"], context)
        self.assertEqual(result["lanes"], [
            {"lane": "Research approval", "owner": "Alex", "status": "Awaiting update", "latest": "Approval pending", "next": "Obtain approval", "due": "2026-10-05", "blocker": "", "evidence": "mail-link", "artifact": "doc-link", "notes": "Implementation is tracked separately."},
            {"lane": "Implementation", "owner": "Sam", "status": "Blocked", "latest": "Access pending", "next": "Obtain access", "due": "", "blocker": "Access is not available.", "evidence": "", "artifact": "", "notes": ""},
        ])
        self.assertEqual(result["range"], "'Delivery'!A1:J80")
        self.assertNotIn("values", result)
        self.assertGreater(text.count("\n"), 10)

    def test_reordered_headers_and_extra_columns_keep_their_values(self):
        result, _ = self.read([
            ["Notes", "STATUS", "Lane", "Cost", "PIC"],
            ["Ready for review", "On track", "Design", 0, "Lee"],
        ])
        self.assertEqual(result["lanes"], [{
            "notes": "Ready for review", "status": "On track", "lane": "Design", "cost": 0, "owner": "Lee",
        }])

    def test_ambiguous_or_missing_headers_preserve_raw_values(self):
        cases = [
            [["Metric", "Value"], ["Latency", 30]],
            [["Lane", "Status", "Status"], ["Design", "On track", "Draft"]],
            [["Lane", "Status", ""], ["Design", "On track", "Unlabeled value"]],
            [["Lane", "Status"], ["Design", "On track", "Extra value"]],
            [],
        ]
        for values in cases:
            with self.subTest(values=values):
                result, _ = self.read(values)
                self.assertEqual(result["values"], values)
                self.assertNotIn("lanes", result)


if __name__ == "__main__":
    unittest.main()
