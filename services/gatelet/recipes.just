# Gatelet container operations.
gatelet-start:
    cd {{quote(repo)}} && ./scripts/compose.sh gatelet-start

gatelet-stop:
    cd {{quote(repo)}} && ./scripts/compose.sh gatelet-stop

gatelet-logs:
    cd {{quote(repo)}} && ./scripts/compose.sh gatelet-logs
