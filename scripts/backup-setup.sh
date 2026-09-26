#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
lock
python3 scripts/provision.py login
python3 scripts/provision.py setup-backup
