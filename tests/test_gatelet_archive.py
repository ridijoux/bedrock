"""Gatelet snapshots preserve live WAL data and reject incomplete restores."""
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parent.parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


snapshot = load('gatelet_snapshot', 'gatelet-snapshot.py').snapshot
restore = load('gatelet_restore', 'gatelet-restore.py').restore


class GateletArchiveTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.data = self.root / 'data'
        self.data.mkdir()
        self.archive = self.root / 'snapshot.zip'
        (self.data / 'admin.token').write_text('a' * 64)
        self.connection = sqlite3.connect(self.data / 'gatelet.db')
        self.addCleanup(self.connection.close)
        self.connection.execute('PRAGMA journal_mode=WAL')
        self.connection.execute('CREATE TABLE mail (id TEXT)')
        self.connection.execute("INSERT INTO mail VALUES ('committed-in-wal')")
        self.connection.commit()

    def test_snapshot_and_restore_committed_wal_and_token(self):
        snapshot(self.data, self.archive)
        destination = self.root / 'restored'
        destination.mkdir()
        restore(self.archive, destination, check_only=True)
        self.assertFalse((destination / 'admin.token').exists())
        restore(self.archive, destination)
        self.assertEqual((destination / 'admin.token').read_text(), 'a' * 64)
        with sqlite3.connect(destination / 'gatelet.db') as db:
            self.assertEqual(db.execute('SELECT id FROM mail').fetchone()[0], 'committed-in-wal')
        self.assertEqual((destination / 'admin.token').stat().st_mode & 0o777, 0o600)

    def test_missing_token_does_not_publish_snapshot(self):
        (self.data / 'admin.token').unlink()
        with self.assertRaises(ValueError):
            snapshot(self.data, self.archive)
        self.assertFalse(self.archive.exists())

    def test_malicious_extra_member_rejected_before_restore(self):
        with zipfile.ZipFile(self.archive, 'w') as archive:
            archive.writestr('gatelet.db', b'garbage')
            archive.writestr('admin.token', b'x')
            archive.writestr('../extra', b'bad')
        with self.assertRaises(ValueError):
            restore(self.archive, self.data)
        self.assertEqual((self.data / 'admin.token').read_text(), 'a' * 64)


if __name__ == '__main__':
    unittest.main()
