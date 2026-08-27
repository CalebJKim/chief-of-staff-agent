from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from install import ROUTING_START, SCOPE_GUARD_PLUGIN, install_agent, install_soul


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

    def test_updates_existing_routing_without_replacing_custom_soul(self) -> None:
        self.target.write_text(
            'My custom Soul.\n\nWhen the user addresses you as "chief of staff", load the skill.\n\nKeep this too.\n',
            encoding="utf-8",
        )

        status = install_soul(self.source, self.target, overwrite=False)
        installed = self.target.read_text(encoding="utf-8")

        self.assertEqual("preserved; chief-of-staff routing updated", status)
        self.assertTrue(installed.startswith("My custom Soul.\n\n"))
        self.assertIn("follows up on that plan", installed)
        self.assertIn("requests Google Workspace work", installed)
        self.assertTrue(installed.endswith("\n\nKeep this too.\n"))

    def test_install_agent_copies_scope_guard_plugin(self) -> None:
        profile = Path(self.temp_dir.name) / "profile"

        install_agent(Path(__file__).resolve().parents[1], profile, overwrite_soul=True)

        plugin = profile / "plugins" / SCOPE_GUARD_PLUGIN
        self.assertTrue((plugin / "plugin.yaml").exists())
        self.assertTrue((plugin / "__init__.py").exists())
        self.assertIn(
            "tools.override",
            (plugin / "plugin.yaml").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
