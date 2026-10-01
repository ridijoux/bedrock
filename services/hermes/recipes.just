# Hermes container and its encrypted archive.
start:
    cd {{quote(repo)}} && ./scripts/compose.sh start

stop:
    cd {{quote(repo)}} && ./scripts/compose.sh stop

restart:
    cd {{quote(repo)}} && ./scripts/compose.sh restart

logs:
    cd {{quote(repo)}} && ./scripts/compose.sh logs

update:
    cd {{quote(repo)}} && ./scripts/update.sh

check-hermes:
    cd {{quote(repo)}} && ./scripts/check.sh hermes

backup-list:
    cd {{quote(repo)}} && ./scripts/compose.sh backup-list

restore archive="latest":
    cd {{quote(repo)}} && ./scripts/restore.sh {{quote(archive)}}