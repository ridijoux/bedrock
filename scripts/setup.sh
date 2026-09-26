#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
lock
prepare_data
docker compose config --quiet
if [[ -f /etc/bedrock/setup-complete && -f data/hermes/config.yaml ]]; then
  # Reapplying installation uses the same backup/rollback path as maintenance.
  docker compose up -d --pull never --wait --wait-timeout 240 hermes
  ./scripts/update.sh
  exit 0
fi
if [[ ${HERMES_IMAGE:-} != bedrock-hermes:rollback ]]; then
  docker compose pull hermes
fi
python3 scripts/provision.py sync-secrets
if [[ ! -f /etc/bedrock/setup-complete ]]; then
  echo 'Select ChatGPT or Codex Subscription in the wizard. Telegram is already provisioned.'
  docker compose stop hermes
  docker compose run --rm --no-deps hermes setup
  python3 scripts/provision.py sync-secrets
fi
docker compose up -d --wait --wait-timeout 240 hermes
./scripts/check.sh
install -d -m 0700 /etc/bedrock
touch /etc/bedrock/setup-complete
