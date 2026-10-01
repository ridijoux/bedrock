#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
lock
[[ $PWD == /opt/hermes-home/git/bedrock ]] || { echo 'Install the repository at /opt/hermes-home/git/bedrock.' >&2; exit 1; }
[[ -s /etc/bedrock/last-backup ]] || { echo 'A verified first backup is required before enabling timers.' >&2; exit 1; }
install -m 0644 systemd/hermes-* /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now hermes-backup.timer hermes-update.timer hermes-check.timer
systemctl --no-pager list-timers 'hermes-*'
