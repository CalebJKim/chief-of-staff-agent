"""Refresh installed skill code from an immutable Git ref, preserving private state."""
from __future__ import annotations

import argparse
import difflib
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

INIT = ". (Join-Path $env:PPLX_SKILLS_DIR 'productivity\\chief-of-staff\\scripts\\runtime.ps1') -WorkspaceRoot 'WORKSPACE_ROOT'"
GUARD = "if ($LASTEXITCODE -ne 0) { throw 'Chief of Staff command failed; inspect the error above.' }"


def adapt(text: str, name: str) -> str:
    description_line = "description: 'Pull bounded Gmail, Calendar, Drive, and Google Tasks evidence.'"
    if name == 'chief-of-staff':
        header = re.match(r'\A---\n(.*?)\n---\n', text, flags=re.S)
        description = re.search(r'^description: (.+)$', header[1], flags=re.M) if header else None
        if description is None or description[1].strip() in ('|', '>'):
            raise ValueError('Expected a single-line Chief of Staff description')
        description_line = description[0]
    text = re.sub(r'\A---\n.*?\n---\n',
                  f"---\nname: {name}\n{description_line}\n---\n<!-- Original authors: NVIDIA, Hermes Agent. License: MIT. -->\n",
                  text, count=1, flags=re.S)
    return adapt_body(text)


