# Deployment audit — 2026-09-26

## Changes

| Finding | Correction |
| --- | --- |
| Installation assumed sudo was available | Root installation through `su -`, with optional sudo setup documented |
| Deployment required several separate manual steps | `scripts/install.sh` orchestrates dependencies, secrets, initial backup, and timers; `--restore` provisions a replacement server |
| Python was used without an explicit package dependency | Python 3 installation, Debian 13/architecture/systemd checks, APT retries, and dpkg lock timeout |
| rclone remotes and encryption required manual configuration | Google OAuth through an SSH tunnel, generated secrets, and staged configuration files |
| Recovery configuration had to be copied to 1Password manually | Automatic document creation and updates, with read-back verification and credential synchronization during backups |
| Reinstallation could replace recovery keys | Existing keys are reused; conflicts, duplicates, and access errors stop provisioning; failed publication preserves generated keys for retry |
| Remote verification only checked the filename | ZIP validation and SHA-256 comparison against the complete decrypted remote archive |
| Local archives were deleted after failed uploads | Failed archives are retained; remote retention runs after verification and recovery configuration synchronization |
| Restore required manual secret recovery and an exact archive name | 1Password recovery, `latest` selection, validation before stopping Hermes, and a local snapshot of existing data |
| Health checks only tested container state | Gateway process health check and monitoring of disk usage and backup age every 15 minutes |
| Updates had no rollback | Verified backup before update, previous image retention, and automatic image rollback on failed startup checks |
| Docker logs had no size limit | Local logging driver with three 10 MB files |
| Secret injection did not configure a Telegram allowlist | Validated token, personal user allowlist, and home channel provisioned together |
| Some secrets were passed as command arguments | Encryption secrets and the Telegram URL passed through stdin; the service account token passed in the `op` process environment |
| No regression checks | Python tests, simulated shell workflows, a real local rclone encryption test, a verification script, and GitHub Actions |

## Validation results

- **32 tests passed**, covering provisioning and retries, key preservation and recovery, 1Password failures, duplicates, corrupt archives, unsafe paths, upload and checksum failures, interrupted import, image updates, rollback, and reapplying installation.
- **rclone 1.60.1:** local content and filename encryption, successful decryption, and rejection of an incorrect key. The test used the Ubuntu package variant; Debian 13 ships the same upstream version. The newer `--no-output` option is unavailable in this version and is not used.
- **Bash syntax and ShellCheck 0.11.0:** passed for all shell scripts.
- **just 1.45.0:** Justfile parsing passed.
- **Docker Compose 2.40.3:** configuration validation passed without starting a container.
- **systemd-analyze verify:** passed on temporary unit copies referencing the extracted just binary and a stub Docker service. These dependencies were unavailable on the validation host.

Test tools were extracted under `/tmp`. Shell tests execute the deployment scripts with simulated Docker and Drive commands and temporary filesystem paths.

## Limitations and operational choices

- A complete deployment on Debian 13 was not performed. APT installation, the Hermes image, Google authorization, actual 1Password operations, and Telegram responses still require validation on the target server.
- The service account has read and write access and remains on the host in a root-owned `0600` file for automatic credential synchronization. Its scope should be limited to the Bedrock vault. The token is excluded from the container.
- Google and model provider authentication require interactive authorization. Revocation requires authorization again.
- Image rollback preserves the current data. An incompatible migration may require restoring the preceding backup. Process health checks do not validate model responses.
- Automatic updates use `latest`. The previous image is retained, and general Docker image pruning is not automated. Disk usage is monitored.
- Remote retention is 14 days. Failed local archives and `pre-restore-*` snapshots are retained for recovery and may require cleanup after an incident.
- The checkout owner can modify scripts executed by root. This account must be a trusted administrator.

## References

- [Docker installation on Debian](https://docs.docker.com/engine/install/debian/).
- [Debian 13 rclone package](https://packages.debian.org/trixie/rclone), [remote setup](https://rclone.org/remote_setup/), [remote creation](https://rclone.org/commands/rclone_config_create/).
- [1Password service accounts](https://www.1password.dev/service-accounts/use-with-1password-cli), [document management](https://www.1password.dev/cli/reference/management-commands/document).
- [Hermes CLI: gateway, backup, and import](https://hermes-agent.nousresearch.com/docs/reference/cli-commands), [official Dockerfile](https://github.com/NousResearch/hermes-agent/blob/main/Dockerfile), [Telegram access control](https://hermes-agent.nousresearch.com/docs/user-guide/security).
