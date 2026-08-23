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
    def args(self):
        return argparse.Namespace(
            max_files=12,
            max_meetings=15,
            max_mail=12,
            work_start=8,
            work_end=18,
            min_focus_minutes=30,
        )

    def test_conflict_and_priority_evidence(self):
        snapshot = json.loads(FIXTURE.read_text(encoding="utf-8"))
        packet = brief.build_packet(snapshot, self.args())
        self.assertEqual(len(packet["conflicts"]), 1)
        self.assertEqual(len(packet["conflicts"][0]["events"]), 3)
        self.assertEqual(packet["mail"][0]["id"], "msg-urgent")
        self.assertNotIn('"signal_score"', json.dumps(packet))
        self.assertEqual(packet["mail"][0]["url"], "https://mail.google.com/mail/u/0/#all/thread-urgent")
        self.assertEqual(packet["source_status"], {"calendar": "ok", "gmail": "ok", "drive": "ok"})
        self.assertIn("no more than three sentences", packet["instruction"])
        self.assertIn("Recommended action item(s):", packet["instruction"])
        self.assertIn("inline links", packet["instruction"])
        self.assertIn("workstreams[0:3]", packet["instruction"])
        self.assertIn("never split", packet["instruction"])
        exec_event = next(event for event in packet["meetings"] if event["id"] == "evt-exec")
        self.assertTrue(any(item["id"] == "deck-1" for item in exec_event["related"]["files"]))

    def test_tracker_workstreams_are_grouped_ranked_and_linked(self):
        snapshot = json.loads(FIXTURE.read_text(encoding="utf-8"))
        snapshot["trackers"] = [{
            "id": "sheet-1",
            "name": "Product launch tracker",
            "url": "https://docs.google.com/spreadsheets/d/sheet-1/edit",
            "rows": [
                {
                    "row": 7,
                    "lane": "Exec launch decision",
                    "pic": "CEO",
                    "status": "Blocked",
                    "latest": "A release blocker is open.",
                    "next": "Move the exec launch decision meeting.",
                    "blocker": "The meeting must move.",
                    "evidence": "https://mail.google.com/mail/u/0/#all/thread-urgent",
                    "artifact": "https://docs.google.com/spreadsheets/d/sheet-1/edit",
                },
                {
                    "row": 8,
                    "lane": "Launch readiness",
                    "pic": "PM",
                    "status": "In progress",
                    "latest": "The work is ready.",
                    "next": "Change only this lane's status to Ready for review.",
                    "blocker": "None",
                    "evidence": "https://mail.google.com/mail/u/0/#all/thread-customer",
                    "artifact": "https://docs.google.com/document/d/doc-1/edit",
                },
                {
                    "row": 9,
                    "lane": "Launch positioning deck",
                    "pic": "Owner",
                    "status": "Awaiting update",
                    "latest": "The headline is approved.",
                    "next": "Replace APPROVED HEADLINE PLACEHOLDER with “Meet the launch: a faster path to completed work.” on slide 4.",
                    "blocker": "None",
                    "evidence": "https://mail.google.com/mail/u/0/#all/thread-urgent",
                    "artifact": "https://docs.google.com/presentation/d/deck-1/edit",
                },
            ],
        }]

        packet = brief.build_packet(snapshot, self.args())
        workstreams = packet["workstreams"]
        self.assertEqual(["Exec launch decision", "Launch readiness", "Launch positioning deck"], [item["outcome"] for item in workstreams])
        self.assertEqual(["Calendar", "Tracker", "Deck"], [item["target"]["label"] for item in workstreams])
        self.assertEqual("msg-urgent", workstreams[0]["supporting_mail"]["id"])
        self.assertEqual("evt-exec", workstreams[0]["target"]["id"])
        self.assertTrue(all("action_command" not in item and "_action" not in item for item in workstreams))

        reply = brief.render_initial_reply(packet)
        self.assertTrue(reply.startswith("Today's workload centers on "))
        self.assertIn("Exec launch decision", reply)
        self.assertIn("Change only this lane's status to Ready for review.", reply)
        self.assertIn("Meet the launch: a faster path to completed work.", reply)
        self.assertEqual(3, reply.count("Recommended action item(s):"))
        self.assertEqual(1, reply.count("[Calendar]("))
        self.assertEqual(1, reply.count("[Tracker]("))
        self.assertEqual(1, reply.count("[Deck]("))
        self.assertNotIn("action_command", reply)
        self.assertNotIn("cos.sh", reply)

    def test_packet_respects_context_budget(self):
        snapshot = json.loads(FIXTURE.read_text(encoding="utf-8"))
        encoded = brief.fit_packet(brief.build_packet(snapshot, self.args()), 5000)
        self.assertLessEqual(len(encoded), 5000)
        self.assertIn("conflicts", json.loads(encoded))

    def test_normal_budget_preserves_six_highest_signal_messages(self):
        packet = {
            "mail": [
                {"id": f"message-{index}", "snippet": "signal " * 100}
                for index in range(8)
            ],
            "meetings": [{"id": index, "detail": "calendar " * 100} for index in range(10)],
            "recent_files": [{"id": index, "detail": "file " * 100} for index in range(8)],
            "conflicts": [{"id": index, "detail": "conflict " * 100} for index in range(5)],
            "trackers": [{"rows": [{"row": index, "detail": "tracker " * 100} for index in range(8)]}],
        }

        fitted = json.loads(brief.fit_packet(packet, 14000))

        self.assertLessEqual(len(json.dumps(fitted, ensure_ascii=False, separators=(",", ":"))), 14000)
        self.assertGreaterEqual(len(fitted["mail"]), 6)

    def test_empty_success_is_not_reported_as_unavailable(self):
        snapshot = json.loads(FIXTURE.read_text(encoding="utf-8"))
        snapshot["events"] = []
        snapshot["files"] = []
        snapshot["coverage"].update({"events": 0, "files": 0, "errors": []})
        packet = brief.build_packet(snapshot, self.args())
        self.assertEqual(packet["source_status"]["calendar"], "ok_empty")
        self.assertEqual(packet["source_status"]["drive"], "ok_empty")


if __name__ == "__main__":
    unittest.main()
