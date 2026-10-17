# Host installation and basic container operations.
install:
    cd {{quote(repo)}} && bash scripts/install.sh

alias setup := install

status:
    cd {{quote(repo)}} && ./scripts/compose.sh status

test:
    cd {{quote(repo)}} && python3 -m unittest discover -s tests -v
