#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
target=${1:-all}
[[ $# -le 1 && -n $target ]] || { echo 'Usage: check.sh [all|service]' >&2; exit 2; }
[[ $target == all ]] || [[ $target =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]*$ ]] || {
  echo "Invalid service: $target" >&2; exit 2;
}
services=$(docker compose config --services)
[[ -n $services ]] || { echo 'No Compose services configured.' >&2; exit 1; }
if [[ $target != all ]]; then
  found=false
  while IFS= read -r service; do
    [[ $service == "$target" ]] && found=true
  done <<< "$services"
  [[ $found == true ]] || { echo "Unknown Compose service: $target" >&2; exit 2; }
  services=$target
fi
while IFS= read -r service; do
  [[ -n $service ]] || continue
  containers=$(docker compose ps -q "$service")
  [[ -n $containers ]] || { echo "$service container is missing or stopped." >&2; exit 1; }
  while IFS= read -r container; do
    [[ -n $container ]] || continue
    docker inspect "$container" | python3 -c '
import json, sys
service = sys.argv[1]
try:
    entries = json.load(sys.stdin)
    state = entries[0]["State"] if len(entries) == 1 else {}
    health = state.get("Health")
    healthy = state.get("Status") == "running" and (
        health.get("Status") == "healthy" if health else service != "hermes"
    )
except (ValueError, KeyError, TypeError, IndexError):
    healthy = False
if not healthy:
    print(f"{service} is stopped or unhealthy.", file=sys.stderr)
sys.exit(0 if healthy else 1)
' "$service" || exit 1
  done <<< "$containers"
done <<< "$services"
used=$(df -P . | awk 'NR == 2 {gsub("%", "", $5); print $5}')
((used < 90)) || { echo "Disk usage is ${used}%." >&2; exit 1; }
echo "Checked ${target} service(s); disk usage is below 90%."
