#!/usr/bin/env bash
# Shared host paths and serialization. Source from a root-only command.
set -Eeuo pipefail
umask 077
cd "$(dirname "${BASH_SOURCE[0]}")/.."
[[ $EUID -eq 0 ]] || { echo 'Run with sudo (or as root).' >&2; exit 1; }
export COMPOSE_FILE="$PWD/compose.yaml"
if [[ -f "$PWD/.env" ]]; then
  export COMPOSE_ENV_FILES="$PWD/.env"
elif [[ -f /opt/hermes-home/.env ]]; then
  export COMPOSE_ENV_FILES=/opt/hermes-home/.env
else
  unset COMPOSE_ENV_FILES
fi
export HERMES_DATA_DIR=${HERMES_DATA_DIR:-/opt/hermes-home/data/hermes}
if [[ -s /etc/bedrock/image.env ]]; then
  export HERMES_IMAGE
  HERMES_IMAGE=$(</etc/bedrock/image.env)
fi
lock() {
  if [[ ${BEDROCK_LOCKED:-} != "$PWD" ]] || [[ ! -e /proc/$$/fd/9 ]]; then
    exec 9>/run/lock/hermes-home.lock
    flock -w 3600 9 || { echo 'Another deployment operation is still running.' >&2; exit 1; }
    export BEDROCK_LOCKED="$PWD"
  fi
}
prepare_data() {
  install -d -m 0700 /opt/hermes-home /opt/hermes-home/data
  install -d -m 0700 -o 10000 -g 10000 "$HERMES_DATA_DIR"
  install -d -m 0700 /opt/hermes-home/data/gatelet
}
