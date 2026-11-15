#!/usr/bin/env bash
# One cron job: load the saved environment, run the command, log to the container's stdout.
source /app/.cronenv
cd /app
echo "[$(date -u +%FT%TZ)] start: $*" >> /proc/1/fd/1
"$@" >> /proc/1/fd/1 2>&1
echo "[$(date -u +%FT%TZ)] exit $?: $*" >> /proc/1/fd/1
