#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo 'Run as root (su -), or with sudo if installed.' >&2
  exit 1
fi

. /etc/os-release
if [[ ${ID} != debian || ${VERSION_ID%%.*} != 13 ]]; then
  echo 'This installer supports Debian 13 (trixie).' >&2
  exit 1
fi

case "$(dpkg --print-architecture)" in
  amd64|arm64) ;;
  *) echo 'Supported architectures: amd64, arm64.' >&2; exit 1 ;;
esac
[[ -d /run/systemd/system ]] || { echo 'A booted Debian host with systemd is required.' >&2; exit 1; }
export DEBIAN_FRONTEND=noninteractive
apt-get -o Acquire::Retries=5 -o DPkg::Lock::Timeout=300 update
apt-get -o Acquire::Retries=5 -o DPkg::Lock::Timeout=300 install -y ca-certificates curl git gnupg just rclone jq util-linux unattended-upgrades python3 debian-archive-keyring
install -m 0755 -d /etc/apt/keyrings
curl -fsSL --retry 5 --connect-timeout 20 https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian ${VERSION_CODENAME} stable" > /etc/apt/sources.list.d/docker.list
apt-get -o Acquire::Retries=5 -o DPkg::Lock::Timeout=300 update
apt-get -o Acquire::Retries=5 -o DPkg::Lock::Timeout=300 install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
"$(dirname "$0")/install-1password-cli.sh"
systemctl enable --now docker unattended-upgrades
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
docker compose version
docker info >/dev/null

echo 'Host dependencies ready.'
