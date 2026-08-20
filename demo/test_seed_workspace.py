import importlib.util
import unittest
from pathlib import Path

MODULE = Path(__file__).with_name("seed_workspace.py")
spec = importlib.util.spec_from_file_location("workspace_seed", MODULE)
seed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed)

class WorkspaceSeedTests(unittest.TestCase):
    def test_reference_names_and_no_demo_labels(self):
        source = MODULE.read_text(encoding="utf-8")
        self.assertIn("RTX Spark Campaign Tracker", source)
        self.assertIn("RTX Spark Campaign Plan", source)
        self.assertIn("RTX Spark Exec Review", source)
        self.assertNotIn("Public Demo", source)
        self.assertNotIn("August", source)
        self.assertNotIn("Caleb", source)

    def test_pre_email_tracker_baseline(self):
        rows = seed.tracker_rows("deck", "doc", "sheet", {})
        by_lane = {row[0]: row for row in rows[1:]}
        for lane in ("Product performance claims", "Exec Review deck", "Agent Messaging", "Legal intake LGL-2026-0847"):
            self.assertEqual(by_lane[lane][2], "Awaiting update")
        self.assertIn("still pending", by_lane["Product performance claims"][3])
        self.assertNotIn("2.1", by_lane["Product performance claims"][3])
        self.assertEqual(by_lane["Marketing shoot"][2], "Blocked")
        self.assertEqual(by_lane["Retail demo readiness"][2], "Blocked")

    def test_deck_and_calendar_shape(self):
        self.assertEqual(len(seed.SLIDES), 10)
        self.assertIn("Mike Chen to provide", seed.SLIDES[3][1])
        self.assertEqual(seed.SLIDES[5][0], "Move the detail out of the live flow")
        self.assertEqual(len(seed.EVENTS), 16)
        self.assertTrue(any(x[2].startswith("RTX Spark Exec Review") for x in seed.EVENTS))

if __name__ == "__main__":
    unittest.main()
