from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import call, patch

from install import (
    PROFILE_NAME,
    ROUTING_START,
    activate_profile,
    configure_enabled_skills,
    configure_profile_home_env,
    ensure_dedicated_profile,
    install_soul,
    installed_skill_names,
    profile_home_from_show,
)


def completed(returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["hermes"], returncode, stdout, stderr)


class InstallProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.hermes_root = Path(self.temp_dir.name) / "hermes"
        self.profile_home = self.hermes_root / "profiles" / PROFILE_NAME
        self.profile_home.mkdir(parents=True)
        self.show_output = f"Profile: {PROFILE_NAME}\nPath:    {self.profile_home}\n"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_refreshes_existing_dedicated_profile_without_recreating_it(self) -> None:
        with patch("install.run_hermes", return_value=completed(stdout=self.show_output)) as run:
            profile_home, created = ensure_dedicated_profile("hermes")

        self.assertFalse(created)
        self.assertEqual(self.profile_home.resolve(), profile_home)
        run.assert_called_once_with("hermes", "profile", "show", PROFILE_NAME)

    def test_creates_dedicated_profile_from_default_when_missing(self) -> None:
        with patch(
            "install.run_hermes",
            side_effect=[completed(1, stderr="not found"), completed(), completed(stdout=self.show_output)],
        ) as run:
            profile_home, created = ensure_dedicated_profile("hermes")

        self.assertTrue(created)
        self.assertEqual(self.profile_home.resolve(), profile_home)
        self.assertEqual(
            [
                call("hermes", "profile", "show", PROFILE_NAME),
                call("hermes", "profile", "create", PROFILE_NAME, "--clone-all", "--clone-from", "default"),
                call("hermes", "profile", "show", PROFILE_NAME),
            ],
            run.call_args_list,
        )

    def test_rejects_default_profile_path(self) -> None:
        default_home = self.hermes_root.resolve()

        with self.assertRaisesRegex(RuntimeError, "unexpected path"):
            profile_home_from_show(f"Profile: {PROFILE_NAME}\nPath:    {default_home}\n")

    def test_profile_env_is_updated_without_removing_other_values(self) -> None:
        env_path = self.profile_home / ".env"
        env_path.write_text('API_SETTING="preserve-me"\nHERMES_HOME="old-path"\n', encoding="utf-8")

        configure_profile_home_env(env_path, self.profile_home)

        result = env_path.read_text(encoding="utf-8")
        self.assertIn('API_SETTING="preserve-me"', result)
        self.assertIn(f'HERMES_HOME="{self.profile_home.as_posix()}"', result)
        self.assertNotIn("old-path", result)

    def test_activation_is_verified_from_hermes_marker(self) -> None:
        (self.hermes_root / "active_profile").write_text(PROFILE_NAME, encoding="utf-8")

        with patch("install.run_hermes", return_value=completed()) as run:
            activate_profile("hermes", self.profile_home)

        run.assert_called_once_with("hermes", "profile", "use", PROFILE_NAME)


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
