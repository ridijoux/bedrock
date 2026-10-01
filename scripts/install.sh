#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
if [[ $EUID -ne 0 ]]; then
  if command -v sudo >/dev/null; then
    exec sudo bash scripts/install.sh "$@"
  fi
  echo 'sudo is not installed. Run su -, then cd /opt/hermes-home/git/bedrock and bash scripts/install.sh.' >&2
  exit 1
fi
[[ $PWD == /opt/hermes-home/git/bedrock ]] || { echo 'Move the checkout to /opt/hermes-home/git/bedrock first.' >&2; exit 1; }
[[ $# -eq 0 || ( $# -le 2 && $1 == --restore ) ]] || { echo 'Usage: install.sh [--restore [archive|latest]]' >&2; exit 1; }
source scripts/common.sh
lock
./scripts/install-host.sh
prepare_data
python3 scripts/provision.py login
if [[ ${1:-} == --restore ]]; then
  python3 scripts/provision.py recover-backup
  docker compose config --quiet
  if [[ ${HERMES_IMAGE:-} != bedrock-hermes:rollback ]]; then
    docker compose pull hermes
  fi
  ./scripts/restore.sh "${2:-latest}"
  docker compose pull gatelet
  docker compose up -d --wait --wait-timeout 240 gatelet
  # Recover the most recent Gatelet snapshot before the installer's first
  # combined backup. Otherwise a new, empty Gatelet DB could become "latest".
  if [[ -n $(rclone lsf 'hermes-crypt:daily' --files-only --include '/gatelet-backup-*.zip') ]]; then
    ./scripts/restore-gatelet.sh latest
  fi
else
  python3 scripts/provision.py sync-secrets
  python3 scripts/provision.py setup-backup
  # setup.sh retains a verified local snapshot (or uploads if daily backups
  # are stale) while reapplying an existing install.
  # A fresh install still needs its first backup below.
  if [[ -f /etc/bedrock/setup-complete && -f $HERMES_DATA_DIR/config.yaml ]]; then
    reapply=true
  else
    reapply=false
  fi
  ./scripts/setup.sh
fi
./scripts/secrets-sync.sh
if [[ ${reapply:-false} == false ]]; then
  ./scripts/backup.sh
fi
./scripts/install-timers.sh
echo 'Installation complete: Hermes and Gatelet started, backup verified, timers enabled.'
