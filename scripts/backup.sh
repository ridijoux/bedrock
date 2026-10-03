#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
lock
[[ $# -eq 0 || ( $# -eq 1 && $1 == --local ) ]] || { echo 'Usage: backup.sh [--local]' >&2; exit 1; }
local_only=false
if [[ ${1:-} == --local ]]; then
  local_only=true
else
  require_backup_config
fi
# Gatelet's SQLite snapshot is valid even when its container is stopped.
# The backup still fails closed if the token or database cannot be captured.
./scripts/check.sh hermes
prepare_data
stamp=$(date -u +%Y%m%dT%H%M%SZ)
archive="hermes-backup-$stamp-$$.zip"
if $local_only; then archive="pre-install-$archive"; fi
local_archive="$HERMES_DATA_DIR/backups/$archive"
verified=false
cleanup() {
  if $verified && ! $local_only; then
    rm -f "$local_archive"
    python3 scripts/prune-local-backups.py "$HERMES_DATA_DIR/backups" remote
  else
    if ! $verified; then
      if $local_only; then
        # Never let an incomplete pair displace a validated pre-install pair.
        rm -f "$local_archive"
        if [[ -n ${gatelet_local:-} ]]; then rm -f "$gatelet_local"; fi
      else
        echo "Backup did not complete; local archive retained if present: $local_archive" >&2
      fi
    fi
    python3 scripts/prune-local-backups.py "$HERMES_DATA_DIR/backups" local
  fi
}
trap cleanup EXIT
# Before the image update, `exec` still runs in the *existing* container;
# changing Compose PATH does not affect it until a recreate. Old images may
# have Hermes only in the user-local bin, whereas new ones use the shim/venv.
docker compose exec -T hermes /bin/sh -c '
  PATH="/opt/hermes/bin:/opt/hermes/.venv/bin:/opt/data/.local/bin:$PATH"
  export PATH
  exec hermes "$@"
' -- backup --output "/opt/data/backups/$archive" --keep 0
[[ -s $local_archive ]] || { echo 'Hermes did not create a backup archive.' >&2; exit 1; }
chmod 0600 "$local_archive"
python3 scripts/validate-archive.py "$local_archive"
if $local_only; then
  gatelet_archive="gatelet-backup-$stamp-$$.zip"
  gatelet_archive="pre-install-$gatelet_archive"
  gatelet_local="$HERMES_DATA_DIR/backups/$gatelet_archive"
  python3 scripts/gatelet-snapshot.py /opt/hermes-home/data/gatelet "$gatelet_local"
  chmod 0600 "$gatelet_local"
  verified=true
  echo "Validated local pre-install backups: $local_archive and $gatelet_local"
  exit 0
fi
# Never upload with keys whose recovery copy cannot be verified.
python3 scripts/provision.py sync-backup
rclone copyto "$local_archive" "hermes-crypt:daily/$archive" --immutable
# Read and decrypt the entire uploaded object, then compare plaintext hashes.
local_hash=$(sha256sum "$local_archive" | cut -d ' ' -f 1)
remote_hash=$(rclone cat "hermes-crypt:daily/$archive" | sha256sum | cut -d ' ' -f 1)
[[ $local_hash == "$remote_hash" ]] || { echo 'Remote backup checksum mismatch; retention skipped.' >&2; exit 1; }
# Gatelet's database is separate from Hermes state; back up its live SQLite
# snapshot together with the admin token needed to decrypt OAuth credentials.
gatelet_archive="gatelet-backup-$(date -u +%Y%m%dT%H%M%SZ)-$$.zip"
gatelet_local="$HERMES_DATA_DIR/backups/$gatelet_archive"
gatelet_verified=false
gatelet_cleanup() {
  if $gatelet_verified; then rm -f "$gatelet_local"; else echo "Gatelet backup retained if present: $gatelet_local" >&2; fi
}
trap 'gatelet_cleanup; cleanup' EXIT
python3 scripts/gatelet-snapshot.py /opt/hermes-home/data/gatelet "$gatelet_local"
rclone copyto "$gatelet_local" "hermes-crypt:daily/$gatelet_archive" --immutable
local_hash=$(sha256sum "$gatelet_local" | cut -d ' ' -f 1)
remote_hash=$(rclone cat "hermes-crypt:daily/$gatelet_archive" | sha256sum | cut -d ' ' -f 1)
[[ $local_hash == "$remote_hash" ]] || { echo 'Gatelet backup checksum mismatch; retention skipped.' >&2; exit 1; }
# rclone may have refreshed OAuth credentials during the transfer.
python3 scripts/provision.py sync-backup
rclone delete 'hermes-crypt:daily' --min-age 14d --include '/hermes-backup-*.zip'
rclone delete 'hermes-crypt:daily' --min-age 14d --include '/gatelet-backup-*.zip'
verified=true
gatelet_verified=true
install -d -m 0700 /etc/bedrock
date -u +%s > /etc/bedrock/last-backup
echo "Uploaded and decrypted/verified backup: $archive"
