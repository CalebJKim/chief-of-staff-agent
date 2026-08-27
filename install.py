from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


ROUTING_START = 'When the user addresses you as "chief of staff"'
SCOPE_GUARD_PLUGIN = "chief-of-staff-scope-guard"


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
    routing_start = source_text.index(ROUTING_START)
    routing_end = source_text.find("\n\n", routing_start)
    routing = source_text[routing_start:routing_end if routing_end >= 0 else None].strip()
    if ROUTING_START in existing:
        existing_start = existing.index(ROUTING_START)
        existing_end = existing.find("\n\n", existing_start)
        existing_end = len(existing) if existing_end < 0 else existing_end
        current_routing = existing[existing_start:existing_end].strip()
        if current_routing == routing:
            return "preserved; chief-of-staff routing already present"
        updated = f"{existing[:existing_start]}{routing}{existing[existing_end:]}"
        target.write_text(updated, encoding="utf-8")
        return "preserved; chief-of-staff routing updated"

    target.write_text(f"{existing.rstrip()}\n\n{routing}\n", encoding="utf-8")
    return "preserved; chief-of-staff routing added"


def install_agent(source: Path, target: Path, overwrite_soul: bool) -> tuple[Path, str]:
    """Install the skills and SOUL into an already-created Hermes home."""
    source = source.expanduser().resolve()
    target = target.expanduser().resolve()
    skills_target = target / "skills" / "productivity"
    skills_target.mkdir(parents=True, exist_ok=True)
    for name in ("ingest", "chief-of-staff"):
        destination = skills_target / name
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(
            source / "skills" / "productivity" / name,
            destination,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    plugin_target = target / "plugins" / SCOPE_GUARD_PLUGIN
    plugin_target.parent.mkdir(parents=True, exist_ok=True)
    if plugin_target.exists():
        shutil.rmtree(plugin_target)
    shutil.copytree(
        source / "plugins" / SCOPE_GUARD_PLUGIN,
        plugin_target,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    obsolete_launcher = target / "cos.sh"
    if obsolete_launcher.exists():
        obsolete_launcher.unlink()
    obsolete_plan = target / "chief-of-staff" / "action-plan.json"
    if obsolete_plan.exists():
        obsolete_plan.unlink()
    soul_status = install_soul(source / "SOUL.md", target / "SOUL.md", overwrite_soul)
    return skills_target, soul_status


def main() -> int:
    parser = argparse.ArgumentParser(description="Install the Chief of Staff skills into a Hermes profile")
    parser.add_argument("--hermes-home", type=Path, default=default_home())
    parser.add_argument("--overwrite-soul", action="store_true", help="Replace an existing SOUL.md (otherwise preserve it)")
    args = parser.parse_args()
    source = Path(__file__).resolve().parent
    skills_target, soul_status = install_agent(source, args.hermes_home, args.overwrite_soul)
    print(f"Installed skills into {skills_target}")
    print(f"SOUL.md: {soul_status}")
    print(f"Installed plugin: {SCOPE_GUARD_PLUGIN} (enable it with setup_profile.py).")
    print("Next: enable the skills + terminal toolsets and complete Google OAuth (see QUICKSTART.md).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
