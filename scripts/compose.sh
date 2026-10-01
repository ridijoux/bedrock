#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
case "${1:-}" in
  start) lock; docker compose up -d --wait --wait-timeout 240 gatelet hermes ;;
  stop) lock; docker compose stop hermes ;;
  status) docker compose ps --all ;;
  logs) docker compose logs --tail=100 -f hermes ;;
  gatelet-start) lock; docker compose up -d --wait --wait-timeout 240 gatelet ;;
  gatelet-stop) lock; docker compose stop gatelet ;;
  gatelet-logs) docker compose logs --tail=100 -f gatelet ;;
  gatelet-check)
    container=$(docker compose ps -q gatelet)
    [[ -n $container ]] || { echo 'Gatelet container is missing.' >&2; exit 1; }
    docker inspect "$container" | jq -e 'length == 1 and .[0].State.Status == "running" and .[0].State.Health.Status == "healthy"' >/dev/null
    ;;
  backup-list) require_backup_config; rclone lsf hermes-crypt:daily --files-only --include '/hermes-backup-*.zip' ;;
  gatelet-backup-list) require_backup_config; rclone lsf hermes-crypt:daily --files-only --include '/gatelet-backup-*.zip' ;;
  *) echo 'Unknown command.' >&2; exit 1 ;;
esac
