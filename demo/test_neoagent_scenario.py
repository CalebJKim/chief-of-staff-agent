import json
import re
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent

class NeoAgentScenarioTests(unittest.TestCase):
    def test_active_assets_have_no_retired_brand_or_hardware_claims(self):
        retired = re.compile(r"RTX[ -]?Spark|rtx-spark|Blackwell|FP4|6,144|petaflop", re.I)
        for p in (ROOT / "CoS_SecondBrain").rglob("*.md"):
            self.assertIsNone(retired.search(p.name + p.read_text(encoding="utf-8")), str(p))
        for p in (ROOT / "templates").iterdir():
            if p.suffix not in (".zip", ".docx", ".xlsx", ".pptx"):
                continue
            self.assertIsNone(retired.search(p.name), str(p))
            with zipfile.ZipFile(p) as archive:
                for name in archive.namelist():
                    if Path(name).suffix in (".xml", ".rels", ".md"):
                        self.assertIsNone(retired.search(name + archive.read(name).decode("utf-8")), (p.name, name))

    def test_comparison_and_pending_edits_are_distinct(self):
        deck = json.loads((ROOT / "neoagent_deck.json").read_text(encoding="utf-8"))
        self.assertEqual(10, len(deck))
        self.assertIn("Performance results to go here", deck[3]["body"])
        self.assertIn("local product catalog", deck[5]["body"])
        self.assertIn("still to be summarized", deck[6]["body"])
        self.assertIn("No selection is approved yet", deck[6]["body"])
        evidence = (ROOT / "CoS_SecondBrain/concepts/performance-results.md").read_text(encoding="utf-8")
        for phrase in ("80% (160/200)", "92% (184/200)", "+12 percentage points", "30% lower", "25% fewer", "same underlying model", "same 200", "same execution environment", "fictional", "leadership review only"):
            self.assertIn(phrase, evidence)

if __name__ == "__main__":
    unittest.main()
