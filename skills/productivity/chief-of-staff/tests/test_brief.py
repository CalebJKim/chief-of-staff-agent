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

    def test_packet_contains_full_workspace_context_with_fixed_ranked_mail_anchors(self):
        snapshot = json.loads(FIXTURE.read_text(encoding="utf-8"))
        packet = brief.build_packet(snapshot, self.args())

        self.assertEqual(1, len(packet["conflicts"]))
        self.assertEqual(3, len(packet["conflicts"][0]["events"]))
        self.assertEqual(3, len(packet["mail"]))
        self.assertEqual("msg-urgent", packet["mail"][0]["id"])
        self.assertEqual([1, 2, 3], [item["selection_order"] for item in packet["mail"]])
        self.assertTrue(all(item["selected_for_output"] for item in packet["mail"]))
        self.assertNotIn('"signal_score"', json.dumps(packet))
        self.assertNotIn('"signals"', json.dumps(packet["mail"]))
        self.assertEqual("https://mail.google.com/mail/u/0/#all/thread-urgent", packet["mail"][0]["url"])
        self.assertEqual(
            {"calendar": "ok", "gmail": "ok", "drive": "ok", "sheets": "ok_empty"},
            packet["source_status"],
        )
        self.assertGreater(len(packet["meetings"]), 0)
        self.assertGreater(len(packet["recent_files"]), 0)
        self.assertIn("sheet_evidence", packet)
        packet_rules = json.dumps({
            "instruction": packet["instruction"],
            "ordering_contract": packet["ordering_contract"],
            "response_contract": packet["response_contract"],
        })
        self.assertIn("selected_for_output", packet_rules)
        self.assertIn("do not rank it again", packet_rules)
        self.assertIn("Do not score, rank, reorder, merge, replace, or skip selected entries", packet_rules)
        self.assertIn("supporting context only", packet_rules)
        self.assertIn("must never change which items are returned", packet_rules)
        self.assertIn("a request or proposal remains pending", packet_rules)
        self.assertIn("recommend preparing or saving a draft", packet_rules)
        self.assertIn("Recommended action item(s):", packet_rules)
        self.assertIn("selected entry's distinct [Mail", packet_rules)
        self.assertIn("copying the sender name exactly", packet_rules)
        self.assertIn("Never invent or link an unrelated resource", packet_rules)
        self.assertTrue(packet["response_contract"]["item_template"][1].startswith("   - **Evidence:**"))
        self.assertIn("Never use remembered, learned, or repository-defined", packet_rules)
        self.assertEqual(3, packet["requested_top_n"])
        self.assertEqual(3, packet["selected_item_count"])
        self.assertNotIn("selection_mode", packet)
        self.assertEqual("gmail_metadata_priority_then_recency", packet["ordering"])
        self.assertEqual("important_then_direct_then_unread_then_newest", packet["selection_basis"])
        self.assertEqual("response_contract", next(reversed(packet)))
        exec_event = next(event for event in packet["meetings"] if event["id"] == "evt-exec")
        self.assertTrue(any(item["id"] == "deck-1" for item in exec_event["related"]["files"]))

    def test_deterministic_ranking_uses_generic_metadata_with_stable_recency_tie_breaking(self):
        snapshot = json.loads(FIXTURE.read_text(encoding="utf-8"))
        messages = snapshot["messages"]
        messages[0].update({"internal_ms": 3_000, "important": False, "unread": False, "to": "team@example.com"})
        messages[1].update({"internal_ms": 2_000, "important": False, "unread": True, "to": "owner@example.com"})
        messages[2].update({"internal_ms": 1_000, "important": True, "unread": False, "to": "team@example.com"})

        packet = brief.build_packet(snapshot, self.args(top_n=2))
        selected = [item for item in packet["mail"] if item["selected_for_output"]]

        self.assertEqual(["msg-news", "msg-customer"], [item["id"] for item in selected])
        self.assertEqual([1, 2], [item["selection_order"] for item in selected])
        self.assertNotIn("priority", json.dumps(selected))
        self.assertTrue(brief.is_directly_addressed(messages[1], "owner@example.com"))
        self.assertFalse(brief.is_directly_addressed(messages[0], "owner@example.com"))
        self.assertFalse(hasattr(brief, "mail_score"))
        self.assertFalse(hasattr(brief, "event_score"))

    def test_sheet_schema_samples_and_validations_remain_supporting_context(self):
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
        self.assertEqual(3, packet["selected_item_count"])
        self.assertEqual(3, packet["response_contract"]["item_count"])
        self.assertIn("Render exactly the 3 deterministically ranked Gmail entries", packet["instruction"])
        self.assertFalse(hasattr(brief, "STATUS_PRIORITY"))
        self.assertFalse(hasattr(brief, "KEYWORDS"))
        self.assertFalse(hasattr(brief, "build_workstreams"))
        self.assertFalse(hasattr(brief, "render_initial_reply"))

    def test_packet_respects_context_budget(self):
        snapshot = json.loads(FIXTURE.read_text(encoding="utf-8"))
        encoded = brief.fit_packet(brief.build_packet(snapshot, self.args()), 5000)
        self.assertLessEqual(len(encoded), 5000)
        fitted = json.loads(encoded)
        self.assertEqual("gmail_metadata_priority_then_recency", fitted["ordering"])
        self.assertEqual(3, len(fitted["mail"]))

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
        self.assertGreaterEqual(len(fitted["sheet_evidence"][0]["tabs"][0]["row_units"]), 3)

    def test_empty_success_is_not_reported_as_unavailable(self):
        snapshot = json.loads(FIXTURE.read_text(encoding="utf-8"))
        snapshot["events"] = []
        snapshot["files"] = []
        snapshot["coverage"].update({"events": 0, "files": 0, "errors": []})
        packet = brief.build_packet(snapshot, self.args())
        self.assertEqual("ok", packet["source_status"]["gmail"])
        self.assertEqual("ok_empty", packet["source_status"]["calendar"])
        self.assertEqual("ok_empty", packet["source_status"]["drive"])
        self.assertEqual("ok_empty", packet["source_status"]["sheets"])


if __name__ == "__main__":
    unittest.main()
