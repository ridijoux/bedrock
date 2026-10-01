#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
lock
./scripts/secrets-sync.sh
./scripts/backup.sh
container=$(docker compose ps -q hermes)
previous=$(docker inspect --format '{{.Image}}' "$container")
# Tag the previous image so it survives a later image prune.
docker image tag "$previous" bedrock-hermes:rollback
export HERMES_IMAGE=nousresearch/hermes-agent:latest
docker compose pull hermes
if docker compose up -d --wait --wait-timeout 240 hermes && ./scripts/check.sh hermes; then
  install -d -m 0700 /etc/bedrock
  printf '%s\n' "$HERMES_IMAGE" > /etc/bedrock/image.env
  ./scripts/install-timers.sh
else
  echo 'Update failed; restoring previous container image. The pre-update data backup is on Drive.' >&2
  export HERMES_IMAGE=bedrock-hermes:rollback
  printf '%s\n' "$HERMES_IMAGE" > /etc/bedrock/image.env
  docker compose up -d --pull never --wait --wait-timeout 240 hermes
  ./scripts/check.sh hermes
  # Signal failure to systemd even when rollback succeeds.
  exit 1
fi
