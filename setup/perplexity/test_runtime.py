"""Offline regression checks for Perplexity startup. No Google requests."""
from __future__ import annotations

import base64
import importlib.util
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
cache_spec = importlib.util.spec_from_file_location('evidence_cache', ROOT / 'demo/evidence_cache.py')
evidence_cache = importlib.util.module_from_spec(cache_spec)
cache_spec.loader.exec_module(evidence_cache)


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
        self.vault = self.workspace / 'CoS_SecondBrain'
        self.vault.mkdir()
        (self.vault / 'index.md').write_text('# Second Brain\nNeoAgent V2 review context\n', encoding='utf-8')
        self.env = os.environ.copy()
        self.env.pop('COS_STATE_DIR', None)
        self.env.pop('HERMES_HOME', None)
        self.env.pop('COS_WORKSPACE_ROOT', None)
        self.env['PPLX_SKILLS_DIR'] = str(SKILLS)

    def ps(self, command):
        encoded = base64.b64encode(command.encode('utf-16-le')).decode()
        return subprocess.run([str(POWERSHELL), '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
                              env=self.env, cwd=self.workspace, capture_output=True, encoding='utf-8', timeout=45)

    def initialize(self, workspace=None):
        return self.ps('. ' + quoted(self.chief / 'scripts/runtime.ps1') +
                       ' -WorkspaceRoot ' + quoted(workspace or self.workspace) +
                       '\n[PSCustomObject]@{python=$Python;source=$CosPythonSource;state=$env:COS_STATE_DIR} | ConvertTo-Json -Compress')

    def test_prefers_perplexity_python_and_uses_workspace_state(self):
        result = self.initialize()
        self.assertEqual(result.returncode, 0, result.stderr)
        info = json.loads(result.stdout)
        self.assertEqual(Path(info['python']), MANAGED)
        self.assertEqual(info['source'], 'perplexity')
        self.assertEqual(Path(info['state']), self.workspace / '.chief-of-staff-state')

    def test_extended_workspace_path_initializes_and_update_launcher_runs_once(self):
        extended = '\\\\?\\' + str(self.workspace)
        before = (self.vault / 'index.md').read_bytes()
        result = self.ps('& ' + quoted(self.chief / 'scripts/daily_brief.ps1') +
                         ' -WorkspaceRoot ' + quoted(extended) + ' -Mode second-brain-update -Fixture')
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt, encoded = result.stdout.splitlines()
        packet = json.loads(encoded)
        self.assertEqual(packet['mode'], 'second-brain-update')
        self.assertNotIn('three-section', packet['instruction'])
        self.assertLessEqual(len(encoded), 14000)
        self.assertTrue(Path(json.loads(receipt)['packet_path']).is_relative_to(self.workspace))
        self.assertEqual(len(list(self.workspace.rglob('snapshot.json'))), 1)
        self.assertEqual(len(list(self.workspace.rglob('packet.json'))), 1)
        self.assertEqual((self.vault / 'index.md').read_bytes(), before)

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
        result = self.ps('& ' + quoted(self.chief / 'scripts/daily_brief.ps1') + ' -WorkspaceRoot ' + quoted(self.workspace) + ' -Fixture')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('No Perplexity or system Python', result.stderr)
        self.assertFalse((self.workspace / '.chief-of-staff-state').exists())

    def test_present_python_with_missing_dependencies_does_not_fall_back(self):
        profile = self.root / 'profile'
        subprocess.run([str(MANAGED), '-B', '-m', 'venv', '--without-pip', str(profile / 'template/venv')],
                       check=True, capture_output=True, timeout=30)
        self.env['PPLX_SKILLS_DIR'] = str(profile / 'skills')
        result = self.ps('& ' + quoted(self.chief / 'scripts/daily_brief.ps1') + ' -WorkspaceRoot ' + quoted(self.workspace) + ' -Fixture')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Cannot use perplexity Python', result.stderr)
        self.assertFalse((self.workspace / '.chief-of-staff-state').exists())

    def test_launcher_runs_fixture_once_and_saves_complete_bounded_packet(self):
        result = self.ps('& ' + quoted(self.chief / 'scripts/daily_brief.ps1') + ' -WorkspaceRoot ' + quoted(self.workspace) + ' -Fixture')
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

    def test_explicit_root_works_from_a_subdirectory_and_ignores_stale_settings(self):
        selected_root = self.workspace
        self.workspace = selected_root / 'outputs'
        self.workspace.mkdir()
        self.env['COS_WORKSPACE_ROOT'] = str(self.root / 'obsolete-workspace')
        (self.chief / 'runtime/state/second-brain.json').write_text(
            json.dumps({'vault_path': str(self.root / 'obsolete-vault')}), encoding='utf-8')
        result = self.initialize(selected_root)
        self.assertEqual(result.returncode, 0, result.stderr)
        state = selected_root / '.chief-of-staff-state'
        self.assertEqual(Path(json.loads(result.stdout)['state']), state)
        connection = json.loads((state / 'second-brain.json').read_text(encoding='utf-8'))
        self.assertEqual(Path(connection['vault_path']), self.vault)
        self.assertFalse((self.workspace / '.chief-of-staff-state').exists())

    def test_missing_argument_stops_without_guessing_workspace(self):
        result = self.ps('& ' + quoted(self.chief / 'scripts/daily_brief.ps1') + ' -Fixture')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Pass -WorkspaceRoot', result.stderr)
        self.assertEqual(list(self.root.rglob('packet.json')), [])
        self.assertFalse((self.workspace / '.chief-of-staff-state').exists())

    def test_missing_direct_child_vault_stops_before_writes(self):
        self.vault.rename(self.workspace / 'DifferentVault')
        result = self.initialize()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Second Brain folder is missing or inaccessible', result.stderr)
        self.assertFalse((self.workspace / '.chief-of-staff-state').exists())
        self.assertFalse(self.vault.exists())

    def test_relative_workspace_is_rejected(self):
        result = self.initialize('relative-workspace')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('absolute path', result.stderr)
        self.assertFalse((self.workspace / '.chief-of-staff-state').exists())

    def test_legacy_environment_override_uses_new_vault_convention(self):
        self.env['COS_WORKSPACE_ROOT'] = str(self.workspace)
        result = self.ps('. ' + quoted(self.chief / 'scripts/runtime.ps1') +
                         '\nWrite-Output $env:COS_STATE_DIR')
        self.assertEqual(result.returncode, 0, result.stderr)
        state = self.workspace / '.chief-of-staff-state'
        self.assertEqual(Path(result.stdout.strip()), state)
        self.assertEqual(json.loads((state / 'second-brain.json').read_text())['vault_path'], str(self.vault))

    def test_existing_workspace_credentials_are_preserved(self):
        state = self.workspace / '.chief-of-staff-state'
        state.mkdir()
        token = state / 'google_token.json'
        token.write_text('existing refreshed credential', encoding='utf-8')
        (self.chief / 'runtime/state/google_token.json').write_text('older seed', encoding='utf-8')
        result = self.initialize()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(token.read_text(), 'existing refreshed credential')

    def test_reset_then_initialization_does_not_restore_bundled_evidence(self):
        self.workspace.rename(self.root / 'CoS_Workspace')
        self.workspace = self.root / 'CoS_Workspace'
        self.vault = self.workspace / 'CoS_SecondBrain'
        seed = self.chief / 'runtime/state/chief-of-staff'
        live = self.workspace / '.chief-of-staff-state/chief-of-staff'
        stale = '{"generated_at":"2026-09-29T17:02:04Z"}'
        for folder in (seed, live):
            folder.mkdir(parents=True)
            (folder / 'snapshot.json').write_text(stale, encoding='utf-8')
            run = folder / ('daily-brief-' + 'a' * 32)
            run.mkdir()
            (run / 'snapshot.json').write_text(stale, encoding='utf-8')
            (run / 'packet.json').write_text(stale, encoding='utf-8')

        removed = evidence_cache.clear_evidence_cache(self.root)
        self.assertEqual(removed, {'run_folders_removed': 1, 'files_removed': 3})
        for _ in range(2):
            result = self.initialize()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(list(self.workspace.rglob('snapshot.json')), [])
            self.assertEqual(list(self.workspace.rglob('packet.json')), [])
        self.assertEqual((seed / 'snapshot.json').read_text(), stale)
        self.assertTrue((self.vault / 'index.md').exists())


if __name__ == '__main__':
    unittest.main()
