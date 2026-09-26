from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from test_provision import load

archive = load('archive', 'validate-archive.py')
health = load('health', 'container-health.py')


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'backup.zip'

    def test_valid_archive(self):
        with zipfile.ZipFile(self.path, 'w') as z:
            z.writestr('config.yaml', 'model: test')
        archive.validate(self.path)

    def test_corruption_rejected(self):
        self.path.write_bytes(b'not a zip')
        with self.assertRaises(zipfile.BadZipFile):
            archive.validate(self.path)

    def test_traversal_rejected(self):
        with zipfile.ZipFile(self.path, 'w') as z:
            z.writestr('config.yaml', 'model: test')
            z.writestr('../escape', 'bad')
        with self.assertRaises(ValueError):
            archive.validate(self.path)

    def test_wrong_zip_rejected(self):
        with zipfile.ZipFile(self.path, 'w') as z:
            z.writestr('holiday.jpg', 'irrelevant')
        with self.assertRaises(ValueError):
            archive.validate(self.path)

    def test_process_check_ignores_shell_wrapper(self):
        proc = Path(self.temp.name) / 'proc'
        entry = proc / '9999999'
        entry.mkdir(parents=True)
        (entry / 'cmdline').write_bytes(b'sh\0-c\0hermes gateway run\0')
        self.assertFalse(health.healthy(proc))
        (entry / 'cmdline').write_bytes(b'python3\0/opt/hermes/.venv/bin/hermes\0gateway\0run\0--no-supervise\0')
        self.assertTrue(health.healthy(proc))

    @unittest.skipUnless(shutil.which('rclone'), 'rclone not installed')
    def test_real_rclone_encryption_roundtrip_and_wrong_key(self):
        folder = Path(self.temp.name)
        config = folder / 'rclone.conf'
        cryptdir = folder / 'encrypted'
        secret = subprocess.check_output(['rclone', 'obscure', '-'], input=b'first test password').decode().strip()
        config.write_text(f'[encrypted]\ntype = crypt\nremote = {cryptdir}\npassword = {secret}\nfilename_encryption = standard\n')
        self.path.write_bytes(b'private payload')
        base = ['rclone', '--config', str(config)]
        subprocess.run([*base, 'copyto', str(self.path), 'encrypted:daily/backup.zip'], check=True, capture_output=True)
        output = subprocess.check_output([*base, 'cat', 'encrypted:daily/backup.zip'])
        self.assertEqual(output, self.path.read_bytes())
        raw = list(cryptdir.rglob('*'))
        self.assertNotIn('backup.zip', [p.name for p in raw])
        self.assertTrue(all(b'private payload' not in p.read_bytes() for p in raw if p.is_file()))
        wrong = subprocess.check_output(['rclone', 'obscure', '-'], input=b'wrong password').decode().strip()
        config.write_text(config.read_text().replace(secret, wrong))
        result = subprocess.run([*base, 'cat', 'encrypted:daily/backup.zip', '--retries', '1'], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
