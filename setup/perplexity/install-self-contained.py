"""Install the private Windows demo bundle without a Desktop runtime dependency.

Code/config are refreshed. Existing installed credentials and state are
preserved. The task workspace supplies the Second Brain; no notes are bundled.
No network, Google API calls, package installs, or app setting changes.
"""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path
from uuid import uuid4


def copy_code(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'runtime', 'notes', 'runtime-local.json'))


def retire_ingest(source: Path, skills: Path) -> str | None:
    """Move the legacy exposed skill to a unique backup outside skill discovery."""
    legacy = skills / 'productivity/ingest'
    if not legacy.exists():
        return None
    # Reject redirected parents or vaults before moving a directory on Windows.
    if legacy.resolve() != legacy or not legacy.is_dir():
        raise ValueError(f'Refusing to retire a redirected ingest skill: {legacy}')
    backup_root = source / '.pplx-state/retired-skills'
    if backup_root.resolve() != backup_root or backup_root.is_relative_to(skills):
        raise ValueError('Retired skill backups must stay outside the installed skills directory')
    backup = backup_root / (datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid4().hex[:8]) / 'ingest'
    backup.parent.mkdir(parents=True)
    shutil.move(str(legacy), str(backup))
    return str(backup)


def install_code(source: Path, skills: Path) -> dict:
    source = source.resolve()
    skills = skills.resolve()
    if source.name != 'ChiefOfStaff_PPLX':
        raise ValueError('Use the prepared ChiefOfStaff_PPLX copy, never the original demo')
    chief = skills / 'productivity/chief-of-staff'
    copy_code(source / 'skills/productivity/chief-of-staff', chief)
    return {'skill_root': str(chief), 'retired_ingest_backup': retire_ingest(source, skills)}


def install(source: Path, skills: Path) -> dict:
    source = source.resolve()
    result = install_code(source, skills)
    chief = Path(result['skill_root'])
    state = chief / 'runtime/state'

    initial_state = not state.exists()
    state.mkdir(parents=True, exist_ok=True)
    for name in ('google_token.json', 'google_client_secret.json', 'chief-of-staff-workspace-state.json'):
        target = state / name
        if not target.exists():
            shutil.copy2(source / '.pplx-state' / name, target)
    # Generated snapshots and packets are not installation state. Never bundle them.
    # runtime.ps1 generates second-brain.json from <workspace>/CoS_SecondBrain.
    # Preserve any legacy installed connection, but never use it as a fallback.
    config = {'format_version': 4, 'seed_state_root': 'runtime/state', 'python_selection': 'perplexity-then-system'}
    (chief / 'runtime-local.json').write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
    return {**result, 'python_selection': 'perplexity-then-system',
            'state_root': str(state), 'initial_state_copy': initial_state}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--skills-dir', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(install(args.source, args.skills_dir), indent=2))
