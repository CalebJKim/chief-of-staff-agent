from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


def default_home() -> Path:
    if os.environ.get("HERMES_HOME"):
        return Path(os.environ["HERMES_HOME"]).expanduser()
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "hermes"
    return Path.home() / ".hermes"


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
    if not soul.exists() or args.overwrite_soul:
        shutil.copy2(source / "SOUL.md", soul)
        soul_status = "installed"
    else:
        soul_status = "preserved; merge the routing paragraph from this repository manually"
    print(f"Installed skills into {skills_target}")
    print(f"SOUL.md: {soul_status}")
    print("Next: enable the skills + terminal toolsets and complete Google OAuth (see README.md).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
