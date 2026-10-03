"""Exercise production shell control flow with isolated Docker/Drive substitutes."""
import os
import json
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
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
if name == 'jq':
    data = json.load(sys.stdin)
    sys.exit(0 if len(data) == 1 and data[0]['State']['Health']['Status'] == 'healthy' else 1)
if name == 'docker':
    if args[:3] == ['compose', 'exec', '-T'] and mode == 'missing-hermes-path':
        command = args[4:]
        if (command[:2] != ['/bin/sh', '-c'] or
            not all(location in command[2] for location in
                    ['/opt/hermes/bin', '/opt/hermes/.venv/bin', '/opt/data/.local/bin']) or
            'exec hermes "$@"' not in command[2]):
            print('OCI runtime exec failed: exec: "hermes": executable file not found in $PATH', file=sys.stderr)
            sys.exit(127)
    if args[0] == 'inspect':
        print('sha256:previous' if '--format' in args else json.dumps([{'State': {'Status': 'running', 'Health': {'Status': 'healthy'}}}]))
    elif 'ps' in args:
        print('hermes' if '--services' in args else 'container-id')
    elif 'backup' in args:
        destination = root / 'data/hermes/backups' / pathlib.Path(args[args.index('--output')+1]).name
        if mode == 'invalid-rollback' and destination.name.startswith('pre-restore-'):
            destination.write_bytes(b'corrupt')
        else:
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
                destination.write_text(original.read_text().replace('/etc/bedrock', str(self.root / 'state')).replace('/opt/hermes-home/data/gatelet', str(self.root / 'data/gatelet')))
                destination.chmod(0o755)
        (scripts / 'common.sh').write_text('''set -Eeuo pipefail
umask 077
cd "$TEST_ROOT"
lock() { :; }
require_backup_config() { :; }
prepare_data() { mkdir -p data/hermes/backups; }
HERMES_DATA_DIR="$TEST_ROOT/data/hermes"
''')
        (scripts / 'check.sh').write_text('#!/bin/bash\nexit 0\n')
        (scripts / 'secrets-sync.sh').write_text('#!/bin/bash\nexit 0\n')
        (scripts / 'install-timers.sh').write_text('#!/bin/bash\nexit 0\n')
        (scripts / 'provision.py').write_text("import os, sys\nsys.exit(1 if os.environ.get('FAIL_MODE') == 'vault' else 0)\n")
        (scripts / 'gatelet-snapshot.py').write_text((ROOT / 'scripts/gatelet-snapshot.py').read_text())
        bindir = self.root / 'bin'
        bindir.mkdir()
        for command in ['docker', 'rclone', 'chown', 'jq']:
            binary = bindir / command
            binary.write_text(FAKE)
            binary.chmod(0o755)
        (self.root / 'state').mkdir()
        (self.root / 'remote/daily').mkdir(parents=True)
        gatelet = self.root / 'data/gatelet'
        gatelet.mkdir(parents=True)
        (gatelet / 'admin.token').write_text('a' * 64)
        with sqlite3.connect(gatelet / 'gatelet.db') as db:
            db.execute('CREATE TABLE connections (id TEXT)')
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
        self.assertEqual(len(list((self.root / 'remote/daily').glob('gatelet-backup-*.zip'))), 1)

    def test_backup_on_old_container_with_hermes_missing_from_path(self):
        result = self.run_script('backup.sh', 'missing-hermes-path')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / 'state/last-backup').exists())

    def test_backup_shell_wrapper_executes_with_exact_arguments(self):
        source = (ROOT / 'scripts/backup.sh').read_text()
        match = re.search(r"docker compose exec -T hermes /bin/sh -c '([^']+)' -- backup", source, re.S)
        assert match is not None, 'Backup must invoke the shell wrapper'
        binary_dir = self.root / 'legacy-bin'
        binary_dir.mkdir()
        hermes = binary_dir / 'hermes'
        hermes.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys
