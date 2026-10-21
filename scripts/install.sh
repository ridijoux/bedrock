#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
if [[ $EUID -ne 0 ]]; then
  if command -v sudo >/dev/null; then
    exec sudo env HERMES_INSTANCE="${HERMES_INSTANCE:-gonzabot}" bash scripts/install.sh "$@"
  fi
  echo 'Run su -, then cd /opt/hermes-home/git/bedrock and bash scripts/install.sh.' >&2
  exit 1
fi
[[ $PWD == /opt/hermes-home/git/bedrock ]] || { echo 'Move the checkout to /opt/hermes-home/git/bedrock first.' >&2; exit 1; }
[[ $# -eq 0 ]] || { echo 'Usage: install.sh' >&2; exit 1; }
source scripts/common.sh
lock
# Upgrade migration: prevent previously installed units from invoking removed
# scripts. Do not delete existing archives or encryption keys on this host.
if [[ $HERMES_INSTANCE == gonzabot ]]; then
for unit in hermes-backup.timer hermes-update.timer hermes-check.timer; do
  if [[ -e /etc/systemd/system/$unit ]]; then
    systemctl disable --now "$unit"
  fi
done
for unit in hermes-backup.timer hermes-update.timer hermes-check.timer \
            hermes-backup.service hermes-update.service hermes-check.service \
            'hermes-alert@.service'; do
  rm -f "/etc/systemd/system/$unit"
done
systemctl daemon-reload
fi
./scripts/install-host.sh
prepare_data
python3 scripts/provision.py login
./scripts/setup.sh
docker compose exec -T hermes gh --version >/dev/null
echo 'Installation complete: Hermes and Gatelet started; no backups or maintenance jobs are configured.'
