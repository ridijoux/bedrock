#!/usr/bin/env bash
# Shared host paths and serialization. Source from a root-only command.
set -Eeuo pipefail
umask 077
cd "$(dirname "${BASH_SOURCE[0]}")/.."
[[ $EUID -eq 0 ]] || { echo 'Run with sudo (or as root).' >&2; exit 1; }
export RCLONE_CONFIG=/root/.config/rclone/rclone.conf
export RCLONE_RETRIES=5 RCLONE_CONTIMEOUT=20s RCLONE_TIMEOUT=5m
export COMPOSE_FILE="$PWD/compose.yaml"
export COMPOSE_ENV_FILES=/opt/hermes-home/.env
export HERMES_DATA_DIR=${HERMES_DATA_DIR:-/opt/hermes-home/data/hermes}
if [[ -s /etc/bedrock/image.env ]]; then
  export HERMES_IMAGE
  HERMES_IMAGE=$(cat /etc/bedrock/image.env)
fi
lock() {
  # A child inherits fd 9; never trust a caller-supplied --locked flag.
  if [[ ${BEDROCK_LOCKED:-} != "$PWD" ]] || [[ ! -e /proc/$$/fd/9 ]]; then
    exec 9>/run/lock/hermes-home.lock
    flock -w 3600 9 || { echo 'Another maintenance operation is still running.' >&2; exit 1; }
    export BEDROCK_LOCKED="$PWD"
  fi
}
prepare_data() {
  install -d -m 0700 /opt/hermes-home /opt/hermes-home/data
  install -d -m 0700 -o 10000 -g 10000 "$HERMES_DATA_DIR" "$HERMES_DATA_DIR/backups"
}
require_backup_config() {
  python3 scripts/provision.py validate-backup
}
