#!/usr/bin/env bash
set -Eeuo pipefail

[[ $EUID -eq 0 ]] || { echo 'Run as root (su -), or with sudo if installed.' >&2; exit 1; }
arch="$(dpkg --print-architecture)"
install -d -m 0755 /usr/share/keyrings /etc/debsig/policies/AC2D62742012EA22 /usr/share/debsig/keyrings/AC2D62742012EA22
key="$(mktemp)"
trap 'rm -f "$key"' EXIT
curl -fsSL --retry 5 --connect-timeout 20 https://downloads.1password.com/linux/keys/1password.asc -o "$key"
gpg --batch --yes --dearmor -o /usr/share/keyrings/1password-archive-keyring.gpg "$key"
gpg --batch --yes --dearmor -o /usr/share/debsig/keyrings/AC2D62742012EA22/debsig.gpg "$key"
curl -fsSL --retry 5 --connect-timeout 20 https://downloads.1password.com/linux/debian/debsig/1password.pol -o /etc/debsig/policies/AC2D62742012EA22/1password.pol
chmod 0644 /usr/share/keyrings/1password-archive-keyring.gpg /usr/share/debsig/keyrings/AC2D62742012EA22/debsig.gpg /etc/debsig/policies/AC2D62742012EA22/1password.pol
echo "deb [arch=${arch} signed-by=/usr/share/keyrings/1password-archive-keyring.gpg] https://downloads.1password.com/linux/debian/${arch} stable main" > /etc/apt/sources.list.d/1password.list
apt-get -o Acquire::Retries=5 -o DPkg::Lock::Timeout=300 update
apt-get -o Acquire::Retries=5 -o DPkg::Lock::Timeout=300 install -y 1password-cli
