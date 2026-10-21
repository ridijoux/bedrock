#!/usr/bin/env bash
# Stable personal paths preserve the existing installation.
export HERMES_INSTANCE=${HERMES_INSTANCE:-gonzabot}
case "$HERMES_INSTANCE" in
  gonzabot)
    export HERMES_HOME=/opt/hermes-home
    export BEDROCK_STATE=/etc/bedrock
    export COMPOSE_PROJECT_NAME=hermes-home
    export HERMES_VAULT=Bedrock HERMES_ITEM=Hermes
    export HERMES_ROLLBACK_IMAGE=bedrock-hermes:rollback
    export HERMES_DASHBOARD_PORT=9119 GATELET_ADMIN_PORT=4001
    ;;
  saruman)
    export HERMES_HOME=/opt/hermes-saruman
    export BEDROCK_STATE=/etc/bedrock-saruman
    export COMPOSE_PROJECT_NAME=hermes-saruman
    export HERMES_VAULT=Bedrock-Pro HERMES_ITEM=Saruman
    export HERMES_ROLLBACK_IMAGE=bedrock-saruman:rollback
    export HERMES_DASHBOARD_PORT=9120
    unset GATELET_ADMIN_PORT
    ;;
  *) echo 'HERMES_INSTANCE must be gonzabot or saruman.' >&2; return 1 ;;
esac
export HERMES_DATA_DIR="$HERMES_HOME/data/hermes"
