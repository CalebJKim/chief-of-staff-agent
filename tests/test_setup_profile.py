from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from setup_profile import DEFAULT_MAX_TURNS, setup_profile


ROOT = Path(__file__).resolve().parents[1]


class SetupProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.hermes_root = Path(self.temp_dir.name) / "hermes"
        self.hermes_root.mkdir()
        self.commands: list[list[str]] = []

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def runner(self, command) -> None:
        command = list(command)
        self.commands.append(command)
        if command[1:3] == ["profile", "create"]:
            target = self.hermes_root / "profiles" / command[3]
            target.mkdir(parents=True)
            (target / "profile.yaml").write_text("name: chief-of-staff-demo\n", encoding="utf-8")

    def test_creates_and_configures_isolated_profile(self) -> None:
        (self.hermes_root / "config.yaml").write_text("model: inherited\n", encoding="utf-8")

        target, created = setup_profile(ROOT, self.hermes_root, runner=self.runner)

        self.assertTrue(created)
        self.assertEqual("model: inherited\n", (target / "config.yaml").read_text(encoding="utf-8"))
        self.assertTrue((target / ".no-bundled-skills").exists() or any(
            command[1:3] == ["profile", "create"] and "--no-skills" in command
            for command in self.commands
        ))
        self.assertTrue((target / "skills" / "productivity" / "chief-of-staff" / "SKILL.md").exists())
        self.assertTrue((target / "skills" / "productivity" / "ingest" / "SKILL.md").exists())
        self.assertTrue((target / "SOUL.md").exists())
        self.assertIn(
            [
                "hermes", "-p", "chief-of-staff-demo", "config", "set",
                "platform_toolsets.cli", '["skills","terminal"]', "--force",
            ],
            self.commands,
        )
        self.assertIn(
            [
                "hermes", "-p", "chief-of-staff-demo", "config", "set",
                "agent.max_turns", str(DEFAULT_MAX_TURNS), "--force",
            ],
            self.commands,
        )
        self.assertIn(
            [
                "hermes", "-p", "chief-of-staff-demo", "config", "set",
                "skills.creation_nudge_interval", "0", "--force",
            ],
            self.commands,
        )

    def test_existing_profile_is_updated_without_replacing_config(self) -> None:
        target = self.hermes_root / "profiles" / "chief-of-staff-demo"
        target.mkdir(parents=True)
        (target / "profile.yaml").write_text("name: chief-of-staff-demo\n", encoding="utf-8")
        (target / "config.yaml").write_text("model: keep-me\n", encoding="utf-8")
        (self.hermes_root / "config.yaml").write_text("model: do-not-copy\n", encoding="utf-8")

        installed, created = setup_profile(
            ROOT,
            self.hermes_root,
            max_turns=24,
            runner=self.runner,
        )

        self.assertFalse(created)
        self.assertEqual(target, installed)
        self.assertEqual("model: keep-me\n", (target / "config.yaml").read_text(encoding="utf-8"))
        self.assertFalse(any(command[1:3] == ["profile", "create"] for command in self.commands))
        self.assertIn(
            [
                "hermes", "-p", "chief-of-staff-demo", "config", "set",
                "agent.max_turns", "24", "--force",
            ],
            self.commands,
        )
        self.assertIn(
            [
                "hermes", "-p", "chief-of-staff-demo", "config", "set",
                "skills.creation_nudge_interval", "0", "--force",
            ],
            self.commands,
        )

    def test_rejects_non_positive_turn_limit(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least 1"):
            setup_profile(ROOT, self.hermes_root, max_turns=0, runner=self.runner)


if __name__ == "__main__":
    unittest.main()
