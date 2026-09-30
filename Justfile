default:
    @just --list

setup:
    bash scripts/install.sh

start:
    ./scripts/compose.sh start

stop:
    ./scripts/compose.sh stop

status:
    ./scripts/compose.sh status

gatelet-start:
    ./scripts/compose.sh gatelet-start

gatelet-stop:
    ./scripts/compose.sh gatelet-stop

gatelet-logs:
    ./scripts/compose.sh gatelet-logs

gatelet-check:
    ./scripts/compose.sh gatelet-check

gatelet-backup-list:
    ./scripts/compose.sh gatelet-backup-list

gatelet-restore archive="latest":
    ./scripts/restore-gatelet.sh {{quote(archive)}}

logs:
    ./scripts/compose.sh logs

backup:
    ./scripts/backup.sh

update:
    ./scripts/update.sh

check:
    ./scripts/check.sh

# Run as root; credentials are loaded from /etc/bedrock/op-token.
secrets-sync:
    ./scripts/secrets-sync.sh

backup-list:
    ./scripts/compose.sh backup-list

restore archive="latest":
    ./scripts/restore.sh {{quote(archive)}}

alert target:
    ./scripts/alert.sh {{quote(target)}}

install-timers:
    ./scripts/install-timers.sh

monitor:
    ./scripts/monitor.sh

backup-setup:
    ./scripts/backup-setup.sh

test:
    python3 -m unittest discover -s tests -v
