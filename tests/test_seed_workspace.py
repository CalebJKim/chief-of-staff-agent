from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("seed_workspace", ROOT / "demo" / "seed_workspace.py")
assert SPEC and SPEC.loader
seed_workspace = importlib.util.module_from_spec(SPEC)
googleapiclient = types.ModuleType("googleapiclient")
discovery = types.ModuleType("googleapiclient.discovery")
discovery.build = Mock()
googleapiclient.discovery = discovery
with patch.dict(sys.modules, {"googleapiclient": googleapiclient, "googleapiclient.discovery": discovery}):
    SPEC.loader.exec_module(seed_workspace)


class SeedWorkspaceTests(unittest.TestCase):
    def test_campaign_lanes_match_tracker_row_contract(self) -> None:
        api = Mock()
        api.spreadsheets().create.return_value.execute.return_value = {
            "spreadsheetId": "sheet-1",
            "sheets": [{"properties": {"sheetId": 123}}],
        }

        seed_workspace.create_sheet(api)

        update = api.spreadsheets().values().update.call_args.kwargs
        self.assertEqual("Campaign Lanes!A6:J14", update["range"])
        validation = api.spreadsheets().batchUpdate.call_args.kwargs["body"]["requests"][0]["setDataValidation"]["range"]
        self.assertEqual(
            {
                "sheetId": 123,
                "startRowIndex": 6,
                "endRowIndex": 14,
                "startColumnIndex": 2,
                "endColumnIndex": 3,
            },
            validation,
        )


if __name__ == "__main__":
    unittest.main()
