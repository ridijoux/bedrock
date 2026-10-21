#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
if [[ $HERMES_INSTANCE == saruman && ${1:-} == gatelet-* ]]; then
  echo "Gatelet is not available for Saruman." >&2
  exit 1
fi
case "${1:-}" in
  start) lock; docker compose up -d --no-recreate --wait --wait-timeout 240 "${HERMES_SERVICES[@]}" ;;
  restart) lock; docker compose restart hermes ;;
  stop) lock; docker compose stop hermes ;;
  status) docker compose ps --all ;;
  logs) docker compose logs --tail=100 -f hermes ;;
  gatelet-start) lock; docker compose up -d --no-recreate --wait --wait-timeout 240 gatelet ;;
  gatelet-stop) lock; docker compose stop gatelet ;;
  gatelet-logs) docker compose logs --tail=100 -f gatelet ;;
  *) echo 'Unknown command.' >&2; exit 1 ;;
esac
