from __future__ import annotations

import argparse
import os
import re
import shutil
from pathlib import Path


ROUTING_START = 'When the user addresses you as "chief of staff"'
ENABLED_SKILLS = {"chief-of-staff", "ingest"}


def default_home() -> Path:
    if os.environ.get("HERMES_HOME"):
        return Path(os.environ["HERMES_HOME"]).expanduser()
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "hermes"
    return Path.home() / ".hermes"


def install_soul(source: Path, target: Path, overwrite: bool) -> str:
    source_text = source.read_text(encoding="utf-8")
    if not target.exists() or overwrite:
        shutil.copy2(source, target)
        return "installed"

    existing = target.read_text(encoding="utf-8")
    if ROUTING_START in existing:
        return "preserved; chief-of-staff routing already present"

    routing_start = source_text.index(ROUTING_START)
    routing = source_text[routing_start:].strip()
    target.write_text(f"{existing.rstrip()}\n\n{routing}\n", encoding="utf-8")
    return "preserved; chief-of-staff routing added"


def installed_skill_names(hermes_home: Path) -> set[str]:
    names = set()
    for skill_file in (hermes_home / "skills").rglob("SKILL.md"):
        name = skill_file.parent.name
        try:
            header = skill_file.read_text(encoding="utf-8")[:4000]
            match = re.search(r"(?m)^name:\s*['\"]?([^'\"\r\n]+)", header)
            if match:
                name = match.group(1).strip()
        except OSError:
            pass
        if name:
            names.add(name)
    return names


def configure_enabled_skills(config_path: Path, installed: set[str]) -> set[str]:
    """Disable every installed skill except this demo's two required skills."""
    disabled = sorted(installed - ENABLED_SKILLS)
    text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    lines = text.splitlines()
    skills_start = next((index for index, line in enumerate(lines) if line.strip() == "skills:" and not line.startswith((" ", "\t"))), None)
    disabled_lines = ["  disabled:", *(f"    - {name}" for name in disabled)]

    if skills_start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend(["skills:", *disabled_lines])
    else:
        skills_end = next(
            (index for index in range(skills_start + 1, len(lines)) if lines[index].strip() and not lines[index].startswith((" ", "\t", "#"))),
            len(lines),
        )
        disabled_start = next(
            (index for index in range(skills_start + 1, skills_end) if re.match(r"^  disabled\s*:", lines[index])),
            None,
        )
        if disabled_start is None:
            lines[skills_start + 1:skills_start + 1] = disabled_lines
        else:
            disabled_end = disabled_start + 1
            while disabled_end < skills_end and (not lines[disabled_end].strip() or lines[disabled_end].startswith(("    ", "\t"))):
                disabled_end += 1
            lines[disabled_start:disabled_end] = disabled_lines

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return set(disabled)


def main() -> int:
    parser = argparse.ArgumentParser(description="Install the Chief of Staff skills into a Hermes profile")
    parser.add_argument("--hermes-home", type=Path, default=default_home())
    parser.add_argument("--overwrite-soul", action="store_true", help="Replace an existing SOUL.md (otherwise preserve it)")
    args = parser.parse_args()
    source = Path(__file__).resolve().parent
    target = args.hermes_home.expanduser().resolve()
    skills_target = target / "skills" / "productivity"
    skills_target.mkdir(parents=True, exist_ok=True)
    for name in ("ingest", "chief-of-staff"):
        destination = skills_target / name
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source / "skills" / "productivity" / name, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    soul = target / "SOUL.md"
    soul_status = install_soul(source / "SOUL.md", soul, args.overwrite_soul)
    disabled = configure_enabled_skills(target / "config.yaml", installed_skill_names(target))
    print(f"Installed skills into {skills_target}")
    print(f"SOUL.md: {soul_status}")
    print(f"Skills: enabled {', '.join(sorted(ENABLED_SKILLS))}; disabled {len(disabled)} others")
    print("Next: enable the skills + terminal toolsets and complete Google OAuth (see QUICKSTART.md).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
