"""Offline parity against the retained Python reference; never calls Google APIs."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills/productivity/chief-of-staff'
REFERENCE = ROOT / 'compat/python-runtime/scripts'
if not REFERENCE.exists():
    REFERENCE = SKILL / 'scripts'
EXE = Path(os.environ.get('COS_TEST_EXE', ROOT / 'out/experiments-20261007/rust-actions/target/debug/cos-actions.exe'))


class Parity(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        self.env = {**os.environ, 'COS_STATE_DIR': str(self.state), 'PYTHONUTF8': '1'}
        self.fixture = json.loads((SKILL / 'tests/fixtures/workspace.json').read_text())

    def run_command(self, native, script, *args):
        prefix = [str(EXE), {'second_brain': 'second-brain', 'daily_brief': 'daily-brief'}.get(script, script)] if native else [sys.executable, '-X', 'utf8', '-B', str(REFERENCE / (script + '.py'))]
        return subprocess.run([*prefix, *map(str, args)], capture_output=True, text=True, encoding='utf-8', env=self.env)

    def compare(self, script, *args):
        expected, actual = [self.run_command(native, script, *args) for native in (False, True)]
        self.assertEqual(actual.returncode, expected.returncode, actual.stderr + expected.stderr)
        self.assertEqual(actual.returncode, 0, actual.stderr + expected.stderr)
        self.assertEqual(json.loads(actual.stdout), json.loads(expected.stdout))

    def test_packets(self):
        for kind in ('standard', 'tasks', 'empty', 'large'):
            data = copy.deepcopy(self.fixture)
            if kind == 'tasks':
                data['tasks'] = [{'id': 't1', 'title': 'Prepare launch', 'notes': 'See https://mail.google.com/mail/u/0/#all/abc', 'due': '2026-08-12', 'status': 'needsAction'}, {'id': 't2', 'title': 'Ünicode task', 'notes': 'Résumé 🧭', 'due': '2026-08-10'}]
            if kind == 'empty':
                data.update(events=[], messages=[], files=[], tasks=[])
            if kind == 'large':
                for field in ('messages', 'files', 'events'):
                    data[field] = data[field] * 8
                for item in data['messages']:
                    item['snippet'] = 'Unicode Ω 🧭 and long evidence. ' * 30
            path = self.state / 'snapshot.json'
            path.write_text(json.dumps(data), encoding='utf-8')
            for mode in ('daily-brief', 'second-brain-update'):
                for limit in (14000, 7000):
                    with self.subTest(kind=kind, mode=mode, limit=limit):
                        self.compare('brief', '--snapshot', path, '--mode', mode, '--max-chars', limit)

    def test_ingest_fixture(self):
        self.compare('ingest', '--fixture', SKILL / 'tests/fixtures/workspace.json', '--output', self.state / 'snapshot.json', '--stdout', 'json')

    def test_second_brain(self):
        vault = self.state / 'vault'
        vault.mkdir()
        (self.state / 'second-brain.json').write_text(json.dumps({'vault_path': str(vault)}))
        (vault / 'launch.md').write_text('---\ntitle: Launch review\nupdated: 2026-08-11\n---\n# Launch review\nThe exec launch decision has Unicode 🧭 context.\n', encoding='utf-8')
        (vault / 'customer.md').write_text('# Customer launch review\nCustomer discussion is background only.\n', encoding='utf-8')
        self.compare('second_brain', 'search', 'launch review')
        self.compare('second_brain', 'read', 'launch.md', '--max-chars', 20)
        path = self.state / 'snapshot.json'
        path.write_text(json.dumps(self.fixture))
        self.compare('brief', '--snapshot', path)

    def test_daily_brief(self):
        packets = []
        for native in (False, True):
            result = self.run_command(native, 'daily_brief', '--fixture', SKILL / 'tests/fixtures/workspace.json')
            self.assertEqual(result.returncode, 0, result.stderr)
            receipt, text = result.stdout.split('\n', 1)
            path = Path(json.loads(receipt)['packet_path'])
            self.assertTrue(path.is_relative_to(self.state))
            self.assertEqual(json.loads(text), json.loads(path.read_text(encoding='utf-8')))
            packets.append(json.loads(text))
        self.assertEqual(*packets)


if __name__ == '__main__':
    unittest.main()
