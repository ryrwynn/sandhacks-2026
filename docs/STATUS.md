# Overnight run status

Heartbeat: 2026-11-15 — api + mcp merged (89304c7; 329 tests, tsc, build pass); data, models, web running

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

Heartbeat: 2026-11-15 — api + mcp merged (89304c7; 329 tests, tsc, build pass); data, models, web running

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

Heartbeat: 2026-11-15 — api + mcp merged (89304c7; 329 tests, tsc, build pass); data, models, web running

- [x] 1. Connectivity: database ok (8 s timeout)
- [x] 2. Schedules and rules: weekly zillow_rent Thu 12:00 UTC; FMR_RULE_VERIFIED=True; HUD SAFMR refused (202 empty), fmr.yaml stays unverified; BD estimate ≈ $17–26/month in WAKEUP.md
- [x] 3. Facebook roommate offers: prompt + roommate_wanted flag + 3 tests. Full run re-extracted (no scrape, ~30 Flash Lite calls): 290 posts, 133 usable (45.9%), 18 whole, 94 rooms (94 roommate-wanted), 21 sublets, 0 unusual; not_offer 70, no_zip 47, no_price_or_beds 40. Staging: 107 listings after dedupe (52 in the 12 ZIPs). Sample not re-extracted: all 40 of its posts are in the full run. Not replayed to shared.
- [x] 4. Live-query ZIP filter in api/db.py (CORE_ZIPS) + api/tests/test_zip_filter.py (24 tests)
- [x] 5. Partner fixes a–g (a buyer values, b Starter in Find, c Save at bottom, d favicon, e tags API+UI, f /saved multi-select [lane], g Roommate wanted/Sublet)
- [x] 6. /privacy and /terms [lane] + footer, /about, sign-in links; added rent-check storage to privacy
- [x] 7. Docs (PLAN current state, DESIGN, ACCOUNTS step 2)
- [x] 8. Checks
  - [x] preflight: all OK except FAIL "on battery" (laptop power) and WARNs (no DEV_DATABASE_URL, extra tables, no local Docker)
  - [x] pytest 299 passed; build + tsc pass
  - [x] local servers: API :8000 (RENTORKNOT_READ_STAGING=1) pid 92617; web :3000 pids 93238
  - [x] interaction checks 10/10 (map pan loads Orange County, first paint x4 themes + dark first visit, /saved shift-click, Find Starter)
  - [x] full ui-check 186/186 (UI_BATCH=6 UI_PARALLEL=2); earlier 150 and 181 failed only on headless WebGL contexts
  - [x] capacity SQL (read-only) recorded in TIGER_CAPACITY.md
  - [x] sign-in: /auth/session null signed out (no email/name), button shows, /auth/saves 401 without session, wrong token 401 handled quietly
- [x] 9. Servers stopped, night pushed, PR #2 ready for review, WAKEUP.md final-run section
- [ ] 10. Waiting for "go" (PR #2 ready, mergeable)

# Sprint (2026-11-15, docs/SPRINT.md)

Heartbeat: 2026-11-15 — api + mcp merged (89304c7; 329 tests, tsc, build pass); data, models, web running

Settings: Bright Data budget $40; areas = data/zips_county.txt + queued requests + 95014; county refresh monthly;
contact none; Apartments.com collector none (D4 skipped).

- [x] Preflight run; database reachable (TimescaleDB 2.32.0; raw_records 11,339; areas core 12 / county 103 /
      index 1,684 / on_demand 3; area_requests loaded 9, queued 1, failed 4)
- [x] Step 0: `ZipSummary.tier` + `county`, `contracts/prefill.py` (shared prefill table) with generated
      `frontend/src/lib/prefill.ts`, regenerated `api.generated.ts`; personal address removed from docs/FINAL.md
- [~] Lanes running on sprint/<lane>: data, api, models, web, mcp
- [ ] Merges + checks
- [ ] Retrain on staging, fair-rent decision
- [ ] Checks before go
- [ ] docs/SPRINT_REPORT.md, push night, wait for "go"

Errors that stopped a thread: none yet.
