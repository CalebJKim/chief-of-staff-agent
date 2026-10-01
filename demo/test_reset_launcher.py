"""Reset routing checks using temporary state and a stub seeder. No Google writes."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).parent))
import reset_workspace as reset
import seed_workspace as seed


class ResetStateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.state = self.root / 'CoS_Workspace/.chief-of-staff-state'
        self.state.mkdir(parents=True)
        for name in ('google_token.json', 'chief-of-staff-workspace-state.json'):
            (self.state / name).write_text('{}')
        templates = self.root / 'demo/templates'
        templates.mkdir(parents=True)
        with ZipFile(templates / 'CoS_SecondBrain.zip', 'w') as archive:
            archive.writestr('index.md', '# Baseline')
        self.env = patch.dict(os.environ, {'COS_STATE_DIR': str(self.root / 'wrong'),
                                           'HERMES_HOME': str(self.root / 'wrong')})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_check_is_read_only_and_uses_checkout_even_with_inherited_state(self):
        output = io.StringIO()
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with patch.object(reset, 'ROOT', self.root), patch.object(reset.subprocess, 'call') as delegate, contextlib.redirect_stdout(output):
            self.assertEqual(reset.main(['--check']), 0)
        delegate.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())['state'], str(self.state))
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        self.assertFalse((self.state.parent / 'CoS_SecondBrain').exists())

    def test_reset_delegates_once_with_same_python_state_and_week(self):
        with patch.object(reset, 'ROOT', self.root), patch.object(reset.subprocess, 'call', return_value=7) as delegate:
            self.assertEqual(reset.main(['--week-of', '2026-09-28']), 7)
        delegate.assert_called_once_with([sys.executable, str(self.root / 'demo/seed_workspace.py'),
                                         '--reset', '--confirm', '--week-of', '2026-09-28'])
        self.assertEqual(os.environ['COS_STATE_DIR'], str(self.state))

    def test_missing_state_and_bad_baseline_prevent_google_reset(self):
        for path in (self.state / 'chief-of-staff-workspace-state.json', self.root / 'demo/templates/CoS_SecondBrain.zip'):
            original = path.read_bytes()
            path.unlink()
            with patch.object(reset, 'ROOT', self.root), patch.object(reset.subprocess, 'call') as delegate:
                with self.assertRaises((SystemExit, FileNotFoundError)):
                    reset.main([])
            delegate.assert_not_called()
            path.write_bytes(original)

    def test_direct_seeder_ignores_legacy_variable_and_aligns_credentials(self):
        os.environ.pop('COS_STATE_DIR')
        with patch.object(seed, 'ROOT', self.root):
            self.assertEqual(seed.state_path(), self.state / seed.STATE_FILE)
        self.assertEqual(os.environ['COS_STATE_DIR'], str(self.state))


@unittest.skipUnless(os.name == 'nt', 'Windows launcher')
class PowerShellResetTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.demo = self.root / 'demo'
        self.demo.mkdir()
        shutil.copy2(Path(__file__).with_name('reset_workspace.ps1'), self.demo)
        (self.demo / 'reset_workspace.py').write_text('import json,sys\nprint(json.dumps({"python":sys.executable,"args":sys.argv[1:]}))')
        self.env = os.environ.copy()
        self.env.pop('PPLX_SKILLS_DIR', None)
        self.env['HERMES_HOME'] = str(self.root / 'wrong')
        self.shell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'

    def run_script(self, *args):
        return subprocess.run([str(self.shell), '-NoProfile', '-NonInteractive', '-File',
                               str(self.demo / 'reset_workspace.ps1'), *args],
                              env=self.env, cwd=self.root, capture_output=True, text=True, timeout=30)

    def test_auto_discovers_perplexity_and_forwards_arguments(self):
        result = self.run_script('-Check', '-WeekOf', '2026-09-28')
        self.assertEqual(result.returncode, 0, result.stderr)
        info = json.loads(result.stdout)
        self.assertIn('template\\venv\\scripts\\python.exe', info['python'].lower())
        self.assertEqual(info['args'], ['--check', '--week-of', '2026-09-28'])

    def test_absent_managed_python_uses_system_python(self):
        self.env['PATH'] = str(Path(sys.executable).parent)
        result = self.run_script('-SkillsDir', str(self.root / 'account/skills'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(json.loads(result.stdout)['python']), Path(sys.executable))

    def test_failure_is_propagated_without_retry(self):
        (self.demo / 'reset_workspace.py').write_text('raise SystemExit(9)')
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('exit 9', result.stderr)

    def test_ambiguous_accounts_require_explicit_selection(self):
        self.env['USERPROFILE'] = str(self.root)
        for name in ('one', 'two'):
            skill = self.root / '.pplx/users' / name / 'skills/productivity/chief-of-staff/SKILL.md'
            skill.parent.mkdir(parents=True)
            skill.write_text('# Example')
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Multiple Perplexity installations', result.stderr)

    def test_missing_python_stops_and_excludes_legacy_interpreter(self):
        legacy = self.root / 'hermes/venv/Scripts'
        legacy.mkdir(parents=True)
        (legacy / 'python.exe').touch()
        self.env['PATH'] = str(legacy)
        result = self.run_script('-SkillsDir', str(self.root / 'account/skills'))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('No Perplexity or system Python', result.stderr)


if __name__ == '__main__':
    unittest.main()
