"""CLI and Compose contracts without requiring a running deployment."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from test_provision import ROOT

JUST = shutil.which('just')


class OperationsContracts(unittest.TestCase):
    def test_compose_resolves_hermes_from_current_and_legacy_images(self):
        compose = (ROOT / 'compose.yaml').read_text()
        hermes = compose.split('  hermes:', 1)[1].split('  gatelet:', 1)[0]
        path_line = next((line for line in hermes.splitlines() if line.strip().startswith('PATH:')), '')
        self.assertTrue(path_line, 'Hermes exec needs an explicit PATH for legacy images')
        locations = path_line.split('PATH:', 1)[1].strip().strip('"').split(':')
        self.assertEqual(locations[:3], ['/opt/hermes/bin', '/opt/hermes/.venv/bin', '/opt/data/.local/bin'])
        self.assertIn('/usr/bin', locations)
        self.assertIn('/bin', locations)

    @unittest.skipUnless(JUST, 'just binary not available')
    def test_just_recipes_are_grouped_and_exposed(self):
        recipes = subprocess.run([str(JUST), '--list'], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(recipes.returncode, 0, recipes.stderr)
        for recipe in ('install', 'update', 'restart', 'check', 'check-hermes',
                       'check-gatelet', 'gatelet-check', 'setup', 'backup', 'monitor'):
            self.assertIn(recipe, recipes.stdout)
        for domain in ('services/hermes/recipes.just', 'services/gatelet/recipes.just',
                       'just/host.just'):
            self.assertTrue((ROOT / domain).is_file(), domain)

    @unittest.skipUnless(JUST, 'just binary not available')
    def test_imported_recipes_execute_from_repository_root(self):
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
            result = subprocess.run([str(JUST), 'status'], cwd=root, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), str(root))
