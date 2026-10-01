#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
lock
prepare_data
python3 scripts/provision.py sync-secrets
if docker compose ps --status running --services | grep -Fxq hermes; then
  # Restart the existing container; `up` can recreate it with changed Compose
  # settings before the update path has taken its verified backup.
  ./scripts/compose.sh restart
fi
