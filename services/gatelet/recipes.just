# Gatelet container and its encrypted archive.
gatelet-start:
    cd {{quote(repo)}} && ./scripts/compose.sh gatelet-start

gatelet-stop:
    cd {{quote(repo)}} && ./scripts/compose.sh gatelet-stop

gatelet-logs:
    cd {{quote(repo)}} && ./scripts/compose.sh gatelet-logs

check-gatelet:
    cd {{quote(repo)}} && ./scripts/check.sh gatelet

alias gatelet-check := check-gatelet

gatelet-backup-list:
    cd {{quote(repo)}} && ./scripts/compose.sh gatelet-backup-list

gatelet-restore archive="latest":
    cd {{quote(repo)}} && ./scripts/restore-gatelet.sh {{quote(archive)}}