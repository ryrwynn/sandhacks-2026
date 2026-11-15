# Overnight run status

Heartbeat: 2026-11-15 04:22 PST — run complete; see docs/MORNING.md

## Phase 0, setup
- [x] preflight: all clear; WARN no DEV_DATABASE_URL (stage in shared DB), WARN no Google keys (sign-in off), WARN no local Docker
- [x] night-scout started (runs in background)

## Phase 1, contracts
- [x] db/migrations/002_night.sql (applied to shared DB)
- [x] contracts/api_models.py + fixtures
- [x] stubs + routers registered in api/main.py
- [x] frontend deps (lucide-react, Mastra, Auth.js)
- [x] contracts commit on night

## Phase 2, features
- [x] night-data (merged)
- [x] night-forecast (merged)
- [x] night-match (merged)
- [x] night-web (merged)
- [x] night-rules (merged into night)
- [x] night-accounts (merged)

## Phase 3, integrate
- [x] merge rules, forecast, data, match, accounts, web
- [x] regenerate frontend types
- [x] pytest (247) + tsc + build
- [x] local smoke (new endpoints pass; 4 DB-only checks fail locally, no DB) + smoke.sh endpoints
- [x] push night

## Phase 4, interface
- [x] night-theme merged, checks rerun (247 tests, contrast, tsc, build), pushed

## Phase 5, hand-off
- [x] draft PR night -> Setup: https://github.com/ryrwynn/sandhacks-2026/pull/2
- [x] docs/MORNING.md
- [x] STATUS complete

# Morning run (2026-11-15)

Heartbeat: 2026-11-15 07:40 PST — steps 1–7 done except DB-bound items; waiting for the owner (docs/WAKEUP.md)

## 1. Data
- [x] Load the data 1: index tier staged (160,122 and 3,056 rows) — ran by owner this morning, not rerun
- [x] Load the data 2: macro data and scenario forecasts written — ran by owner, not rerun
- [x] Load the data 3: 171 listings embedded — ran by owner, not rerun
- [x] raw_records check: zillow_research_ca 2,493, census_acs_ca 3,056 (this morning). NOTE: sources.facebook_groups_sd.terms_checked_on is already 2026-11-15 (not set by me; left as is)
- [x] county-tier CLI entry point: worker/county.py (refuses core ZIPs)
- [x] Bright Data sample 92037, 92014, 92106: cap 18, DELIVERED 96 records ($0.144, snapshot sd_mwhwxlaj4qpz5oojd), 96 staged. Fields confirmed (input url + discover_by=url; zpid, price, bedrooms, homeStatus FOR_RENT, streetAddress, zipcode). limit_per_input is NOT a hard cap (5.3x)

## 2. Local stack
- [x] uv sync, API :8000, npm ci + production build :3000 — PIDs: api 64703 (uv 64698), web 64752 (npm 64723)
- [x] pytest 247 passed, tsc clean (after build; Next generates PageProps), build ok

## 3. Facebook listings
- [x] commit groups.yaml (7 group URLs)
- [x] a. collect: worker/facebook.py. Sample 2 groups x 20 = 40 records (= cap, $0.06), 23/40 usable (57.5%), staged.
      Full run snapshot sd_mwhxcv0l15owbti9eg: 301 records (cap 350, ~$0.45); 6 groups public, UCSD group private (skipped).
- [ ] a2. full-run processing: FAILED twice on the same error — DB unreachable from this laptop (TCP to the DB port times
      out; DNS ok, internet ok, live server still reaches the DB). Thread stopped per the rules. Resume, no new cost:
      `uv run python -m worker.facebook collect --snapshot sd_mwhxcv0l15owbti9eg` (Gemini answers are cached).
- [x] b. extract: api.llm.gemini.parse_posts (10/request, Flash Lite), per-item validation, data/fb_neighborhood_zips.csv (77 single-ZIP names)
- [x] c. listings in staging (migration 003 staging_price_observations; dedupe, reposts, 21-day inactive) — sample's 23 loaded
- [x] d. API (source/unit_type filters, weighted medians, source breakdown, /health sources, contracts, RENTORKNOT_READ_STAGING=1)
- [x] e. UI (card, apartment page, Find filters, Alerts, market + ZIP breakdown, /about)
- [x] f. freshness cron (Mon/Thu 15:00 UTC, --cron gate on terms_checked_on)
- [x] g. tests: api/tests/test_facebook.py (18)

## 4. Browser check
- [x] Playwright (scripts/package.json) + scripts/ui-check.mjs. Run 2: 133/152; all 19 failures = WebGL contexts exhausted (fixed: browser per theme). Fixed: /auth/session 404 on every page, /listings/{id}/trends 500 for ZIPs without ZORI
- [x] screenshots reviewed (Desert Clay all pages both widths; home/Find/ZIP other themes). Final rerun blocked: DB unreachable

## 5. Fixes
- [x] Find source race, House filter 422, auth/session 404, trends 500, buyer raw ratios, legend over logo
- [x] h1 on /apartments/{id}; ZHVI measured coverage on charts + MODEL_CARD; PC 396 unverified -> unclear + note

## 6. Deploy readiness
- [x] preflight (see WAKEUP); zillow_rent ≈1,777 records/run ≈ $640/month; Facebook ≈ $3.90/month

## 7. Hand-off
- [x] servers stopped (8000 and 3000 free), night pushed, docs/WAKEUP.md written. Waiting for the owner.
- NOTE: preflight hung on the DB (laptop can't reach it since ~07:00; same error twice, thread stopped)

# Final run (2026-11-15)

Heartbeat: 2026-11-15 10:35 PST — step 2 done, starting step 3

- [x] 1. Connectivity: database ok (8 s timeout)
- [x] 2. Schedules and rules: weekly zillow_rent Thu 12:00 UTC; FMR_RULE_VERIFIED=True; HUD SAFMR refused (202 empty), fmr.yaml stays unverified; BD estimate ≈ $17–26/month in WAKEUP.md
- [ ] 3. Facebook roommate offers + full-run re-extract (staging only)
- [ ] 4. Live-query ZIP filter in api/db.py + test
- [ ] 5. Partner fixes a–g
- [ ] 6. /privacy and /terms
- [ ] 7. Docs (PLAN, DESIGN, ACCOUNTS)
- [ ] 8. Checks (preflight, pytest, build/tsc, ui-check, capacity SQL, sign-in)
- [ ] 9. Stop servers, commit, push night, PR #2 ready, WAKEUP.md
- [ ] 10. Wait for "go"
