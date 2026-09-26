#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
lock
require_backup_config
./scripts/check.sh
prepare_data
archive="hermes-backup-$(date -u +%Y%m%dT%H%M%SZ)-$$.zip"
local_archive="data/hermes/backups/$archive"
verified=false
cleanup() {
  if $verified; then rm -f "$local_archive"; else echo "Backup did not complete; local archive retained if present: $local_archive" >&2; fi
}
trap cleanup EXIT
docker compose exec -T hermes hermes backup --output "/opt/data/backups/$archive" --keep 0
[[ -s $local_archive ]] || { echo 'Hermes did not create a backup archive.' >&2; exit 1; }
chmod 0600 "$local_archive"
python3 scripts/validate-archive.py "$local_archive"
# Never upload with keys whose recovery copy cannot be verified.
python3 scripts/provision.py sync-backup
rclone copyto "$local_archive" "hermes-crypt:daily/$archive" --immutable
# Read and decrypt the entire uploaded object, then compare plaintext hashes.
local_hash=$(sha256sum "$local_archive" | cut -d ' ' -f 1)
remote_hash=$(rclone cat "hermes-crypt:daily/$archive" | sha256sum | cut -d ' ' -f 1)
[[ $local_hash == "$remote_hash" ]] || { echo 'Remote backup checksum mismatch; retention skipped.' >&2; exit 1; }
# rclone may have refreshed OAuth credentials during the transfer.
python3 scripts/provision.py sync-backup
rclone delete 'hermes-crypt:daily' --min-age 14d --include '/hermes-backup-*.zip'
verified=true
install -d -m 0700 /etc/bedrock
date -u +%s > /etc/bedrock/last-backup
echo "Uploaded and decrypted/verified backup: $archive"
