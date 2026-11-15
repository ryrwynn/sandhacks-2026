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

Heartbeat: 2026-11-15 start — morning orchestrator on `night`; nothing pushed to Setup or main.

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
- [ ] a. collect (CLI, 2-group sample, gates, full run, fb_groups)
- [ ] b. extract (Gemini batches of ~10, neighborhood→ZIP table)
- [ ] c. listings in staging (dedupe, reposts → price observations, inactive after 21 days)
- [ ] d. API (filters, medians, source breakdown, health counts, contracts, staging flag)
- [ ] e. UI
- [ ] f. freshness cron (Mon/Thu, gated on terms_checked_on)
- [ ] g. tests

## 4. Browser check
- [ ] Playwright + scripts/ui-check.mjs, screenshots reviewed

## 5. Fixes
- [ ] renter flow, Find/Saved, map, buyer, owner, advisor, themes
- [ ] h1 on /apartments/{id}; ZHVI coverage; PC 396 "unverified" note

## 6. Deploy readiness
- [ ] preflight, Bright Data monthly cost estimate

## 7. Hand-off
- [ ] stop servers, push night, docs/WAKEUP.md
