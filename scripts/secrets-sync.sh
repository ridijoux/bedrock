#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
lock
prepare_data
python3 scripts/provision.py sync-secrets
if docker compose ps --status running --services | grep -Fxq hermes; then
  docker compose restart hermes
  docker compose up -d --wait --wait-timeout 240 hermes
  ./scripts/check.sh
fi
