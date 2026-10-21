# Gonzabot and Saruman — Hermes servers

Hermes on Debian 13, running in Docker and accessed through Telegram and its web dashboard. Gatelet runs in a separate container for Gonzabot only; review [its setup and security limitations](docs/gatelet.md) before connecting mail.

**No backup, restore, scheduled update, monitoring, health-check or alert facility is provided by Bedrock.** Data in `/opt/hermes-home/data/` is not protected against host loss, accidental deletion, or a failed image migration. Make your own recovery arrangements before reinstalling or changing images. Reapplying this repository disables and removes the legacy `hermes-backup`, `hermes-update`, `hermes-check`, and alert systemd units; it does **not** erase existing local archives, Drive archives, or 1Password recovery documents. It also removes the `20auto-upgrades` APT policy only if it exactly matches the one previously installed by Bedrock. Other independently managed host update services and policies are left alone.

## Two independent assistants

**Gonzabot** is the existing personal assistant and remains the default for every command.
**Saruman** is the professional assistant, selected with `HERMES_INSTANCE=saruman`.
Both use the same checkout at `/opt/hermes-home/git/bedrock`.

| Resource | Gonzabot (personal) | Saruman (professional) |
| --- | --- | --- |
| Docker project | hermes-home | hermes-saruman |
| State and conversations | /opt/hermes-home/data/hermes | /opt/hermes-saruman/data/hermes |
| Dashboard port | 9119 | 9120 |
| Gatelet admin port (localhost) | 4001 | — |
| Gatelet data | /opt/hermes-home/data/gatelet | — |
| 1Password vault / item | Bedrock / Hermes | Bedrock-Pro / Saruman |
| Host credentials and deployment state | /etc/bedrock | /etc/bedrock-saruman |

No personal data migration or secret renaming is required. Saruman starts with its own
empty data directory and setup wizard; personal conversations, memory and provider
credentials are not copied. Each container has its own 4 GB memory limit;
size the host for both.

To add Saruman, create a **second Telegram bot** with BotFather, then create the
**Bedrock-Pro** vault and **Saruman** item with the same fields listed below and
distinct dashboard credentials. Use a separate 1Password service account with
read-only access to **Bedrock-Pro only**. During installation, authorize the
professional model provider account.

From the existing checkout, run as root:

```bash
just saruman-setup
just saruman-status
just saruman-logs
```

Open Saruman at `http://<server LAN address>:9120`. Its optional dashboard bind
setting belongs in `/opt/hermes-saruman/.env`.

The Justfile provides explicit `gonzabot-*` and `saruman-*` commands for
`install`, `setup`, `start`, `stop`, `restart`, `status` and `logs`.
The `gatelet-start`, `gatelet-stop` and `gatelet-logs` commands are available only for Gonzabot.
For example, `just gonzabot-status` checks the personal assistant.
Explicit commands select their named instance even if `HERMES_INSTANCE` is
already set in the environment. The original commands remain available.

All instructions below default to Gonzabot. For Saruman, use the explicit recipes
or prefix installer commands with `HERMES_INSTANCE=saruman` and use the
professional paths from the table. Saruman runs Hermes only, without Gatelet,
its data directory, or its private network. Reapplying Saruman removes any
previous Gatelet container from its Docker project; existing Gatelet data is retained.

For direct Docker Compose commands, load the selected environment first as root:

```bash
export HERMES_INSTANCE=saruman
source scripts/common.sh
docker compose exec hermes hermes auth add openai-codex
```

Do not run bare `docker compose` for Saruman: its defaults address Gonzabot.
The containers share the host and image but have separate writable data and
credentials; this is not isolation from a host administrator.

## Requirements

- Debian 13 (amd64 or arm64) with systemd, Git, root access, at least 4 GB RAM, and Docker host connectivity.
- SSH access to `git@github.com:ridijoux/bedrock.git` from the checkout owner.
- A Telegram bot, a ChatGPT or Codex subscription, and a 1Password service account with **read access** to the Bedrock vault. No Google Drive or rclone setup is required.

## 1Password configuration

Create a **Bedrock** vault with a **Hermes** item containing:

| Field | Type | Value |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | Password | BotFather token |
| `TELEGRAM_CHAT_ID` | Text | Personal Telegram chat ID, positive integer |
| `HERMES_DASHBOARD_BASIC_AUTH_USERNAME` | Text | Dashboard login name |
| `HERMES_DASHBOARD_BASIC_AUTH_PASSWORD` | Password | Unique password of at least 16 characters |
| `HERMES_DASHBOARD_BASIC_AUTH_SECRET` | Password | Stable session-signing secret of at least 32 characters; generate with `openssl rand -hex 32` |

A read-only 1Password service account is sufficient. Its token is kept in `/etc/bedrock/op-token` (root-only). Existing service accounts with broader privileges can still authenticate; restrict or rotate them separately. The installer syncs these fields into Hermes's `.env` when run; there is no recurring secret-sync job.

## Install

Clone the repository and place it at `/opt/hermes-home/git/bedrock`. Run as root:

```bash
cd /opt/hermes-home/git/bedrock
bash scripts/install.sh
```

The installer installs host dependencies, reads the 1Password item, starts Hermes (and Gatelet for Gonzabot), and on a fresh installation runs the Hermes setup wizard. Select **ChatGPT or Codex Subscription**; Telegram credentials and the user allowlist are provisioned automatically. It also installs `gh` on the Debian host and bind-mounts `/usr/bin/gh` into Hermes. Authenticate `gh` separately inside Hermes if needed.

Re-running `just install` reapplies the deployment, including Compose changes; it does **not** take a pre-install snapshot or fetch a new Hermes image when an installation already exists. A changed Compose configuration may recreate a container without a backup. Gatelet remains pinned to the image in `compose.override.yaml`; image changes must be intentional. `just setup` is an alias of `just install`. Existing data remains under `/opt/hermes-home/data/hermes` and `/opt/hermes-home/data/gatelet`.

The legacy selected image in `/etc/bedrock/image.env`, if present, remains in effect. Inspect it before reinstalling, particularly if a previous update left the server on `bedrock-hermes:rollback`; no automatic update or rollback service remains. The repository itself is updated explicitly with `git pull --ff-only` by its checkout owner.

## Operations

From the installed checkout as root (or with `sudo`):

```bash
just status
just start
just stop
just restart
just logs
just gatelet-start
just gatelet-stop
just gatelet-logs
```

`just stop` and `just restart` target Hermes only. `just start` starts the selected instance’s existing containers without recreating them. There are **no** `backup`, `restore`, `update`, `check`, `monitor`, or alert commands in this repository. Docker's `restart: unless-stopped` still restarts containers after a crash or host boot, but no Bedrock timer checks whether the application actually works.

## Dashboard and Gatelet

Hermes publishes the dashboard on port 9119. On your trusted LAN, open `http://<server LAN address>:9119` with the 1Password dashboard credentials. Restrict port 9119 to the trusted LAN or VPN; do not publish password-only access directly to the internet. Set `HERMES_DASHBOARD_BIND=<interface address>` in `/opt/hermes-home/.env` and reapply the installation if a narrower binding is needed. For the separate mail proxy, follow [the Gatelet guide](docs/gatelet.md); its admin port 4001 is host-loopback only.

## Verification

```bash
bash scripts/verify.sh
```

The local suite checks provisioning, deployment contracts, and Gatelet policy templates without touching a live host. It does not verify actual Debian/Docker installation or data recoverability.
