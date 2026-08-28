import sys
import unittest
from pathlib import Path
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "demo"))
from baseline import PRE_EMAIL_ROWS, reset_sheet_baseline


class SeedWorkspaceTests(unittest.TestCase):
    def test_campaign_lanes_match_tracker_row_contract(self) -> None:
        sheets = Mock()
        state = {
            "sheet": {"id": "sheet-1", "url": "sheet-url"},
            "slides": {"url": "deck-url"},
            "doc": {"url": "doc-url"},
        }
        evidence = {"priya": "priya-url", "aisha": "aisha-url"}

        reset_sheet_baseline(sheets, state, evidence, "2026-08-28")

        self.assertEqual(
            8,
            len(PRE_EMAIL_ROWS),
        )
        self.assertEqual(
            ["'Campaign Lanes'!A7:J14", "'Campaign Lanes'!A3:J3"],
            [item["range"] for item in sheets.spreadsheets().values().batchUpdate.call_args.kwargs["body"]["data"]],
        )


if __name__ == "__main__":
    unittest.main()
