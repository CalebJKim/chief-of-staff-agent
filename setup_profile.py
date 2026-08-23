from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Sequence

from install import install_agent


DEFAULT_PROFILE_NAME = "chief-of-staff-demo"
DEFAULT_MAX_TURNS = 40
PROFILE_DESCRIPTION = "Isolated Chief of Staff demo"


def default_hermes_root() -> Path:
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "hermes"
    return Path.home() / ".hermes"


def profile_home(hermes_root: Path, profile_name: str) -> Path:
    return hermes_root.expanduser().resolve() / "profiles" / profile_name


def run_command(command: Sequence[str]) -> None:
    subprocess.run(list(command), check=True)


def setup_profile(
    source: Path,
    hermes_root: Path,
    profile_name: str = DEFAULT_PROFILE_NAME,
    max_turns: int = DEFAULT_MAX_TURNS,
    runner: Callable[[Sequence[str]], None] = run_command,
) -> tuple[Path, bool]:
    """Create or refresh the dedicated profile without replacing existing model config."""
    if max_turns < 1:
        raise ValueError("max_turns must be at least 1")

    source = source.expanduser().resolve()
    hermes_root = hermes_root.expanduser().resolve()
    target = profile_home(hermes_root, profile_name)
    created = not (target / "profile.yaml").exists()

    if created:
        runner(
            [
                "hermes",
                "profile",
                "create",
                profile_name,
                "--no-skills",
                "--description",
                PROFILE_DESCRIPTION,
            ]
        )
        target.mkdir(parents=True, exist_ok=True)
        default_config = hermes_root / "config.yaml"
        if default_config.exists():
            shutil.copy2(default_config, target / "config.yaml")

    runner(
        [
            "hermes",
            "-p",
            profile_name,
            "config",
            "set",
            "platform_toolsets.cli",
            json.dumps(["skills", "terminal"], separators=(",", ":")),
            "--force",
        ]
    )
    runner(
        [
            "hermes",
            "-p",
            profile_name,
            "config",
            "set",
            "agent.max_turns",
            str(max_turns),
            "--force",
        ]
    )
    install_agent(source, target, overwrite_soul=True)
    return target, created


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create or refresh the isolated Hermes Chief of Staff profile"
    )
    parser.add_argument("--profile-name", default=DEFAULT_PROFILE_NAME)
    parser.add_argument("--hermes-root", type=Path, default=default_hermes_root())
    parser.add_argument("--max-turns", type=int, default=DEFAULT_MAX_TURNS)
    args = parser.parse_args()

    source = Path(__file__).resolve().parent
    try:
        target, created = setup_profile(
            source=source,
            hermes_root=args.hermes_root,
            profile_name=args.profile_name,
            max_turns=args.max_turns,
        )
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        parser.error(str(exc))

    status = "Created" if created else "Updated"
    print(f"{status} Hermes profile '{args.profile_name}' at {target}")
    print("Enabled toolsets: skills, terminal")
    print(f"Max agent steps: {args.max_turns}")
    print("Installed skills: chief-of-staff, ingest")
    print("Next: complete Google OAuth (see QUICKSTART.md).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
