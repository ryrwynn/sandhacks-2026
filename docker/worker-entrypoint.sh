#!/usr/bin/env bash
# Saves the container's environment (from .env via compose) for cron jobs, installs the crontab,
# then runs cron in the foreground.
set -euo pipefail
export -p > /app/.cronenv
chmod 600 /app/.cronenv
crontab /app/docker/worker.crontab
echo "worker: cron installed"; crontab -l
exec cron -f
