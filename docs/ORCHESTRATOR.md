# Orchestrator run (Setup branch)

The runbook's parallel build (section 4b), adjusted for this repo: everything is built, merged and deployed on `Setup`, the web app is `frontend/`, and deploys are followed with `scripts/watch-deploy.sh` instead of `gh run watch`.

## Before you start

1. Laptop plugged in, lid open, the Claude app or terminal left running.
2. Vultr server, one time:

   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/rentwatch_deploy -N ""
   # Vultr dashboard: Ubuntu Cloud Compute instance with ~/.ssh/rentwatch_deploy.pub as its SSH key; ports 80 and 443 open
   ssh -i ~/.ssh/rentwatch_deploy root@<server-ip>
   curl -fsSL https://get.docker.com | sh
   git clone -b Setup https://github.com/ryrwynn/sandhacks-2026.git /opt/rentwatch
   exit
   scp -i ~/.ssh/rentwatch_deploy .env root@<server-ip>:/opt/rentwatch/.env
   ```

3. GoDaddy Registry DNS: an A record for `@` pointing at the server IP. Wait until `dig +short <domain>` prints it.
4. GitHub secrets for the deploy workflow:

   ```bash
   gh secret set VULTR_HOST --body "<server-ip>"
   gh secret set VULTR_SSH_KEY < ~/.ssh/rentwatch_deploy
   gh secret set PUBLIC_URL --body "https://<domain>"
   ```

5. `./scripts/preflight.sh` shows no FAIL lines.
6. Start on `Setup`: `git switch Setup && claude --model opus`, then paste the prompt below.

## The prompt

```text
You are the orchestrator for RentWatch. Plan: docs/PLAN.md. Lane agents: .claude/agents/lane-*.md.
Work on the Setup branch: lanes branch from it, you merge into it, and every push to Setup deploys.
Never push to or merge into main. The app only reads and analyzes data. Never read or print .env.

Phase 0. Run ./scripts/preflight.sh. Record any FAIL in docs/DECISIONS.md and carry on with what
works: fixtures stand in for a failing source, and deploy checks wait until the server is reachable.

Phase 1, alone. Do M1: the repo layout from the plan (the web app is frontend/, not web/), a
pyproject.toml for uv, db/migrations/001_init.sql, db/seed_caps.sql (San Diego County: 8.8% for
2025-08-01 to 2026-07-31, 8.2% for 2026-08-01 to 2027-07-31), db/seed_sources.sql,
contracts/canonical.py, contracts/api_models.py, one fixture per endpoint, and stub modules with the
function signatures each lane will fill (check_increase, fair_rent.predict, forecast_12, score_zips,
analyze_listing, the adapter base class, and api/llm/gemini.py's parse_listing and text functions,
which every Gemini caller must use). Add an llm_cache table to 001_init.sql (key TEXT PRIMARY KEY,
job, model, response JSONB, created_at) and note in DECISIONS.md that it caches Gemini answers to
save free-tier quota. Run the migrations against DATABASE_URL. Scrape one rental
and one for-sale listing and record in docs/DECISIONS.md whether priceHistory and yearBuilt came
back. Commit and push Setup. Start no lane before the contracts are pushed.

Phase 2, in parallel. Start lane-data, lane-rules, lane-models, lane-api and lane-web as background
subagents at the same time, telling each its done-when check. While they run, write
docker-compose.yml (api, worker with cron, web, caddy), a Caddyfile for PUBLIC_HOST (/api/* to api
with the prefix stripped, everything else to web), scripts/deploy.sh and scripts/smoke.sh.
smoke.sh [URL]: the URL defaults to PUBLIC_URL read from .env without printing it; retry for up to
5 minutes; check /api/health; POST the plan's demo rent check expecting verdict over_cap and
max_legal_rent 2272.20; rank neighborhoods for both personas; exit non-zero on any failure; chmod +x
it. Keep .github/workflows/deploy.yml triggering on Setup. Push Setup and run
./scripts/watch-deploy.sh until the skeleton deploys.

Phase 3, integrate. As each lane reports done, review its branch and merge it into Setup in this
order: rules, models, data, api, web. Lanes own separate folders; if a conflict appears, keep the
contract and fix the lane's side. After api and web are merged, generate TypeScript types from
/api/openapi.json into frontend/src/lib/api.generated.ts and wire frontend/src/lib/api.ts to them,
keeping its existing functions. Run `uv run pytest api/tests -q` and
`cd frontend && npx tsc --noEmit && npm run build`, push Setup, and run ./scripts/watch-deploy.sh.
On failure read ./scripts/server-logs.sh api 200, fix, and repeat until the smoke test passes on
PUBLIC_URL. Then follow the plan's mode order: Renter (gate 2), Buyer, Owner.

Gemini is on the free tier: about 500 requests a day for the Flash Lite models and 20 for the Flash
models. Follow the quota rules in .claude/agents/lane-rules.md, lane-data.md and lane-api.md, keep
smoke.sh off the letter endpoint, and never loop over real Gemini calls while debugging. If
generated text comes back empty because the quota is used up, that's expected: the numbers still
show, so note it and carry on.

If a lane fails twice on the same error, stop it, write the problem to docs/DECISIONS.md and carry
on with the others. Report at each gate: what's merged, test output and live URL status. Finish with
a short report: what works, the live URL, the test and smoke-test output, and anything skipped.
```

## If the Vultr server isn't ready

Turn off the deploy workflow so each push doesn't produce a failed run (`gh workflow disable deploy`), and put this paragraph at the top of the prompt:

```text
The Vultr server isn't set up yet, so preflight FAILs for Vultr, the domain and the GitHub secrets
are expected. Skip every deploy step: don't run ./scripts/watch-deploy.sh or ./scripts/server-logs.sh,
and list the skipped deploy steps in the final report. Still write docker-compose.yml, the Caddyfile,
scripts/deploy.sh and scripts/smoke.sh. In place of the live smoke test, run the API with uvicorn and
the web app with `npm run build && npm start` on this machine, and make smoke.sh pass against them;
let smoke.sh take the API's base URL separately (SMOKE_API_URL) for this local run.
```

When the server is ready: do steps 2 to 4 of "Before you start", run `gh workflow enable deploy`, then tell the orchestrator (or a fresh session) "The server is ready: push Setup and run ./scripts/watch-deploy.sh until the smoke test passes on PUBLIC_URL."

## Switching to main later

Change `branches: [Setup]` in `.github/workflows/deploy.yml`, the default `DEPLOY_BRANCH` in `scripts/*.sh`, and the "Branches and deploy" section of `CLAUDE.md`. The server switches branches on its next deploy.
