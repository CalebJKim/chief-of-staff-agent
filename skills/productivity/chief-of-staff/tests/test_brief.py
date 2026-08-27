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
        self.assertIn("Do not rank or regroup", packet_rules)
        self.assertIn("Do not score, rank, regroup, reorder, merge, replace, or skip items", packet_rules)
        self.assertIn("Other Workspace data may enrich", packet_rules)
        self.assertIn("cannot change the selected items or order", packet_rules)
        self.assertIn("past tense only for facts already completed", packet_rules)
        self.assertIn("Name pending work without implying it is complete", packet_rules)
        self.assertIn("One or two high-level sentences", packet_rules)
        self.assertNotIn("Recommended action item(s):", packet_rules)
        self.assertIn("primary and assigned supporting [Mail", packet_rules)
        self.assertIn("exact sender names", packet_rules)
        self.assertIn("Never invent or link an unrelated resource", packet_rules)
        self.assertTrue(packet["response_contract"]["item_template"][1].startswith("   - **Context:**"))
        self.assertNotIn("**Evidence:**", packet_rules)
        self.assertEqual(
            "N. **WORK ITEM NAME**",
            packet["response_contract"]["item_template"][0],
        )
        self.assertTrue(any(
            rule.startswith("Titles name pending work")
            for rule in packet["response_contract"]["self_check"]
        ))
        self.assertIn("never use remembered or repository-defined mappings", packet_rules)
        self.assertEqual(3, packet["requested_top_n"])
        self.assertEqual(3, packet["selected_item_count"])
        self.assertNotIn("selection_mode", packet)
        self.assertEqual("gmail_metadata_priority_then_recency", packet["ordering"])
        self.assertEqual(
            "important_then_direct_then_unread_then_newest_distinct_live_tasks",
            packet["selection_basis"],
        )
        self.assertEqual("response_contract", next(reversed(packet)))
        exec_event = next(event for event in packet["meetings"] if event["id"] == "evt-exec")
        self.assertEqual("evt-exec", packet["meetings"][0]["id"])
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

    def test_related_messages_are_one_distinct_work_item_without_seed_specific_rules(self):
        snapshot = json.loads(FIXTURE.read_text(encoding="utf-8"))
        snapshot["events"] = []
        snapshot["files"] = []
        snapshot["messages"] = [
            {
                "id": "mail-renewal-blocker",
                "thread_id": "thread-renewal-blocker",
                "from": "owner@supplier.example",
                "to": "owner@example.com",
                "subject": "Supplier renewal approval blocked",
                "internal_ms": 4_000,
                "unread": True,
                "important": True,
                "snippet": "Northwind contract renewal is blocked pending supplier approval and contract signing must move.",
            },
            {
                "id": "mail-renewal-schedule",
                "thread_id": "thread-renewal-schedule",
                "from": "legal@example.com",
                "to": "owner@example.com",
                "subject": "New signing slot for Northwind renewal",
                "internal_ms": 3_000,
                "unread": True,
                "important": True,
                "snippet": "Move contract signing to Friday and prepare the supplier confirmation after approval.",
            },
            {
                "id": "mail-hiring",
                "thread_id": "thread-hiring",
                "from": "people@example.com",
                "to": "owner@example.com",
                "subject": "Hiring plan ready for review",
                "internal_ms": 2_000,
                "unread": True,
                "important": False,
                "snippet": "The workforce hiring plan and headcount budget are complete and ready for review.",
            },
            {
                "id": "mail-onboarding",
                "thread_id": "thread-onboarding",
                "from": "operations@example.com",
                "to": "owner@example.com",
                "subject": "Publish the onboarding guide",
                "internal_ms": 1_000,
                "unread": True,
                "important": False,
                "snippet": "The employee onboarding guide passed legal review and is ready to publish.",
            },
        ]
        snapshot["sheets"] = [{
            "id": "generic-workbook",
            "name": "Operations workbook",
            "tabs": [{
                "title": "Open work",
                "table": {
                    "columns": [
                        {"column": "A", "name": "Item"},
                        {"column": "B", "name": "State"},
                        {"column": "C", "name": "Next step"},
                    ],
                    "representative_rows": [
                        {"values": {
                            "A": "Northwind supplier contract renewal",
                            "B": "Approval blocked",
                            "C": "Move contract signing to Friday and prepare supplier confirmation",
                        }},
                        {"values": {
                            "A": "Workforce hiring plan",
                            "B": "Ready for review",
                            "C": "Review completed headcount budget",
                        }},
                        {"values": {
                            "A": "Employee onboarding guide",
                            "B": "Approved",
                            "C": "Publish after legal review",
                        }},
                    ],
                },
            }],
        }]

        packet = brief.build_packet(snapshot, self.args(top_n=3))
        by_id = {item["id"]: item for item in packet["mail"]}
        selected = [item for item in packet["mail"] if item["selected_for_output"]]

        self.assertEqual(
            ["mail-renewal-blocker", "mail-hiring", "mail-onboarding"],
            [item["id"] for item in selected],
        )
        self.assertEqual([1, 2, 3], [item["selection_order"] for item in selected])
        self.assertEqual(1, by_id["mail-renewal-schedule"]["supports_selection_order"])
        self.assertNotIn("_task_signals", json.dumps(packet))
        self.assertEqual(3, packet["selected_item_count"])

    def test_shared_project_language_does_not_merge_different_live_rows(self):
        snapshot = json.loads(FIXTURE.read_text(encoding="utf-8"))
        snapshot["events"] = []
        snapshot["files"] = []
        snapshot["messages"] = [
            {
                "id": "mail-atlas-finance",
                "thread_id": "thread-atlas-finance",
                "from": "finance@example.com",
                "to": "owner@example.com",
                "subject": "Atlas rollout finance review",
                "internal_ms": 2_000,
                "unread": True,
                "important": True,
                "snippet": "Approve the Atlas rollout budget and finance forecast.",
            },
            {
                "id": "mail-atlas-research",
                "thread_id": "thread-atlas-research",
                "from": "research@example.com",
                "to": "owner@example.com",
                "subject": "Atlas rollout research review",
                "internal_ms": 1_000,
                "unread": True,
                "important": True,
                "snippet": "Review the Atlas rollout customer survey and research findings.",
            },
        ]
        snapshot["sheets"] = [{
            "id": "atlas-workbook",
            "name": "Atlas workbook",
            "tabs": [{
                "title": "Work",
                "table": {
                    "columns": [{"column": "A", "name": "Item"}, {"column": "B", "name": "Next"}],
                    "representative_rows": [
                        {"values": {"A": "Atlas rollout finance budget", "B": "Approve finance forecast"}},
                        {"values": {"A": "Atlas rollout customer research", "B": "Review survey findings"}},
                    ],
                },
            }],
        }]

        packet = brief.build_packet(snapshot, self.args(top_n=2))
        selected = [item for item in packet["mail"] if item["selected_for_output"]]

        self.assertEqual(["mail-atlas-finance", "mail-atlas-research"], [item["id"] for item in selected])
        self.assertFalse(any(item.get("supports_selection_order") for item in packet["mail"]))

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
        self.assertIn("Render 3 pre-ranked distinct items", packet["instruction"])
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

    def test_timeout_returns_only_a_google_side_retry_message_contract(self):
        snapshot = json.loads(FIXTURE.read_text(encoding="utf-8"))
        snapshot["coverage"]["errors"] = ["sheets: read operation timed out"]

        packet = brief.build_packet(snapshot, self.args())

        self.assertTrue(packet["temporary_google_error"])
        self.assertEqual(0, packet["response_contract"]["item_count"])
        self.assertEqual(brief.GOOGLE_TEMPORARY_USER_MESSAGE, packet["user_message"])
        self.assertIn("Return exactly this sentence", packet["instruction"])
        self.assertNotIn("mail", packet)


if __name__ == "__main__":
    unittest.main()
