from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
from pathlib import Path


ROUTING_START = 'When the user addresses you as "chief of staff"'
ENABLED_SKILLS = {"chief-of-staff", "ingest"}
PROFILE_NAME = "chief-of-staff"
PROFILE_FILES = (
    "config.yaml", ".env", "SOUL.md", "auth.json", ".no-bundled-skills",
    "google_client_secret.json", "google_token.json",
    "chief-of-staff-workspace-state.json", "memories/MEMORY.md", "memories/USER.md",
)


def default_home() -> Path:
    if os.environ.get("HERMES_HOME"):
        return Path(os.environ["HERMES_HOME"]).expanduser()
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "hermes"
    return Path.home() / ".hermes"


def profile_base(home: Path) -> Path:
    home = home.expanduser().resolve()
    return home.parent.parent if home.parent.name == "profiles" else home


def prepare_profile(base: Path, target: Path) -> None:
    """Clone demo settings once; never replace an existing profile's local state."""
    if not target.exists():
        target.mkdir(parents=True)
        for name in PROFILE_FILES:
            source_file = base / name
            if source_file.is_file():
                destination = target / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_file, destination)
                if name in {".env", "auth.json", "google_client_secret.json", "google_token.json"}:
                    destination.chmod(0o600)
        if (base / "skills").is_dir():
            shutil.copytree(base / "skills", target / "skills", symlinks=True,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    # Keep the existing skill's Python lookup valid without copying the runtime.
    runtime = base / "hermes-agent" / "venv"
    link = target / "hermes-agent" / "venv"
    if runtime.is_dir() and not link.exists() and not link.is_symlink():
        link.parent.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            env = dict(os.environ, COS_PROFILE_VENV=str(link), COS_SHARED_VENV=str(runtime))
            subprocess.run([
                "powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                "$ErrorActionPreference = 'Stop'; New-Item -ItemType Junction "
                "-Path $env:COS_PROFILE_VENV -Target $env:COS_SHARED_VENV | Out-Null",
            ], env=env, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            link.symlink_to(runtime, target_is_directory=True)


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


def disable_desktop_ui(config_path: Path) -> None:
    """Ensure the demo profile cannot use Hermes Desktop preview tools."""
    text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    if "    - desktop_ui\n" in text:
        return
    if "  disabled_toolsets: []" in text:
        text = text.replace("  disabled_toolsets: []", "  disabled_toolsets:\n    - desktop_ui", 1)
    elif "  disabled_toolsets:\n" in text:
        text = text.replace("  disabled_toolsets:\n", "  disabled_toolsets:\n    - desktop_ui\n", 1)
    elif "agent:\n" in text:
        text = text.replace("agent:\n", "agent:\n  disabled_toolsets:\n    - desktop_ui\n", 1)
    else:
        text = f"{text.rstrip()}\n\nagent:\n  disabled_toolsets:\n    - desktop_ui\n"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(text.rstrip() + "\n", encoding="utf-8")


def configure_desktop_tools(env_path: Path) -> None:
    """Pin Desktop's tool surface; its auto-discovery can re-add UI previews."""
    text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    setting = "HERMES_TUI_TOOLSETS=skills,terminal"
    pattern = r"(?m)^(?:export\s+)?HERMES_TUI_TOOLSETS=.*$"
    if re.search(pattern, text):
        text = re.sub(pattern, setting, text)
    else:
        text = text.rstrip() + "\n" + setting + "\n"
    env_path.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Install the Chief of Staff skills into a Hermes profile")
    parser.add_argument("--hermes-home", type=Path, help="Explicit target override (default: profiles/chief-of-staff under the Hermes root)")
    parser.add_argument("--overwrite-soul", action="store_true", help="Replace an existing SOUL.md (otherwise preserve it)")
    args = parser.parse_args()
    source = Path(__file__).resolve().parent
    base = profile_base(default_home())
    target = (args.hermes_home or base / "profiles" / PROFILE_NAME).expanduser().resolve()
    prepare_profile(base, target)
    skills_target = target / "skills" / "productivity"
    skills_target.mkdir(parents=True, exist_ok=True)
    for name in ("ingest", "chief-of-staff"):
        destination = skills_target / name
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source / "skills" / "productivity" / name, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    soul = target / "SOUL.md"
    soul_status = install_soul(source / "SOUL.md", soul, args.overwrite_soul)
    config_path = target / "config.yaml"
    disabled = configure_enabled_skills(config_path, installed_skill_names(target))
    disable_desktop_ui(config_path)
    configure_desktop_tools(target / ".env")
    print(f"Installed skills into {skills_target}")
    print(f"SOUL.md: {soul_status}")
    print(f"Skills: enabled {', '.join(sorted(ENABLED_SKILLS))}; disabled {len(disabled)} others")
    print("Toolsets: desktop_ui disabled")
    print("Desktop: skills + terminal only; restart Hermes Desktop to apply")
    print(f"Profile location: {target}")
    if target.parent.name == "profiles":
        print(f"Select {target.name} in Hermes Desktop and start a new chat.")
    print("For OAuth and seed/reset commands, set HERMES_HOME to the profile location above.")
    print("Next: verify the copied Google connection, or complete OAuth if not yet connected (see QUICKSTART.md).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
