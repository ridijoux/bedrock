#!/usr/bin/env bash
# Shared host paths and serialization. Source from a root-only command.
set -Eeuo pipefail
umask 077
cd "$(dirname "${BASH_SOURCE[0]}")/.."
[[ $EUID -eq 0 ]] || { echo 'Run with sudo (or as root).' >&2; exit 1; }
source scripts/instance.sh
export COMPOSE_FILE="$PWD/compose.yaml"
HERMES_SERVICES=(hermes)
if [[ $HERMES_INSTANCE == gonzabot ]]; then
  export COMPOSE_FILE="$COMPOSE_FILE:$PWD/compose.override.yaml"
  HERMES_SERVICES=(gatelet hermes)
fi
# Do not load personal settings into the professional instance.
if [[ $HERMES_INSTANCE == gonzabot && -f "$PWD/.env" ]]; then
  export COMPOSE_ENV_FILES="$PWD/.env"
elif [[ -f "$HERMES_HOME/.env" ]]; then
  export COMPOSE_ENV_FILES="$HERMES_HOME/.env"
else
  export COMPOSE_ENV_FILES=/dev/null
fi
unset HERMES_IMAGE
if [[ -s "$BEDROCK_STATE/image.env" ]]; then
  export HERMES_IMAGE
  HERMES_IMAGE=$(<"$BEDROCK_STATE/image.env")
fi
lock() {
  if [[ ${BEDROCK_LOCKED:-} != "$PWD:$HERMES_INSTANCE" ]] || [[ ! -e /proc/$$/fd/9 ]]; then
    exec 9>"/run/lock/$COMPOSE_PROJECT_NAME.lock"
    flock -w 3600 9 || { echo 'Another deployment operation is still running.' >&2; exit 1; }
    export BEDROCK_LOCKED="$PWD:$HERMES_INSTANCE"
  fi
}
prepare_data() {
  install -d -m 0700 "$HERMES_HOME" "$HERMES_HOME/data"
  install -d -m 0700 -o 10000 -g 10000 "$HERMES_DATA_DIR"
  if [[ $HERMES_INSTANCE == gonzabot ]]; then
    install -d -m 0700 "$HERMES_HOME/data/gatelet"
  fi
}
