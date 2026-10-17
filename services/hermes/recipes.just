# Hermes container operations.
start:
    cd {{quote(repo)}} && ./scripts/compose.sh start

stop:
    cd {{quote(repo)}} && ./scripts/compose.sh stop

restart:
    cd {{quote(repo)}} && ./scripts/compose.sh restart

logs:
    cd {{quote(repo)}} && ./scripts/compose.sh logs
