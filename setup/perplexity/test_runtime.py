"""Offline regression checks for Perplexity startup. No Google requests."""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
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
SKILLS = Path(os.environ.get('PPLX_SKILLS_DIR', ROOT / 'out/unused-skills'))
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
        (self.chief / 'runtime/state').mkdir(parents=True)
        (self.chief / 'tests/fixtures').mkdir(parents=True)
        shutil.copy2(ROOT / 'skills/productivity/chief-of-staff/tests/fixtures/workspace.json',
                     self.chief / 'tests/fixtures/workspace.json')
        (self.chief / 'runtime-local.json').write_text(json.dumps({
            'format_version': 5, 'seed_state_root': 'runtime/state',
            'runtime_backend': 'rust'}), encoding='utf-8')
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
                       '\n[PSCustomObject]@{executable=$CosExecutable;state=$env:COS_STATE_DIR} | ConvertTo-Json -Compress')

    def test_native_executable_and_workspace_state(self):
        result = self.initialize()
        self.assertEqual(result.returncode, 0, result.stderr)
        info = json.loads(result.stdout)
        self.assertEqual(Path(info['executable']), self.chief / 'scripts/cos-actions.exe')
        self.assertEqual(Path(info['state']), self.workspace / '.chief-of-staff-state')

    def test_second_brain_launcher_search_and_read_in_fresh_shells(self):
        note = self.vault / 'Café project.md'
        content = '# Café project\nNeoAgent launch decisions and owners.\n'
        note.write_text(content, encoding='utf-8')
        launcher = '& ' + quoted(self.chief / 'scripts/run-second-brain.ps1')
        setup = launcher + ' -WorkspaceRoot ' + quoted(self.workspace)
        search = self.ps(setup + " search 'NeoAgent launch' --max 1")
        self.assertEqual(search.returncode, 0, search.stderr)
        self.assertEqual([n['note'] for n in json.loads(search.stdout)['notes']], [note.name])
        read = self.ps(setup + ' read ' + quoted(note.name) + ' --max-chars 25')
        self.assertEqual(read.returncode, 0, read.stderr)
        result = json.loads(read.stdout)
        self.assertEqual(result['text'], content.strip()[:25])
        self.assertTrue(result['truncated'])
        self.assertEqual(note.read_text(encoding='utf-8'), content)

    def test_second_brain_launcher_stops_on_initialization_error(self):
        result = self.ps('& ' + quoted(self.chief / 'scripts/run-second-brain.ps1') +
                         ' -WorkspaceRoot ' + quoted(self.root / 'missing') + " read 'index.md'")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), '')
        self.assertFalse((self.root / 'missing').exists())

    def test_second_brain_launcher_propagates_helper_errors(self):
        result = self.ps('& ' + quoted(self.chief / 'scripts/run-second-brain.ps1') +
                         ' -WorkspaceRoot ' + quoted(self.workspace) + " read '../outside.md'")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('error', result.stderr)

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

    def test_no_python_or_profile_required(self):
        self.env.pop('PPLX_SKILLS_DIR', None)
        self.env['PATH'] = ''
        result = self.ps('& ' + quoted(self.chief / 'scripts/daily_brief.ps1') + ' -WorkspaceRoot ' + quoted(self.workspace) + ' -Fixture')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('packet_path', result.stdout)

    def test_missing_executable_stops_before_writes(self):
        (self.chief / 'scripts/cos-actions.exe').unlink()
        result = self.initialize()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('installation is incomplete', result.stderr)
        self.assertFalse((self.workspace / '.chief-of-staff-state').exists())

    def test_batch_preserves_quoted_unicode_arguments(self):
        (self.vault / 'quoted.md').write_text('# Quoted\nShe said "ready", Café.\n', encoding='utf-8')
        result = self.ps('& ' + quoted(self.chief / 'scripts/run-actions.ps1') + ' -WorkspaceRoot ' + quoted(self.workspace) + ''' -Batch {
            action second-brain search '"ready" Café' --max 1
            action second-brain read 'quoted.md'
        }''')
        self.assertEqual(result.returncode, 0, result.stderr)
        results = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(results[0]['notes'][0]['note'], 'quoted.md')
        self.assertIn('"ready", Café', results[1]['text'])

    def test_piped_bom_json_reaches_validation_without_api_call(self):
        state = self.workspace / '.chief-of-staff-state'
        state.mkdir()
        (state / 'google_token.json').write_text('{"token":"offline-placeholder"}')
        # Invalid status is rejected before the API is called. No network needed.
        payload = json.dumps([{'lane': 'Café', 'status': 'not-a-status'}], ensure_ascii=False)
        command = "([char]0xfeff + " + quoted(payload) + ') | & ' + quoted(self.chief / 'scripts/run-actions.ps1') + ' -WorkspaceRoot ' + quoted(self.workspace) + ' sheets update-lanes offline --updates-file - --confirm'
        result = self.ps(command)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Invalid status for', result.stderr)
        self.assertNotIn('expected value', result.stderr)

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
        result = subprocess.run([str(self.chief / 'scripts/cos-actions.exe'), 'daily-brief',
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

    def test_matching_connection_is_not_rewritten(self):
        self.assertEqual(self.initialize().returncode, 0)
        connection = self.workspace / '.chief-of-staff-state/second-brain.json'
        # Formatting and unrelated settings do not require rewriting a matching path.
        content = json.dumps({'vault_path': str(self.vault), 'extra': 'preserve'})
        connection.write_text(content, encoding='utf-8')
        os.utime(connection, (1_600_000_000, 1_600_000_000))
        before = connection.stat().st_mtime_ns
        result = self.initialize()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(connection.read_text(encoding='utf-8'), content)
        self.assertEqual(connection.stat().st_mtime_ns, before)

    def test_parallel_initializations_seed_once_and_preserve_config(self):
        seed = self.chief / 'runtime/state'
        names = ['google_token.json', 'google_client_secret.json',
                 'chief-of-staff-workspace-state.json']
        for name in names:
            (seed / name).write_text(json.dumps({'fixture': name}), encoding='utf-8')
        for round_number in range(2):
            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(lambda _: self.initialize(), range(8)))
            for result in results:
                self.assertEqual(result.returncode, 0, result.stderr)
            state = self.workspace / '.chief-of-staff-state'
            for name in names:
                self.assertEqual((state / name).read_bytes(), (seed / name).read_bytes())
            config = state / 'second-brain.json'
            self.assertEqual(json.loads(config.read_text())['vault_path'], str(self.vault))
            if round_number == 0:
                timestamp = config.stat().st_mtime_ns
            else:
                self.assertEqual(config.stat().st_mtime_ns, timestamp)

    def test_initialization_error_releases_lock(self):
        state = self.workspace / '.chief-of-staff-state'
        state.mkdir()
        connection = state / 'second-brain.json'
        connection.mkdir()  # Force the connection write to fail after lock acquisition.
        failed = self.initialize()
        self.assertNotEqual(failed.returncode, 0)
        connection.rmdir()
        succeeded = self.initialize()
        self.assertEqual(succeeded.returncode, 0, succeeded.stderr)

    def test_stale_or_malformed_connection_is_repaired(self):
        state = self.workspace / '.chief-of-staff-state'
        state.mkdir()
        connection = state / 'second-brain.json'
        for content in ['not json', json.dumps({'vault_path': str(self.root / 'old-vault')})]:
            connection.write_text(content, encoding='utf-8')
            result = self.initialize()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(connection.read_text())['vault_path'], str(self.vault))

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
        self.assertEqual(removed, {'folders_removed': 1, 'files_removed': 3})
        for _ in range(2):
            result = self.initialize()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(list(self.workspace.rglob('snapshot.json')), [])
            self.assertEqual(list(self.workspace.rglob('packet.json')), [])
        self.assertEqual((seed / 'snapshot.json').read_text(), stale)
        self.assertTrue((self.vault / 'index.md').exists())


if __name__ == '__main__':
    unittest.main()
