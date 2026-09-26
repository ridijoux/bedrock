import contextlib
import importlib.util
import io
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
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


provision = load('provision', 'provision.py')
merge = load('merge', 'merge-env.py')
CONFIG = '''[hermes-drive]
type = drive
token = {"access_token":"test","refresh_token":"refresh"}
[hermes-crypt]
type = crypt
remote = hermes-drive:bedrock-backups
password = test-obscured
password2 = test-salt
filename_encryption = standard
directory_name_encryption = true
'''


class ProvisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'rclone.conf'
        p = patch.object(provision, 'CONFIG', self.path)
        p.start()
        self.addCleanup(p.stop)

    def test_refuses_unencrypted_remote(self):
        with self.assertRaises(ValueError):
            provision.parse_config(CONFIG.replace('type = crypt', 'type = alias'))

    def test_refuses_disabled_content_encryption(self):
        with self.assertRaisesRegex(ValueError, 'content encryption'):
            provision.parse_config(CONFIG + 'no_data_encryption = true\n')

    def test_first_setup_publishes_keys_before_probe(self):
        events = []
        def authorize(env):
            Path(env['RCLONE_CONFIG']).write_text(CONFIG.split('[hermes-crypt]')[0])
        def run(args, **kwargs):
            if args[1] == 'obscure':
                return subprocess.CompletedProcess(args, 0, stdout='obscured-' + kwargs['input'])
            events.append(args[3])
            return subprocess.CompletedProcess(args, 0)
        with patch.object(provision, 'document_id', return_value=None), patch.object(provision.os, 'chown'), patch.object(provision, 'authorize_drive', side_effect=authorize), patch.object(provision, 'run', side_effect=run), patch.object(provision, 'sync_backup', side_effect=lambda: events.append('escrow')):
            provision.setup_backup()
        config = provision.parse_config(self.path.read_text())
        self.assertNotEqual(config['hermes-crypt']['password'], config['hermes-crypt']['password2'])
        self.assertEqual(events, ['escrow', 'mkdir', 'lsf'])
        self.assertFalse(self.path.with_name('rclone.pending.conf').exists())

    def test_failed_escrow_keeps_generated_keys_for_retry(self):
        def authorize(env):
            Path(env['RCLONE_CONFIG']).write_text(CONFIG.split('[hermes-crypt]')[0])
        with patch.object(provision, 'document_id', return_value=None), patch.object(provision.os, 'chown'), patch.object(provision, 'authorize_drive', side_effect=authorize), patch.object(provision, 'run', return_value=subprocess.CompletedProcess([], 0, stdout='obscured')), patch.object(provision, 'sync_backup', side_effect=ValueError('vault write failed')):
            with self.assertRaisesRegex(ValueError, 'vault write'):
                provision.setup_backup()
        generated = self.path.read_text()
        with patch.object(provision, 'document_id', return_value=None), patch.object(provision, 'sync_backup'), patch.object(provision, 'run'), patch.object(provision, 'authorize_drive') as auth:
            provision.setup_backup()
            auth.assert_not_called()
        self.assertEqual(self.path.read_text(), generated)

    def test_recovery_missing_keys_never_generates(self):
        with patch.object(provision, 'document_id', return_value=None), patch.object(provision, 'authorize_drive') as auth:
            with self.assertRaisesRegex(ValueError, 'No recovery'):
                provision.setup_backup(recovery=True)
            auth.assert_not_called()
        self.assertFalse(self.path.exists())

    def test_vault_outage_never_generates_keys(self):
        with patch.object(provision, 'op', side_effect=subprocess.CalledProcessError(1, ['op'])), patch.object(provision, 'authorize_drive') as auth:
            with self.assertRaises(subprocess.CalledProcessError):
                provision.setup_backup()
            auth.assert_not_called()
        self.assertFalse(self.path.exists())

    def test_duplicates_fail_closed(self):
        items = [{'title': 'rclone.conf', 'id': 'one'}, {'title': 'rclone.conf', 'id': 'two'}]
        with patch.object(provision, 'op', return_value=json.dumps(items)):
            with self.assertRaisesRegex(ValueError, 'Multiple'):
                provision.document_id()

    def test_changed_key_cannot_overwrite_recovery(self):
        self.path.write_text(CONFIG.replace('test-obscured', 'new-key'))
        with patch.object(provision, 'document_id', return_value='doc'), patch.object(provision, 'op', return_value=CONFIG) as op:
            with self.assertRaisesRegex(ValueError, 'Refusing'):
                provision.sync_backup()
            self.assertEqual(op.call_count, 1)

    def test_refresh_token_is_synchronized_and_read_back(self):
        renewed = CONFIG.replace('"refresh"', '"renewed"')
        self.path.write_text(renewed)
        with patch.object(provision, 'document_id', return_value='doc'), patch.object(provision, 'op', side_effect=[CONFIG, '', renewed]) as op:
            provision.sync_backup()
        self.assertEqual(op.call_args_list[1].args[:3], ('document', 'edit', 'doc'))
        self.assertEqual(op.call_args_list[2].args[:3], ('document', 'get', 'doc'))

    def test_failed_readback_fails(self):
        self.path.write_text(CONFIG)
        with patch.object(provision, 'document_id', return_value=None), patch.object(provision, 'op', side_effect=['{"id":"doc"}', 'damaged']):
            with self.assertRaisesRegex(ValueError, 'read-back'):
                provision.sync_backup()

    def test_existing_keys_reused_without_oauth(self):
        self.path.write_text(CONFIG)
        with patch.object(provision, 'document_id', return_value='doc'), patch.object(provision, 'op', return_value=CONFIG), patch.object(provision, 'sync_backup'), patch.object(provision, 'run'), patch.object(provision, 'authorize_drive') as auth:
            provision.setup_backup()
            provision.setup_backup()
            auth.assert_not_called()
        self.assertEqual(self.path.read_text(), CONFIG)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_recovery_restores_configuration(self):
        with patch.object(provision, 'document_id', return_value='doc'), patch.object(provision, 'op', return_value=CONFIG), patch.object(provision.os, 'chown'), patch.object(provision, 'sync_backup'), patch.object(provision, 'run') as run:
            provision.setup_backup(recovery=True)
        self.assertEqual([call.args[0][3] for call in run.call_args_list], ['lsf'])
        self.assertEqual(self.path.read_text(), CONFIG)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_oauth_stdout_does_not_expose_token(self):
        class Process:
            stdout = iter(['Open http://127.0.0.1:53682/auth?state=xyz\n', 'token = PRIVATE-TOKEN\n'])
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def wait(self): return 0
        output = io.StringIO()
        with patch.object(provision.subprocess, 'Popen', return_value=Process()) as call, contextlib.redirect_stdout(output):
            provision.authorize_drive({})
        self.assertNotIn('PRIVATE-TOKEN', output.getvalue())
        self.assertIn('http://127.0.0.1:', output.getvalue())
        self.assertNotIn('--no-output', call.call_args.args[0])
        self.assertIn('config_auth_no_browser', call.call_args.args[0])

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
        item = {'fields': [{'label': 'TELEGRAM_BOT_TOKEN', 'value': '123:abc'}, {'label': 'TELEGRAM_CHAT_ID', 'value': '-100123'}]}
        with patch.object(provision, 'op', return_value=json.dumps(item)):
            with self.assertRaisesRegex(ValueError, 'positive'):
                provision.sync_secrets()
