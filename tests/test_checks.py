"""Check all Compose services and individual targets without a Docker daemon."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_provision import ROOT


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'scripts').mkdir()
        (self.root / 'scripts/common.sh').write_text('set -Eeuo pipefail\ncd "$TEST_ROOT"\n')
        (self.root / 'scripts/check.sh').write_text((ROOT / 'scripts/check.sh').read_text())
        (self.root / 'bin').mkdir()
        docker = self.root / 'bin/docker'
        docker.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
root = pathlib.Path(os.environ['TEST_ROOT'])
with (root / 'calls').open('a') as f:
    f.write(json.dumps(args) + '\\n')
if args[:3] == ['compose', 'config', '--services']:
    print('hermes\\ngatelet\\nfuture-service')
elif args[:3] == ['compose', 'ps', '-q']:
    if args[3] not in os.environ.get('MISSING', '').split(','):
        print(args[3] + '-id')
        if args[3] in os.environ.get('MULTIPLE', '').split(','):
            print(args[3] + '-id-2')
elif args[0] == 'inspect':
    service = args[1].split('-id')[0]
    status = 'exited' if service in os.environ.get('STOPPED', '').split(',') else 'running'
    health = os.environ.get('UNHEALTHY', '').split(',')
    state = {'Status': status}
    if service == 'hermes' or service in health:
        state['Health'] = {'Status': 'unhealthy' if service in health else 'healthy'}
    print(json.dumps([{'State': state}]))
else:
    sys.exit(2)
''')
        docker.chmod(0o755)
        self.env = {**os.environ, 'TEST_ROOT': str(self.root), 'PATH': f'{self.root / "bin"}:{os.environ["PATH"]}'}

    def check(self, *args, **environ):
        return subprocess.run(['bash', str(self.root / 'scripts/check.sh'), *args],
                              env={**self.env, **environ}, capture_output=True, text=True)

    def calls(self):
        path = self.root / 'calls'
        return path.read_text() if path.exists() else ''

    def test_all_checks_every_compose_service(self):
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stderr)
        for service in ('hermes', 'gatelet', 'future-service'):
            self.assertIn(f'"{service}"', self.calls())

    def test_specific_target_only_checks_that_service(self):
        result = self.check('gatelet', STOPPED='hermes')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('hermes-id', self.calls())
        self.assertIn('gatelet-id', self.calls())

    def test_unknown_target_rejected_before_docker(self):
        result = self.check('typo')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('"ps"', self.calls())
        self.assertNotIn('"inspect"', self.calls())

    def test_missing_or_stopped_service_fails(self):
        for state in ('MISSING', 'STOPPED'):
            with self.subTest(state=state):
                result = self.check('all', **{state: 'gatelet'})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('gatelet', result.stderr)

    def test_unhealthy_service_fails_even_when_running(self):
        result = self.check('all', UNHEALTHY='gatelet')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('gatelet', result.stderr)

    def test_hermes_must_have_healthcheck(self):
        result = self.check('hermes', UNHEALTHY='hermes')
        self.assertNotEqual(result.returncode, 0)

    def test_all_inspects_each_replica_of_scaled_service(self):
        result = self.check('all', MULTIPLE='gatelet')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"inspect", "gatelet-id-2"', self.calls())
