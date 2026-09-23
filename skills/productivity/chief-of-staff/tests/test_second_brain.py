from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


second_brain = load("cos_second_brain_tests", SCRIPTS / "second_brain.py")
brief = load("cos_brief_second_brain_tests", SCRIPTS / "brief.py")


def compact(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def workspace_fixture() -> dict:
    """Enough unrelated work to exercise fitting before local context is added."""
    return {
        "schema": 1,
        "generated_at": "2026-05-12T08:00:00Z",
        "timezone": "UTC",
        "window": {"start": "2026-05-12T00:00:00Z", "end": "2026-05-13T00:00:00Z"},
        "identity": {"email": "owner@example.test"},
        "coverage": {"events": 8, "messages": 8, "files": 8, "errors": []},
        "events": [
            {
                "id": f"event-{i}",
                "title": f"Warehouse planning session {i}",
                "start": "2026-05-12T09:00:00Z",
                "end": "2026-05-12T10:00:00Z",
                "organizer": "organizer@example.test",
                "attendees": [],
                "html_link": f"https://calendar.example.test/events/{i}",
            }
            for i in range(8)
        ],
        "messages": [
            {
                "id": f"message-{i}",
                "thread_id": f"thread-{i}",
                "from": "coordinator@example.test",
                "to": "owner@example.test",
                "subject": f"Orchard Migration decision {i}",
                "date": "Tue, 12 May 2026 07:00:00 +0000",
                "internal_ms": 1778569200000 + i,
                "unread": True,
                "important": True,
                "snippet": "Choose the migration sequence before the next decision meeting. " * 8,
                "links": [f"https://files.example.test/project/{i}"],
            }
            for i in range(8)
        ],
        "files": [
            {
                "id": f"file-{i}",
                "name": f"Warehouse planning document {i}",
                "kind": "doc",
                "modified": "2026-05-12T06:00:00Z",
                "url": f"https://files.example.test/documents/{i}",
            }
            for i in range(8)
        ],
    }


class SecondBrainTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="cos-vault-test-")
        self.addCleanup(temporary.cleanup)
        self.sandbox = Path(temporary.name).resolve()
        self.profile = self.sandbox / "profile"
        self.vault = self.sandbox / "Knowledge Vault"
        self.profile.mkdir()
        self.vault.mkdir()

    def note(self, relative: str, text: str) -> Path:
        path = self.vault / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def configure(self, vault: Path | None = None):
        (self.profile / "second-brain.json").write_text(
            json.dumps({"vault_path": str(vault or self.vault)}), encoding="utf-8"
        )

    def fingerprint(self) -> dict:
        return {
            path.relative_to(self.sandbox).as_posix(): (
                path.read_bytes(), path.stat().st_mtime_ns
            ) if path.is_file() else None
            for path in self.sandbox.rglob("*")
        }

    def run_brief(self, snapshot: Path, max_chars: int = 5000):
        env = os.environ.copy()
        env.update({
            "HERMES_HOME": str(self.profile),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "brief.py"), "--snapshot", str(snapshot),
             "--max-chars", str(max_chars)],
            cwd=self.sandbox, env=env, capture_output=True, text=True,
            encoding="utf-8", timeout=20, check=False,
        )

    def test_unconfigured_vault_is_optional(self):
        self.assertIsNone(second_brain.configured_vault(self.profile))
        self.assertIsNone(second_brain.packet_context({}, self.profile))

    def test_search_excerpt_includes_late_matching_passage(self):
        self.note("handbook.md", "# Operations Handbook\n" + "Background information. " * 25
                  + "Warehouse cutover rehearsal requires an owner. " + "Additional background. " * 20)
        result = second_brain.search(self.vault, ["warehouse cutover rehearsal"])
        self.assertEqual(len(result), 1)
        self.assertIn("Warehouse cutover rehearsal requires an owner.", result[0]["excerpt"])
        self.assertLessEqual(len(result[0]["excerpt"]), 280)
        self.assertTrue(result[0]["excerpt"].startswith("… "))

    def test_excerpt_keeps_context_when_match_was_near_previous_cutoff(self):
        text = "Background notes. " * 15 + "Define fail-closed behavior when policy evaluation is unavailable."
        result = second_brain.matched_excerpt(text, {"fail", "closed", "behavior"}, 280)
        self.assertIn("fail-closed behavior when policy evaluation is unavailable.", result)
        self.assertLessEqual(len(result), 280)

    def test_excerpt_respects_limits_and_unmatched_fallback(self):
        text = "Résumé of unrelated warehouse activity. " * 20
        for size in (0, 1, 3, 20, 280):
            with self.subTest(size=size):
                result = second_brain.matched_excerpt(text, {"absent"}, size)
                self.assertLessEqual(len(result), size)
        self.assertTrue(second_brain.matched_excerpt(text, {"absent"}, 280).startswith("Résumé"))

    def test_empty_queries_skip_filesystem_scan(self):
        with patch.object(second_brain.os, "walk") as walk:
            self.assertEqual(second_brain.search(self.vault, ["", "the and"]), [])
            self.assertEqual(second_brain.search(self.vault, ["warehouse"], limit=0), [])
        walk.assert_not_called()

    def test_directory_budget_bounds_scan_even_without_markdown(self):
        visited = []
        def directories():
            for i in range(5000):
                visited.append(i)
                yield str(self.vault / str(i)), [], ["image.png"]
        with patch.object(second_brain, "MAX_DIRECTORIES", 3), \
                patch.object(second_brain.os, "walk", return_value=directories()):
            self.assertEqual(second_brain.search(self.vault, ["warehouse"]), [])
        self.assertEqual(visited, [0, 1, 2])

    def test_looping_note_is_skipped_without_losing_other_notes(self):
        self.note("loop.md", "# Broken link fixture")
        self.note("warehouse.md", "# Warehouse Cutover\nA rehearsal needs an owner.")
        original = second_brain.read_note
        def read(root, relative, max_chars=4000):
            if Path(relative).name == "loop.md":
                raise RuntimeError("Symlink loop")
            return original(root, relative, max_chars)
        with patch.object(second_brain, "read_note", side_effect=read):
            result = second_brain.search(self.vault, ["warehouse cutover"])
        self.assertEqual([note["note"] for note in result], ["warehouse.md"])

    def test_looping_configuration_returns_optional_context_error(self):
        with patch.object(second_brain, "configured_vault", side_effect=RuntimeError("Symlink loop")):
            context = second_brain.packet_context({"mail": []}, self.profile)
        self.assertEqual(context, {"status": "error", "error": "Symlink loop"})

    def test_configured_vault_resolves_and_empty_search_succeeds(self):
        self.configure()
        self.assertEqual(second_brain.configured_vault(self.profile), self.vault)
        context = second_brain.packet_context({"mail": [{"subject": "Unrelated project"}]}, self.profile)
        self.assertEqual(context["status"], "ok_empty")
        self.assertEqual(context["notes"], [])

    def test_missing_configured_vault_reports_error(self):
        self.configure(self.sandbox / "missing")
        with self.assertRaises(ValueError):
            second_brain.configured_vault(self.profile)
        context = second_brain.packet_context({}, self.profile)
        self.assertEqual(context["status"], "error")
        self.assertIn("unavailable", context["error"].casefold())

    def test_bad_optional_configuration_is_an_error_not_a_brief_crash(self):
        for config in ({"vault_path": None}, {}, [], "invalid json"):
            (self.profile / "second-brain.json").write_text(json.dumps(config), encoding="utf-8")
            self.assertEqual("error", second_brain.packet_context({}, self.profile)["status"])

    def test_search_uses_titles_body_and_unicode_without_unrelated_notes(self):
        self.note("projects/orchard.md", "---\ntitle: Orchard Migration\n---\n# Plan\nSequence options remain open.")
        self.note("projects/cafe.md", "---\ntitle: Énergie durable café\n---\n# Options\nA seasonal operations proposal.")
        self.note("references/handbook.md", "# Operations handbook\nWarehouse cutover rehearsal requires an owner.")
        self.note("projects/garden.md", "# Garden planning\nOrder bulbs before winter.")
        notes = second_brain.search(
            self.vault, ["Orchard Migration", "ÉNERGIE CAFÉ", "warehouse cutover rehearsal"], limit=5
        )
        self.assertEqual(
            [note["note"] for note in notes],
            ["projects/orchard.md", "projects/cafe.md", "references/handbook.md"],
        )
        self.assertEqual(notes[1]["title"], "Énergie durable café")

    def test_search_limits_results_and_never_repeats_a_note(self):
        for i in range(5):
            self.note(f"projects/option-{i}.md", f"# Orchard Migration option {i}\nSequence decisions.")
        notes = second_brain.search(self.vault, ["Orchard Migration"] * 8, limit=2)
        self.assertEqual(len(notes), 2)
        self.assertEqual(len({note["note"] for note in notes}), 2)

    def test_single_name_and_empty_queries(self):
        self.note("people/mara.md", "# Mara Santos\nCoordinates supplier handoffs.")
        self.note("projects/orchard.md", "# Orchard Migration\nPlanning context.")
        result = second_brain.search(self.vault, ["Mara"])
        self.assertEqual([note["note"] for note in result], ["people/mara.md"])
        self.assertEqual([], second_brain.search(self.vault, ["", "the and"]))

    def test_read_and_search_observe_changed_content_on_every_call(self):
        relative = "projects/orchard.md"
        self.note(relative, "---\nupdated: 2026-05-01\n---\n# Orchard Migration\nFirst sequence proposal.")
        self.configure()
        packet = {"mail": [{"subject": "Orchard Migration"}]}
        first = second_brain.packet_context(packet, self.profile)
        self.assertIn("First sequence proposal", first["notes"][0]["excerpt"])
        self.note(relative, "---\nupdated: 2026-05-12\n---\n# Orchard Migration\nRevised bridge dependency.")
        second = second_brain.packet_context(packet, self.profile)
        self.assertIn("Revised bridge dependency", second["notes"][0]["excerpt"])
        self.assertNotIn("First sequence proposal", second["notes"][0]["excerpt"])
        self.assertEqual(second["notes"][0]["updated"], "2026-05-12")
        self.assertIn("Revised bridge dependency", second_brain.read_note(self.vault, relative)["text"])

    def test_read_rejects_parent_absolute_and_same_prefix_escape(self):
        outside = self.sandbox / "outside.md"
        outside.write_text("# Outside\nPrivate material.", encoding="utf-8")
        sibling = self.sandbox / "Knowledge Vault extra"
        sibling.mkdir()
        (sibling / "outside.md").write_text("Private material.", encoding="utf-8")
        for relative in ("../outside.md", str(outside), "../Knowledge Vault extra/outside.md"):
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                second_brain.read_note(self.vault, relative)

    def test_search_and_read_exclude_hidden_archived_large_and_non_markdown(self):
        body = "# Orchard Migration\nWarehouse cutover rehearsal."
        excluded = [".private/secret.md", "_archive/old.md", ".hidden.md", "_draft.md", "note.txt"]
        for relative in excluded:
            self.note(relative, body)
        self.note("large.md", body + "x" * (128 * 1024))
        self.note("projects/current.md", body)
        results = second_brain.search(self.vault, ["Orchard Migration"] * 8, limit=8)
        self.assertEqual([note["note"] for note in results], ["projects/current.md"])
        for relative in excluded + ["large.md"]:
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                second_brain.read_note(self.vault, relative)

    def test_bounded_context_preserves_source_dates_and_encoded_note_links(self):
        self.configure()
        topics = ["Orchard Migration", "Warehouse Cutover", "Harbor Relocation"]
        for i, topic in enumerate(topics):
            date_key = "updated" if i == 0 else "source_date"
            self.note(
                f"projects/source {i}.md",
                f"---\ntitle: {topic}\n{date_key}: 2026-05-0{i + 1}\n---\n"
                f"# {topic}\n" + "Dependency context needs an owner. " * 30,
            )
        context = second_brain.packet_context(
            {"mail": [{"subject": topic} for topic in topics]}, self.profile
        )
        self.assertEqual(context["status"], "ok")
        self.assertLessEqual(len(compact(context)), 3000)
        self.assertGreaterEqual(len(context["notes"]), 2)
        self.assertLessEqual(len(context["notes"]), 3)
        for i, note in enumerate(context["notes"]):
            self.assertEqual(note["updated"], f"2026-05-0{i + 1}")
            self.assertEqual(note["note"], f"projects/source {i}.md")
            self.assertTrue(note["url"].startswith("obsidian://open?path="))
            self.assertIn("%20", note["url"])
            self.assertNotIn(" ", note["url"])

    def test_packet_includes_at_most_five_distinct_notes_with_unchanged_excerpts(self):
        self.configure()
        for i in range(7):
            self.note(f"projects/option-{i}.md", f"# Orchard Migration option {i}\n"
                      + "Sequence decisions need dependency context. " * 20)
        packet = {"mail": [{"subject": "Orchard Migration"}] * 7}
        context = second_brain.packet_context(packet, self.profile)
        self.assertEqual(len(context["notes"]), 5)
        self.assertEqual(len({note["note"] for note in context["notes"]}), 5)
        self.assertTrue(all(len(note["excerpt"]) <= 280 for note in context["notes"]))
        self.assertLessEqual(len(compact(context)), 3000)
        with patch.object(second_brain, "CONTEXT_CHARS", 700):
            limited = second_brain.packet_context(packet, self.profile)
        self.assertGreater(len(limited["notes"]), 0)
        self.assertLess(len(limited["notes"]), 5)
        self.assertLessEqual(len(compact(limited)), 700)

    def test_vault_operations_do_not_write_files_or_change_existing_content(self):
        self.configure()
        self.note("projects/orchard.md", "# Orchard Migration\nRetain the bridge dependency.")
        before = self.fingerprint()
        second_brain.configured_vault(self.profile)
        second_brain.read_note(self.vault, "projects/orchard.md")
        second_brain.search(self.vault, ["Orchard Migration"])
        second_brain.packet_context({"mail": [{"subject": "Orchard Migration"}]}, self.profile)
        self.assertEqual(self.fingerprint(), before)

    def test_brief_cli_without_configuration_matches_existing_packet_bytes(self):
        snapshot = workspace_fixture()
        path = self.sandbox / "snapshot.json"
        path.write_text(json.dumps(snapshot), encoding="utf-8")
        args = argparse.Namespace(
            max_meetings=15, max_mail=12, max_files=12,
            work_start=8, work_end=18, min_focus_minutes=30,
        )
        packet = brief.build_packet(snapshot, args)
        self.assertGreater(len(compact(packet)), 5000)
        expected = brief.fit_packet(packet, 5000)
        result = self.run_brief(path)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip().encode("utf-8"), expected.encode("utf-8"))
        self.assertNotIn("second_brain", json.loads(result.stdout))

    def test_brief_cli_adds_separate_context_without_refitting_workspace(self):
        path = self.sandbox / "snapshot.json"
        path.write_text(json.dumps(workspace_fixture()), encoding="utf-8")
        original = self.run_brief(path)
        self.assertEqual(original.returncode, 0, original.stderr)
        self.assertLessEqual(len(original.stdout.strip()), 5000)
        self.configure()
        self.note(
            "projects/orchard.md",
            "---\nupdated: 2026-05-01\n---\n# Orchard Migration\nUnique bridge dependency from local notes.",
        )
        before = self.fingerprint()
        result = self.run_brief(path)
        self.assertEqual(result.returncode, 0, result.stderr)
        combined = json.loads(result.stdout)
        context = combined.pop("second_brain")
        self.assertEqual(context["status"], "ok")
        self.assertIn("Unique bridge dependency", context["notes"][0]["excerpt"])
        self.assertLessEqual(len(compact(context)), 3000)
        self.assertEqual(compact(combined), original.stdout.strip())
        self.assertGreater(len(result.stdout.strip()), len(original.stdout.strip()))
        self.assertLessEqual(len(result.stdout.strip()), len(original.stdout.strip()) + 3020)
        self.assertEqual(self.fingerprint(), before)


if __name__ == "__main__":
    unittest.main()