def adapt_body(text: str) -> str:
    """Convert platform instructions in a skill or a supporting reference."""
    text = text.replace(
        'The terminal already runs Bash: submit these commands directly, without an outer `bash -c`/`bash -lc` wrapper. Keep heredoc delimiters on their own lines.',
        "Perplexity's `shell` tool runs Windows PowerShell 5.1. Submit commands directly, without an outer shell wrapper. Load the runtime initialization shown below at the start of each shell call; variables do not persist between calls. Keep single-quoted here-string delimiters on their own lines. `CosRoot` is the installed Chief of Staff skill folder; scripts and seed credentials are installed there. `CosHome` and `COS_STATE_DIR` point to the selected workspace’s `.chief-of-staff-state` directory. Do not use the old Desktop copy. If access is denied, use Perplexity's normal folder-access permission flow.")
    text = text.replace(
        'The `terminal` tool runs Bash. Omit `bash -c`/`bash -lc` wrappers. Keep heredoc delimiters on their own lines.',
        "Perplexity's `shell` tool runs Windows PowerShell 5.1. Submit commands directly, without an outer wrapper. For Start of Day, use its launcher, which initializes everything. For other scripts, load the initialization below in each shell call. It selects Perplexity’s Python, or system Python if absent, and prepares writable credentials and snapshots in the workspace's `.chief-of-staff-state` folder; installed skills are read-only. No Desktop checkout is needed. Keep single-quoted PowerShell here-string delimiters on their own lines.")

    def block(match: re.Match) -> str:
        body = match[1]
        if body.strip() == '"$PYTHON" "$DAILY_BRIEF"':
            return "```powershell\n& (Join-Path $env:PPLX_SKILLS_DIR 'productivity\\chief-of-staff\\scripts\\daily_brief.ps1') -WorkspaceRoot 'WORKSPACE_ROOT'\n```"
        lines = body.splitlines()
        python_line = next((i for i, line in enumerate(lines) if line.startswith('if [ -f "$COS_HOME/hermes-agent/')), None)
        if python_line is not None:
            end = python_line
            if lines[python_line].rstrip().endswith('then'):
                end = next(i for i in range(python_line + 1, len(lines)) if lines[i] == 'fi')
            body = '\n'.join(lines[end + 1:])
        body = re.sub(r'^(?:INGEST|BRIEF|DAILY_BRIEF|ACTION|SECOND_BRAIN)="\$COS_HOME/[^\n]*"\n?', '', body, flags=re.M)
        body = INIT + '\n' + body.lstrip('\n')
        body = re.sub(r"^([^\n]*?) <<'(EMAIL|JSON)'\n(.*?)\n\2$",
                      lambda m: "@'\n" + m[3] + "\n'@ | " + m[1], body, flags=re.M | re.S)
        body = body.replace('"$PYTHON"', '& $Python').replace('"$ACTION"', '$Action')
        for variable, helper in [('INGEST', 'ingest.py'), ('BRIEF', 'brief.py'), ('DAILY_BRIEF', 'daily_brief.py'), ('SECOND_BRAIN', 'second_brain.py')]:
            body = body.replace('"$' + variable + '"', '"$CosRoot/scripts/' + helper + '"')
        body = body.replace('$COS_HOME/skills/productivity/ingest/scripts/', '$CosRoot/scripts/')
        body = body.replace('$COS_HOME/skills/productivity/chief-of-staff/scripts/', '$CosRoot/scripts/')
        body = re.sub(r'\s*&&\s*', '\n', body)
        output = []
        for line in body.rstrip().splitlines():
            output.append(line)
            if line.startswith('& $Python ') or line.startswith("'@ | & $Python "):
                output.append(GUARD)
        return '```powershell\n' + '\n'.join(output) + '\n```'

    text = re.sub(r'```bash\n(.*?)\n```', block, text, flags=re.S)
    workspace_guidance = 'Replace `WORKSPACE_ROOT` in each command with the absolute path of the folder selected for this task, not a working subfolder. It must contain `CoS_SecondBrain` directly. Initialization generates `.chief-of-staff-state/second-brain.json` from that location.'
    for heading in ('### How to run the scripts\n', '## How to Run\n'):
        if heading in text and workspace_guidance not in text:
            text = text.replace(heading, heading + '\n' + workspace_guidance + '\n', 1)
    text = text.replace('| `daily_brief.py` |', '| `daily_brief.ps1` |')
    text = text.replace('"$PYTHON" "$ACTION"', '& $Python $Action')
    for skill in ('ingest', 'chief-of-staff'):
        text = text.replace(f'"$PYTHON" "$COS_HOME/skills/productivity/{skill}/scripts/', '& $Python "$CosRoot/scripts/')
    text = text.replace('quoted heredoc', 'single-quoted PowerShell here-string')
    text = text.replace('heredoc form', 'PowerShell here-string form')
    text = text.replace('not `printf`, `echo`,', 'not `Write-Output`, `echo`,')
    text = text.replace('For unsupported operations, load the full Google Workspace skill only then.',
                        'For unsupported operations, check for a relevant installed Google Workspace skill or connected tool and load it only then. If none is available, report the limitation.')
    scheduling = ('For this script-based workflow, set worker `enabled_toolsets: ["skills", "terminal"]` and attach this skill. '
                  'State the authorized work in the job prompt; refer to the skill rather than copying its commands or runtime paths. '
                  'Verify the saved scope, schedule, and time zone, then show the job name and returned next-run time. '
                  'The native scheduler saves the final response as the local report; no separate report-file write is needed.')
    text = text.replace(scheduling,
                        "When the user requests scheduling, load Perplexity's built-in `automations` skill and use its native tools. State the authorized work in the job prompt; refer to this skill rather than copying commands or runtime paths. Verify the saved scope, schedule, and time zone, then show the job name and returned next-run time. Results appear in the source thread; do not assume Hermes worker toolsets or report paths. If native scheduling is unavailable, report that limitation. Installing this skill does not create a schedule.")
    text = text.replace("`sed -n '/^## Response$/,$p' REPORT_PATH`",
                        "`([regex]::Match((Get-Content -LiteralPath 'REPORT_PATH' -Raw), '(?ms)^## Response\\r?\\n(.*?)(?=^## |\\z)')).Groups[1].Value`")
    text = text.replace("OAuth token at the active Hermes profile's `google_token.json`.",
                        'The installed Chief of Staff skill includes a saved Google token. Its initialization prepares a writable token copy in the current workspace’s `.chief-of-staff-state` folder for silent refresh. A permission error is not evidence that OAuth is missing; report the exact failed path and operation instead of asking for sign-in.')
    text = text.replace('Google Python dependencies installed by the bundled Google Workspace setup.',
                        'Use Perplexity’s Python, or system Python if absent. The selected Python must have the Google dependencies installed during setup. No Desktop checkout is required.')
    text = text.replace('Use `terminal` with the active profile root:',
                        "Use Perplexity's `shell` tool with Windows PowerShell 5.1 in the selected workspace. Load the runtime initialization at the start of each call; `CosRoot` is the read-only installed skill and `CosHome` is writable state in the thread workspace:")
    text = text.replace('`$COS_HOME/chief-of-staff/snapshot.json`', '`$CosHome/chief-of-staff/snapshot.json`')
    # Use standard Markdown blockquotes; the desktop renderer has no confirmed
    # GitHub alert extension, so do not emit a literal alert marker.
    text = re.sub(r'^[ \t]*> \[!IMPORTANT\]\n(?:[ \t]*>[ \t]*\n)?', '', text, flags=re.M)
    text = text.replace('start with this callout', 'start with this Markdown blockquote (a bold label, with no alert marker)')
    text = text.replace("When available, lead with the explicitly identified manager's update.", "When available, lead with the explicitly identified manager's update in this Markdown blockquote (a bold label, with no alert marker).")
    text = text.replace("Lead with the manager's update when available:", "Lead with the manager's update when available, using this Markdown blockquote (a bold label, with no alert marker):")
    text = text.replace('Important callout with', 'Markdown blockquote with')
    for forbidden in ('```bash', 'heredoc', '$COS_HOME', '$PYTHON', '$ACTION', '$INGEST', '$BRIEF', '$DAILY_BRIEF', '$SECOND_BRAIN', 'enabled_toolsets', 'bash -c', '[!IMPORTANT]'):
        if forbidden in text:
            raise ValueError(f'Unconverted Hermes instruction: {forbidden}')
    return text


