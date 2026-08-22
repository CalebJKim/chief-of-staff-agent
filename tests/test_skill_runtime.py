from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = (
    ROOT / "skills" / "productivity" / "chief-of-staff" / "SKILL.md",
    ROOT / "skills" / "productivity" / "ingest" / "SKILL.md",
)
WINDOWS_PYTHON = r'${LOCALAPPDATA//\\//}/hermes/hermes-agent/venv/Scripts/python.exe'
WINDOWS_HOME = r'${COS_HOME//\\//}'


class SkillRuntimeTests(unittest.TestCase):
    def test_windows_uses_bundled_python_with_native_paths(self) -> None:
        for skill in SKILLS:
            text = skill.read_text(encoding="utf-8")
            with self.subTest(skill=str(skill.relative_to(ROOT))):
                self.assertIn(WINDOWS_PYTHON, text)
                self.assertIn(WINDOWS_HOME, text)
                self.assertLess(text.index(WINDOWS_PYTHON), text.index("command -v python3"))


if __name__ == "__main__":
    unittest.main()
