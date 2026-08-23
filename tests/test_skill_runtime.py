from __future__ import annotations

import os
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHIEF_SKILL = ROOT / "skills" / "productivity" / "chief-of-staff" / "SKILL.md"
INGEST_SKILL = ROOT / "skills" / "productivity" / "ingest" / "SKILL.md"
WINDOWS_PYTHON = r'${LOCALAPPDATA//\\//}/hermes/hermes-agent/venv/Scripts/python.exe'
WINDOWS_HOME = r'${COS_HOME//\\//}'
START_DAY = ROOT / "skills" / "productivity" / "chief-of-staff" / "scripts" / "start_day.sh"
ACTION = ROOT / "skills" / "productivity" / "chief-of-staff" / "scripts" / "action.sh"
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

    def test_daily_brief_uses_one_installed_start_day_command(self) -> None:
        skill = CHIEF_SKILL.read_text(encoding="utf-8")
        routing = skill.split("## Request Routing", 1)[1].split("## Start of Day", 1)[0]
        start_section = skill.split("## Start of Day", 1)[1].split("## Initial Reply", 1)[0]

        self.assertIn("Daily brief", routing)
        self.assertIn("as the only terminal command", routing)
        self.assertIn("scripts/start_day.sh", routing)
        self.assertEqual(1, skill.count("scripts/start_day.sh"))
        self.assertIn("do not add redirection", start_section)
        self.assertNotIn("ingest.py", routing)
        self.assertNotIn("brief.py", routing)

        script = START_DAY.read_text(encoding="utf-8")
        self.assertIn('ingest.py" --max-messages 20', script)
        self.assertIn('brief.py" --max-meetings 6 --max-mail 8 --max-files 4 --max-chars 14000 --reply-only', script)
        self.assertNotIn(b"\r\n", START_DAY.read_bytes())

    def test_followups_are_flexible_and_use_conversation_history(self) -> None:
        skill = CHIEF_SKILL.read_text(encoding="utf-8")
        routing = skill.split("## Request Routing", 1)[1].split("## Start of Day", 1)[0]
        soul = SOUL.read_text(encoding="utf-8")

        self.assertIn("Plan follow-up", routing)
        self.assertIn("conversation history", routing)
        self.assertIn("newest instructions and constraints override", routing)
        self.assertIn("Direct Workspace request", routing)
        self.assertIn("General question", routing)
        self.assertIn("Never translate an item number directly into a stored command", routing)
        self.assertIn("Do not ask for redundant confirmation", skill)
        self.assertIn("end each draft with `Thanks,` and never `Best regards,`", skill)
        self.assertIn("calendar availability", skill)
        self.assertIn("rejects conflicts", skill)
        self.assertIn("scripts/action.sh", skill)
        self.assertNotIn("action-plan.json", skill)
        self.assertNotIn("cos.sh", skill)
        self.assertNotIn("workstream.py", ACTION.read_text(encoding="utf-8"))
        self.assertFalse((ROOT / "cos.sh").exists())
        self.assertFalse((ROOT / "skills" / "productivity" / "chief-of-staff" / "scripts" / "workstream.py").exists())
        self.assertIn("requests Google Workspace work", soul)

    def test_presentation_contract_is_enforced_without_scenario_content(self) -> None:
        skill = CHIEF_SKILL.read_text(encoding="utf-8")
        self.assertIn("one-sentence workload summary", skill)
        self.assertIn("Recommended action item(s):", skill)
        self.assertIn("exactly two links", skill)
        self.assertIn("creates recommendations only", skill)
        self.assertNotIn("RTX Spark", skill)
        self.assertNotIn("Ready for review", skill)
        self.assertNotIn("APPROVED HEADLINE", skill)

    @unittest.skipUnless(bash_executable(), "Git Bash or bash is required for syntax validation")
    def test_shell_syntax(self) -> None:
        for script in (START_DAY, ACTION):
            result = subprocess.run([bash_executable(), "-n", script.as_posix()], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
