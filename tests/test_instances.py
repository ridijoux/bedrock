"""Verify instance isolation without touching the host or external accounts."""
import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parent.parent


class InstanceTests(unittest.TestCase):
    def profile(self, instance):
        result = subprocess.run(
            ['bash', '-ec', 'source scripts/instance.sh; python3 -c "import os,json; print(json.dumps(dict(os.environ)))"'],
            cwd=ROOT, env={**os.environ, 'HERMES_INSTANCE': instance},
            capture_output=True, text=True,
        )
        return result

    def test_personal_installation_keeps_existing_identity(self):
        values = json.loads(self.profile('gonzabot').stdout)
        self.assertEqual(values['HERMES_HOME'], '/opt/hermes-home')
        self.assertEqual(values['BEDROCK_STATE'], '/etc/bedrock')
        self.assertEqual(values['HERMES_VAULT'], 'Bedrock')
        self.assertEqual(values['HERMES_ITEM'], 'Hermes')
        self.assertEqual(values['COMPOSE_PROJECT_NAME'], 'hermes-home')
        self.assertEqual(values['HERMES_DASHBOARD_PORT'], '9119')

    def test_professional_resources_are_distinct(self):
        personal = json.loads(self.profile('gonzabot').stdout)
        professional = json.loads(self.profile('saruman').stdout)
        for key in ('HERMES_HOME', 'BEDROCK_STATE', 'HERMES_DATA_DIR',
                    'COMPOSE_PROJECT_NAME', 'GATELET_ADMIN_PORT', 'HERMES_VAULT',
                    'HERMES_ITEM', 'HERMES_ROLLBACK_IMAGE',
                    'HERMES_DASHBOARD_PORT'):
            with self.subTest(key=key):
                self.assertNotEqual(personal[key], professional[key])

    def test_invalid_instance_fails(self):
        self.assertNotEqual(self.profile('saruman-typo').returncode, 0)

    def test_professional_provisioning_uses_selected_resources(self):
        command = """source scripts/instance.sh
python3 -c 'import scripts.provision as p; import json; print(json.dumps([str(p.TOKEN), p.VAULT, p.ITEM, str(p.HOME)]))'
"""
        result = subprocess.run(['bash', '-ec', command], cwd=ROOT,
                                env={**os.environ, 'HERMES_INSTANCE': 'saruman'},
                                capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), [
            '/etc/bedrock-saruman/op-token', 'Bedrock-Pro', 'Saruman',
            '/opt/hermes-saruman',
        ])
