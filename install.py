from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


ROUTING_START = 'When the user addresses you as "chief of staff"'


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
    print(f"Installed skills into {skills_target}")
    print(f"SOUL.md: {soul_status}")
    print("Next: enable the skills + terminal toolsets and complete Google OAuth (see QUICKSTART.md).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
