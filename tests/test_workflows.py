"""Exercise production shell control flow with isolated Docker/Drive substitutes."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from test_provision import ROOT

FAKE = r'''#!/usr/bin/env python3
import json, os, pathlib, shutil, sys, zipfile
root = pathlib.Path(os.environ['TEST_ROOT'])
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with (root / 'calls').open('a') as stream:
    stream.write(json.dumps([name, *args]) + '\n')
mode = os.environ.get('FAIL_MODE', '')
if name == 'chown':
    sys.exit(0)
if name == 'docker':
    if args[0] == 'inspect':
        print('sha256:previous')
    elif 'ps' in args:
        print('container-id')
    elif 'backup' in args:
        destination = root / 'data/hermes/backups' / pathlib.Path(args[args.index('--output')+1]).name
        with zipfile.ZipFile(destination, 'w') as archive:
            archive.writestr('config.yaml', 'model: test')
    elif 'import' in args and mode == 'import':
        sys.exit(1)
    elif 'pull' in args and mode == 'pull':
        sys.exit(1)
    elif 'up' in args and mode == 'update' and os.environ.get('HERMES_IMAGE') != 'bedrock-hermes:rollback':
        sys.exit(1)
    sys.exit(0)
if name == 'rclone':
    def local(value):
        return root / 'remote' / value.split(':', 1)[1] if value.startswith('hermes-crypt:') else pathlib.Path(value)
    if args[0] == 'copyto':
        if mode == 'upload' and args[2].startswith('hermes-crypt:'):
            sys.exit(1)
        target = local(args[2]); target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(local(args[1]), target)
    elif args[0] == 'cat':
        sys.stdout.buffer.write(b'corrupt' if mode == 'checksum' else local(args[1]).read_bytes())
    elif args[0] == 'lsf':
        for p in sorted((root / 'remote/daily').glob('*.zip')):
            print(p.name)
    sys.exit(0)
'''


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        scripts = self.root / 'scripts'
        scripts.mkdir()
        for original in (ROOT / 'scripts').iterdir():
            if original.is_file():
                destination = scripts / original.name
                destination.write_text(original.read_text().replace('/etc/bedrock', str(self.root / 'state')))
                destination.chmod(0o755)
        (scripts / 'common.sh').write_text('''set -Eeuo pipefail
umask 077
cd "$TEST_ROOT"
lock() { :; }
require_backup_config() { :; }
prepare_data() { mkdir -p data/hermes/backups; }
''')
        (scripts / 'check.sh').write_text('#!/bin/bash\nexit 0\n')
        (scripts / 'secrets-sync.sh').write_text('#!/bin/bash\nexit 0\n')
        (scripts / 'install-timers.sh').write_text('#!/bin/bash\nexit 0\n')
        (scripts / 'provision.py').write_text("import os, sys\nsys.exit(1 if os.environ.get('FAIL_MODE') == 'vault' else 0)\n")
        bindir = self.root / 'bin'
        bindir.mkdir()
        for command in ['docker', 'rclone', 'chown']:
            binary = bindir / command
            binary.write_text(FAKE)
            binary.chmod(0o755)
        (self.root / 'state').mkdir()
        (self.root / 'remote/daily').mkdir(parents=True)
        self.env = {**os.environ, 'TEST_ROOT': str(self.root), 'PATH': f'{bindir}:{os.environ["PATH"]}'}

    def run_script(self, name, mode='', *args):
        return subprocess.run(['bash', str(self.root / 'scripts' / name), *args], env={**self.env, 'FAIL_MODE': mode}, capture_output=True, text=True)

    def calls(self):
        path = self.root / 'calls'
        return path.read_text() if path.exists() else ''

    def make_remote_archive(self, corrupt=False):
        path = self.root / 'remote/daily/hermes-backup-20260926T000000Z-1.zip'
        if corrupt:
            path.write_bytes(b'corrupt')
        else:
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('config.yaml', 'model: restored')
        return path.name

    def test_backup_success_verifies_then_prunes_and_cleans(self):
        result = self.run_script('backup.sh')
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        self.assertLess(calls.index('"cat"'), calls.index('"delete"'))
        self.assertTrue((self.root / 'state/last-backup').exists())
        self.assertFalse(list((self.root / 'data/hermes/backups').glob('*.zip')))

    def test_backup_failure_retains_local_archive_and_never_prunes(self):
        for mode in ['upload', 'checksum', 'vault']:
            with self.subTest(mode=mode):
                result = self.run_script('backup.sh', mode)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('"delete"', self.calls())
                self.assertFalse((self.root / 'state/last-backup').exists())
                self.assertTrue(list((self.root / 'data/hermes/backups').glob('*.zip')))

    def test_corrupt_restore_never_stops_gateway(self):
        archive = self.make_remote_archive(corrupt=True)
        result = self.run_script('restore.sh', '', archive)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('"stop"', self.calls())
        self.assertNotIn('"import"', self.calls())

    def test_restore_failed_import_stays_stopped(self):
        archive = self.make_remote_archive()
        result = self.run_script('restore.sh', 'import', archive)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('"stop"', self.calls())
        self.assertNotIn('"up"', self.calls())

    def test_restore_latest_on_empty_server(self):
        self.make_remote_archive()
        result = self.run_script('restore.sh')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / 'state/setup-complete').exists())
        self.assertIn('"up"', self.calls())

    def test_restore_invalid_name_never_downloads(self):
        result = self.run_script('restore.sh', '', '../escape.zip')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), '')

    def test_update_failure_rolls_back_but_reports_failure(self):
        result = self.run_script('update.sh', 'update')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('"--pull", "never"', self.calls())
        self.assertEqual((self.root / 'state/image.env').read_text().strip(), 'bedrock-hermes:rollback')

    def test_failed_backup_prevents_image_pull(self):
        result = self.run_script('update.sh', 'upload')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('"pull"', self.calls())

    def test_failed_pull_does_not_replace_running_container(self):
        result = self.run_script('update.sh', 'pull')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('"up"', self.calls())

    def test_update_success_persists_latest_image(self):
        result = self.run_script('update.sh')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / 'state/image.env').read_text().strip(), 'nousresearch/hermes-agent:latest')

    def test_reapplying_setup_uses_backup_before_update(self):
        (self.root / 'state/setup-complete').touch()
        (self.root / 'data/hermes').mkdir(parents=True)
        (self.root / 'data/hermes/config.yaml').write_text('model: configured')
        result = self.run_script('setup.sh')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('"setup"', self.calls())
        self.assertLess(self.calls().index('"cat"'), self.calls().index('"pull"'))
