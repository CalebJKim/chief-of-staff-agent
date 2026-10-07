"""Offline tests of real Git Bash launchers; no Google reads or writes."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills/productivity/chief-of-staff/scripts'
BASH = Path('C:/Program Files/Git/bin/bash.exe')

@unittest.skipUnless(BASH.exists(), 'Git Bash required')
class NativeLaunchers(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='cos native ')
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        vault = self.state / 'vault'
        vault.mkdir()
        (vault / 'launch.md').write_text('# Launch review\nUnicode café and quoted input.', encoding='utf-8')
        self.config = self.state / 'second-brain.json'
        self.config.write_text(json.dumps({'vault_path': str(vault)}))
        self.before = self.config.read_bytes()
        self.env = dict(os.environ, HERMES_HOME=str(self.state))
        self.env.pop('COS_STATE_DIR', None)

    def call(self, launcher, *args, stdin=None):
        return subprocess.run([str(BASH), str(SCRIPTS / launcher), *map(str,args)],
            input=stdin, capture_output=True, text=True, encoding='utf-8', env=self.env)

    def test_read_and_search_use_profile_without_rewriting_config(self):
        for args in [('read','launch.md'), ('search','launch')]:
            result = self.call('run-second-brain.sh', *args)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('launch', result.stdout.lower())
        self.assertEqual(self.before, self.config.read_bytes())

    def test_batch_and_single_share_initialization(self):
        result = self.call('run-actions.sh', '--batch', stdin="action second-brain read 'launch.md'\naction second-brain search 'launch'\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertGreaterEqual(result.stdout.lower().count('launch'), 2)

    def test_batch_stops_on_error(self):
        result = self.call('run-actions.sh', '--batch', stdin="action invalid command\nprintf 'SHOULD_NOT_RUN'\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('SHOULD_NOT_RUN', result.stdout)

    def test_daily_brief_fixture(self):
        result = self.call('daily_brief.sh', '--fixture', ROOT / 'skills/productivity/chief-of-staff/tests/fixtures/workspace.json')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('packet_path', result.stdout)
        self.assertTrue(list((self.state / 'chief-of-staff').glob('*/packet.json')))

    def test_explicit_state_precedes_profile(self):
        self.env['COS_STATE_DIR'] = str(self.state)
        self.env['HERMES_HOME'] = str(self.state / 'missing')
        result = self.call('run-second-brain.sh', 'read', 'launch.md')
        self.assertEqual(result.returncode, 0, result.stderr)

if __name__ == '__main__':
    unittest.main()
