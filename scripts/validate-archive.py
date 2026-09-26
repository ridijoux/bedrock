#!/usr/bin/env python3
"""Reject corrupt or unsafe archives before stopping the live gateway."""
from pathlib import Path, PurePosixPath
import stat
import sys
import zipfile


def validate(path):
    with zipfile.ZipFile(path) as archive:
        names = set()
        for member in archive.infolist():
            name = PurePosixPath(member.filename)
            if name.is_absolute() or '..' in name.parts or '\\' in member.filename or stat.S_ISLNK(member.external_attr >> 16):
                raise ValueError('Unsafe path in archive')
            if member.filename in names:
                raise ValueError('Duplicate path in archive')
            names.add(member.filename)
        if not any(PurePosixPath(name).name == 'config.yaml' for name in names):
            raise ValueError('Archive does not contain a Hermes config.yaml')
        if archive.testzip() is not None:
            raise ValueError('Archive CRC verification failed')


if __name__ == '__main__':
    try:
        validate(Path(sys.argv[1]))
    except (ValueError, OSError, zipfile.BadZipFile) as error:
        sys.exit(f'Invalid backup archive: {error}')
