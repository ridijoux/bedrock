#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
for script in scripts/*.sh; do bash -n "$script"; done
python3 -m unittest discover -s tests -v
# CI installs PyYAML so the policy permission tests must not silently skip.
if [[ ${CI:-} ]]; then
  python3 -c 'import yaml'
fi
if command -v shellcheck >/dev/null; then
  shellcheck -x -P SCRIPTDIR scripts/*.sh
fi
if command -v just >/dev/null; then
  just --list >/dev/null
fi
if command -v docker >/dev/null; then
  docker compose config --quiet
fi
