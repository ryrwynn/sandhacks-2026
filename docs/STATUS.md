# Overnight run status

Heartbeat: 2026-11-15 00:53 PST — Phase 0

## Phase 0, setup
- [x] preflight: all clear; WARN no DEV_DATABASE_URL (stage in shared DB), WARN no Google keys (sign-in off), WARN no local Docker
- [ ] night-scout started (runs in background)

## Phase 1, contracts
- [ ] db/migrations/002_night.sql
- [ ] contracts/api_models.py + fixtures
- [ ] stubs + routers registered in api/main.py
- [ ] frontend deps (lucide-react, Mastra, Auth.js)
- [ ] contracts commit on night

## Phase 2, features
- [ ] night-data
- [ ] night-forecast
- [ ] night-match
- [ ] night-web
- [ ] night-rules
- [ ] night-accounts

## Phase 3, integrate
- [ ] merge rules, forecast, data, match, accounts, web
- [ ] regenerate frontend types
- [ ] pytest + tsc + build
- [ ] local smoke + smoke.sh endpoints
- [ ] push night

## Phase 4, interface
- [ ] night-theme merged, checks rerun, pushed

## Phase 5, hand-off
- [ ] draft PR night -> Setup
- [ ] docs/MORNING.md
- [ ] STATUS complete