def adapt_script(text: str) -> str:
    """Perplexity requires explicit writable state; never use a Hermes default."""
    if 'from brief import hermes_home' in text:
        return text.replace('except (OSError, ValueError, subprocess.CalledProcessError)',
                            'except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError)')
    pattern = r'(?ms)^def (hermes_home|home)\(\) -> Path:\n.*?(?=^def |^class |^if __name__|\Z)'
    def replace(match):
        return (f'def {match[1]}() -> Path:\n'
                '    configured = os.environ.get("COS_STATE_DIR")\n'
                '    if not configured:\n'
                '        raise RuntimeError("COS_STATE_DIR is missing. Run the Perplexity launcher from the current thread workspace.")\n'
                '    state = Path(configured).expanduser()\n'
                '    if not state.is_absolute() or not state.is_dir():\n'
                '        raise RuntimeError("COS_STATE_DIR must point to an existing absolute workspace directory.")\n'
                '    return state\n\n\n')
    result, count = re.subn(pattern, replace, text)
    if count != 1:
        raise ValueError('Expected one state-directory resolver')
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', type=Path, required=True)
    parser.add_argument('--ref', required=True)
    parser.add_argument('--skills-dir', type=Path, required=True)
    parser.add_argument('--deploy', action='store_true')
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[2]
    if source.name != 'ChiefOfStaff_PPLX':
        raise ValueError('Run only from the PPLX source copy')
    git = lambda *a: subprocess.check_output(['git', '-C', str(args.repository), *a])
    commit = git('rev-parse', args.ref + '^{commit}').decode().strip()
    paths = git('ls-tree', '-r', '--name-only', commit, 'skills/productivity').decode().splitlines()
    raw = {p: git('show', f'{commit}:{p}') for p in paths}
    desired = dict(raw)
    for name in ('chief-of-staff', 'ingest'):
        p = f'skills/productivity/{name}/SKILL.md'
        desired[p] = adapt(raw[p].decode('utf-8'), name).encode('utf-8')
    for p in paths:
        if '/references/' in p and p.endswith('.md'):
            desired[p] = adapt_body(raw[p].decode('utf-8')).encode('utf-8')
    p = 'skills/productivity/chief-of-staff/scripts/second_brain.py'
    old = '    root = Path(json.loads(config.read_text(encoding="utf-8"))["vault_path"]).expanduser().resolve()'
    new = '    root = Path(json.loads(config.read_text(encoding="utf-8"))["vault_path"]).expanduser()\n    if not root.is_absolute():\n        root = profile / root\n    root = root.resolve()'
    helper = raw[p].decode('utf-8')
    if old not in helper and new not in helper:
        raise ValueError('Review relative-vault adaptation for this source version')
    desired[p] = helper.replace(old, new).encode('utf-8')
    # Retain the local relative-vault regression test alongside upstream tests.
    p = 'skills/productivity/chief-of-staff/tests/test_second_brain.py'
    extra = '''    def test_relative_vault_is_resolved_from_profile_not_working_directory(self):
        (self.profile / "second-brain.json").write_text(
            json.dumps({"vault_path": "../Knowledge Vault"}), encoding="utf-8"
        )
        self.assertEqual(second_brain.configured_vault(self.profile), self.vault)

'''
    desired[p] = raw[p].decode('utf-8').replace('class SecondBrainTests(unittest.TestCase):\n',
                                              'class SecondBrainTests(unittest.TestCase):\n' + extra).encode('utf-8')
    for p, data in list(desired.items()):
        if '/scripts/' in p and Path(p).name in ('brief.py', 'daily_brief.py', 'second_brain.py', 'ingest.py', 'actions.py', 'verify.py'):
            desired[p] = adapt_script(data.decode('utf-8')).encode('utf-8')
        elif '/tests/' in p and p.endswith('.py'):
            desired[p] = data.replace(b'HERMES_HOME', b'COS_STATE_DIR')
    record = source / '.pplx-state' / ('skill-refresh-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    record.mkdir()
    for p, data in desired.items():
        target = record / 'proposed' / p
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    diff = ''.join(''.join(difflib.unified_diff(raw[p].decode().splitlines(True), desired[p].decode().splitlines(True),
                                             fromfile=commit[:7] + '/' + p, tofile='perplexity/' + p))
                   for p in paths if raw[p] != desired[p])
    (record / 'source-to-perplexity.diff').write_text(diff, encoding='utf-8')
    receipt = {'source_ref': args.ref, 'source_commit': commit, 'installed_skills': str(args.skills_dir),
               'deployed': args.deploy, 'adapted_files': [p for p in paths if desired[p] != raw[p]]}
    if args.deploy:
        chief = args.skills_dir / 'productivity/chief-of-staff'
        digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
        protected = {str(p): digest(p) for directory in (chief / 'runtime', chief / 'notes')
                     for p in directory.rglob('*') if p.is_file()}
        for p, data in desired.items():
            for old_path, label in ((source / p, 'source'), (args.skills_dir / Path(p).relative_to('skills'), 'installed')):
                if old_path.exists():
                    backup = record / 'backup' / label / p
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(old_path, backup)
            (source / p).parent.mkdir(parents=True, exist_ok=True)
            (source / p).write_bytes(data)
        spec = importlib.util.spec_from_file_location('self_contained_installer', Path(__file__).with_name('install-self-contained.py'))
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        installer.install(source, args.skills_dir)
        for name in ('chief-of-staff', 'ingest'):
            installer.copy_code(source / 'skills/productivity' / name, source / '.pplx-runtime/skills/productivity' / name)
        if not all(digest(Path(p)) == h for p, h in protected.items()):
            raise RuntimeError('Installed runtime, notes, or state changed during refresh')
        receipt['runtime_notes_state_preserved'] = True
        receipt['protected_file_count'] = len(protected)
        receipt['skill_sha256'] = digest(chief / 'SKILL.md')
        (source / 'setup/perplexity/source-version.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
        (chief / 'SOURCE_VERSION.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    (record / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'record': str(record), **receipt}, indent=2))


if __name__ == '__main__':
    main()
