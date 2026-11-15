# RentWatch
Plan: docs/PLAN.md is the source of truth. Read only the section you need.

## This repo
- The plan says `web/`; here the Next.js app is `frontend/` (Next.js 16: read frontend/AGENTS.md before changing it). Build on the existing pages and components; don't delete teammates' work.
- The API is FastAPI in `api/`. The Django folders (`sandhacks/`, `django_app/`) are unused scaffolding: don't build on them or delete them.
- Lane agents live in .claude/agents/; each lane edits only the folders its file names.

## Commands
- Python tests: `uv run pytest api/tests -q`
- Web checks: `cd frontend && npx tsc --noEmit && npm run build`
- Local stack: `docker compose up -d --build`
- Live smoke test: `./scripts/smoke.sh "$PUBLIC_URL"`

## Rules
- IMPORTANT: never read, print or commit .env. Code reads settings from environment variables.
- Verdicts come from api/rules/ab1482.py; forecasts and scores from api/ml/. Gemini only parses and writes words, and its text must pass figures_ok.
- Scores use prices, forecasts, listings and amenities only, never who lives in a ZIP.
- Label demo rows is_demo = true. Never invent price history.
- Every source goes through its sources/<key>.yaml template; drop personal fields before storing anything.
- The app only reads and analyzes. Never write code that posts, messages or submits anything to another site.
- Don't edit contracts/ or db/migrations/ without saying why in the commit message.
- After each working step: commit with a short message and push your branch. Only the orchestrator merges lane branches.

# Compact instructions
Keep the milestone list, failing test names and the live URL.