#!/usr/bin/env bash
set -Eeuo pipefail

target="${1:?Missing service name}"
if [[ -z ${TELEGRAM_BOT_TOKEN:-} || -z ${TELEGRAM_CHAT_ID:-} ]]; then
  echo 'Telegram alert credentials are missing; check journalctl.' >&2
  exit 1
fi
[[ $TELEGRAM_BOT_TOKEN =~ ^[0-9]+:[A-Za-z0-9_-]+$ ]] || { echo 'Invalid Telegram alert token.' >&2; exit 1; }
# Pass the secret URL on stdin, keeping it out of the process argument list.
curl -fsS --retry 3 --connect-timeout 10 --max-time 30 --config - -X POST \
  --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
  --data-urlencode "text=Hermes maintenance failed: ${target}. Check the systemd journal." >/dev/null <<EOF
url = "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage"
EOF
