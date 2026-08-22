from __future__ import annotations

import os
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INGEST_SKILL = ROOT / "skills" / "productivity" / "ingest" / "SKILL.md"
WINDOWS_PYTHON = r'${LOCALAPPDATA//\\//}/hermes/hermes-agent/venv/Scripts/python.exe'
WINDOWS_HOME = r'${COS_HOME//\\//}'
START_DAY = ROOT / "skills" / "productivity" / "chief-of-staff" / "scripts" / "start_day.sh"
ACTION = ROOT / "skills" / "productivity" / "chief-of-staff" / "scripts" / "action.sh"
LAUNCHER = ROOT / "cos.sh"
WORKSTREAM = ROOT / "skills" / "productivity" / "chief-of-staff" / "scripts" / "workstream.py"
SOUL = ROOT / "SOUL.md"


def bash_executable() -> str | None:
    if os.name == "nt":
        candidate = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "bin" / "bash.exe"
        return str(candidate) if candidate.is_file() else None
    return shutil.which("bash")


class SkillRuntimeTests(unittest.TestCase):
    def test_windows_uses_bundled_python_with_native_paths(self) -> None:
        for path in (INGEST_SKILL, START_DAY, ACTION):
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=str(path.relative_to(ROOT))):
                self.assertIn(WINDOWS_PYTHON, text)
                self.assertIn(WINDOWS_HOME, text)
                self.assertLess(text.index(WINDOWS_PYTHON), text.index("command -v python3"))

    def test_chief_skill_runs_installed_start_day_script(self) -> None:
        skill = (ROOT / "skills" / "productivity" / "chief-of-staff" / "SKILL.md").read_text(encoding="utf-8")
        start_section = skill.split("## Start of Day", 1)[1].split("## Initial Reply", 1)[0]
        router = skill.split("## Turn Router", 1)[1].split("## Start of Day", 1)[0]

        self.assertIn("Fresh daily plan", router)
        self.assertIn("only terminal command", router)
        self.assertIn("scripts/start_day.sh", router)
        self.assertEqual(1, skill.count("scripts/start_day.sh"))
        self.assertIn("do not add redirection", start_section)
        self.assertNotIn("ACTION=", router)
        self.assertNotIn("ingest.py", router)
        self.assertNotIn("brief.py", router)

        script = START_DAY.read_text(encoding="utf-8")
        self.assertIn("ingest.py\" --max-messages 20", script)
        self.assertIn("brief.py\" --max-meetings 6 --max-mail 8 --max-files 4 --max-chars 14000 --reply-only", script)
        self.assertNotIn("ACTION=", script)
        self.assertNotIn(b"\r\n", START_DAY.read_bytes())

    def test_chief_skill_keeps_followups_on_focused_helper(self) -> None:
        skill = (ROOT / "skills" / "productivity" / "chief-of-staff" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("scripts/action.sh", skill)
        self.assertIn("calendar move", skill)
        self.assertIn("one-sentence workload summary", skill)
        self.assertIn("Recommended action item(s):", skill)
        self.assertIn("exactly two links", skill)
        self.assertIn("Never launch Chrome", skill)
        self.assertIn("Do not load the generic Google Workspace skill", skill)
        self.assertIn("numbered follow-up", skill)
        self.assertIn("chief-of-staff/action-plan.json", skill)
        self.assertIn("workstream.py", ACTION.read_text(encoding="utf-8"))
        self.assertTrue(WORKSTREAM.is_file())
        self.assertIn("ACTION=", ACTION.read_text(encoding="utf-8"))
        self.assertNotIn(b"\r\n", ACTION.read_bytes())

    def test_followup_router_precedes_start_of_day_and_is_single_path(self) -> None:
        skill = (ROOT / "skills" / "productivity" / "chief-of-staff" / "SKILL.md").read_text(encoding="utf-8")
        router = skill.split("## Turn Router", 1)[1].split("## Start of Day", 1)[0]
        command = 'bash "$HERMES_HOME/cos.sh" N'
        soul = SOUL.read_text(encoding="utf-8")

        self.assertLess(skill.index("## Turn Router"), skill.index("## Start of Day"))
        self.assertIn("Choose exactly one path", router)
        self.assertIn(command, router)
        self.assertEqual(1, skill.count(command))
        self.assertIn("Never combine paths", router)
        self.assertIn("do not load another skill", router)
        self.assertNotIn("start_day.sh", soul)
        self.assertNotIn("action.sh", soul)
        self.assertNotIn("google-workspace", soul)
        self.assertIn("follows up on a numbered priority", soul)

    @unittest.skipUnless(bash_executable(), "Git Bash or bash is required for syntax validation")
    def test_start_day_shell_syntax(self) -> None:
        for script in (START_DAY, ACTION, LAUNCHER):
            result = subprocess.run([bash_executable(), "-n", script.as_posix()], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)

    def test_short_launcher_forwards_only_ranked_workstreams(self) -> None:
        launcher = LAUNCHER.read_text(encoding="utf-8")
        self.assertIn('^[1-3]$', launcher)
        self.assertIn('action.sh" workstream "$1" --confirm', launcher)
        self.assertNotIn(b"\r\n", LAUNCHER.read_bytes())


if __name__ == "__main__":
    unittest.main()
