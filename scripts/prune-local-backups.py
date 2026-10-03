#!/usr/bin/env python3
"""Bound plaintext on-host snapshots without touching unknown files."""
import re
import sys
from pathlib import Path

PATTERN = re.compile(
    r"^(pre-install-hermes-backup|pre-install-gatelet-backup|"
    r"pre-restore-gatelet|pre-restore|hermes-backup|gatelet-backup)"
    r"-[0-9]{8}T[0-9]{6}Z-[0-9]+\.zip$"
)


def prune(directory: Path, remote_verified: bool) -> None:
    if not directory.is_dir():
        return
    groups: dict[str, list[Path]] = {}
    for path in directory.iterdir():
        match = PATTERN.fullmatch(path.name)
        if match and path.is_file() and not path.is_symlink():
            groups.setdefault(match.group(1), []).append(path)
    # Reinstallation snapshots are one recovery point only when both services
    # have the same timestamp and PID. Never let an orphan evict a full pair.
    hermes = {p.name.removeprefix('pre-install-hermes-backup-'): p
              for p in groups.pop('pre-install-hermes-backup', [])}
    gatelet = {p.name.removeprefix('pre-install-gatelet-backup-'): p
               for p in groups.pop('pre-install-gatelet-backup', [])}
    paired = hermes.keys() & gatelet.keys()
    for suffix in sorted(paired)[:-3]:
        hermes[suffix].unlink()
        gatelet[suffix].unlink()
    for snapshots in (hermes, gatelet):
        orphans = sorted(suffix for suffix in snapshots if suffix not in paired)
        # Keep orphaned plaintext archives bounded even through a Drive outage,
        # without counting them against complete recovery pairs.
        keep = 0 if remote_verified else 3
        for suffix in orphans[:-keep or None]:
            snapshots[suffix].unlink()
    for kind, archives in groups.items():
        # A verified off-site backup supersedes leftover failed uploads.
        keep = 0 if remote_verified and kind in ('hermes-backup', 'gatelet-backup') else 3
        for path in sorted(archives)[:-keep or None]:
            path.unlink()


if __name__ == '__main__':
    if len(sys.argv) != 3 or sys.argv[2] not in ('remote', 'local'):
        sys.exit('Usage: prune-local-backups.py DIRECTORY remote|local')
    prune(Path(sys.argv[1]), sys.argv[2] == 'remote')
