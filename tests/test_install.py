from __future__ import annotations

import os
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from install import (
    ROUTING_START,
    configure_desktop_tools,
    configure_enabled_skills,
    connect_second_brain,
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
            "cron/jobs.json": b'{"jobs": [{"id": "default-only-job", "enabled": true}]}',
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

    def test_installer_connects_vault_and_preserves_connection_on_rerun(self) -> None:
        vault = Path(self.temp_dir.name) / "Project Notes"
        vault.mkdir()
        installer = Path(__file__).resolve().parents[1] / "install.py"
        command = [sys.executable, "-B", str(installer), "--hermes-home", str(self.target)]
        env = dict(os.environ, HERMES_HOME=str(self.base), PYTHONIOENCODING="utf-8")
        subprocess.run(command + ["--second-brain", str(vault)], env=env, capture_output=True, check=True)
        connection = self.target / "second-brain.json"
        self.assertEqual({"vault_path": str(vault.resolve())}, json.loads(connection.read_text()))
        first = connection.read_bytes()
        self.assertIn("HERMES_TUI_TOOLSETS=skills,terminal,cronjob", (self.target / ".env").read_text())
        self.assertIn("    - desktop_ui", (self.target / "config.yaml").read_text())
        self.assertFalse((self.target / "cron").exists())
        jobs = self.write_fixture("cron/jobs.json", b'{"jobs": [{"id": "keep-paused", "enabled": false}]}', root=self.target)
        previous_jobs = jobs.read_bytes()
        subprocess.run(command, env=env, capture_output=True, check=True)
        self.assertEqual(first, connection.read_bytes())
        self.assertEqual(previous_jobs, jobs.read_bytes())
        self.assertFalse((self.base / "cron").exists())
        self.assertFalse((self.base / "second-brain.json").exists())
        self.assertEqual([], list(vault.iterdir()))

    def test_invalid_vault_is_rejected_before_installing(self) -> None:
        installer = Path(__file__).resolve().parents[1] / "install.py"
        result = subprocess.run(
            [sys.executable, "-B", str(installer), "--hermes-home", str(self.target), "--second-brain", str(self.base / "missing")],
            env=dict(os.environ, HERMES_HOME=str(self.base)), capture_output=True,
        )
        self.assertNotEqual(0, result.returncode)
        self.assertFalse(self.target.exists())

    def test_default_second_brain_connection_does_not_modify_notes(self) -> None:
        source = Path(self.temp_dir.name) / "repo"
        vault = source / "demo" / "CoS_SecondBrain"
        vault.mkdir(parents=True)
        note = vault / "index.md"
        note.write_text("Existing notes", encoding="utf-8")
        self.assertEqual(vault.resolve(), connect_second_brain(source, self.target))
        self.assertEqual({"vault_path": str(vault.resolve())},
                         json.loads((self.target / "second-brain.json").read_text()))
        self.assertEqual("Existing notes", note.read_text())

    def test_existing_vault_connection_preserved_unless_explicitly_overridden(self) -> None:
        personal = Path(self.temp_dir.name) / "personal"
        personal.mkdir()
        note = personal / "keep.md"
        note.write_text("Personal notes", encoding="utf-8")
        self.write_fixture("second-brain.json", json.dumps({"vault_path": str(personal)}).encode(), root=self.target)
        source = Path(__file__).resolve().parents[1]
        self.assertEqual(personal, connect_second_brain(source, self.target))
        bundled = source / "demo" / "CoS_SecondBrain"
        self.assertEqual(bundled.resolve(), connect_second_brain(source, self.target, bundled))
        self.assertEqual("Personal notes", note.read_text())


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
        self.assertEqual("UNRELATED_SETTING=keep-me\nHERMES_TUI_TOOLSETS=skills,terminal,cronjob\n", first)

    def test_desktop_tools_migrate_old_allowlist_and_preserve_local_jobs(self) -> None:
        env = self.hermes_home / ".env"
        env.write_text("# Keep this comment\nexport HERMES_TUI_TOOLSETS=skills,terminal\nOTHER=value\n", encoding="utf-8")
        jobs = self.hermes_home / "cron" / "jobs.json"
        jobs.parent.mkdir()
        content = b'{"jobs": [{"id": "existing-job", "enabled": false}]}'
        jobs.write_bytes(content)

        configure_desktop_tools(env)
        configure_desktop_tools(env)

        self.assertEqual("# Keep this comment\nHERMES_TUI_TOOLSETS=skills,terminal,cronjob\nOTHER=value\n", env.read_text())
        self.assertEqual(content, jobs.read_bytes())

    def test_desktop_tools_missing_setting_adds_only_the_three_toolsets(self) -> None:
        env = self.hermes_home / ".env"
        configure_desktop_tools(env)
        self.assertEqual("HERMES_TUI_TOOLSETS=skills,terminal,cronjob", env.read_text().strip())
        self.assertFalse((self.hermes_home / "cron").exists())

    def test_example_toolsets_separate_job_management_from_execution(self) -> None:
        config = (Path(__file__).resolve().parents[1] / "config.example.yaml").read_text(encoding="utf-8")
        self.assertIn("  cli:\n    - skills\n    - terminal\n    - cronjob\n", config)
        self.assertIn("  cron:\n    - skills\n    - terminal\n", config)
        self.assertIn("  disabled_toolsets:\n    - desktop_ui", config)

    def test_disables_every_installed_skill_except_demo_and_workspace_fallback(self) -> None:
        config = self.hermes_home / "config.yaml"
        config.write_text(
            "model:\n  default: local-model\nskills:\n  creation_nudge_interval: 15\n  disabled:\n    - old-skill\nagent:\n  max_turns: 40\n",
            encoding="utf-8",
        )

        disabled = configure_enabled_skills(config, installed_skill_names(self.hermes_home))
        result = config.read_text(encoding="utf-8")

        self.assertEqual({"pdf"}, disabled)
        self.assertIn("model:\n  default: local-model", result)
        self.assertIn("  creation_nudge_interval: 15", result)
        self.assertIn("  disabled:\n    - pdf", result)
        self.assertNotIn("    - google-workspace", result)
        self.assertNotIn("old-skill", result)
        self.assertNotIn("    - chief-of-staff", result)
        self.assertNotIn("    - ingest", result)
        self.assertIn("agent:\n  max_turns: 40", result)

    def test_creates_skills_config_when_config_is_missing(self) -> None:
        config = self.hermes_home / "config.yaml"

        configure_enabled_skills(config, installed_skill_names(self.hermes_home))

        self.assertEqual(
            "skills:\n  disabled:\n    - pdf\n",
            config.read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
