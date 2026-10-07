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
            for skill in ('chief-of-staff',):
                folder = source / 'skills/productivity' / skill
                (folder / 'scripts').mkdir(parents=True)
                (folder / 'SKILL.md').write_text('Skill instructions')
            for helper in ('cos-actions.exe', 'run-actions.ps1', 'run-second-brain.ps1', 'daily_brief.ps1'):
                (source / 'skills/productivity/chief-of-staff/scripts' / helper).write_text('# helper')
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
            for helper in ('cos-actions.exe', 'run-actions.ps1', 'run-second-brain.ps1', 'daily_brief.ps1'):
                self.assertEqual((chief / 'scripts' / helper).read_text(), '# helper')
            self.assertFalse((skills / 'productivity/ingest').exists())
            self.assertFalse((chief / 'notes').exists())
            self.assertFalse((chief / 'runtime/state/second-brain.json').exists())
            self.assertFalse((chief / 'runtime/state/chief-of-staff').exists())
            token = chief / 'runtime/state/google_token.json'
            token.write_text('refreshed credential')
            legacy = skills / 'productivity/ingest'
            legacy.mkdir()
            (legacy / 'SKILL.md').write_text('Old standalone skill')
            (legacy / 'private-state.json').write_text('Preserve this')
            (chief / 'scripts/actions.py').write_text('retired code')
            result = installer.install(source, skills)
            self.assertFalse((chief / 'scripts/actions.py').exists())
            self.assertEqual((Path(result['retired_python_backup']) / 'scripts/actions.py').read_text(), 'retired code')
            backup = Path(result['retired_ingest_backup'])
            self.assertFalse(backup.is_relative_to(skills))
            self.assertEqual((backup / 'SKILL.md').read_text(), 'Old standalone skill')
            self.assertEqual((backup / 'private-state.json').read_text(), 'Preserve this')
            self.assertFalse(legacy.exists())
            self.assertFalse((source / 'skills/productivity/ingest').exists())
            self.assertIsNone(installer.install(source, skills)['retired_ingest_backup'])
            self.assertEqual(token.read_text(), 'refreshed credential')
            self.assertFalse((chief / 'runtime/state/chief-of-staff').exists())
            self.assertFalse((chief / 'notes').exists())
            self.assertEqual(json.loads((chief / 'runtime-local.json').read_text())['seed_state_root'], 'runtime/state')
            # Refresh must also produce a self-contained code-only bundle.
            staging = source / '.pplx-runtime/skills'
            old = staging / 'productivity/ingest'
            old.mkdir(parents=True)
            (old / 'SKILL.md').write_text('Old staging skill')
            installer.install_code(source, staging)
            self.assertFalse(old.exists())
            for helper in ('cos-actions.exe', 'run-actions.ps1', 'run-second-brain.ps1', 'daily_brief.ps1'):
                self.assertEqual((staging / 'productivity/chief-of-staff/scripts' / helper).read_text(), '# helper')

    def test_refresh_removes_old_public_helper_rows(self):
        spec = importlib.util.spec_from_file_location('refresh', Path(__file__).with_name('refresh-from-git.py'))
        refresh = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(refresh)
        source = '''---
name: chief-of-staff
description: Chief of Staff
---
| `ingest.py` | Collect evidence. | Follow the ingest skill. |
| `brief.py` | Build a packet. | Run after ingest. |
| `actions.py` | Read and edit Google data. | Old direct invocation. |
| `daily_brief.ps1` | Build evidence. | Follow task guidance. |
'''
        result = refresh.adapt(source, 'chief-of-staff')
        self.assertNotIn('| `ingest.py` |', result)
        self.assertNotIn('| `brief.py` |', result)
        self.assertNotIn('| `actions.py` |', result)
        self.assertIn('| `run-actions.ps1` | Read and edit Google data.', result)
        self.assertIn('| `daily_brief.ps1` |', result)

    def test_refresh_normalizes_legacy_helper_paths(self):
        spec = importlib.util.spec_from_file_location('refresh', Path(__file__).with_name('refresh-from-git.py'))
        refresh = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(refresh)
        old = 'skills/productivity/ingest/scripts/'
        new = 'skills/productivity/chief-of-staff/scripts/'
        test = 'skills/productivity/ingest/tests/test_ingest.py'
        source = {old + 'ingest.py': b'legacy', new + 'actions.py': b'current',
                  old + 'actions.py': b'old actions',
                  test: b'ROOT = Path(__file__).resolve().parents[1]'}
        result = refresh.consolidate_helpers(source)
        self.assertEqual(result[new + 'ingest.py'], b'legacy')
        self.assertEqual(result[new + 'actions.py'], b'current')
        self.assertFalse(any(path.startswith(old) for path in result))
        self.assertIn(b'parents[2] / "chief-of-staff"', result[test])
        self.assertEqual(refresh.consolidate_helpers(result), result)


if __name__ == '__main__':
    unittest.main()
