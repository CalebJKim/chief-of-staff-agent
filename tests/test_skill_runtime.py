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
        self.assertIn("default is three priorities", routing)
        self.assertIn("append `--top N`", routing)
        self.assertIn("returns one compact live-evidence packet", routing)
        self.assertIn("produce the final brief yourself", routing)
        self.assertEqual(1, skill.count("scripts/start_day.sh"))
        self.assertIn("Never add redirection", start_section)
        self.assertNotIn("ingest.py", routing)
        self.assertNotIn("brief.py", routing)

        script = START_DAY.read_text(encoding="utf-8")
        self.assertIn('ingest.py" --max-messages 20', script)
        self.assertIn('brief.py" --max-meetings 6 --max-mail 8 --max-files 4 --max-chars 14000 --top "$TOP_N"', script)
        self.assertNotIn("--reply-only", script)
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
        self.assertIn("Include `--confirm` in the first invocation", skill)
        self.assertIn("Never rewrite a date from the earlier brief into `--user-request-text`", skill)
        self.assertIn("end each draft with exactly `Thanks` with no comma", skill)
        self.assertIn("A reply body must contain a substantive message before the closing", skill)
        self.assertIn("pass that event's returned `id` once as `--verify-calendar-event EVENT_ID`", skill)
        self.assertIn("rereads the live event and validates all five facts before creating anything", skill)
        self.assertIn("omit speculative causes, availability claims, or calendar-day references", skill)
        self.assertIn("Move on only after `status: drafted` or `status: already_drafted`", skill)
        self.assertIn("with `content_validated: true` and `verified: true`", skill)
        self.assertIn("use the original issue/request message as the primary reply", skill)
        self.assertIn("run one `gmail search` for the shared task, meeting, or subject phrase", skill)
        self.assertIn("Never pipe a Gmail result into another command", skill)
        self.assertIn("at most one simple name-only search for each missing person", skill)
        self.assertIn("say `draft saved (not sent)`", skill)
        self.assertIn("Never say `draft sent`", skill)
        self.assertIn("fabricate, echo, or simulate an out-of-band user-message marker", skill)
        self.assertIn("use the returned `timezone_abbreviation` exactly", skill)
        self.assertIn("mention internal notification settings", skill)
        self.assertIn("make the final response exactly that field and nothing else", skill)
        self.assertIn("stop generating immediately", skill)
        self.assertIn("a successful helper result containing `confirmation_markdown` is the entire final answer", soul)
        self.assertIn('--closing "Thanks"', ACTION.read_text(encoding="utf-8"))
        self.assertIn("calendar reschedule", skill)
        self.assertIn("default working window is 8:00 AM through 5:00 PM", skill)
        self.assertIn("finds the earliest conflict-free slot", skill)
        self.assertIn("Never construct dates, IDs, or UTC offsets with shell `date`", skill)
        self.assertIn("run one bounded `gmail search` using a short distinctive meeting phrase", skill)
        self.assertIn("never choose a date yourself", skill)
        self.assertIn("--date-source-message MESSAGE_ID", skill)
        self.assertIn("--user-directed-date", skill)
        self.assertIn("--expected-weekday", skill)
        self.assertIn("a Calendar URL is a link, not an event ID", skill)
        self.assertIn("Do not assign a shell variable", skill)
        self.assertIn("or submit to `process`", skill)
        self.assertIn("sheets inspect", skill)
        self.assertIn("sheets set-cell", skill)
        self.assertIn("Never assume a tab name, row number, column letter, or list of allowed values", skill)
        self.assertIn("exact visible headers, representative row units, and validation previews", skill)
        self.assertIn("Never assume canonical field names, fixed status meanings or order", skill)
        self.assertIn("Never use remembered, user-learned, or workspace-specific mappings", skill)
        self.assertNotIn("sheets update-lanes", skill)
        self.assertIn("Never call `skill_manage`", skill)
        self.assertIn("Never call `skill_manage`", soul)
        self.assertIn("Never run `git`, `pwd`, `ls`, `echo`", skill)
        self.assertIn("Never run `git`, `pwd`, `ls`, `echo`", soul)
        self.assertIn("Never launch Chrome or use browser/computer tools", skill)
        self.assertIn("Return links inline", skill)
        self.assertIn("scripts/action.sh", skill)
        self.assertNotIn("action-plan.json", skill)
        self.assertNotIn("cos.sh", skill)
        self.assertNotIn("workstream.py", ACTION.read_text(encoding="utf-8"))
        self.assertFalse((ROOT / "cos.sh").exists())
        self.assertFalse((ROOT / "skills" / "productivity" / "chief-of-staff" / "scripts" / "workstream.py").exists())
        self.assertIn("requests Google Workspace work", soul)

    def test_presentation_contract_is_enforced_without_scenario_content(self) -> None:
        skill = CHIEF_SKILL.read_text(encoding="utf-8")
        self.assertIn("one workload-summary sentence", skill)
        self.assertIn("Recommended action item(s):", skill)
        self.assertIn("a distinct `[Mail — SENDER](URL)` link for every live message", skill)
        self.assertIn("bounded to at most three Mail links", skill)
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
