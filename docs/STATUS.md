# Overnight run status

Heartbeat: 2026-11-15 00:59 PST — Phase 2: data, forecast, match, web running; rules and accounts queued

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
- [ ] night-data (running)
- [ ] night-forecast (running)
- [ ] night-match (running)
- [ ] night-web (running)
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
