#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
lock
prepare_data
if [[ $HERMES_INSTANCE == gonzabot ]]; then
  python3 scripts/provision.py sync-secrets
else
  python3 scripts/provision.py local-secrets
fi
docker compose config --quiet
if [[ -f "$BEDROCK_STATE/setup-complete" && -f $HERMES_DATA_DIR/config.yaml ]]; then
  # Reapply an existing deployment without fetching a new image. Compose may
  # recreate containers when configuration changed; no backup is performed.
  docker compose up -d --remove-orphans --wait --wait-timeout 240 "${HERMES_SERVICES[@]}"
  # The credential file is bind-mounted. Compose may not recreate an unchanged
  # container, so restart the gateway to pick up a changed allowlist or token.
  docker compose restart hermes
  exit 0
fi
if [[ ${HERMES_IMAGE:-} != "$HERMES_ROLLBACK_IMAGE" ]]; then
  docker compose pull hermes
fi
if [[ $HERMES_INSTANCE == gonzabot ]]; then
  docker compose pull gatelet
  docker compose up -d --wait --wait-timeout 240 gatelet
fi
if [[ $HERMES_INSTANCE == gonzabot ]]; then
  echo 'Select ChatGPT or Codex Subscription in the wizard. Telegram is already provisioned.'
else
  echo 'Configure your model provider and Telegram in the Hermes setup wizard.'
fi
docker compose run --rm --no-deps hermes setup
if [[ $HERMES_INSTANCE == gonzabot ]]; then
  python3 scripts/provision.py sync-secrets
else
  python3 scripts/provision.py local-secrets
fi
docker compose up -d --remove-orphans --wait --wait-timeout 240 "${HERMES_SERVICES[@]}"
install -d -m 0700 "$BEDROCK_STATE"
touch "$BEDROCK_STATE/setup-complete"
