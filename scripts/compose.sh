#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
case "${1:-}" in
  start) lock; docker compose up -d --no-recreate --wait --wait-timeout 240 gatelet hermes ;;
  restart)
    lock
    docker compose restart hermes
    # Never `up` here: it may recreate a changed image/config without backup.
    for ((attempt=0; attempt<48; attempt++)); do
      if ./scripts/check.sh hermes >/dev/null 2>&1; then
        break
      fi
      sleep 5
    done
    ./scripts/check.sh hermes
    ;;
  stop) lock; docker compose stop hermes ;;
  status) docker compose ps --all ;;
  logs) docker compose logs --tail=100 -f hermes ;;
  gatelet-start) lock; docker compose up -d --no-recreate --wait --wait-timeout 240 gatelet ;;
  gatelet-stop) lock; docker compose stop gatelet ;;
  gatelet-logs) docker compose logs --tail=100 -f gatelet ;;
  gatelet-check) ./scripts/check.sh gatelet ;;
  backup-list) require_backup_config; rclone lsf hermes-crypt:daily --files-only --include '/hermes-backup-*.zip' ;;
  gatelet-backup-list) require_backup_config; rclone lsf hermes-crypt:daily --files-only --include '/gatelet-backup-*.zip' ;;
  *) echo 'Unknown command.' >&2; exit 1 ;;
esac
