#!/usr/bin/env python3
"""Merge resolved 1Password keys into Hermes' local dotenv file atomically."""

import os
import re
import sys
import tempfile
from pathlib import Path


def parse_updates(path: Path) -> dict[str, str]:
    updates: dict[str, str] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)=(.*)", line)
        if not match:
            raise SystemExit(f"Invalid line {number} in the resolved template")
        key, value = match.groups()
        if "op://" in value:
            raise SystemExit(f"Unresolved 1Password reference for {key}")
        if key in updates:
            raise SystemExit(f"Duplicate key in template: {key}")
        updates[key] = value
    if not updates:
        raise SystemExit("The 1Password template has no keys")
    return updates


def main() -> None:
    incoming, destination = map(Path, sys.argv[1:3])
    updates = parse_updates(incoming)
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    lines = destination.read_text(encoding="utf-8").splitlines() if destination.exists() else []
    result: list[str] = []
    seen: set[str] = set()
    for line in lines:
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=", line)
        if match and match.group(1) in updates:
            key = match.group(1)
            if key not in seen:
                result.append(f"{key}={updates[key]}")
                seen.add(key)
        else:
            result.append(line)
    result.extend(f"{key}={value}" for key, value in updates.items() if key not in seen)
    fd, temporary = tempfile.mkstemp(prefix=".hermes-env-", dir=destination.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write("\n".join(result) + "\n")
        os.chmod(temporary, 0o600)
        os.chown(temporary, 10000, 10000)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


if __name__ == "__main__":
    main()
