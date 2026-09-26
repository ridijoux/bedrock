#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
case "${1:-}" in
  start) lock; docker compose up -d --wait --wait-timeout 240 hermes ;;
  stop) lock; docker compose stop hermes ;;
  status) docker compose ps --all ;;
  logs) docker compose logs --tail=100 -f hermes ;;
  backup-list) require_backup_config; rclone lsf hermes-crypt:daily --files-only --include '/hermes-backup-*.zip' ;;
  *) echo 'Unknown command.' >&2; exit 1 ;;
esac
