#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
lock
[[ $# -eq 0 || ( $# -eq 1 && $1 == --local-backup ) ]] || { echo 'Usage: update.sh [--local-backup]' >&2; exit 1; }
./scripts/secrets-sync.sh
if [[ -s /etc/bedrock/last-backup ]]; then
  last=$(< /etc/bedrock/last-backup)
else
  last=''
fi
now=$(date -u +%s)
if [[ ${1:-} == --local-backup ]]; then
  if [[ $last =~ ^[0-9]+$ ]] && (( now >= 10#$last && now - 10#$last < 36 * 3600 )); then
    ./scripts/backup.sh --local
    backup_location='on this server'
  else
    ./scripts/backup.sh
    backup_location='on Drive'
  fi
else
  # The scheduled update relies on today's verified off-site daily backup;
  # do not duplicate its upload or create an unneeded local snapshot.
  if [[ ! $last =~ ^[0-9]+$ ]] || (( now < 10#$last )) ||
    [[ $(date -d "@$last" +%F) != "$(date +%F)" ]]; then
    echo "Today's verified daily backup is missing; update skipped." >&2
    exit 1
  fi
  backup_location='on Drive (daily)'
fi
container=$(docker compose ps -q hermes)
previous=$(docker inspect --format '{{.Image}}' "$container")
# Tag the previous image so it survives a later image prune.
docker image tag "$previous" bedrock-hermes:rollback
export HERMES_IMAGE=nousresearch/hermes-agent:latest
docker compose pull hermes
# A verified backup precedes this recreation. Recreate even when the image
# is unchanged so host package upgrades replace bind-mounted CLI inodes.
if docker compose up -d --force-recreate --wait --wait-timeout 240 hermes && ./scripts/check.sh hermes; then
  install -d -m 0700 /etc/bedrock
  printf '%s\n' "$HERMES_IMAGE" > /etc/bedrock/image.env
  ./scripts/install-timers.sh
else
  echo "Update failed; restoring previous container image. The pre-update data backup is $backup_location." >&2
  export HERMES_IMAGE=bedrock-hermes:rollback
  printf '%s\n' "$HERMES_IMAGE" > /etc/bedrock/image.env
  docker compose up -d --pull never --wait --wait-timeout 240 hermes
  ./scripts/check.sh hermes
  # Signal failure to systemd even when rollback succeeds.
  exit 1
fi
