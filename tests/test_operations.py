"""Public deployment contracts without requiring a running host."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from test_provision import ROOT

JUST = shutil.which('just')


class OperationsContracts(unittest.TestCase):
    def test_gh_is_installed_on_host_and_available_in_hermes(self):
        installer = (ROOT / 'scripts/install-host.sh').read_text()
        self.assertIn('debian-archive-keyring gh', installer)
        self.assertIn('[[ -f /usr/bin/gh && -x /usr/bin/gh ]]', installer)
        compose = (ROOT / 'compose.yaml').read_text()
        hermes = compose.split('  hermes:', 1)[1].split('  gatelet:', 1)[0]
        self.assertIn('source: /usr/bin/gh', hermes)
        self.assertIn('target: /usr/local/bin/gh', hermes)
        self.assertIn('create_host_path: false', hermes)

    def test_compose_has_no_healthcheck_or_backup_mount(self):
        compose = (ROOT / 'compose.yaml').read_text() + (ROOT / 'compose.override.yaml').read_text()
        self.assertNotIn('healthcheck:', compose)
        self.assertNotIn('bedrock-health.py', compose)
        self.assertNotIn('/backups', compose)

    @unittest.skipUnless(JUST, 'just binary not available')
    def test_just_exposes_only_install_and_container_commands(self):
        assert JUST is not None
        recipes = subprocess.run([JUST, '--list'], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(recipes.returncode, 0, recipes.stderr)
        for name in ('install', 'setup', 'status', 'start', 'stop', 'restart',
                     'logs', 'gatelet-start', 'gatelet-stop', 'gatelet-logs', 'test'):
            self.assertIn(name, recipes.stdout)
        for name in ('backup', 'restore', 'update', 'check', 'monitor', 'alert', 'secrets-sync'):
            self.assertNotIn(name, recipes.stdout)

    @unittest.skipUnless(JUST, 'just binary not available')
    def test_imported_recipes_execute_from_repository_root(self):
        assert JUST is not None
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            for file in ('Justfile', 'just/host.just', 'services/hermes/recipes.just',
                         'services/gatelet/recipes.just'):
                (root / file).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / file, root / file)
            script = root / 'scripts/compose.sh'
            script.parent.mkdir()
            script.write_text('#!/bin/sh\npwd\n')
            script.chmod(0o755)
            result = subprocess.run([JUST, 'status'], cwd=root, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), str(root))

    @unittest.skipUnless(JUST, 'just binary not available')
    def test_explicit_recipes_override_inherited_instance(self):
        import os
        assert JUST is not None
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            for file in ('Justfile', 'just/host.just', 'services/hermes/recipes.just',
                         'services/gatelet/recipes.just'):
                (root / file).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / file, root / file)
            script = root / 'scripts/compose.sh'
            script.parent.mkdir()
            script.write_text('#!/bin/sh\nprintf "%s %s\\n" "$HERMES_INSTANCE" "$1"\n')
            script.chmod(0o755)
            for instance in ('gonzabot', 'saruman'):
                other = 'saruman' if instance == 'gonzabot' else 'gonzabot'
                operations = ['status', 'start', 'stop', 'restart', 'logs']
                if instance == 'gonzabot':
                    operations += ['gatelet-start', 'gatelet-stop', 'gatelet-logs']
                for operation in operations:
                    with self.subTest(instance=instance, operation=operation):
                        result = subprocess.run(
                            [JUST, f'{instance}-{operation}'], cwd=root,
                            env={**os.environ, 'HERMES_INSTANCE': other},
                            text=True, capture_output=True)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(result.stdout.strip(), f'{instance} {operation}')
