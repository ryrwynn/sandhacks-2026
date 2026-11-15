#!/usr/bin/env bash
# RentWatch preflight: checks every key and service the agentic build needs.
# Usage: ./scripts/preflight.sh     Prints OK / WARN / FAIL only, never a key's value.
cd "$(dirname "$0")/.." || exit 1
[ -f .env ] || { echo "FAIL  no .env in $(pwd)"; exit 1; }

BRANCH="${DEPLOY_BRANCH:-Setup}"   # the branch that deploys
FAILS=0
ok()   { printf "  \033[32mOK\033[0m    %s\n" "$1"; }
warn() { printf "  \033[33mWARN\033[0m  %s\n" "$1"; }
fail() { printf "  \033[31mFAIL\033[0m  %s\n" "$1"; FAILS=$((FAILS+1)); }

set -a; source ./.env; set +a

echo "1. .env variables"
for k in BRIGHTDATA_API_TOKEN DATABASE_URL GEMINI_API_KEY PARSE_MODEL LETTER_MODEL \
         GEMINI_FALLBACK_MODEL CENSUS_API_KEY VULTR_HOST PUBLIC_HOST PUBLIC_URL; do
  [ -n "${!k}" ] && ok "$k is set" || fail "$k is empty"
done
[ -n "$PUBLIC_HOST" ] && [ "$PUBLIC_URL" != "https://$PUBLIC_HOST" ] && warn "PUBLIC_URL isn't https://\$PUBLIC_HOST"

echo "2. Tiger Cloud (DATABASE_URL)"
if [ -n "$DATABASE_URL" ]; then
  [[ $DATABASE_URL == *sslmode=require* ]] || warn "DATABASE_URL has no ?sslmode=require"
  out=$(psql "$DATABASE_URL" -tAc "select coalesce((select default_version from pg_available_extensions where name='timescaledb_toolkit'),'missing')" 2>&1)
  if [ $? -ne 0 ]; then
    fail "can't connect: $(echo "$out" | grep -o 'FATAL.*\|could not.*\|timeout.*' | head -1)"
  elif [ "$out" = missing ]; then
    fail "connects, but the timescaledb_toolkit extension isn't available"
  else
    ok "connects; timescaledb_toolkit $out available"
    n=$(psql "$DATABASE_URL" -tAc "select count(*) from information_schema.tables where table_schema='public'" 2>/dev/null)
    [ "${n:-0}" -gt 0 ] && warn "$n tables already exist in public; 001_init.sql has no IF NOT EXISTS, so drop them or expect M1 to trip" || ok "public schema is empty"
  fi
fi

echo "3. Gemini models"
if [ -n "$GEMINI_API_KEY" ]; then
  for m in "$PARSE_MODEL" "$LETTER_MODEL" "$GEMINI_FALLBACK_MODEL"; do
    [ -z "$m" ] && continue
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
      "https://generativelanguage.googleapis.com/v1beta/models/${m}:generateContent" \
      -H "Content-Type: application/json" -H "x-goog-api-key: ${GEMINI_API_KEY}" \
      -d '{"contents":[{"parts":[{"text":"Say OK"}]}]}')
    case $code in
      200) ok "$m returned 200" ;;
      503) warn "$m returned 503 (busy right now; fine as the fallback)" ;;
      429) fail "$m returned 429 (no quota on this key)" ;;
      *)   fail "$m returned $code" ;;
    esac
  done
fi

echo "4. Bright Data"
if [ -n "$BRIGHTDATA_API_TOKEN" ]; then
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 20 \
    -H "Authorization: Bearer $BRIGHTDATA_API_TOKEN" "https://api.brightdata.com/datasets/list")
  case $code in
    200)     ok "token accepted (now confirm the \$100 credit shows in Billing)" ;;
    401|403) fail "token rejected ($code)" ;;
    *)       warn "couldn't verify the token (HTTP $code); test one scrape by hand" ;;
  esac
fi

echo "5. Census API"
if [ -n "$CENSUS_API_KEY" ]; then
  body=$(curl -s --max-time 20 "https://api.census.gov/data/2023/acs/acs5?get=B19013_001E&for=zip%20code%20tabulation%20area:92104&key=${CENSUS_API_KEY}")
  case $body in
    '[["B19013_001E"'*) ok "key works" ;;
    *) fail "key rejected (click the activation link in the Census email first)" ;;
  esac
