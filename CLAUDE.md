# RentOrKnot
Plan: docs/PLAN.md is the source of truth for the engine, data and API. docs/DESIGN.md is the source of truth for the product and UI: an apartment tracker first, with the renter, buyer and owner tools under "Tools". Read only the section you need.

## Name
- The product is **RentOrKnot**, live at https://rentorknot.us. It was called RentWatch earlier; use RentOrKnot in all new text, titles and code.
- Keep these old names on purpose, because renaming them breaks the deploy: the server path `/opt/rentwatch`, the deploy key `~/.ssh/rentwatch_deploy`, the Python project name `rentwatch` in pyproject.toml and uv.lock (the Docker build runs `uv sync --frozen`), and the comment in db/migrations/001_init.sql.

## This repo
- The plan says `web/`; here the Next.js app is `frontend/` (Next.js 16: read frontend/AGENTS.md before changing it). Build on the existing pages and components; don't delete teammates' work.
- The API is FastAPI in `api/`. The Django folders (`sandhacks/`, `django_app/`) are unused scaffolding: don't build on them or delete them.
- Lane agents live in .claude/agents/; each lane edits only the folders its file names.

## Branches and deploy
- `Setup` is the working branch and the only one that deploys. Lanes branch from it and the orchestrator merges into it. Don't push to or merge into `main`.
- Every push to `Setup` runs .github/workflows/deploy.yml: the Vultr server (`/opt/rentwatch`) checks out `Setup`, runs `docker compose up -d --build`, then `scripts/smoke.sh` runs against PUBLIC_URL.
- Overnight runs on the `night` branch follow docs/NIGHT.md, which overrides these branch, deploy and lane rules (no deploys, nothing pushed to Setup or main, new data staged).

## Commands
- Keys and services check: `./scripts/preflight.sh` (prints OK/FAIL only)
- Python tests: `uv run pytest api/tests -q`
- Web checks: `cd frontend && npx tsc --noEmit && npm run build`
- Local stack: `docker compose up -d --build` (only where Docker is installed; otherwise test through the deploy)
- Follow a deploy: `git push origin Setup && ./scripts/watch-deploy.sh` (waits for the run on HEAD; use a 10-minute timeout or run it in the background; prints the failed-step log on failure)
- Server logs: `./scripts/server-logs.sh api 200`
- Live smoke test: `./scripts/smoke.sh` (URL defaults to PUBLIC_URL from .env)

## Rules
- IMPORTANT: never read, print or commit .env. Code reads settings from environment variables.
- Verdicts come from api/rules/ab1482.py; forecasts and scores from api/ml/. Gemini only parses and writes words, and its text must pass figures_ok.
- Gemini is on the free tier (about 500 requests a day for Flash Lite, 20 for Flash). Call it only through api/llm/gemini.py, which caches answers; tests mock it; never loop over real Gemini calls.
- Scores use prices, forecasts, listings and amenities only, never who lives in a ZIP.
- Label demo rows is_demo = true. Never invent price history.
- Every source goes through its sources/<key>.yaml template; drop personal fields before storing anything.
- The app only reads and analyzes. Never write code that posts, messages or submits anything to another site.
- Don't edit contracts/ or db/migrations/ without saying why in the commit message.
- After each working step: commit with a short message and push your branch. Only the orchestrator merges lane branches, into `Setup`.
- Talk to the server only through scripts/ (they read just the keys they need from .env); don't ssh by hand.

# Compact instructions
Keep the milestone list, failing test names and the live URL.