"""Install the private Windows demo bundle without a Desktop runtime dependency.

Code/config are refreshed. Existing installed credentials and state are
preserved. The task workspace supplies the Second Brain; no notes are bundled.
No network, Google API calls, package installs, or app setting changes.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def copy_code(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'runtime', 'notes', 'runtime-local.json'))


def install(source: Path, skills: Path) -> dict:
    source = source.resolve()
    skills = skills.resolve()
    if source.name != 'ChiefOfStaff_PPLX':
        raise ValueError('Use the prepared ChiefOfStaff_PPLX copy, never the original demo')
    chief = skills / 'productivity/chief-of-staff'
    ingest = skills / 'productivity/ingest'
    runtime = chief / 'runtime'
    state = runtime / 'state'
    copy_code(source / 'skills/productivity/chief-of-staff', chief)
    copy_code(source / 'skills/productivity/ingest', ingest)
    # The main skill also owns these helpers so it can run without its companion.
    for helper in ('actions.py', 'workspace_formatting.py', 'ingest.py', 'verify.py'):
        shutil.copy2(source / 'skills/productivity/ingest/scripts' / helper, chief / 'scripts' / helper)

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
    return {'skill_root': str(chief), 'python_selection': 'perplexity-then-system',
            'state_root': str(state), 'initial_state_copy': initial_state}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--skills-dir', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(install(args.source, args.skills_dir), indent=2))
