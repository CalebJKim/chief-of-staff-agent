"""Offline actions-launcher contract tests. No accounts, network or live state."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

CHIEF = Path(__file__).resolve().parents[1]
HARNESS = 'hermes'
FAKE = r'''
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
payload = sys.stdin.read()
record = {"args": args, "stdin": payload, "python": sys.executable}
with Path(os.environ['COS_LAUNCHER_LOG']).open('a', encoding='utf-8') as log:
    log.write(json.dumps(record, ensure_ascii=False) + '\n')
if args[0] == 'fail':
    print('simulated failure', file=sys.stderr)
    sys.exit(7)
if args[0] == 'large':
    sys.stderr.write('E' * 90000 + '\n')
    print(json.dumps({'text': 'X' * 90000}))
else:
    print(json.dumps(record, ensure_ascii=False))
'''

def psquote(value):
    value = str(value).replace("'", "''").replace('\u2019', '\u2019\u2019').replace('\u2018', '\u2018\u2018')
    return "'" + value + "'"

def shq(value):
    return "'" + str(value).replace("'", "'\"'\"'") + "'"

class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='cos launcher offline ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.chief = self.root / 'skills/productivity/chief-of-staff'
        self.scripts = self.chief / 'scripts'
        self.scripts.mkdir(parents=True)
        self.env = os.environ.copy()
        self.env.pop('COS_STATE_DIR', None)
        self.env.pop('COS_WORKSPACE_ROOT', None)
        self.env['HERMES_HOME'] = str(self.root)
        self.env['COS_LAUNCHER_LOG'] = str(self.root / 'calls.jsonl')
        if HARNESS == 'perplexity':
            self.shell = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
            if not self.shell.exists():
                self.skipTest('Requires Windows PowerShell 5.1')
            self.launcher = self.scripts / 'run-actions.ps1'
            shutil.copy2(CHIEF / 'scripts/run-actions.ps1', self.launcher)
            self.fake = self.scripts / 'actions.py'
            self.runtime = self.scripts / 'runtime.ps1'
            self.runtime.write_text(
                'param([string]$WorkspaceRoot)\n'
                'if (-not $WorkspaceRoot) { throw "missing workspace" }\n'
                f'$Python = {psquote(sys.executable)}\n'
                "$Action = Join-Path $PSScriptRoot 'actions.py'\n"
                f"Add-Content -LiteralPath {psquote(self.root / 'init.log')} -Value 'init'\n",
                encoding='utf-8')
        else:
            candidates = [os.environ.get('COS_TEST_BASH', ''),
                          'C:/Program Files/Git/bin/bash.exe', shutil.which('bash') or '']
            self.shell = next((Path(p) for p in candidates if p and Path(p).is_file()), None)
            if self.shell is None:
                self.skipTest('Requires Bash')
            self.launcher = self.scripts / 'run-actions.sh'
            shutil.copy2(CHIEF / 'scripts/run-actions.sh', self.launcher)
            self.fake = self.root / 'skills/productivity/ingest/scripts/actions.py'
            self.fake.parent.mkdir(parents=True)
            # Fake the managed Python candidate with a shell proxy. The launcher
            # must select it rather than guessing or depending on prior variables.
            proxy = self.root / ('hermes-agent/venv/Scripts/python.exe' if os.name == 'nt' else 'hermes-agent/venv/bin/python')
            proxy.parent.mkdir(parents=True)
            proxy.write_text('#!/usr/bin/env bash\nexec ' + shq(Path(sys.executable).as_posix()) + ' "$@"\n', encoding='utf-8', newline='\n')
            proxy.chmod(0o755)
        self.fake.write_text(FAKE, encoding='utf-8')

    def run_shell(self, script):
        if HARNESS == 'perplexity':
            script_path = self.root / 'command.ps1'
            script_path.write_text(script, encoding='utf-8-sig')
            command = [str(self.shell), '-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(script_path)]
        else:
            script_path = self.root / 'command.sh'
            script_path.write_text(script, encoding='utf-8', newline='\n')
            command = [str(self.shell), '--noprofile', '--norc', script_path.as_posix()]
        return subprocess.run(command, input='', env=self.env, cwd=self.root,
                              capture_output=True, encoding='utf-8', timeout=30)

    def call(self, args, payload=None):
        if HARNESS == 'perplexity':
            command = '& ' + psquote(self.launcher) + ' -WorkspaceRoot ' + psquote(self.root) + ' ' + ' '.join(psquote(a) for a in args)
            if payload is not None:
                command = psquote(payload) + ' | ' + command
        else:
            command = 'bash ' + shq(self.launcher.as_posix()) + ' ' + ' '.join(shq(a) for a in args)
            if payload is not None:
                command += " <<'INPUT'\n" + payload + '\nINPUT\n'
        return self.run_shell(command)

    def batch(self, lines):
        if HARNESS == 'perplexity':
            command = '& ' + psquote(self.launcher) + ' -WorkspaceRoot ' + psquote(self.root) + ' -Batch {\n' + lines + '\n}'
        else:
            command = 'bash ' + shq(self.launcher.as_posix()) + " --batch <<'COMMANDS'\n" + lines + '\nCOMMANDS\n'
        return self.run_shell(command)

    def records(self):
        path = Path(self.env['COS_LAUNCHER_LOG'])
        return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []

    def test_flags_spaces_unicode_quotes_empty_arguments_and_paths_are_preserved(self):
        args = ['docs', 'replace-text', 'id with space', '--find', 'Jürgen’s "note"',
                '--replace', '', '--confirm', '--path', 'C:\\folder with space\\',
                '--literal', 'value\\"quoted', '--url', 'https://example.test/a?q=x&b=y',
                '--raw-json', '{"key":"value"}', '--range', "'Team Sheet'!A1:H9"]
        result = self.call(args)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(args, self.records()[0]['args'])

    def test_piped_unicode_json_reaches_helper(self):
        payload = '[{"lane":"Révision","status":"In progress","latest":"A \\"quote\\""}]'
        result = self.call(['sheets', 'update-lanes', 'id', '--updates-file', '-', '--confirm'], payload)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(payload, self.records()[0]['stdin'].rstrip('\r\n'))

    def test_large_input_and_output_do_not_deadlock(self):
        result = self.call(['large'], 'ü' * 90000)
        self.assertEqual(0, result.returncode, result.stderr[:300])
        self.assertEqual('ü' * 90000, self.records()[0]['stdin'].rstrip('\r\n'))
        self.assertEqual(90000, len(json.loads(result.stdout)['text']))
        self.assertIn('E' * 100, result.stderr)

    def test_batch_runs_in_order_with_one_initialization(self):
        result = self.batch('action sheets get spreadsheet\naction gmail important --max 12')
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([['sheets', 'get', 'spreadsheet'], ['gmail', 'important', '--max', '12']], [r['args'] for r in self.records()])
        self.assertTrue(all(r['stdin'] == '' for r in self.records()))
        if HARNESS == 'perplexity':
            self.assertEqual(['init'], (self.root / 'init.log').read_text().splitlines())

    def test_batch_failure_stops_without_retrying_or_running_later_commands(self):
        result = self.batch('action gmail get first\naction fail\naction gmail get never')
        self.assertNotEqual(0, result.returncode)
        self.assertEqual([['gmail', 'get', 'first'], ['fail']], [r['args'] for r in self.records()])
        self.assertIn('simulated failure', result.stderr)

    def test_batch_input_is_assigned_to_its_own_command(self):
        payload = '{"heading":2}'
        if HARNESS == 'perplexity':
            lines = psquote(payload) + ' | action docs format id --style-file - --confirm\naction gmail get next'
        else:
            lines = "action docs format id --style-file - --confirm <<'JSON'\n" + payload + '\nJSON\naction gmail get next'
        result = self.batch(lines)
        self.assertEqual(0, result.returncode, result.stderr)
        records = self.records()
        self.assertEqual(payload, records[0]['stdin'].rstrip('\r\n'))
        self.assertEqual('', records[1]['stdin'])
        self.assertEqual(['gmail', 'get', 'next'], records[1]['args'])

    def test_bad_or_empty_batch_fails_before_actions(self):
        result = self.batch('')
        self.assertNotEqual(0, result.returncode)
        self.assertEqual([], self.records())

    def test_setup_failure_runs_no_action(self):
        if HARNESS == 'perplexity':
            self.runtime.write_text("throw 'setup unavailable'\n", encoding='utf-8')
        else:
            self.fake.unlink()
        result = self.call(['gmail', 'important'])
        self.assertNotEqual(0, result.returncode)
        self.assertEqual([], self.records())

    def test_two_fresh_calls_each_initialize_without_prior_variables(self):
        for ident in ('first', 'second'):
            result = self.call(['gmail', 'get', ident])
            self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(2, len(self.records()))
        if HARNESS == 'perplexity':
            self.assertEqual(['init', 'init'], (self.root / 'init.log').read_text().splitlines())

    def test_real_runtime_only_uses_temporary_workspace_state(self):
        if HARNESS != 'perplexity':
            self.skipTest('Perplexity runtime integration')
        skills = os.environ.get('PPLX_SKILLS_DIR')
        if not skills:
            self.skipTest('Set PPLX_SKILLS_DIR to test the managed Python runtime')
        managed = Path(skills).parent / 'template/venv/Scripts/python.exe'
        if not managed.is_file():
            self.skipTest('Perplexity managed Python is not installed')
        shutil.copy2(CHIEF / 'scripts/runtime.ps1', self.runtime)
        (self.chief / 'runtime/state').mkdir(parents=True)
        (self.chief / 'runtime-local.json').write_text(json.dumps({
            'seed_state_root': 'runtime/state',
        }), encoding='utf-8')
        (self.root / 'CoS_SecondBrain').mkdir()
        marker = self.root / 'CoS_SecondBrain/untouched.md'
        marker.write_text('Keep this note.', encoding='utf-8')
        result = self.batch('action sheets get id\naction gmail important --max 12')
        self.assertEqual(0, result.returncode, result.stderr)
        records = self.records()
        self.assertEqual(2, len(records))
        self.assertTrue(all(Path(r['python']) == managed for r in records))
        state = self.root / '.chief-of-staff-state'
        connection = json.loads((state / 'second-brain.json').read_text())
        self.assertEqual(str(self.root / 'CoS_SecondBrain'), connection['vault_path'])
        self.assertFalse((state / 'google_token.json').exists())
        self.assertEqual('Keep this note.', marker.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
