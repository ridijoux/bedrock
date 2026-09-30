#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
lock
require_backup_config
archive="${1:-latest}"
if [[ $archive == latest ]]; then
  archive=$(rclone lsf 'hermes-crypt:daily' --files-only --include '/gatelet-backup-*.zip' | LC_ALL=C sort | tail -n 1)
fi
[[ $archive =~ ^gatelet-backup-[0-9]{8}T[0-9]{6}Z-[0-9]+\.zip$ ]] || { echo 'No valid Gatelet backup found.' >&2; exit 1; }
prepare_data
local_archive="$HERMES_DATA_DIR/backups/restore-$archive"
trap 'rm -f "$local_archive"' EXIT
rclone copyto "hermes-crypt:daily/$archive" "$local_archive"
chmod 0600 "$local_archive"
python3 scripts/gatelet-restore.py "$local_archive" /opt/hermes-home/data/gatelet --check
# Keep a local rollback snapshot before overwriting an existing installation.
if [[ -f /opt/hermes-home/data/gatelet/gatelet.db ]]; then
  rollback="$HERMES_DATA_DIR/backups/pre-restore-gatelet-$(date -u +%Y%m%dT%H%M%SZ)-$$.zip"
  python3 scripts/gatelet-snapshot.py /opt/hermes-home/data/gatelet "$rollback"
  echo "Local Gatelet rollback snapshot: $rollback"
fi
docker compose stop gatelet
python3 scripts/gatelet-restore.py "$local_archive" /opt/hermes-home/data/gatelet || {
  echo 'Gatelet restore failed; Gatelet remains stopped. Use the local rollback snapshot.' >&2
  exit 1
}
docker compose up -d --wait --wait-timeout 240 gatelet
./scripts/compose.sh gatelet-check
echo "Restored Gatelet backup: $archive"
