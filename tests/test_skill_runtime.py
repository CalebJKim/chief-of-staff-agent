from __future__ import annotations

import os
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = (
    ROOT / "skills" / "productivity" / "chief-of-staff" / "SKILL.md",
    ROOT / "skills" / "productivity" / "ingest" / "SKILL.md",
)
WINDOWS_PYTHON = r'${LOCALAPPDATA//\\//}/hermes/hermes-agent/venv/Scripts/python.exe'
WINDOWS_HOME = r'${COS_HOME//\\//}'
START_DAY = ROOT / "skills" / "productivity" / "chief-of-staff" / "scripts" / "start_day.sh"


def bash_executable() -> str | None:
    if os.name == "nt":
        candidate = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "bin" / "bash.exe"
        return str(candidate) if candidate.is_file() else None
    return shutil.which("bash")


class SkillRuntimeTests(unittest.TestCase):
    def test_windows_uses_bundled_python_with_native_paths(self) -> None:
        for skill in SKILLS:
            text = skill.read_text(encoding="utf-8")
            with self.subTest(skill=str(skill.relative_to(ROOT))):
                self.assertIn(WINDOWS_PYTHON, text)
                self.assertIn(WINDOWS_HOME, text)
                self.assertLess(text.index(WINDOWS_PYTHON), text.index("command -v python3"))

    def test_chief_skill_runs_installed_start_day_script(self) -> None:
        skill = (ROOT / "skills" / "productivity" / "chief-of-staff" / "SKILL.md").read_text(encoding="utf-8")
        start_section = skill.split("## Start of Day", 1)[1].split("## Decide", 1)[0]
        command_block = start_section.split("```bash", 1)[1].split("```", 1)[0]

        self.assertIn("scripts/start_day.sh", start_section)
        self.assertNotIn("ACTION=", command_block)
        self.assertNotIn("ingest.py", command_block)
        self.assertNotIn("brief.py", command_block)

        script = START_DAY.read_text(encoding="utf-8")
        self.assertIn("ingest.py\" --max-messages 20", script)
        self.assertIn("brief.py\" --max-meetings 6 --max-mail 8 --max-files 4 --max-chars 14000", script)
        self.assertNotIn("ACTION=", script)
        self.assertNotIn(b"\r\n", START_DAY.read_bytes())

    @unittest.skipUnless(bash_executable(), "Git Bash or bash is required for syntax validation")
    def test_start_day_shell_syntax(self) -> None:
        result = subprocess.run([bash_executable(), "-n", START_DAY.as_posix()], capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
