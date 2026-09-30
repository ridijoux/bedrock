# Personal Hermes server

Hermes on Debian 13, running in Docker and accessed through Telegram and its web dashboard. Telegram uses outbound long polling; the dashboard listens on port 9119 for devices on the trusted local network. Systemd schedules encrypted Google Drive backups, container updates, and health checks.

## Requirements

- Debian 13, amd64 or arm64, with systemd, Git, and root access. At least 4 GB RAM and disk space for the container image and backup archives.
- Access to `git@github.com:ridijoux/bedrock.git` from the account that owns the checkout.
- A Telegram bot, a ChatGPT or Codex subscription, Google Drive, and a 1Password account supporting service accounts.
- A private Telegram conversation with the bot, started with `/start`, for maintenance alerts.

## 1Password configuration

Create a **Bedrock** vault containing a **Hermes** item with these fields:

| Field | Type | Value |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | Password | BotFather token |
| `TELEGRAM_CHAT_ID` | Text | Personal Telegram user/chat ID, a positive integer |
| `HERMES_DASHBOARD_BASIC_AUTH_USERNAME` | Text | Dashboard login name |
| `HERMES_DASHBOARD_BASIC_AUTH_PASSWORD` | Password | Unique password of at least 16 characters |
| `HERMES_DASHBOARD_BASIC_AUTH_SECRET` | Password | Stable session signing secret of at least 32 characters; generate with `openssl rand -hex 32` |

Create a service account with **read and write access to Bedrock only**. Store a recovery copy of its token in a personal vault.

The installer creates the `rclone.conf` document in Bedrock and maintains it automatically. Write access is required to save the encryption keys and refreshed Google Drive credentials. The service account token is stored in `/etc/bedrock/op-token` with mode `0600`, under a `0700` directory. It is excluded from the Hermes container and its backups.

## Install

Git is the only additional package required before cloning. Installation runs as root; `sudo` is optional.

Connect with local port forwarding for Google Drive OAuth:

```bash
ssh -L 53682:127.0.0.1:53682 user@server
```

Clone as the account that will maintain the repository:

```bash
git clone git@github.com:ridijoux/bedrock.git
su -
```

In the root session, place the checkout under `git/` and install. Adjust the source path to match the checkout:

```bash
mkdir -p /opt/hermes-home/git
mv /home/user/bedrock /opt/hermes-home/git/bedrock
cd /opt/hermes-home/git/bedrock
bash scripts/install.sh
```

The checkout retains its original ownership for subsequent `git pull` operations. Hermes state stays in `/opt/hermes-home/data/hermes`; the checkout is under `/opt/hermes-home/git/bedrock`. On an existing server, leave `data/`, `.env`, and `ops.env` where they are. Place a checkout in `git/bedrock` and run the installer there; it will reapply the systemd units with the new checkout path.

The installer installs dependencies, provisions secrets and backup storage, configures Hermes, verifies an initial backup, and enables the maintenance timers. Interactive steps are:

- Enter the 1Password service account token.
- Authorize Google Drive using the localhost URL printed by rclone. The SSH tunnel handles the callback.
- Select **ChatGPT or Codex Subscription** in the Hermes wizard and complete authentication. Telegram credentials and the user allowlist are provisioned automatically.

Installation can be rerun after a failure. Existing encryption keys are reused, and completed Hermes setup is skipped. Reapplying an existing installation uses the backup and image rollback procedure. Conflicting local and remote encryption settings stop provisioning. An invalid or expired 1Password service account token can be replaced in `/etc/bedrock/op-token` as root.

### Optional sudo setup

As root:

```bash
apt-get update
apt-get install -y sudo
usermod -aG sudo user
```

Start a new login session to apply group membership. Administrative commands can then be run with `sudo`, including `sudo bash scripts/install.sh`.

## Operations

Run these commands as root from `/opt/hermes-home/git/bedrock`, or prefix them with `sudo`:

```bash
just status
just check
just logs
just backup
just backup-list
systemctl list-timers 'hermes-*'
```

The health check verifies the gateway process and disk usage. A Telegram conversation is required to verify the complete bot and model path.

`just check` only checks that the container is healthy and disk usage is below 90%; it does **not** check backup freshness or whether the host needs a reboot. For the full scheduled-monitor checks, run `just monitor` as root: it also requires a verified backup from the last 36 hours and reports pending reboots. Neither command replaces sending a test message to the Telegram bot to verify the end-to-end path.

### Dashboard and remote backend

The Hermes dashboard starts with the gateway and publishes port 9119 on the server's interfaces. From another device on the same local network, open `http://<server LAN address>:9119` and sign in with the dashboard credentials from 1Password. In Hermes Desktop, set **Settings → Gateways → Remote gateway → Remote URL** to that same address, sign in, then save and reconnect. No SSH tunnel is needed.

