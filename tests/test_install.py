from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from install import (
    ROUTING_START,
    configure_desktop_tools,
    configure_enabled_skills,
    default_home,
    install_soul,
    installed_skill_names,
    prepare_profile,
    profile_base,
)


class PrepareProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.base = Path(self.temp_dir.name) / "Hermes demo"
        self.base.mkdir()
        self.target = self.base / "profiles" / "chief-of-staff"

    def write_fixture(self, relative: str, content: bytes, root: Path | None = None) -> Path:
        path = (root or self.base) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def test_new_profile_copies_demo_identity_credentials_and_skills_without_history(self) -> None:
        preserved = {
            "config.yaml": b"model:\r\n  default: demo-model\r\nagent:\r\n  max_turns: 40\r\n",
            ".env": b"DEMO_SETTING=fixture\r\nHERMES_TUI_TOOLSETS=skills,terminal\r\n",
            "SOUL.md": b"My customized demo Soul.\r\n",
            "auth.json": b'{"fixture_provider": {"token": "fake-test-token"}}\n',
            ".no-bundled-skills": b"Preserve the selected skill catalog.\n",
            "google_client_secret.json": b'{"installed": {"client_id": "fake-client"}}\n',
            "google_token.json": b'{"refresh_token": "fake-refresh-token"}\n',
            "chief-of-staff-workspace-state.json": b'{"fixture": "workspace-state"}\n',
            "memories/MEMORY.md": b"Remember the demo priorities.\n",
            "memories/USER.md": b"Use the existing user preferences.\n",
            "skills/productivity/chief-of-staff/SKILL.md": b"Custom chief-of-staff skill.\r\n",
            "skills/productivity/ingest/scripts/ingest.py": b"# Existing ingestion behavior\r\n",
            "skills/custom-helper/SKILL.md": b"Keep installed helper skills too.\n",
        }
        excluded = {
            "sessions/old-session.json": b"source session history",
            "state.db": b"source database",
            "backups/old-backup.zip": b"source backup",
            "image_cache/image.png": b"cached image",
            "logs/agent.log": b"source log",
            "hooks/custom-hook.py": b"# unrelated hook",
            "skills/custom-helper/__pycache__/helper.pyc": b"regenerable bytecode",
            "skills/custom-helper/helper.pyc": b"regenerable bytecode",
            "profiles/other/SOUL.md": b"Another profile's identity",
        }
        source_files = {**preserved, **excluded}
        for relative, content in source_files.items():
            self.write_fixture(relative, content)

        prepare_profile(self.base, self.target)

        for relative, content in preserved.items():
            with self.subTest(copied=relative):
                self.assertEqual(content, (self.target / relative).read_bytes())
        for relative in excluded:
            with self.subTest(excluded=relative):
                self.assertFalse((self.target / relative).exists())
        for relative, content in source_files.items():
            with self.subTest(source_unchanged=relative):
                self.assertEqual(content, (self.base / relative).read_bytes())
        self.assertFalse((self.target / "hermes-agent").exists())

    def test_rerun_keeps_existing_profile_settings_credentials_state_and_skills(self) -> None:
        existing = {
            "config.yaml": b"model: customized-profile-model\n",
            ".env": b"PROFILE_SETTING=keep-me\n",
            "SOUL.md": b"Profile-specific Soul.\n",
            "auth.json": b'{"profile": "fake-profile-credential"}\n',
            "google_token.json": b'{"refresh_token": "fake-profile-token"}\n',
            "chief-of-staff-workspace-state.json": b'{"profile": "workspace-state"}\n',
            "memories/MEMORY.md": b"Profile-specific memory.\n",
            "skills/productivity/ingest/SKILL.md": b"Profile-specific ingest instructions.\n",
            "sessions/new-session.json": b"Profile-specific session.\n",
        }
        for relative, content in existing.items():
            self.write_fixture(relative, b"Different default data\n")
            self.write_fixture(relative, content, root=self.target)
        self.write_fixture("google_client_secret.json", b"Default-only credentials\n")
        self.write_fixture("skills/default-only/SKILL.md", b"Default-only skill\n")

        prepare_profile(self.base, self.target)
        prepare_profile(self.base, self.target)

        for relative, content in existing.items():
            with self.subTest(preserved=relative):
                self.assertEqual(content, (self.target / relative).read_bytes())
                self.assertEqual(b"Different default data\n", (self.base / relative).read_bytes())
        self.assertFalse((self.target / "google_client_secret.json").exists())
        self.assertFalse((self.target / "skills/default-only").exists())

    def test_active_named_profile_resolves_to_original_install_root(self) -> None:
        with patch.dict(os.environ, {"HERMES_HOME": str(self.base / "profiles" / "other")}):
            self.assertEqual(self.base.resolve(), profile_base(default_home()))
        self.assertEqual(self.base.resolve(), profile_base(self.base))

    def test_runtime_bridge_uses_shared_venv_and_is_idempotent(self) -> None:
        runtime = self.base / "hermes-agent" / "venv"
        self.write_fixture("hermes-agent/venv/runtime-marker", b"Shared runtime\n")
        self.write_fixture("hermes-agent/unrelated-source.py", b"# Runtime source\n")
        link = self.target / "hermes-agent" / "venv"

        if os.name == "nt":
            # Simulate the junction's existence without executing PowerShell
            # or creating any actual links on the developer's machine.
            with patch("install.subprocess.run", side_effect=lambda *args, **kwargs: link.mkdir()) as run:
                prepare_profile(self.base, self.target)
                prepare_profile(self.base, self.target)
            run.assert_called_once()
            argv = run.call_args.args[0]
            options = run.call_args.kwargs
            self.assertEqual("powershell.exe", argv[0])
            self.assertIn("-NonInteractive", argv)
            self.assertIn("New-Item -ItemType Junction", argv[-1])
            self.assertEqual(str(link), options["env"]["COS_PROFILE_VENV"])
            self.assertEqual(str(runtime), options["env"]["COS_SHARED_VENV"])
            self.assertTrue(options["check"])
            self.assertEqual(subprocess.CREATE_NO_WINDOW, options["creationflags"])
        else:
            prepare_profile(self.base, self.target)
            prepare_profile(self.base, self.target)
            self.assertTrue(link.is_symlink())
            self.assertEqual(runtime.resolve(), link.resolve())
            self.assertEqual(b"Shared runtime\n", (link / "runtime-marker").read_bytes())

        self.assertFalse((self.target / "hermes-agent/unrelated-source.py").exists())
        self.assertEqual(b"Shared runtime\n", (runtime / "runtime-marker").read_bytes())

    def test_existing_profile_runtime_is_preserved(self) -> None:
        self.write_fixture("hermes-agent/venv/runtime-marker", b"Default runtime\n")
        marker = self.write_fixture(
            "hermes-agent/venv/runtime-marker", b"Existing profile runtime\n", root=self.target,
        )

        with patch("install.subprocess.run") as run:
            prepare_profile(self.base, self.target)

        run.assert_not_called()
        self.assertEqual(b"Existing profile runtime\n", marker.read_bytes())


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

    def test_desktop_tools_setting_preserves_other_environment_values(self) -> None:
        env = self.hermes_home / ".env"
        env.write_text("UNRELATED_SETTING=keep-me\nHERMES_TUI_TOOLSETS=browser\n", encoding="utf-8")

        configure_desktop_tools(env)
        first = env.read_text(encoding="utf-8")
        configure_desktop_tools(env)

        self.assertEqual(first, env.read_text(encoding="utf-8"))
        self.assertEqual("UNRELATED_SETTING=keep-me\nHERMES_TUI_TOOLSETS=skills,terminal\n", first)

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
