"""Verify instance isolation without touching the host or external accounts."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
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
                    'COMPOSE_PROJECT_NAME', 'HERMES_VAULT',
                    'HERMES_ITEM', 'HERMES_ROLLBACK_IMAGE',
                    'HERMES_DASHBOARD_PORT'):
            with self.subTest(key=key):
                self.assertNotEqual(personal[key], professional[key])

    def test_professional_has_no_gatelet_admin_port(self):
        self.assertNotIn('GATELET_ADMIN_PORT', json.loads(self.profile('saruman').stdout))

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

    def test_selected_compose_files_and_data_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scripts = root / 'scripts'
            scripts.mkdir()
            common = (ROOT / 'scripts/common.sh').read_text()
            common = common.replace('[[ $EUID -eq 0 ]]', 'true').replace('-o 10000 -g 10000 ', '')
            (scripts / 'common.sh').write_text(common)
            instance = (ROOT / 'scripts/instance.sh').read_text()
            instance = instance.replace('/opt/', f'{root}/opt/').replace('/etc/', f'{root}/etc/')
            (scripts / 'instance.sh').write_text(instance)
            for name in ('gonzabot', 'saruman'):
                result = subprocess.run(
                    ['bash', '-ec', 'source scripts/common.sh; prepare_data; '
                     'python3 -c "import os,json; print(json.dumps(dict(os.environ)))"'],
                    cwd=root, env={**os.environ, 'HERMES_INSTANCE': name},
                    capture_output=True, text=True, check=True,
                )
                values = json.loads(result.stdout)
                files = [str(root / 'compose.yaml')]
                if name == 'gonzabot':
                    files.append(str(root / 'compose.override.yaml'))
                self.assertEqual(values['COMPOSE_FILE'], ':'.join(files))
                home = Path(values['HERMES_HOME'])
                self.assertTrue((home / 'data/hermes').is_dir())
                self.assertEqual((home / 'data/gatelet').exists(), name == 'gonzabot')
