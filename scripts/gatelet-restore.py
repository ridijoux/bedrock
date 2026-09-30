#!/usr/bin/env python3
"""Validate and restore an offline Gatelet snapshot, without extracting ZIP paths."""
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import zipfile


def restore(archive_path: Path, data_dir: Path, check_only=False):
    with zipfile.ZipFile(archive_path) as archive:
        if set(archive.namelist()) != {'gatelet.db', 'admin.token'} or len(archive.namelist()) != 2 or archive.testzip():
            raise ValueError('Invalid Gatelet archive members or checksum.')
        with tempfile.TemporaryDirectory(dir=data_dir) as staging:
            stage = Path(staging)
            for name in ('gatelet.db', 'admin.token'):
                (stage / name).write_bytes(archive.read(name))
            if not (stage / 'admin.token').read_text().strip():
                raise ValueError('Gatelet admin token is empty.')
            with sqlite3.connect(f'file:{stage / "gatelet.db"}?mode=ro', uri=True) as db:
                if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('Gatelet database integrity check failed.')
            if check_only:
                return
            # Restore only after the Gatelet container has been stopped by caller.
            for name in ('admin.token', 'gatelet.db'):
                source = stage / name
                source.chmod(0o600)
                os.replace(source, data_dir / name)
            for suffix in ('-wal', '-shm'):
                (data_dir / f'gatelet.db{suffix}').unlink(missing_ok=True)


if __name__ == '__main__':
    if len(sys.argv) not in (3, 4) or (len(sys.argv) == 4 and sys.argv[3] != '--check'):
        sys.exit('Usage: gatelet-restore.py ARCHIVE.zip DATA_DIR [--check]')
    try:
        restore(Path(sys.argv[1]), Path(sys.argv[2]), len(sys.argv) == 4)
    except (ValueError, OSError, sqlite3.Error, zipfile.BadZipFile, UnicodeError) as error:
        sys.exit(f'Gatelet restore failed: {error}')
