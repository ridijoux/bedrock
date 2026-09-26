#!/usr/bin/env python3
"""Check the actual gateway process, not merely the container's init process."""
from pathlib import Path
import os
import sys


def healthy(proc=Path('/proc')):
    for entry in proc.iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            args = (entry / 'cmdline').read_bytes().split(b'\0')
            if b'gateway' in args and b'run' in args and any(Path(os.fsdecode(arg)).name == 'hermes' for arg in args if arg):
                return True
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
    return False


if __name__ == '__main__':
    sys.exit(0 if healthy() else 1)
