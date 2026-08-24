from __future__ import annotations

import argparse
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "workspace.json"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


brief = load("cos_brief", ROOT / "scripts" / "brief.py")


class BriefTests(unittest.TestCase):
    def args(self, top_n=3):
        return argparse.Namespace(
            max_files=12,
            max_meetings=15,
            max_mail=12,
            top_n=top_n,
            work_start=8,
            work_end=18,
            min_focus_minutes=30,
        )

    def test_packet_contains_bounded_generic_decision_evidence(self):
        snapshot = json.loads(FIXTURE.read_text(encoding="utf-8"))
        packet = brief.build_packet(snapshot, self.args())

        self.assertEqual(1, len(packet["conflicts"]))
        self.assertEqual(3, len(packet["conflicts"][0]["events"]))
        self.assertEqual("msg-urgent", packet["mail"][0]["id"])
        self.assertNotIn('"signal_score"', json.dumps(packet))
        self.assertEqual("https://mail.google.com/mail/u/0/#all/thread-urgent", packet["mail"][0]["url"])
        self.assertEqual(
            {"calendar": "ok", "gmail": "ok", "drive": "ok", "sheets": "ok_empty"},
            packet["source_status"],
        )
        packet_rules = json.dumps({
            "instruction": packet["instruction"],
            "selection_rules": packet["selection_rules"],
            "response_contract": packet["response_contract"],
        })
        self.assertIn("top 3 distinct actionable outcomes", packet_rules)
        self.assertIn("Recommended action item(s):", packet_rules)
        self.assertIn("one distinct Mail link for every message", packet_rules)
        self.assertIn("bounded to at most three Mail links", packet_rules)
        self.assertIn("Copy sender names exactly", packet_rules)
        self.assertIn("URL-valued cell", packet_rules)
        self.assertIn("exactly matches live mail.from", packet_rules)
        self.assertTrue(packet["response_contract"]["item_template"][1].startswith("   - **Evidence:**"))
        self.assertIn("separate Evidence line", packet_rules)
        self.assertIn("never use remembered, learned, or repository-defined", packet_rules)
        self.assertIn("never merge row_units", packet_rules)
        self.assertEqual(3, packet["requested_top_n"])
        self.assertEqual("response_contract", next(reversed(packet)))
        exec_event = next(event for event in packet["meetings"] if event["id"] == "evt-exec")
        self.assertTrue(any(item["id"] == "deck-1" for item in exec_event["related"]["files"]))

    def test_sheet_schema_samples_and_validations_pass_through_without_mappings(self):
        snapshot = json.loads(FIXTURE.read_text(encoding="utf-8"))
        snapshot["sheets"] = [{
            "id": "sheet-1",
            "name": "Live workbook",
            "url": "https://docs.google.com/spreadsheets/d/sheet-1/edit",
            "title": "Live workbook",
            "locale": "en_US",
            "timezone": "UTC",
            "tabs": [{
                "title": "Arbitrary tab",
                "grid_size": {"rows": 100, "columns": 12},
                "inspection_truncated": True,
                "preamble": [{"row": 1, "values": {"A": "Overview"}}],
                "table": {
                    "header_row": 3,
                    "columns": [
                        {"column": "A", "name": "Signal"},
                        {"column": "B", "name": "Choice"},
                        {"column": "C", "name": "Instruction"},
                    ],
                    "row_count": 2,
                    "representative_rows": [
                        {"row": 4, "values": {"A": "One", "B": "Alpha", "C": "Review it"}},
                        {"row": 5, "values": {"A": "Two", "B": "Beta", "C": "Wait"}},
                    ],
                },
                "validation_previews": [{
                    "cells": ["B4", "B5"],
                    "cell_count": 2,
                    "validation": {
                        "condition_type": "ONE_OF_LIST",
                        "allowed_values": ["Alpha", "Beta"],
                    },
                }],
            }],
        }]

        packet = brief.build_packet(snapshot, self.args(top_n=5))

        sheet = packet["sheet_evidence"][0]
        self.assertEqual(snapshot["sheets"][0]["url"], sheet["url"])
        self.assertEqual(
            ["Signal", "Choice", "Instruction"],
            [item["name"] for item in sheet["tabs"][0]["schema"]],
        )
        self.assertEqual(2, len(sheet["tabs"][0]["row_units"]))
        self.assertNotIn("row", sheet["tabs"][0]["row_units"][0])
        self.assertEqual(
            ["Signal", "Choice", "Instruction"],
            [cell["header"] for cell in sheet["tabs"][0]["row_units"][0]["cells"]],
        )
        self.assertEqual(
            snapshot["sheets"][0]["tabs"][0]["validation_previews"],
            sheet["tabs"][0]["validation_previews"],
        )
        self.assertNotIn("workstreams", packet)
        self.assertEqual(5, packet["requested_top_n"])
        self.assertIn("top 5 distinct actionable outcomes", packet["instruction"])
        self.assertFalse(hasattr(brief, "STATUS_PRIORITY"))
        self.assertFalse(hasattr(brief, "KEYWORDS"))
        self.assertFalse(hasattr(brief, "build_workstreams"))
        self.assertFalse(hasattr(brief, "render_initial_reply"))

    def test_packet_respects_context_budget(self):
        snapshot = json.loads(FIXTURE.read_text(encoding="utf-8"))
        encoded = brief.fit_packet(brief.build_packet(snapshot, self.args()), 5000)
        self.assertLessEqual(len(encoded), 5000)
        self.assertIn("conflicts", json.loads(encoded))

    def test_normal_budget_preserves_mail_and_sheet_samples(self):
        packet = {
            "mail": [
                {"id": f"message-{index}", "snippet": "signal " * 100}
                for index in range(8)
            ],
            "meetings": [{"id": index, "detail": "calendar " * 100} for index in range(10)],
            "recent_files": [{"id": index, "detail": "file " * 100} for index in range(8)],
            "conflicts": [{"id": index, "detail": "conflict " * 100} for index in range(5)],
            "focus_blocks": [],
            "sheet_evidence": [{"tabs": [{"row_units": [
                {"row": index, "cells": [{"header": "Anything", "value": "sheet " * 100}]}
                for index in range(8)
            ]}]}],
        }

        fitted = json.loads(brief.fit_packet(packet, 14000))

        self.assertLessEqual(len(json.dumps(fitted, ensure_ascii=False, separators=(",", ":"))), 14000)
        self.assertGreaterEqual(len(fitted["mail"]), 6)
        self.assertGreaterEqual(len(fitted["sheet_evidence"][0]["tabs"][0]["row_units"]), 6)

    def test_empty_success_is_not_reported_as_unavailable(self):
        snapshot = json.loads(FIXTURE.read_text(encoding="utf-8"))
        snapshot["events"] = []
        snapshot["files"] = []
        snapshot["coverage"].update({"events": 0, "files": 0, "errors": []})
        packet = brief.build_packet(snapshot, self.args())
        self.assertEqual("ok_empty", packet["source_status"]["calendar"])
        self.assertEqual("ok_empty", packet["source_status"]["drive"])
        self.assertEqual("ok_empty", packet["source_status"]["sheets"])


if __name__ == "__main__":
    unittest.main()
