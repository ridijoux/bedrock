#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
container=$(docker compose ps --all -q hermes)
[[ -n $container ]] || { echo 'Hermes container is missing.' >&2; exit 1; }
docker inspect "$container" | jq -e 'length == 1 and .[0].State.Status == "running" and .[0].State.Health.Status == "healthy"' >/dev/null || {
  echo 'Hermes is stopped or its gateway health check is failing. Run just logs.' >&2; exit 1;
}
used=$(df -P . | awk 'NR == 2 {gsub("%", "", $5); print $5}')
((used < 90)) || { echo "Disk usage is ${used}%." >&2; exit 1; }
echo 'Hermes gateway process is healthy; disk usage is below 90%.'