The server does not need its LAN address in the configuration. Docker listens on `0.0.0.0`; only the browser or Hermes Desktop needs the server's address. Restrict port 9119 to the trusted LAN or VPN with the host/network firewall. To bind Docker to a specific interface instead, set `HERMES_DASHBOARD_BIND=<interface address>` in `/opt/hermes-home/.env` and reapply the installation. Do not publish the password-protected dashboard directly to the public internet; Hermes recommends OAuth for that deployment.

Check the authentication gate with `curl -s http://127.0.0.1:9119/api/status`: `auth_required` should be `true` and `auth_providers` should include `basic`.

## Encrypted backups and restore

The installer provisions the Google Drive remote, generates encryption secrets, and stores the recovery configuration in 1Password. The local configuration is `/root/.config/rclone/rclone.conf` with mode `0600`. New installations store encrypted archives and filenames in the `bedrock-backups` Drive folder through `rclone crypt`.

Each backup:

1. Creates a live SQLite snapshot with `hermes backup` and validates the ZIP.
2. Verifies the recovery configuration in 1Password.
3. Uploads the archive, reads it back through the decrypting remote, and compares SHA-256 hashes.
4. Saves refreshed Drive credentials to 1Password and removes remote archives older than 14 days.

Successful local archives are removed. Failed local archives remain in `/opt/hermes-home/data/hermes/backups/`; failed verification prevents remote retention cleanup.

To restore on the current server:

```bash
just restore                     # Latest archive
just restore hermes-backup-YYYYMMDDTHHMMSSZ-PID.zip
```

Restore validates the downloaded archive before stopping Hermes. If an installation already exists, it first creates a local `pre-restore-*.zip` snapshot. Import overwrites files present in the archive; other local files remain. A failed import leaves the gateway stopped.

To recover from a failed import using the local snapshot:

```bash
docker compose run --rm -T --no-deps hermes import /opt/data/backups/pre-restore-TIMESTAMP-PID.zip --force
just start
```

Pre-restore snapshots are retained until removed manually.

### Replacement server

Clone the repository and install it at `/opt/hermes-home/git/bedrock`, then run as root:

```bash
cd /opt/hermes-home/git/bedrock
bash scripts/install.sh --restore
# Or: bash scripts/install.sh --restore ARCHIVE.zip
```

This installs the host dependencies, retrieves `rclone.conf` from 1Password, restores Hermes, and enables maintenance after a verified backup. Recovery skips the Hermes setup wizard and refuses to generate new keys if the recovery document is missing.

Hermes OAuth credentials are included in the archive. Revoked credentials require authorization again:

```bash
# Google Drive: use the SSH tunnel described above.
rclone --config /root/.config/rclone/rclone.conf config reconnect hermes-drive:
just backup-setup

# Model provider:
docker compose exec hermes hermes auth add openai-codex
```

For installations using the previous manual configuration, `just backup-setup` reuses the existing `hermes-crypt` remote and saves its configuration to 1Password. Vault access errors, duplicate `rclone.conf` items, and conflicting keys stop provisioning without overwriting recovery material.

## Automatic maintenance

Schedules use the server's local time.

| Task | Schedule | Action |
| --- | --- | --- |
| Backup | Daily, around 03:15 | Verified encrypted backup, credential sync, 14-day retention |
| Update | Saturday, around 04:15 | Telegram secret sync, verified backup, image update, health check |
| Monitor | Every 15 minutes | Gateway process, disk usage below 90%, backup age below 36 hours, pending reboot notification |

A shared lock serializes installation and maintenance operations. Service failures trigger Telegram alerts. Docker logs are limited to three 10 MB files. Debian security updates are enabled; host reboots remain an operator action.

If a new image fails startup checks, the update script restarts the previous image and reports failure to systemd. The selected image is persisted in `/etc/bedrock/image.env`, which is also used by `just start`. Image rollback does not undo data migrations; the preceding backup is available on Drive. Process health checks cannot detect every functional regression in `latest`.

Use `just secrets-sync` to apply Telegram field changes immediately, or `just update` to update the container.

## Repository updates

As the checkout owner:

```bash
cd /opt/hermes-home/git/bedrock
git pull --ff-only
```

Then as root:

```bash
cd /opt/hermes-home/git/bedrock
bash scripts/install.sh
```

This reapplies dependencies and systemd units using the existing configuration. Scheduled updates update the Hermes image; repository updates are explicit.

Diagnostics:

```bash
journalctl -u hermes-backup.service -u hermes-update.service -u hermes-check.service -n 100
just --list
```

## Verification

```bash
bash scripts/verify.sh
```

Tests cover provisioning, backup, restore, and update failures using simulated external services. A local encryption round trip also runs when rclone is available. See [AUDIT.md](AUDIT.md) for validation results and limitations.

References: [Docker on Debian](https://docs.docker.com/engine/install/debian/), [rclone remote setup](https://rclone.org/remote_setup/), [rclone crypt](https://rclone.org/crypt/), [1Password documents](https://www.1password.dev/cli/reference/management-commands/document), [Hermes CLI](https://hermes-agent.nousresearch.com/docs/reference/cli-commands).
