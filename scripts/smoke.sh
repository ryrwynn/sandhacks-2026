#!/usr/bin/env bash
# Smoke test for RentOrKnot. Exit 0 only if every check passes.
# Usage: ./scripts/smoke.sh [URL]
#   URL          site root; defaults to PUBLIC_URL read from .env (never printed)
#   SMOKE_API_URL  API base URL when the API isn't at URL/api, e.g. a local uvicorn:
#                  SMOKE_API_URL=http://localhost:8000 ./scripts/smoke.sh http://localhost:3000
#   SMOKE_WAIT   seconds to wait for /health (default 300)
# Never calls the letter endpoint (it spends Gemini quota). Rent checks it creates are is_demo=true.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

URL="${1:-}"
SHOW_URL=1
if [ -z "$URL" ]; then
  SHOW_URL=0
  [ -n "${PUBLIC_URL:-}" ] && URL="$PUBLIC_URL"
  if [ -z "$URL" ] && [ -f .env ]; then
    URL="$(grep -E '^PUBLIC_URL=' .env | head -1 | cut -d= -f2- | sed -e 's/[[:space:]]*#.*$//' -e 's/^"//' -e 's/"$//')"
  fi
fi
[ -n "$URL" ] || { echo "FAIL  no URL given and PUBLIC_URL not set" >&2; exit 1; }
URL="${URL%/}"
API="${SMOKE_API_URL:-$URL/api}"; API="${API%/}"
WAIT="${SMOKE_WAIT:-300}"
FX=contracts/fixtures/requests
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
FAILS=0
ok()   { printf "OK    %s\n" "$1"; }
fail() { printf "FAIL  %s\n" "$1"; FAILS=$((FAILS+1)); }
[ $SHOW_URL = 1 ] && echo "site: $URL   api: $API" || echo "site: PUBLIC_URL from .env"

# json FILE PYTHON_EXPR -> prints the expression's value (d = parsed JSON)
json() { python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print($2)" "$1" 2>/dev/null; }

# 1. Wait for /health
start=$SECONDS; code=000
while :; do
  code=$(curl -sS -o "$TMP/health" -w '%{http_code}' --max-time 10 "$API/health" 2>/dev/null)
  [ "$code" = 200 ] && break
  [ $((SECONDS - start)) -ge "$WAIT" ] && break
  sleep 5
done
if [ "$code" = 200 ]; then
  ok "/api/health 200 after $((SECONDS - start))s: status=$(json "$TMP/health" 'd["status"]'), database=$(json "$TMP/health" 'd["database"]')"
else
  fail "/api/health returned $code after ${WAIT}s"
  echo; echo "$FAILS check(s) failed."; exit 1
fi

# 2. Web root
code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 30 "$URL/" 2>/dev/null)
[ "$code" = 200 ] && ok "web / 200" || fail "web / returned $code"

# 3. The plan's demo rent check: over_cap, max legal rent 2272.20
code=$(curl -sS -o "$TMP/check" -w '%{http_code}' --max-time 30 -H 'Content-Type: application/json' \
  --data @"$FX/checks.json" "$API/checks" 2>/dev/null)
verdict=$(json "$TMP/check" 'd["verdict"]'); max=$(json "$TMP/check" 'd["max_legal_rent"]')
if [ "$code" = 200 ] && [ "$verdict" = over_cap ] && \
   python3 -c "import sys; sys.exit(0 if abs(float(sys.argv[1]) - 2272.20) < 0.005 else 1)" "$max" 2>/dev/null; then
  ok "POST /checks demo case: over_cap, max_legal_rent $max"
else
  fail "POST /checks demo case: HTTP $code, verdict=${verdict:-?}, max_legal_rent=${max:-?} (want over_cap, 2272.20)"
  head -c 300 "$TMP/check" 2>/dev/null; echo
fi

# 4. Rank neighborhoods for both personas
for p in starter wealth; do
  code=$(curl -sS -o "$TMP/rank_$p" -w '%{http_code}' --max-time 60 -H 'Content-Type: application/json' \
    --data @"$FX/neighborhoods_rank_$p.json" "$API/neighborhoods/rank" 2>/dev/null)
  n=$(json "$TMP/rank_$p" 'len(d["ranked"]) + len(d["stretch"])')
  persona=$(json "$TMP/rank_$p" 'd["persona"]')
  if [ "$code" = 200 ] && [ "$persona" = "$p" ] && [ "${n:-0}" -gt 0 ]; then
    ok "POST /neighborhoods/rank $p: $(json "$TMP/rank_$p" 'len(d["ranked"])') ranked, $(json "$TMP/rank_$p" 'len(d["stretch"])') stretch; top $(json "$TMP/rank_$p" '(d["ranked"] or d["stretch"])[0]["zip"]')"
  else
    fail "POST /neighborhoods/rank $p: HTTP $code, $n ZIPs"
    head -c 300 "$TMP/rank_$p" 2>/dev/null; echo
  fi
done

