"""Offline installer checks for an external task workspace."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


spec = importlib.util.spec_from_file_location(
    'workspace_installer', Path(__file__).with_name('install-self-contained.py'))
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class WorkspaceInstallTests(unittest.TestCase):
    def test_install_and_refresh_do_not_bundle_a_vault_or_replace_credentials(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'ChiefOfStaff_PPLX'
            for skill in ('chief-of-staff', 'ingest'):
                folder = source / 'skills/productivity' / skill
                (folder / 'scripts').mkdir(parents=True)
                (folder / 'SKILL.md').write_text('Skill instructions')
            for helper in ('actions.py', 'workspace_formatting.py', 'ingest.py', 'verify.py'):
                (source / 'skills/productivity/ingest/scripts' / helper).write_text('# helper')
            seed = source / '.pplx-state'
            seed.mkdir()
            for name in ('google_token.json', 'google_client_secret.json', 'chief-of-staff-workspace-state.json'):
                (seed / name).write_text('{}')
            evidence = seed / 'chief-of-staff'
            run = evidence / ('daily-brief-' + 'a' * 32)
            run.mkdir(parents=True)
            for path in (evidence / 'snapshot.json', run / 'snapshot.json', run / 'packet.json'):
                path.write_text('stale evidence')
            skills = root / 'installed/skills'
            installer.install(source, skills)
            chief = skills / 'productivity/chief-of-staff'
            for skill in ('chief-of-staff', 'ingest'):
                self.assertEqual((skills / 'productivity' / skill / 'scripts/workspace_formatting.py').read_text(), '# helper')
            self.assertFalse((chief / 'notes').exists())
            self.assertFalse((chief / 'runtime/state/second-brain.json').exists())
            self.assertFalse((chief / 'runtime/state/chief-of-staff').exists())
            token = chief / 'runtime/state/google_token.json'
            token.write_text('refreshed credential')
            installer.install(source, skills)
            self.assertEqual(token.read_text(), 'refreshed credential')
            self.assertFalse((chief / 'runtime/state/chief-of-staff').exists())
            self.assertFalse((chief / 'notes').exists())
            self.assertEqual(json.loads((chief / 'runtime-local.json').read_text())['seed_state_root'], 'runtime/state')


if __name__ == '__main__':
    unittest.main()