fi

echo "6. Vultr server"
KEY=~/.ssh/rentwatch_deploy
SSHOPT=(-o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new)
if [ -f "$KEY" ]; then ok "deploy key exists"; SSHOPT+=(-i "$KEY"); else fail "no deploy key at ~/.ssh/rentwatch_deploy (CI needs one)"; fi
if [ -n "$VULTR_HOST" ]; then
  out=$(ssh "${SSHOPT[@]}" root@"$VULTR_HOST" \
    'docker compose version >/dev/null 2>&1 && echo has_docker
     [ -d /opt/rentwatch/.git ] && echo has_repo && echo "branch=$(git -C /opt/rentwatch rev-parse --abbrev-ref HEAD)"
     [ -s /opt/rentwatch/.env ] && echo has_env' 2>&1)
  if [ $? -ne 0 ] && ! grep -q has_ <<<"$out"; then
    fail "can't ssh to root@VULTR_HOST: $(echo "$out" | tail -1)"
  else
    ok "ssh works"
    grep -q has_docker <<<"$out" && ok "Docker + compose installed" || fail "Docker not installed (curl -fsSL https://get.docker.com | sh)"
    if grep -q has_repo <<<"$out"; then
      sb="$(grep -o 'branch=.*' <<<"$out" | cut -d= -f2)"
      [ "$sb" = "$BRANCH" ] && ok "repo cloned at /opt/rentwatch on $BRANCH" \
        || warn "server checkout is on '$sb'; the first deploy switches it to $BRANCH"
    else
      fail "repo not cloned to /opt/rentwatch (git clone -b $BRANCH https://github.com/ryrwynn/sandhacks-2026.git /opt/rentwatch)"
    fi
    grep -q has_env    <<<"$out" && ok ".env copied to the server" || fail "no /opt/rentwatch/.env (scp it)"
  fi
fi

echo "7. Domain"
if [ -n "$PUBLIC_HOST" ]; then
  ip=$(dig +short "$PUBLIC_HOST" A | tail -1)
  [ -n "$ip" ] && [ "$ip" = "$VULTR_HOST" ] && ok "$PUBLIC_HOST resolves to the server" \
    || fail "$PUBLIC_HOST resolves to '${ip:-nothing}', not VULTR_HOST (add the A record, wait for DNS)"
fi

echo "8. GitHub"
secrets=$(gh secret list 2>/dev/null)
for s in VULTR_HOST VULTR_SSH_KEY PUBLIC_URL; do
  grep -q "^$s[[:space:]]" <<<"$secrets" && ok "secret $s set" || fail "secret $s missing (gh secret set $s ...)"
done
if git ls-files --error-unmatch .github/workflows/deploy.yml >/dev/null 2>&1; then
  ok "deploy.yml committed"
  grep -E '^[[:space:]]*branches:' .github/workflows/deploy.yml | grep -qw "$BRANCH" && ok "deploy.yml triggers on $BRANCH" \
    || fail "deploy.yml doesn't trigger on $BRANCH"
  git fetch -q origin "$BRANCH" 2>/dev/null
  git cat-file -e "origin/$BRANCH:.github/workflows/deploy.yml" 2>/dev/null && ok "deploy.yml is pushed to origin/$BRANCH" \
    || fail "deploy.yml isn't on origin/$BRANCH yet (git push origin $BRANCH)"
else
  fail ".github/workflows/deploy.yml isn't committed"
fi
cur=$(git branch --show-current)
[ "$cur" = "$BRANCH" ] && ok "checked out on $BRANCH" || fail "checked out on '$cur'; start the orchestrator on $BRANCH"

echo "9. This laptop"
pmset -g batt | grep -q "AC Power" && ok "on AC power" || fail "on battery; plug in before walking away"
command -v docker >/dev/null && ok "Docker installed locally" || warn "no local Docker; compose only gets tested on the server"

echo
[ $FAILS -eq 0 ] && echo "All clear." || echo "$FAILS check(s) failed."
