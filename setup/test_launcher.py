"""Run Windows PowerShell against disposable installations; never authenticate."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == 'nt', 'Windows PowerShell launcher')
class LauncherTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repo = self.root / 'demo source'
        self.repo.mkdir()
        shutil.copyfile(ROOT / 'setup.ps1', self.repo / 'setup.ps1')
        helper = self.repo / 'setup/google-workspace/setup.py'
        helper.parent.mkdir(parents=True)
        helper.write_text('''import json,os,sys
print(json.dumps({"state":os.environ.get("COS_STATE_DIR"),"hermes":os.environ.get("HERMES_HOME"),"args":sys.argv[1:]}))
sys.exit(int(os.environ.get("COS_TEST_EXIT", "0")))
''')
        self.workspace = self.repo / 'CoS_Workspace'
        (self.workspace / 'CoS_SecondBrain').mkdir(parents=True)
        self.skills = self.root / 'account/skills'
        skill = self.skills / 'productivity/chief-of-staff/SKILL.md'
        skill.parent.mkdir(parents=True)
        skill.write_text('fake installed skill')
        self.hermes = self.root / 'hermes'
        (self.hermes / 'profiles/chief-of-staff').mkdir(parents=True)
        self.shell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'

    def call(self, *args, prelude='', after='', extra_env=None):
        quote = lambda x: "'" + str(x).replace("'", "''") + "'"
        arguments = ' '.join(str(x) if re.fullmatch(r'-[A-Za-z]+', str(x)) else quote(x) for x in args)
        command = prelude + '\n& ' + quote(self.repo / 'setup.ps1') + ' ' + arguments + '\n' + after
        environment = dict(os.environ, COS_STATE_DIR='unrelated-state', HERMES_HOME='unrelated-profile')
        environment.update(extra_env or {})
        result = subprocess.run([str(self.shell), '-NoProfile', '-NonInteractive', '-Command', command],
                                env=environment, capture_output=True, text=True, timeout=30)
        return result

    def fake_python(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'not an executable: Check must never run it')
        return path

    def test_pplx_selects_managed_python_and_workspace_without_writing(self):
        managed = self.fake_python(self.skills.parent / 'template/venv/Scripts/python.exe')
        result = self.call('-Harness', 'perplexity', '-SkillsDir', self.skills, '-Check')
        self.assertEqual(result.returncode, 0, result.stderr)
        info = json.loads(result.stdout)
        self.assertEqual(Path(info['python']), managed)
        self.assertEqual(Path(info['credential_folder']), self.workspace / '.chief-of-staff-state')
        self.assertFalse((self.workspace / '.chief-of-staff-state').exists())

    def test_hermes_selects_named_profile_and_profile_python(self):
        profile = self.hermes / 'profiles/chief-of-staff'
        managed = self.fake_python(profile / 'hermes-agent/venv/Scripts/python.exe')
        result = self.call('-Harness', 'hermes', '-HermesRoot', self.hermes, '-Check')
        self.assertEqual(result.returncode, 0, result.stderr)
        info = json.loads(result.stdout)
        self.assertEqual(Path(info['credential_folder']), profile)
        self.assertEqual(Path(info['python']), managed)

    def test_hermes_shared_runtime_is_used_when_profile_link_absent(self):
        managed = self.fake_python(self.hermes / 'hermes-agent/venv/Scripts/python.exe')
        result = self.call('-Harness', 'hermes', '-HermesRoot', self.hermes, '-Check')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(json.loads(result.stdout)['python']), managed)

    def test_missing_managed_python_falls_back_to_system(self):
        # Override command discovery only; the real system interpreter runs a
        # tiny fake helper, so execution and environment restoration are tested.
        quoted = str(Path(sys.executable)).replace("'", "''")
        discovery = "function Get-Command { [pscustomobject]@{Source='" + quoted + "'} }"
        after = "@{after_state=$env:COS_STATE_DIR;after_hermes=$env:HERMES_HOME} | ConvertTo-Json -Compress"
        result = self.call('-Harness', 'perplexity', '-SkillsDir', self.skills, prelude=discovery, after=after)
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
        self.assertEqual(Path(rows[0]['state']), self.workspace / '.chief-of-staff-state')
        self.assertEqual(rows[0]['args'], ['--connect'])
        self.assertEqual(rows[-1], {'after_state':'unrelated-state','after_hermes':'unrelated-profile'})

    def test_failed_setup_restores_environment_and_does_not_report_ready(self):
        quoted = str(Path(sys.executable)).replace("'", "''")
        discovery = "function Get-Command { [pscustomobject]@{Source='" + quoted + "'} }; try {"
        after = "} catch { Write-Output 'EXPECTED_FAILURE' }; @{after_state=$env:COS_STATE_DIR;after_hermes=$env:HERMES_HOME} | ConvertTo-Json -Compress"
        result = self.call('-Harness', 'hermes', '-HermesRoot', self.hermes,
                           prelude=discovery, after=after, extra_env={'COS_TEST_EXIT':'7'})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('EXPECTED_FAILURE', result.stdout)
        self.assertNotIn('connection is ready', result.stdout)
        rows = [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
        self.assertEqual(Path(rows[0]['hermes']), self.hermes / 'profiles/chief-of-staff')
        self.assertEqual(rows[-1], {'after_state':'unrelated-state','after_hermes':'unrelated-profile'})

    def test_missing_vault_fails_before_credential_creation(self):
        result = self.call('-Harness', 'perplexity', '-SkillsDir', self.skills,
                           '-WorkspaceRoot', self.root / 'missing', '-Check')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('containing CoS_SecondBrain', result.stderr)
        self.assertFalse((self.root / 'missing').exists())

    def test_relative_workspace_uses_powershell_working_directory(self):
        self.fake_python(self.skills.parent / 'template/venv/Scripts/python.exe')
        directory = str(self.repo).replace("'", "''")
        result = self.call('-Harness', 'perplexity', '-SkillsDir', self.skills,
                           '-WorkspaceRoot', '.\\CoS_Workspace', '-Check',
                           prelude="Set-Location -LiteralPath '" + directory + "'")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(json.loads(result.stdout)['credential_folder']),
                         self.workspace / '.chief-of-staff-state')

    def test_missing_harness_in_check_mode_never_prompts(self):
        result = self.call('-Check')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Pass -Harness', result.stderr)

    def test_interactive_harness_choice(self):
        self.fake_python(self.skills.parent / 'template/venv/Scripts/python.exe')
        # The fake interpreter intentionally fails. Reaching execution proves
        # that omitted Harness was resolved using the prompt.
        result = self.call('-SkillsDir', self.skills, prelude="function Read-Host { 'perplexity' }")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('Choose hermes or perplexity', result.stderr)
        self.assertNotIn('connection is ready', result.stdout)


if __name__ == '__main__':
    unittest.main()
