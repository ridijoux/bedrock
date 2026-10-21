"""Exercise install and container lifecycle with isolated command substitutes."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_provision import ROOT

FAKE = '''#!/usr/bin/env python3
import json, os, pathlib, sys
root = pathlib.Path(os.environ['TEST_ROOT'])
with (root / 'calls').open('a') as stream:
    stream.write(json.dumps([pathlib.Path(sys.argv[0]).name, *sys.argv[1:]]) + '\\n')
if pathlib.Path(sys.argv[0]).name == 'docker':
    args = sys.argv[1:]
    if 'up' in args and 'hermes' in args and os.environ.get('FAIL_UNCONFIGURED') and not (root / 'wizard-done').exists():
        sys.exit(1)
    if 'run' in args and 'setup' in args:
        (root / 'wizard-done').touch()
'''


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        scripts = self.root / 'scripts'
        scripts.mkdir()
        for file in ('install.sh', 'setup.sh', 'compose.sh'):
            text = (ROOT / 'scripts' / file).read_text()
            text = text.replace('/opt/hermes-home/git/bedrock', str(self.root))
            text = text.replace('/etc/systemd/system', str(self.root / 'units'))
            text = text.replace('/etc/bedrock', str(self.root / 'state'))
            text = text.replace('if [[ $EUID -ne 0 ]]; then', 'if false; then')
            destination = scripts / file
            destination.write_text(text)
            destination.chmod(0o755)
        (scripts / 'common.sh').write_text('''set -Eeuo pipefail
cd "$TEST_ROOT"
lock() { :; }
prepare_data() { mkdir -p "$HERMES_DATA_DIR"; }
HERMES_DATA_DIR="$TEST_ROOT/data/hermes"
BEDROCK_STATE="$TEST_ROOT/state"
HERMES_INSTANCE=${HERMES_INSTANCE:-gonzabot}
HERMES_SERVICES=(hermes)
if [[ $HERMES_INSTANCE == gonzabot ]]; then
  HERMES_SERVICES=(gatelet hermes)
fi
HERMES_ROLLBACK_IMAGE=bedrock-hermes:rollback
''')
        (scripts / 'install-host.sh').write_text('#!/bin/bash\nexit 0\n')
        (scripts / 'install-host.sh').chmod(0o755)
        (scripts / 'provision.py').write_text('#!/usr/bin/env python3\n')
        bindir = self.root / 'bin'
        bindir.mkdir()
        for command in ('docker', 'systemctl'):
            binary = bindir / command
            binary.write_text(FAKE)
            binary.chmod(0o755)
        (self.root / 'units').mkdir()
        (self.root / 'state').mkdir()
        self.env = {**os.environ, 'TEST_ROOT': str(self.root),
                    'PATH': f'{bindir}:{os.environ["PATH"]}'}

    def execute(self, script, *args):
        return subprocess.run(['bash', str(self.root / 'scripts' / script), *args],
                              env=self.env, capture_output=True, text=True)

    def calls(self):
        file = self.root / 'calls'
        return [json.loads(line) for line in file.read_text().splitlines()] if file.exists() else []

    def test_install_disables_legacy_timers_but_keeps_old_archives(self):
        for name in ('hermes-backup.timer', 'hermes-update.timer', 'hermes-check.timer',
                     'hermes-backup.service', 'hermes-update.service', 'hermes-check.service',
                     'hermes-alert@.service'):
            (self.root / 'units' / name).touch()
        archive = self.root / 'data/hermes/backups/pre-install.zip'
        archive.parent.mkdir(parents=True)
        archive.write_bytes(b'old archive')
        result = self.execute('install.sh')
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        for name in ('hermes-backup.timer', 'hermes-update.timer', 'hermes-check.timer'):
            self.assertIn(['systemctl', 'disable', '--now', name], calls)
        self.assertIn(['systemctl', 'daemon-reload'], calls)
        self.assertFalse(list((self.root / 'units').iterdir()))
        self.assertEqual(archive.read_bytes(), b'old archive')
        self.assertFalse(any(call[0] == 'rclone' or (call[0] == 'docker' and 'backup' in call) for call in calls))

    def test_old_restore_option_is_rejected_before_host_changes(self):
        (self.root / 'units/hermes-backup.timer').touch()
        result = self.execute('install.sh', '--restore')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [])
        self.assertTrue((self.root / 'units/hermes-backup.timer').exists())

    def test_reapply_has_no_automatic_image_pull_or_setup_wizard(self):
        data = self.root / 'data/hermes'
        data.mkdir(parents=True)
        (data / 'config.yaml').write_text('model: configured')
        (self.root / 'state/setup-complete').touch()
        result = self.execute('setup.sh')
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        self.assertFalse(any('pull' in call or 'setup' in call for call in calls))
        self.assertTrue(any(call[:3] == ['docker', 'compose', 'up'] for call in calls))
        self.assertEqual(calls[-1], ['docker', 'compose', 'restart', 'hermes'])

    def test_fresh_setup_runs_wizard_and_creates_marker(self):
        self.env['FAIL_UNCONFIGURED'] = '1'
        result = self.execute('setup.sh')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / 'state/setup-complete').exists())
        calls = self.calls()
        gatelet = next(i for i, call in enumerate(calls) if 'up' in call and 'gatelet' in call)
        wizard = next(i for i, call in enumerate(calls) if 'run' in call and 'setup' in call)
        gateway = next(i for i, call in enumerate(calls) if 'up' in call and 'hermes' in call)
        self.assertLess(gatelet, wizard)
        self.assertLess(wizard, gateway)
        self.assertFalse(any('backup' in call or 'rclone' in call for call in calls))

    def test_restart_uses_restart_only_and_legacy_commands_fail(self):
        self.assertEqual(self.execute('compose.sh', 'restart').returncode, 0)
        self.assertIn(['docker', 'compose', 'restart', 'hermes'], self.calls())
        for command in ('backup-list', 'gatelet-backup-list', 'gatelet-check'):
            with self.subTest(command=command):
                self.assertNotEqual(self.execute('compose.sh', command).returncode, 0)


    def test_professional_install_preserves_personal_legacy_units(self):
        self.env['HERMES_INSTANCE'] = 'saruman'
        unit = self.root / 'units/hermes-backup.timer'
        unit.touch()
        result = self.execute('install.sh')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(unit.exists())
        self.assertFalse(any(call[0] == 'systemctl' for call in self.calls()))

    def test_professional_fresh_setup_and_reapply_exclude_gatelet(self):
        self.env['HERMES_INSTANCE'] = 'saruman'
        for reapply in (False, True):
            with self.subTest(reapply=reapply):
                if reapply:
                    (self.root / 'data/hermes/config.yaml').write_text('model: configured')
                result = self.execute('setup.sh')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse(any('gatelet' in call for call in self.calls()))
                self.assertTrue(any('up' in call and '--remove-orphans' in call
                                    and 'hermes' in call for call in self.calls()))

    def test_professional_start_excludes_gatelet_and_gatelet_commands_fail(self):
        self.env['HERMES_INSTANCE'] = 'saruman'
        result = self.execute('compose.sh', 'start')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(any('up' in call and 'hermes' in call for call in self.calls()))
        before = self.calls()
        for command in ('gatelet-start', 'gatelet-stop', 'gatelet-logs'):
            result = self.execute('compose.sh', command)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Gatelet is not available for Saruman', result.stderr)
        self.assertEqual(self.calls(), before)
