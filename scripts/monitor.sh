#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
lock
./scripts/check.sh
[[ -s /etc/bedrock/last-backup ]] || { echo 'No verified backup recorded.' >&2; exit 1; }
last=$(cat /etc/bedrock/last-backup)
[[ $last =~ ^[0-9]+$ ]] || { echo 'Invalid backup timestamp.' >&2; exit 1; }
age=$(( $(date -u +%s) - last ))
(( age >= 0 && age < 36 * 3600 )) || { echo 'Last verified backup is older than 36 hours (or clock is incorrect).' >&2; exit 1; }
if [[ -f /var/run/reboot-required ]]; then
  echo 'A host reboot is required after security updates.' >&2
  exit 1
fi