pathlib.Path(os.environ['TEST_ROOT'], 'hermes-args').write_text(json.dumps(sys.argv[1:]))
''')
        hermes.chmod(0o755)
        # This is the CLI's sole location; /bin/sh starts with a PATH that
        # deliberately does not include it, as on the affected container.
        wrapper = match.group(1).replace('/opt/hermes/bin', str(binary_dir))
        result = subprocess.run(['/bin/sh', '-c', wrapper, '--', 'backup', '--output',
                                 '/opt/data/backups/sample.zip', '--keep', '0'],
                                env={**self.env, 'PATH': '/usr/bin:/bin'}, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads((self.root / 'hermes-args').read_text()),
                         ['backup', '--output', '/opt/data/backups/sample.zip', '--keep', '0'])

    def test_missing_gatelet_token_prevents_prune_and_freshness_marker(self):
        (self.root / 'data/gatelet/admin.token').unlink()
        result = self.run_script('backup.sh')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('"delete"', self.calls())
        self.assertFalse((self.root / 'state/last-backup').exists())

    def test_gatelet_restore_rejects_corrupt_archive_without_stopping(self):
        name = 'gatelet-backup-20260926T000000Z-1.zip'
        (self.root / 'remote/daily' / name).write_bytes(b'not a zip')
        result = self.run_script('restore-gatelet.sh', '', name)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('"stop"', self.calls())

    def test_gatelet_restore_keeps_local_pre_restore_snapshot(self):
        name = 'gatelet-backup-20260926T000000Z-1.zip'
        source = self.root / 'data/gatelet'
        snapshot_script = self.root / 'scripts/gatelet-snapshot.py'
        result = subprocess.run(['python3', str(snapshot_script), str(source), str(self.root / 'remote/daily' / name)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        (source / 'admin.token').write_text('b' * 64)
        result = self.run_script('restore-gatelet.sh', '', name)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((source / 'admin.token').read_text(), 'a' * 64)
        self.assertEqual(len(list((self.root / 'data/hermes/backups').glob('pre-restore-gatelet-*.zip'))), 1)

    def test_backup_failure_retains_local_archive_and_never_prunes(self):
        for mode in ['upload', 'checksum', 'vault']:
            with self.subTest(mode=mode):
                result = self.run_script('backup.sh', mode)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('"delete"', self.calls())
                self.assertFalse((self.root / 'state/last-backup').exists())
                self.assertTrue(list((self.root / 'data/hermes/backups').glob('*.zip')))

    def test_repeated_failed_uploads_keep_only_three_local_archives(self):
        for _ in range(4):
            result = self.run_script('backup.sh', 'upload')
            self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(list((self.root / 'data/hermes/backups').glob('hermes-backup-*.zip'))), 3)

    def test_successful_backup_cleans_previous_failed_local_archives(self):
        for _ in range(2):
            self.assertNotEqual(self.run_script('backup.sh', 'upload').returncode, 0)
        self.assertEqual(self.run_script('backup.sh').returncode, 0)
        self.assertFalse(list((self.root / 'data/hermes/backups').glob('hermes-backup-*.zip')))

    def test_repeated_restores_keep_only_three_local_rollback_archives(self):
        name = 'gatelet-backup-20260926T000000Z-1.zip'
        snapshot = self.root / 'scripts/gatelet-snapshot.py'
        subprocess.run(['python3', str(snapshot), str(self.root / 'data/gatelet'),
                        str(self.root / 'remote/daily' / name)], check=True)
        for _ in range(4):
            self.assertEqual(self.run_script('restore-gatelet.sh', '', name).returncode, 0)
        self.assertEqual(len(list((self.root / 'data/hermes/backups').glob('pre-restore-gatelet-*.zip'))), 3)

    def test_invalid_pre_restore_snapshot_does_not_displace_valid_rollbacks(self):
        name = self.make_remote_archive()
        (self.root / 'data/hermes').mkdir(parents=True, exist_ok=True)
        (self.root / 'data/hermes/config.yaml').write_text('model: configured')
        for _ in range(3):
            self.assertEqual(self.run_script('restore.sh', '', name).returncode, 0)
        directory = self.root / 'data/hermes/backups'
        valid = set(directory.glob('pre-restore-*.zip'))
        self.assertEqual(len(valid), 3)
        result = self.run_script('restore.sh', 'invalid-rollback', name)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(set(directory.glob('pre-restore-*.zip')), valid)

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
        (self.root / 'scripts/check.sh').write_text('#!/bin/bash\nprintf "%s\\n" "$@" >> "$TEST_ROOT/check-args"\n')
        result = self.run_script('restore.sh')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / 'state/setup-complete').exists())
        self.assertIn('"up"', self.calls())
        self.assertEqual((self.root / 'check-args').read_text(), 'hermes\n')

    def test_start_never_recreates_existing_service(self):
        result = self.run_script('compose.sh', '', 'start')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"--no-recreate"', self.calls())

    def test_restore_invalid_name_never_downloads(self):
        result = self.run_script('restore.sh', '', '../escape.zip')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), '')

    def test_update_failure_rolls_back_but_reports_failure(self):
        (self.root / 'state/last-backup').write_text(str(int(time.time())))
        result = self.run_script('update.sh', 'update')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('"--pull", "never"', self.calls())
        self.assertEqual((self.root / 'state/image.env').read_text().strip(), 'bedrock-hermes:rollback')

    def test_failed_backup_prevents_image_pull(self):
        result = self.run_script('update.sh')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('"pull"', self.calls())
        self.assertNotIn('"copyto"', self.calls())

    def test_failed_pull_does_not_replace_running_container(self):
        (self.root / 'state/last-backup').write_text(str(int(time.time())))
        result = self.run_script('update.sh', 'pull')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('"up"', self.calls())

    def test_update_success_persists_latest_image(self):
        (self.root / 'state/last-backup').write_text(str(int(time.time())))
        result = self.run_script('update.sh')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / 'state/image.env').read_text().strip(), 'nousresearch/hermes-agent:latest')
        self.assertIn('"--force-recreate"', self.calls())
        self.assertNotIn('"backup"', self.calls())
        self.assertNotIn('"copyto"', self.calls())

    def test_weekly_update_rejects_yesterdays_verified_backup(self):
        (self.root / 'state/last-backup').write_text(str(int(time.time()) - 24 * 3600))
        result = self.run_script('update.sh')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('"pull"', self.calls())
        self.assertNotIn('"backup"', self.calls())

    def test_weekly_update_rejects_future_marker(self):
        (self.root / 'state/last-backup').write_text(str(int(time.time()) + 3600))
        result = self.run_script('update.sh')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('"pull"', self.calls())

    def test_restart_never_backs_up_or_restores(self):
        result = self.run_script('compose.sh', '', 'restart')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"restart"', self.calls())
        self.assertNotIn('"up"', self.calls())
        self.assertNotIn('"backup"', self.calls())
        self.assertNotIn('"import"', self.calls())
        self.assertNotIn('"rclone"', self.calls())

    def test_reapplying_install_with_recent_daily_backup_keeps_local_snapshots(self):
        (self.root / 'state/setup-complete').touch()
        self.daily_timestamp = int(time.time())
        (self.root / 'state/last-backup').write_text(str(self.daily_timestamp))
        (self.root / 'data/hermes').mkdir(parents=True)
        (self.root / 'data/hermes/config.yaml').write_text('model: configured')
        installer = self.root / 'scripts/install.sh'
        installer.write_text(installer.read_text().replace('/opt/hermes-home/git/bedrock', str(self.root)).replace('if [[ $EUID -ne 0 ]]; then', 'if false; then'))
        (self.root / 'scripts/install-host.sh').write_text('#!/bin/bash\nexit 0\n')
        result = self.run_script('install.sh')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('"copyto"', self.calls())
        self.assertNotIn('"cat"', self.calls())
        hermes = list((self.root / 'data/hermes/backups').glob('pre-install-hermes-backup-*.zip'))
        gatelet = list((self.root / 'data/hermes/backups').glob('pre-install-gatelet-backup-*.zip'))
        self.assertEqual(len(hermes), 1)
        self.assertEqual(len(gatelet), 1)
        with zipfile.ZipFile(hermes[0]) as archive:
            self.assertIsNone(archive.testzip())
            self.assertIn('config.yaml', archive.namelist())
        with zipfile.ZipFile(gatelet[0]) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(set(archive.namelist()), {'gatelet.db', 'admin.token'})
        self.assertEqual((self.root / 'state/last-backup').read_text(), str(self.daily_timestamp))
        self.assertNotIn('"import"', self.calls())
        self.assertIn('"gh", "--version"', self.calls())

    def test_reapplying_setup_uses_local_backup_before_update(self):
        (self.root / 'state/setup-complete').touch()
        (self.root / 'state/last-backup').write_text(str(int(time.time())))
        (self.root / 'data/hermes').mkdir(parents=True)
        (self.root / 'data/hermes/config.yaml').write_text('model: configured')
        (self.root / 'scripts/secrets-sync.sh').write_text((ROOT / 'scripts/secrets-sync.sh').read_text())
        result = self.run_script('setup.sh')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('"setup"', self.calls())
        self.assertNotIn('"copyto"', self.calls())
        self.assertNotIn('"cat"', self.calls())
        # A changed Compose model must not recreate Hermes until after backup.
        calls = [json.loads(line) for line in self.calls().splitlines()]
        backup_index = next(i for i, call in enumerate(calls) if 'backup' in call)
        pull_index = next(i for i, call in enumerate(calls) if call[:3] == ['docker', 'compose', 'pull'] and 'hermes' in call)
        self.assertLess(backup_index, pull_index)
        for call in calls[:backup_index]:
            self.assertFalse(call[:3] == ['docker', 'compose', 'up'] and 'hermes' in call, call)

    def test_reapplying_setup_without_recent_daily_backup_uploads_before_update(self):
        (self.root / 'state/setup-complete').touch()
        (self.root / 'data/hermes').mkdir(parents=True)
        (self.root / 'data/hermes/config.yaml').write_text('model: configured')
        result = self.run_script('setup.sh')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLess(self.calls().index('"cat"'), self.calls().index('"pull", "hermes"'))
        self.assertFalse(list((self.root / 'data/hermes/backups').glob('*.zip')))

    def test_local_snapshot_failure_prevents_image_pull(self):
        (self.root / 'state/last-backup').write_text(str(int(time.time())))
        (self.root / 'data/gatelet/admin.token').unlink()
        result = self.run_script('update.sh', '', '--local-backup')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('"pull"', self.calls())
        self.assertFalse(list((self.root / 'data/hermes/backups').glob('pre-install-hermes-backup-*.zip')))

    def test_failed_local_snapshot_does_not_displace_valid_pairs(self):
        directory = self.root / 'data/hermes/backups'
        for _ in range(3):
            self.assertEqual(self.run_script('backup.sh', '', '--local').returncode, 0)
        original = set(directory.glob('pre-install-*.zip'))
        self.assertEqual(len(original), 6)
        (self.root / 'data/gatelet/admin.token').unlink()
        result = self.run_script('backup.sh', '', '--local')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(set(directory.glob('pre-install-*.zip')), original)

    def test_orphan_pre_install_snapshots_are_bounded_without_evicting_pairs(self):
        directory = self.root / 'data/hermes/backups'
        for _ in range(3):
            self.assertEqual(self.run_script('backup.sh', '', '--local').returncode, 0)
        paired = set(directory.glob('pre-install-*.zip'))
        for day in range(1, 6):
            (directory / f'pre-install-hermes-backup-2026090{day}T000000Z-1.zip').write_bytes(b'orphan')
        result = self.run_script('backup.sh', 'upload')
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(paired.issubset(set(directory.glob('pre-install-*.zip'))))
        self.assertEqual(len(list(directory.glob('pre-install-*.zip'))), 9)

    def test_repeated_local_snapshots_retain_only_three_valid_pairs(self):
        directory = self.root / 'data/hermes/backups'
        for _ in range(4):
            result = self.run_script('backup.sh', '', '--local')
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(list(directory.glob('pre-install-hermes-backup-*.zip'))), 3)
        self.assertEqual(len(list(directory.glob('pre-install-gatelet-backup-*.zip'))), 3)

    def test_direct_local_update_without_recent_offsite_backup_uploads(self):
        result = self.run_script('update.sh', '', '--local-backup')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLess(self.calls().index('"cat"'), self.calls().index('"pull", "hermes"'))
        self.assertFalse(list((self.root / 'data/hermes/backups').glob('*.zip')))

    def test_expired_offsite_marker_requires_upload(self):
        (self.root / 'state/last-backup').write_text(str(int(time.time()) - 37 * 3600))
        result = self.run_script('update.sh', '', '--local-backup')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"copyto"', self.calls())

    def test_future_offsite_marker_requires_upload(self):
        (self.root / 'state/last-backup').write_text(str(int(time.time()) + 3600))
        result = self.run_script('update.sh', '', '--local-backup')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"copyto"', self.calls())

    def test_recent_manual_update_is_valid_offsite_recovery_point(self):
        (self.root / 'state/last-backup').write_text(str(int(time.time())))
        result = self.run_script('update.sh')
        self.assertEqual(result.returncode, 0, result.stderr)
        (self.root / 'calls').unlink()
        result = self.run_script('update.sh', '', '--local-backup')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('"copyto"', self.calls())

    def test_backup_checks_hermes_not_stopped_gatelet(self):
        check = self.root / 'scripts/check.sh'
        check.write_text('#!/bin/bash\nprintf "%s\\n" "$@" >> "$TEST_ROOT/check-args"\n')
        result = self.run_script('backup.sh')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / 'check-args').read_text(), 'hermes\n')
