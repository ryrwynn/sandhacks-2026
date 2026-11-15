#!/usr/bin/env bash
# Apply db/migrations/*.sql and the seeds to DATABASE_URL (read from the environment, or from .env
# without printing it). Every file is re-runnable.
# Usage: ./scripts/migrate.sh
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -z "${DATABASE_URL:-}" ] && [ -f .env ]; then
  DATABASE_URL="$(grep -E '^DATABASE_URL=' .env | head -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' -e 's/[[:space:]]*#.*$//')"
fi
[ -n "${DATABASE_URL:-}" ] || { echo "DATABASE_URL is not set" >&2; exit 1; }
for f in db/migrations/*.sql db/seed_sources.sql db/seed_caps.sql; do
  echo "applying $f"
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q -f "$f"
done
echo "migrations applied"
