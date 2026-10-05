"""Offline checks: fake credentials and mocked Google operations only."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


HELPER = Path(__file__).with_name('setup.py')


def load_helper():
    spec = importlib.util.spec_from_file_location('cos_google_setup', HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.state = self.root / 'workspace/.chief-of-staff-state'
        self.hermes = self.root / 'hermes/profile'
        self.environment = patch.dict(os.environ, {
            'COS_STATE_DIR': str(self.state), 'HERMES_HOME': str(self.hermes),
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.helper = load_helper()
        output = contextlib.redirect_stdout(io.StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)

    def test_workspace_state_wins_over_inherited_hermes_home(self):
        self.assertEqual(self.helper.STATE_DIR, self.state)
        self.assertEqual(self.helper.TOKEN_PATH, self.state / 'google_token.json')
        self.assertFalse(self.state.exists())  # Import alone does not write.

    def test_legacy_hermes_resolution_still_works(self):
        with patch.dict(os.environ, {'COS_STATE_DIR': ''}):
            self.assertEqual(load_helper().STATE_DIR, self.hermes)

    def test_reject_relative_state_directory(self):
        with patch.dict(os.environ, {'COS_STATE_DIR': 'wrong-place'}):
            with self.assertRaisesRegex(ValueError, 'absolute'):
                load_helper()

    def test_client_and_pending_files_use_only_selected_state(self):
        client = self.root / 'downloaded-client.json'
        client.write_text(json.dumps({'installed': {'client_id': 'fake-client'}}))
        self.helper.store_client_secret(str(client))
        self.helper._save_pending_auth(state='fake-state', code_verifier='fake-verifier')
        self.assertTrue(self.helper.CLIENT_SECRET_PATH.is_file())
        self.assertTrue(self.helper.PENDING_AUTH_PATH.is_file())
        self.assertFalse(self.hermes.exists())

    def token(self, scopes=None):
        self.state.mkdir(parents=True, exist_ok=True)
        self.helper.TOKEN_PATH.write_text(json.dumps({
            'scopes': self.helper.SCOPES if scopes is None else scopes,
        }))

    def test_valid_connection_reused_without_authorization(self):
        self.token()
        with patch.object(self.helper, 'check_auth', return_value=True), \
             patch.object(self.helper, 'check_auth_live', return_value=True) as live, \
             patch.object(self.helper, 'get_auth_url') as auth:
            self.assertTrue(self.helper.connect())
        live.assert_called_once_with()
        auth.assert_not_called()

    def test_live_failure_does_not_restart_authorization(self):
        self.token()
        with patch.object(self.helper, 'check_auth', return_value=True), \
             patch.object(self.helper, 'check_auth_live', return_value=False), \
             patch.object(self.helper, 'get_auth_url') as auth:
            self.assertFalse(self.helper.connect())
        auth.assert_not_called()

    def test_revoked_token_guides_one_sign_in(self):
        self.token()
        self.helper.CLIENT_SECRET_PATH.write_text('{}')
        callback = 'http://localhost:1/?state=fake&code=fake'
        with patch.object(self.helper, 'check_auth', return_value=False), \
             patch.object(self.helper, 'get_auth_url', return_value='https://accounts.google.com/fake') as auth, \
             patch('webbrowser.open') as browser, \
             patch('getpass.getpass', return_value=callback), \
             patch.object(self.helper, 'exchange_auth_code') as exchange, \
             patch.object(self.helper, 'check_auth_live', return_value=True):
            self.assertTrue(self.helper.connect())
        auth.assert_called_once_with()
        browser.assert_called_once_with('https://accounts.google.com/fake')
        exchange.assert_called_once_with(callback)

    def test_missing_scopes_cannot_report_ready(self):
        self.token(scopes=self.helper.SCOPES[:1])
        self.helper.CLIENT_SECRET_PATH.write_text('{}')
        with patch.object(self.helper, 'check_auth', return_value=True), \
             patch.object(self.helper, 'get_auth_url', return_value='https://accounts.google.com/fake'), \
             patch('webbrowser.open'), \
             patch('getpass.getpass', return_value='http://localhost:1/?state=fake&code=fake'), \
             patch.object(self.helper, 'exchange_auth_code'), \
             patch.object(self.helper, 'check_auth_live') as live:
            self.assertFalse(self.helper.connect())
        live.assert_not_called()

    def test_missing_client_can_be_cancelled_without_auth(self):
        with patch('builtins.input', return_value=''), patch.object(self.helper, 'get_auth_url') as auth:
            self.assertFalse(self.helper.connect())
        auth.assert_not_called()
        self.assertFalse(self.state.exists())


if __name__ == '__main__':
    unittest.main()
