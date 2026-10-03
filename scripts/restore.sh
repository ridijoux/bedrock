#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
lock
require_backup_config
archive="${1:-latest}"
if [[ $archive == latest ]]; then
  archive=$(rclone lsf 'hermes-crypt:daily' --files-only --include '/hermes-backup-*.zip' | LC_ALL=C sort | tail -n 1)
fi
[[ $archive =~ ^hermes-backup-[A-Za-z0-9T-]+\.zip$ ]] || { echo 'No valid backup found; use just backup-list.' >&2; exit 1; }
prepare_data
local_archive="$HERMES_DATA_DIR/backups/restore-$archive"
rollback=''
rollback_valid=false
cleanup() {
  rm -f "$local_archive"
  if [[ -n $rollback ]] && ! $rollback_valid; then rm -f "$rollback"; fi
  python3 scripts/prune-local-backups.py "$HERMES_DATA_DIR/backups" local
}
trap cleanup EXIT
rclone copyto "hermes-crypt:daily/$archive" "$local_archive"
python3 scripts/validate-archive.py "$local_archive"
chown 10000:10000 "$local_archive"
chmod 0600 "$local_archive"
# Preserve existing live data before an explicit destructive import.
if [[ -f $HERMES_DATA_DIR/config.yaml ]]; then
  rollback="$HERMES_DATA_DIR/backups/pre-restore-$(date -u +%Y%m%dT%H%M%SZ)-$$.zip"
  docker compose run --rm -T --no-deps hermes backup --output "/opt/data/backups/$(basename "$rollback")" --keep 0
  python3 scripts/validate-archive.py "$rollback"
  rollback_valid=true
  echo "Local pre-restore snapshot: $rollback"
fi
docker compose stop hermes
if ! docker compose run --rm -T --no-deps hermes import "/opt/data/backups/restore-$archive" --force; then
  echo 'Import failed. Hermes remains stopped; inspect the error before starting it.' >&2
  exit 1
fi
docker compose up -d --wait --wait-timeout 240 hermes
./scripts/check.sh hermes
install -d -m 0700 /etc/bedrock
touch /etc/bedrock/setup-complete
echo "Restored backup: $archive"
