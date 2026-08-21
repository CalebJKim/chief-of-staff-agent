from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("seed_workspace", ROOT / "demo" / "seed_workspace.py")
assert SPEC and SPEC.loader
seed_workspace = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(seed_workspace)


class SeedWorkspaceTests(unittest.TestCase):
    def test_campaign_lanes_match_tracker_row_contract(self) -> None:
        sheets = Mock()
        drive = Mock()
        sheets.spreadsheets().create.return_value.execute.return_value = {
            "spreadsheetId": "sheet-1",
            "sheets": [{"properties": {"sheetId": 123}}],
        }
        drive.files().get.return_value.execute.return_value = {"parents": []}

        result = seed_workspace.create_sheet(
            sheets,
            drive,
            "folder-1",
            "https://example.test/slides",
            "https://example.test/doc",
        )

        self.assertEqual("sheet-1", result["id"])
        update = sheets.spreadsheets().values().update.call_args.kwargs
        self.assertEqual("'Campaign Lanes'!A1:J14", update["range"])
        self.assertEqual(14, len(update["body"]["values"]))
        validation_request = next(
            request["setDataValidation"]
            for request in sheets.spreadsheets().batchUpdate.call_args.kwargs["body"]["requests"]
            if "setDataValidation" in request
        )
        validation = validation_request["range"]
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
        drive.files().update.assert_called_once_with(
            fileId="sheet-1",
            addParents="folder-1",
            removeParents="",
            fields="id,parents",
        )


if __name__ == "__main__":
    unittest.main()
