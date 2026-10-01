#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
lock
prepare_data
docker compose config --quiet
if [[ -f /etc/bedrock/setup-complete && -f $HERMES_DATA_DIR/config.yaml ]]; then
  # Start existing containers without recreating them before the pre-update
  # backup. A missing Gatelet can be created, but an existing one is unchanged.
  docker compose start hermes
  docker compose up -d --no-recreate --wait --wait-timeout 240 gatelet
  # update.sh checks the off-site recovery point before permitting a local-only
  # snapshot; a stale or missing marker falls back to a verified upload.
  ./scripts/update.sh --local-backup
  docker compose pull gatelet
  docker compose up -d --wait --wait-timeout 240 gatelet
  exit 0
fi
if [[ ${HERMES_IMAGE:-} != bedrock-hermes:rollback ]]; then
  docker compose pull hermes
fi
docker compose pull gatelet
docker compose up -d --wait --wait-timeout 240 gatelet
python3 scripts/provision.py sync-secrets
if [[ ! -f /etc/bedrock/setup-complete ]]; then
  echo 'Select ChatGPT or Codex Subscription in the wizard. Telegram is already provisioned.'
  docker compose stop hermes
  docker compose run --rm --no-deps hermes setup
  python3 scripts/provision.py sync-secrets
fi
docker compose up -d --wait --wait-timeout 240 gatelet hermes
./scripts/check.sh
install -d -m 0700 /etc/bedrock
touch /etc/bedrock/setup-complete
