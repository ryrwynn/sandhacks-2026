#!/usr/bin/env bash
# Show what's running on the Vultr server and the recent container logs.
# Usage: ./scripts/server-logs.sh [service] [lines]     e.g. ./scripts/server-logs.sh api 200
# Reads only VULTR_HOST from .env (or the environment) and never prints other settings.
set -euo pipefail
cd "$(dirname "$0")/.."

svc="${1:-}"
lines="${2:-100}"
[[ $svc =~ ^[A-Za-z0-9_-]*$ ]] || { echo "Bad service name: $svc" >&2; exit 2; }
[[ $lines =~ ^[0-9]+$ ]]       || { echo "Lines must be a number" >&2; exit 2; }

if [ -z "${VULTR_HOST:-}" ] && [ -f .env ]; then
  VULTR_HOST="$(grep -E '^VULTR_HOST=' .env | head -1 | cut -d= -f2- | sed -e 's/#.*//' -e 's/[[:space:]"'\'']//g')"
fi
[ -n "${VULTR_HOST:-}" ] || { echo "VULTR_HOST isn't set in .env" >&2; exit 2; }

KEY="${DEPLOY_KEY:-$HOME/.ssh/rentwatch_deploy}"
ssh_opts=(-o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new)
[ -f "$KEY" ] && ssh_opts+=(-i "$KEY")

ssh "${ssh_opts[@]}" root@"$VULTR_HOST" \
  "cd /opt/rentwatch && echo \"branch: \$(git rev-parse --abbrev-ref HEAD) at \$(git log -1 --oneline)\" && \
   if [ -f docker-compose.yml ]; then docker compose ps && docker compose logs --no-color --tail=$lines $svc; \
   else echo 'No docker-compose.yml on the server yet'; fi"
