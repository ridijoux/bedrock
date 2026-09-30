#!/usr/bin/env python3
"""Snapshot a live Gatelet DB and its indispensable encryption token into a ZIP."""
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import zipfile


def snapshot(data_dir: Path, target: Path):
    database = data_dir / 'gatelet.db'
    token = data_dir / 'admin.token'
    if not database.is_file() or not token.is_file() or not token.read_text().strip():
        raise ValueError('Gatelet database or admin token is missing; refusing incomplete backup.')
    with tempfile.TemporaryDirectory(dir=target.parent) as staging:
        staged_db = Path(staging) / 'gatelet.db'
        # Online SQLite backup includes committed pages still in the WAL.
        with sqlite3.connect(f'file:{database}?mode=ro', uri=True) as source:
            with sqlite3.connect(staged_db) as destination:
                source.backup(destination)
        fd, pending = tempfile.mkstemp(prefix='.gatelet-', suffix='.zip', dir=target.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
                    archive.write(staged_db, 'gatelet.db')
                    archive.write(token, 'admin.token')
            with zipfile.ZipFile(pending) as archive:
                if set(archive.namelist()) != {'gatelet.db', 'admin.token'} or archive.testzip():
                    raise ValueError('Invalid Gatelet snapshot.')
            os.replace(pending, target)
        finally:
            if os.path.exists(pending):
                os.unlink(pending)


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit('Usage: gatelet-snapshot.py DATA_DIR ARCHIVE.zip')
    try:
        snapshot(Path(sys.argv[1]), Path(sys.argv[2]))
    except (ValueError, OSError, sqlite3.Error, zipfile.BadZipFile) as error:
        sys.exit(f'Gatelet snapshot failed: {error}')
