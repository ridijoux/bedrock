"""Credentials and dotenv provisioning without recovery infrastructure."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / file)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


provision = load('provision', 'provision.py')
merge = load('merge', 'merge-env.py')


class ProvisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.token = Path(self.temp.name) / 'op-token'
        p = patch.object(provision, 'TOKEN', self.token)
        p.start()
        self.addCleanup(p.stop)

    def test_login_reuses_token_without_reprompting(self):
        self.token.write_text('saved\n')
        with patch.object(provision, 'run', return_value=subprocess.CompletedProcess([], 0, stdout='{}')) as run, \
             patch.object(provision.getpass, 'getpass') as prompt, \
             patch.object(provision.os, 'geteuid', return_value=0), \
             patch.object(provision.sys, 'argv', ['provision.py', 'login']):
            provision.main()
        prompt.assert_not_called()
        self.assertEqual(run.call_args.args[0][:3], ['op', 'vault', 'get'])
        self.assertEqual(run.call_args.kwargs['env']['OP_SERVICE_ACCOUNT_TOKEN'], 'saved')

    def test_login_token_is_private(self):
        with patch.object(provision.getpass, 'getpass', return_value='test-token'), \
             patch.object(provision, 'op', return_value='{}'), \
             patch.object(provision.os, 'geteuid', return_value=0), \
             patch.object(provision.sys, 'argv', ['provision.py', 'login']):
            provision.main()
        self.assertEqual(self.token.read_text(), 'test-token\n')
        self.assertEqual(self.token.stat().st_mode & 0o777, 0o600)

    def test_removed_backup_actions_are_rejected(self):
        with patch.object(provision.os, 'geteuid', return_value=0):
            for action in ('setup-backup', 'recover-backup', 'sync-backup', 'validate-backup'):
                with self.subTest(action=action), patch.object(provision.sys, 'argv', ['provision.py', action]):
                    with self.assertRaisesRegex(ValueError, 'Unknown'):
                        provision.main()

    def test_merge_preserves_settings_and_deduplicates(self):
        incoming = Path(self.temp.name) / 'incoming'
        target = Path(self.temp.name) / '.env'
        incoming.write_text('TELEGRAM_BOT_TOKEN=new\n')
        target.write_text('# settings\nMODEL=custom\nTELEGRAM_BOT_TOKEN=old\nTELEGRAM_BOT_TOKEN=old2\n')
        with patch.object(merge.os, 'chown'), patch.object(merge.sys, 'argv', ['merge', str(incoming), str(target)]):
            merge.main()
        self.assertEqual(target.read_text(), '# settings\nMODEL=custom\nTELEGRAM_BOT_TOKEN=new\n')
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_group_chat_cannot_be_used_as_personal_allowlist(self):
        item = {'fields': [{'label': 'TELEGRAM_BOT_TOKEN', 'value': '123:abc'},
                           {'label': 'TELEGRAM_CHAT_ID', 'value': '-100123'}]}
        with patch.object(provision, 'op', return_value=json.dumps(item)):
            with self.assertRaisesRegex(ValueError, 'positive'):
                provision.sync_secrets()

    def test_dashboard_credentials_required_before_sync(self):
        item = {'fields': [{'label': 'TELEGRAM_BOT_TOKEN', 'value': '123:abc'},
                           {'label': 'TELEGRAM_CHAT_ID', 'value': '123'}]}
        with patch.object(provision, 'op', return_value=json.dumps(item)):
            with self.assertRaisesRegex(ValueError, 'HERMES_DASHBOARD_BASIC_AUTH_USERNAME'):
                provision.sync_secrets()

    def test_credentials_sync_uses_only_hermes_env(self):
        item = {'fields': [{'label': 'TELEGRAM_BOT_TOKEN', 'value': '123:abc'},
                           {'label': 'TELEGRAM_CHAT_ID', 'value': '123'},
                           {'label': 'HERMES_DASHBOARD_BASIC_AUTH_USERNAME', 'value': 'user'},
                           {'label': 'HERMES_DASHBOARD_BASIC_AUTH_PASSWORD', 'value': 'password-long-enough'},
                           {'label': 'HERMES_DASHBOARD_BASIC_AUTH_SECRET', 'value': 's' * 32}]}
        with patch.object(provision, 'op', return_value=json.dumps(item)), \
             patch.object(provision, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
            provision.sync_secrets()
        self.assertEqual(run.call_count, 1)
        self.assertIn('merge-env.py', ' '.join(run.call_args.args[0]))