# 5. Tracker endpoints: listings, one listing's detail, and the market series
code=$(curl -sS -o "$TMP/listings" -w '%{http_code}' --max-time 30 "$API/listings?limit=3" 2>/dev/null)
n=$(json "$TMP/listings" 'len(d["items"])'); total=$(json "$TMP/listings" 'd["total"]')
if [ "$code" = 200 ] && [ "${n:-0}" -gt 0 ]; then
  ok "GET /listings: $n of $total"
  lid=$(json "$TMP/listings" 'd["items"][0]["id"]')
  code=$(curl -sS -o "$TMP/detail" -w '%{http_code}' --max-time 30 "$API/listings/$lid" 2>/dev/null)
  nobs=$(json "$TMP/detail" 'len(d["observations"])')
  if [ "$code" = 200 ] && [ "${nobs:-0}" -gt 0 ]; then
    ok "GET /listings/$lid: $nobs price observations"
  else
    fail "GET /listings/$lid: HTTP $code, $nobs observations"; head -c 300 "$TMP/detail" 2>/dev/null; echo
  fi
  code=$(curl -sS -o "$TMP/byids" -w '%{http_code}' --max-time 30 "$API/listings?ids=$lid" 2>/dev/null)
  [ "$code" = 200 ] && [ "$(json "$TMP/byids" 'len(d["items"])')" = 1 ] && ok "GET /listings?ids=$lid" || fail "GET /listings?ids=$lid: HTTP $code"
else
  fail "GET /listings: HTTP $code, ${n:-0} items"; head -c 300 "$TMP/listings" 2>/dev/null; echo
fi
code=$(curl -sS -o "$TMP/market" -w '%{http_code}' --max-time 30 "$API/market?zip=92104&range=1y" 2>/dev/null)
np=$(json "$TMP/market" 'len(d["points"])')
if [ "$code" = 200 ] && [ "${np:-0}" -gt 0 ]; then
  ok "GET /market 92104: $np monthly points, $(json "$TMP/market" 'd["active_listings"]') active listings"
else
  fail "GET /market 92104: HTTP $code, ${np:-0} points"; head -c 300 "$TMP/market" 2>/dev/null; echo
fi

# 7. Overnight endpoints (docs/NIGHT.md). None spends Gemini quota except /match, whose parse is cached by text.
code=$(curl -sS -o "$TMP/goug" -w '%{http_code}' --max-time 30 -H 'Content-Type: application/json' \
  --data '{"zip":"92104","new_rent":2800,"pre_emergency_rent":2400,"offer_date":"2026-11-01","is_demo":true}' \
  "$API/checks/gouging" 2>/dev/null)
v=$(json "$TMP/goug" 'd["verdict"]')
if [ "$code" = 200 ] && [ -n "$v" ]; then ok "POST /checks/gouging: $v"; else fail "POST /checks/gouging: HTTP $code"; fi
code=$(curl -sS -o "$TMP/geo" -w '%{http_code}' --max-time 30 "$API/geo/zips?bbox=-117.3,32.7,-117.1,32.9" 2>/dev/null)
nf=$(json "$TMP/geo" 'len(d["files"])')
if [ "$code" = 200 ] && [ "${nf:-0}" -gt 0 ]; then ok "GET /geo/zips: $nf county file(s)"; else fail "GET /geo/zips: HTTP $code"; fi
code=$(curl -sS -o "$TMP/areas" -w '%{http_code}' --max-time 30 "$API/areas?limit=3" 2>/dev/null)
if [ "$code" = 200 ]; then ok "GET /areas: total $(json "$TMP/areas" 'd["total"]')"; else fail "GET /areas: HTTP $code"; fi
code=$(curl -sS -o "$TMP/trends" -w '%{http_code}' --max-time 30 "$API/zips/92104/trends" 2>/dev/null)
if [ "$code" = 200 ]; then ok "GET /zips/92104/trends"; else fail "GET /zips/92104/trends: HTTP $code"; fi
code=$(curl -sS -o "$TMP/scen" -w '%{http_code}' --max-time 30 "$API/zips/92104/series?scenario=baseline" 2>/dev/null)
case "$code" in
  200) ok "GET /zips/92104/series?scenario=baseline: $(json "$TMP/scen" 'len(d["scenarios"])') scenarios" ;;
  404) ok "GET /zips/92104/series?scenario=baseline: 404, no scenario run loaded yet (worker.train scenarios)" ;;
  *)   fail "GET /zips/92104/series?scenario=baseline: HTTP $code" ;;
esac
code=$(curl -sS -o "$TMP/match" -w '%{http_code}' --max-time 60 -H 'Content-Type: application/json' \
  --data @"$FX/match.json" "$API/match" 2>/dev/null)
if [ "$code" = 200 ]; then ok "POST /match: $(json "$TMP/match" 'len(d["results"])') results ($(json "$TMP/match" 'd["method"]'))"; else fail "POST /match: HTTP $code"; fi
code=$(curl -sS -o "$TMP/reach" -w '%{http_code}' --max-time 30 -H 'Content-Type: application/json' \
  --data @"$FX/owner_reach.json" "$API/owner/reach" 2>/dev/null)
if [ "$code" = 200 ]; then ok "POST /owner/reach: reach $(json "$TMP/reach" 'd["current_reach_pct"]')%"; else fail "POST /owner/reach: HTTP $code"; fi
for page in gouging scenarios advisor areas owner/reach; do
  code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 30 "$URL/$page" 2>/dev/null)
  if [ "$code" = 200 ]; then ok "page /$page"; else fail "page /$page: HTTP $code"; fi
done

echo
[ $FAILS -eq 0 ] && { echo "Smoke test passed."; exit 0; }
echo "$FAILS check(s) failed."; exit 1
