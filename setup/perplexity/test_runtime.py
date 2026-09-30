"""Offline regression checks for Perplexity startup. No Google requests."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
POWERSHELL = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
SKILLS = Path(os.environ['PPLX_SKILLS_DIR'])
MANAGED = SKILLS.parent / 'template/venv/Scripts/python.exe'


def quoted(path):
    return "'" + str(path).replace("'", "''") + "'"


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='cos-runtime-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.chief = self.root / 'skill'
        shutil.copytree(ROOT / 'skills/productivity/chief-of-staff/scripts', self.chief / 'scripts',
                        ignore=shutil.ignore_patterns('__pycache__'))
        for name in ('ingest.py', 'actions.py', 'verify.py'):
            shutil.copy2(ROOT / 'skills/productivity/ingest/scripts' / name, self.chief / 'scripts' / name)
        (self.chief / 'runtime/state').mkdir(parents=True)
        (self.chief / 'tests/fixtures').mkdir(parents=True)
        shutil.copy2(ROOT / 'skills/productivity/chief-of-staff/tests/fixtures/workspace.json',
                     self.chief / 'tests/fixtures/workspace.json')
        (self.chief / 'runtime-local.json').write_text(json.dumps({
            'format_version': 4, 'seed_state_root': 'runtime/state',
            'python_selection': 'perplexity-then-system'}), encoding='utf-8')
        self.workspace = self.root / 'workspace'
        self.workspace.mkdir()
        self.env = os.environ.copy()
        self.env.pop('COS_STATE_DIR', None)
        self.env.pop('HERMES_HOME', None)
        self.env['COS_WORKSPACE_ROOT'] = str(self.workspace)
        self.env['PPLX_SKILLS_DIR'] = str(SKILLS)

    def ps(self, command):
        encoded = base64.b64encode(command.encode('utf-16-le')).decode()
        return subprocess.run([str(POWERSHELL), '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
                              env=self.env, cwd=self.workspace, capture_output=True, encoding='utf-8', timeout=45)

    def initialize(self):
        return self.ps('. ' + quoted(self.chief / 'scripts/runtime.ps1') +
                       '\n[PSCustomObject]@{python=$Python;source=$CosPythonSource;state=$env:COS_STATE_DIR} | ConvertTo-Json -Compress')

    def test_prefers_perplexity_python_and_uses_workspace_state(self):
        result = self.initialize()
        self.assertEqual(result.returncode, 0, result.stderr)
        info = json.loads(result.stdout)
        self.assertEqual(Path(info['python']), MANAGED)
        self.assertEqual(info['source'], 'perplexity')
        self.assertEqual(Path(info['state']), self.workspace / '.chief-of-staff-state')

    def test_absent_perplexity_python_uses_system_python(self):
        self.env['PPLX_SKILLS_DIR'] = str(self.root / 'empty-profile/skills')
        # Run this suite with the system interpreter, so this is a real fallback.
        self.env['PATH'] = str(Path(sys.executable).parent)
        result = self.initialize()
        self.assertEqual(result.returncode, 0, result.stderr)
        info = json.loads(result.stdout)
        self.assertEqual(info['source'], 'system')
        self.assertEqual(Path(info['python']), Path(sys.executable))

    def test_no_interpreter_fails_before_state_or_brief(self):
        self.env['PPLX_SKILLS_DIR'] = str(self.root / 'empty-profile/skills')
        self.env['PATH'] = ''
        result = self.ps('& ' + quoted(self.chief / 'scripts/daily_brief.ps1') + ' -Fixture')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('No Perplexity or system Python', result.stderr)
        self.assertFalse((self.workspace / '.chief-of-staff-state').exists())

    def test_present_python_with_missing_dependencies_does_not_fall_back(self):
        profile = self.root / 'profile'
        subprocess.run([str(MANAGED), '-B', '-m', 'venv', '--without-pip', str(profile / 'template/venv')],
                       check=True, capture_output=True, timeout=30)
        self.env['PPLX_SKILLS_DIR'] = str(profile / 'skills')
        result = self.ps('& ' + quoted(self.chief / 'scripts/daily_brief.ps1') + ' -Fixture')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Cannot use perplexity Python', result.stderr)
        self.assertFalse((self.workspace / '.chief-of-staff-state').exists())

    def test_launcher_runs_fixture_once_and_saves_complete_bounded_packet(self):
        result = self.ps('& ' + quoted(self.chief / 'scripts/daily_brief.ps1') + ' -Fixture')
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt, packet = result.stdout.splitlines()
        saved = Path(json.loads(receipt)['packet_path'])
        self.assertTrue(saved.is_relative_to(self.workspace / '.chief-of-staff-state'))
        self.assertEqual(saved.read_text(encoding='utf-8'), packet + '\n')
        self.assertLessEqual(len(packet), 14000)
        self.assertIn('source_status', json.loads(packet))
        self.assertEqual(len(list(self.workspace.rglob('snapshot.json'))), 1)
        self.assertEqual(len(list(self.workspace.rglob('packet.json'))), 1)

    def test_missing_state_never_uses_hermes_default(self):
        self.env['HERMES_HOME'] = str(self.root / 'must-not-use-hermes')
        result = subprocess.run([str(MANAGED), '-B', str(self.chief / 'scripts/daily_brief.py'),
                                 '--fixture', str(self.chief / 'tests/fixtures/workspace.json')],
                                env=self.env, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stderr)['stage'], 'prepare')
        self.assertIn('COS_STATE_DIR is missing', result.stderr)
        self.assertFalse((self.root / 'must-not-use-hermes').exists())

    def test_workspace_is_derived_from_current_session_subdirectory(self):
        profile = self.root / 'profile'
        session = profile / 'workspaces/session'
        self.workspace = session / 'outputs'
        self.workspace.mkdir(parents=True)
        self.env.pop('COS_WORKSPACE_ROOT')
        self.env['PPLX_SKILLS_DIR'] = str(profile / 'skills')
        result = self.initialize()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(json.loads(result.stdout)['state']), session / '.chief-of-staff-state')

    def test_outside_session_stops_before_running_brief(self):
        self.env.pop('COS_WORKSPACE_ROOT')
        result = self.ps('& ' + quoted(self.chief / 'scripts/daily_brief.ps1') + ' -Fixture')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Run the skill from the current Perplexity thread workspace', result.stderr)
        self.assertEqual(list(self.root.rglob('packet.json')), [])


if __name__ == '__main__':
    unittest.main()
