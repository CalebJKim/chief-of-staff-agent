import importlib.util
import sys
import unittest
import zipfile
from pathlib import Path

MODULE = Path(__file__).with_name("seed_workspace.py")
sys.path.insert(0, str(Path(__file__).parent))
spec = importlib.util.spec_from_file_location("workspace_seed", MODULE)
seed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed)

class WorkspaceSeedTests(unittest.TestCase):
    def test_reference_names_and_no_private_labels(self):
        source = MODULE.read_text(encoding="utf-8")
        self.assertIn("RTX Spark Campaign Tracker", source)
        self.assertIn("RTX Spark Campaign Plan", source)
        self.assertIn("RTX Spark Exec Review", source)
        self.assertNotIn("Public Demo", source)
        self.assertNotIn("August", source)

    def test_exact_templates_are_present_and_valid(self):
        templates = Path(__file__).with_name("templates")
        expected = {
            "rtx-spark-campaign-tracker.xlsx": "xl/workbook.xml",
            "rtx-spark-exec-review.pptx": "ppt/presentation.xml",
            "rtx-spark-campaign-plan.docx": "word/document.xml",
        }
        for filename, member in expected.items():
            path = templates / filename
            self.assertTrue(path.exists(), filename)
            with zipfile.ZipFile(path) as archive:
                self.assertIn(member, archive.namelist())

    def test_reference_email_and_calendar_shape(self):
        self.assertEqual(len(seed.EVENTS), 16)
        self.assertTrue(any(x[2].startswith("RTX Spark Exec Review") for x in seed.EVENTS))
        self.assertIn("Mike Chen", MODULE.read_text(encoding="utf-8"))
        self.assertIn("2.1x faster", MODULE.read_text(encoding="utf-8"))

if __name__ == "__main__":
    unittest.main()
