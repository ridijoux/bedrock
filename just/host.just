# Host provisioning and maintenance shared by both services.
install:
    cd {{quote(repo)}} && bash scripts/install.sh

alias setup := install

status:
    cd {{quote(repo)}} && ./scripts/compose.sh status

backup:
    cd {{quote(repo)}} && ./scripts/backup.sh

check service="all":
    cd {{quote(repo)}} && ./scripts/check.sh {{quote(service)}}

# Run as root; credentials are loaded from /etc/bedrock/op-token.
secrets-sync:
    cd {{quote(repo)}} && ./scripts/secrets-sync.sh

alert target:
    cd {{quote(repo)}} && ./scripts/alert.sh {{quote(target)}}

install-timers:
    cd {{quote(repo)}} && ./scripts/install-timers.sh

monitor:
    cd {{quote(repo)}} && ./scripts/monitor.sh

backup-setup:
    cd {{quote(repo)}} && ./scripts/backup-setup.sh

test:
    cd {{quote(repo)}} && python3 -m unittest discover -s tests -v