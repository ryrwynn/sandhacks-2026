#!/usr/bin/env bash
# Runs ON the Vultr server (the deploy workflow calls it over ssh): update the checkout, rebuild and
# restart the stack, apply migrations. Never prints .env.
# Usage: /opt/rentwatch/scripts/deploy.sh [branch]      (default: Setup)
set -euo pipefail
BRANCH="${1:-${DEPLOY_BRANCH:-Setup}}"
cd "$(dirname "$0")/.."
[ -s .env ] || { echo "no .env in $(pwd); copy it to the server first" >&2; exit 1; }

git fetch origin "$BRANCH"
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"
git log -1 --oneline

docker compose build
docker compose up -d --remove-orphans
# Migrations and seeds are re-runnable; the api image has psql and DATABASE_URL from .env.
docker compose run --rm --no-deps api ./scripts/migrate.sh
docker compose ps
docker image prune -f >/dev/null
