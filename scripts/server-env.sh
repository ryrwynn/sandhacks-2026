#!/usr/bin/env bash
# Copy named settings to the server's /opt/rentwatch/.env without printing any value.
# Usage: ./scripts/server-env.sh KEY [KEY ...] [KEY=default ...]
#   KEY          copies KEY's value from the local .env (the last line wins, as in dotenv)
#   KEY=value    sets a non-secret value directly (e.g. BRIGHTDATA_BUDGET_USD=10) when it isn't in the local .env
# On the server: backs up .env to .env.bak-<time>, replaces or adds each key, keeps mode 600. It never
# restarts anything; the next deploy (docker compose up) picks the values up. Prints key names only.
set -euo pipefail
cd "$(dirname "$0")/.."
[ $# -gt 0 ] || { echo "Usage: $0 KEY [KEY ...] [KEY=default ...]" >&2; exit 2; }

if [ -z "${VULTR_HOST:-}" ] && [ -f .env ]; then
  VULTR_HOST="$(grep -E '^VULTR_HOST=' .env | head -1 | cut -d= -f2- | sed -e 's/#.*//' -e 's/[[:space:]"'\'']//g')"
fi
[ -n "${VULTR_HOST:-}" ] || { echo "VULTR_HOST isn't set in .env" >&2; exit 2; }

payload=""
for arg in "$@"; do
  key="${arg%%=*}"
  [[ $key =~ ^[A-Z][A-Z0-9_]*$ ]] || { echo "Bad key name: $key" >&2; exit 2; }
  line="$(grep -E "^${key}=" .env 2>/dev/null | tail -1 || true)"
  if [ -z "$line" ] || [ "$line" = "${key}=" ]; then
    if [[ $arg == *=* ]]; then line="$arg"; else echo "$key is not set in the local .env" >&2; exit 2; fi
  fi
  payload+="$line"$'\n'
done

KEY="${DEPLOY_KEY:-$HOME/.ssh/rentwatch_deploy}"
ssh_opts=(-o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new)
[ -f "$KEY" ] && ssh_opts+=(-i "$KEY")

printf '%s' "$payload" | ssh "${ssh_opts[@]}" root@"$VULTR_HOST" 'set -euo pipefail
cd /opt/rentwatch
[ -f .env ] || { echo "no .env on the server" >&2; exit 1; }
cp -p .env ".env.bak-$(date -u +%Y%m%dT%H%M%SZ)"
while IFS= read -r line; do
  [ -n "$line" ] || continue
  k="${line%%=*}"
  grep -v "^${k}=" .env > .env.tmp || true
  printf "%s\n" "$line" >> .env.tmp
  cat .env.tmp > .env && rm -f .env.tmp
  echo "set $k"
done
chmod 600 .env'
