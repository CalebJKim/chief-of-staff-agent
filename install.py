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


def hermes_cli_environment() -> dict[str, str]:
    """Run profile management against the normal Hermes root, not a stale profile override."""
    environment = os.environ.copy()
    environment.pop("HERMES_HOME", None)
    environment.setdefault("NO_COLOR", "1")
    return environment


def run_hermes(executable: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            [executable, *arguments],
            capture_output=True,
            text=True,
            errors="replace",
            env=hermes_cli_environment(),
            check=False,
        )
    except OSError as exc:
        raise RuntimeError(f"Unable to run Hermes CLI: {exc}") from exc


def require_success(result: subprocess.CompletedProcess[str], action: str) -> None:
    if result.returncode == 0:
        return
    detail = (result.stderr or result.stdout or "unknown error").strip()
    raise RuntimeError(f"Unable to {action}: {detail}")


def profile_home_from_show(output: str, profile_name: str = PROFILE_NAME) -> Path:
    match = re.search(r"(?m)^Path:\s*(.+?)\s*$", output)
    if not match:
        raise RuntimeError(f"Hermes did not report a path for profile '{profile_name}'")
    profile_home = Path(match.group(1)).expanduser().resolve()
    if profile_home.name.casefold() != profile_name.casefold() or profile_home.parent.name.casefold() != "profiles":
        raise RuntimeError(f"Hermes resolved '{profile_name}' to an unexpected path: {profile_home}")
    return profile_home


def ensure_dedicated_profile(executable: str, profile_name: str = PROFILE_NAME) -> tuple[Path, bool]:
    show = run_hermes(executable, "profile", "show", profile_name)
    created = False
    if show.returncode != 0:
        create = run_hermes(
            executable,
            "profile",
            "create",
            profile_name,
            "--clone-all",
            "--clone-from",
            "default",
        )
        require_success(create, f"create Hermes profile '{profile_name}'")
        created = True
        show = run_hermes(executable, "profile", "show", profile_name)
    require_success(show, f"inspect Hermes profile '{profile_name}'")
    return profile_home_from_show(show.stdout, profile_name), created


def configure_profile_home_env(env_path: Path, profile_home: Path) -> None:
    """Keep profile-scoped terminal actions on the selected profile after setup exits."""
    text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    lines = text.splitlines()
    setting = f'HERMES_HOME="{profile_home.as_posix()}"'
    match = re.compile(r"^(?:export\s+)?HERMES_HOME\s*=")
    indexes = [index for index, line in enumerate(lines) if match.match(line.strip())]
    if indexes:
        lines[indexes[0]] = setting
        for index in reversed(indexes[1:]):
            del lines[index]
    else:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(setting)
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def activate_profile(executable: str, profile_home: Path, profile_name: str = PROFILE_NAME) -> None:
    result = run_hermes(executable, "profile", "use", profile_name)
    require_success(result, f"select Hermes profile '{profile_name}'")
    active_profile = profile_home.parent.parent / "active_profile"
    selected = active_profile.read_text(encoding="utf-8").strip() if active_profile.exists() else ""
    if selected != profile_name:
        raise RuntimeError(f"Hermes did not persist '{profile_name}' as the active profile")


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
    parser.add_argument(
        "--hermes-home",
        type=Path,
        help="Install into an explicit isolated Hermes home without creating or selecting a named profile",
    )
    parser.add_argument("--overwrite-soul", action="store_true", help="Replace an existing SOUL.md (otherwise preserve it)")
    args = parser.parse_args()
    source = Path(__file__).resolve().parent
    hermes_executable = None
    profile_created = False
    if args.hermes_home is not None:
        target = args.hermes_home.expanduser().resolve()
    else:
        hermes_executable = shutil.which("hermes")
        if not hermes_executable:
            raise RuntimeError("Hermes CLI was not found on PATH; install Hermes before running this setup")
        target, profile_created = ensure_dedicated_profile(hermes_executable)
        configure_profile_home_env(target / ".env", target)
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
    if hermes_executable:
        activate_profile(hermes_executable, target)
    print(f"Installed skills into {skills_target}")
    print(f"SOUL.md: {soul_status}")
    print(f"Skills: enabled {', '.join(sorted(ENABLED_SKILLS))}; disabled {len(disabled)} others")
    if hermes_executable:
        status = "created" if profile_created else "refreshed"
        print(f"Profile: {PROFILE_NAME} {status} and selected")
    else:
        print("Profile: explicit isolated Hermes home; active desktop profile unchanged")
    print("Next: enable the skills + terminal toolsets and complete Google OAuth (see QUICKSTART.md).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
