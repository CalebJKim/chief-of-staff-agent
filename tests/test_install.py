from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from install import ROUTING_START, configure_enabled_skills, install_soul, installed_skill_names


class InstallSoulTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = Path(__file__).resolve().parents[1] / "SOUL.md"
        self.temp_dir = tempfile.TemporaryDirectory()
        self.target = Path(self.temp_dir.name) / "SOUL.md"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_installs_soul_when_missing(self) -> None:
        status = install_soul(self.source, self.target, overwrite=False)

        self.assertEqual("installed", status)
        self.assertEqual(
            self.source.read_text(encoding="utf-8"),
            self.target.read_text(encoding="utf-8"),
        )

    def test_adds_routing_without_replacing_existing_soul(self) -> None:
        self.target.write_text("My custom Soul.\n", encoding="utf-8")

        status = install_soul(self.source, self.target, overwrite=False)
        installed = self.target.read_text(encoding="utf-8")

        self.assertEqual("preserved; chief-of-staff routing added", status)
        self.assertTrue(installed.startswith("My custom Soul.\n\n"))
        self.assertIn(ROUTING_START, installed)

    def test_does_not_duplicate_existing_routing(self) -> None:
        install_soul(self.source, self.target, overwrite=False)
        first = self.target.read_text(encoding="utf-8")

        status = install_soul(self.source, self.target, overwrite=False)

        self.assertEqual("preserved; chief-of-staff routing already present", status)
        self.assertEqual(first, self.target.read_text(encoding="utf-8"))


class InstallSkillsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.hermes_home = Path(self.temp_dir.name)
        for name in ("chief-of-staff", "ingest", "google-workspace", "pdf"):
            skill_dir = self.hermes_home / "skills" / "productivity" / name
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(f"---\nname: {name}\n---\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_disables_every_installed_skill_except_chief_of_staff_and_ingest(self) -> None:
        config = self.hermes_home / "config.yaml"
        config.write_text(
            "model:\n  default: local-model\nskills:\n  creation_nudge_interval: 15\n  disabled:\n    - old-skill\nagent:\n  max_turns: 40\n",
            encoding="utf-8",
        )

        disabled = configure_enabled_skills(config, installed_skill_names(self.hermes_home))
        result = config.read_text(encoding="utf-8")

        self.assertEqual({"google-workspace", "pdf"}, disabled)
        self.assertIn("model:\n  default: local-model", result)
        self.assertIn("  creation_nudge_interval: 15", result)
        self.assertIn("  disabled:\n    - google-workspace\n    - pdf", result)
        self.assertNotIn("old-skill", result)
        self.assertNotIn("    - chief-of-staff", result)
        self.assertNotIn("    - ingest", result)
        self.assertIn("agent:\n  max_turns: 40", result)

    def test_creates_skills_config_when_config_is_missing(self) -> None:
        config = self.hermes_home / "config.yaml"

        configure_enabled_skills(config, installed_skill_names(self.hermes_home))

        self.assertEqual(
            "skills:\n  disabled:\n    - google-workspace\n    - pdf\n",
            config.read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
