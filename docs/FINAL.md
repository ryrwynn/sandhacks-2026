# Final run: what you do first, then the prompt

## Part 1: what you do before pasting the prompt (about 30 minutes)

### A. Google sign-in (optional; skip it and sign-in simply stays off)

1. https://console.cloud.google.com → create or pick a project.
2. **APIs & Services → OAuth consent screen**: External; app name RentOrKnot; your support email; authorized domain
   `rentorknot.us`; no extra scopes (the defaults are openid, email, profile). Then **Publish app**. In "Testing" mode only
   listed test users can sign in. These basic scopes need no Google verification.
3. **Credentials → Create credentials → OAuth client ID → Web application**:
   - Authorized JavaScript origins: `https://rentorknot.us`, `http://localhost:3000`
   - Authorized redirect URIs: `https://rentorknot.us/auth/callback/google`, `http://localhost:3000/auth/callback/google`
   - Copy the client ID and secret.
4. Make two secrets in a terminal: `openssl rand -base64 32` (AUTH_SECRET) and `openssl rand -hex 32` (ACCOUNT_API_TOKEN).

### B. Keys in both `.env` files (your laptop and the server's `/opt/rentwatch/.env`)

The server's `.env` predates the night keys, and every container (api, worker, web) reads that one file. Add:

```
GOOGLE_CLIENT_ID=...            # only if you did A
GOOGLE_CLIENT_SECRET=...
AUTH_SECRET=...
ACCOUNT_API_TOKEN=...
BRIGHTDATA_BUDGET_USD=10
ONDEMAND_DAILY_USD=1
LLM_EXTRACT_MAX_PER_RUN=40
```

You edit the server file yourself (ssh in, edit `/opt/rentwatch/.env`). The agent never touches the server. The deploy's
`docker compose up -d --build` picks the keys up.

### C. Database access from your laptop

Since about 07:00 this laptop can't open a TCP connection to the Tiger database (DNS works and the live site is fine).
Either switch networks or VPN, or in the Tiger console add your current IP to the service's allow list. Check:
`uv run python -c "import os,psycopg; psycopg.connect(os.environ['DATABASE_URL'], connect_timeout=8); print('ok')"`

### D. Three decisions (write them into the prompt's blanks)

1. **Zillow schedule.** The live `zillow_rent` job delivers about 1,777 records a run. At 8 runs a day that's about
   $640 a month. Twice a day is about $160, once a day about $80. Recommended: twice a day.
2. **Facebook terms.** `sources.facebook_groups_sd.terms_checked_on` is already set to 2026-11-15. If you have read
   Facebook's terms and the groups' rules, keep it, and the Monday/Thursday job (about $3.90 a month) runs after the
   deploy. If not, answer "clear" and the job stays off.
3. **Penal Code 396.** If you read the statute on leginfo and the 160%-of-Fair-Market-Rent rule is right, answer
   "verified" and the FMR path gives firm answers again. Otherwise it keeps answering "unclear" with an "Unverified" note.

### E. PR #1

Merging `night` into `Setup` puts it into PR #1 (Setup → main). That's fine if PR #1 just waits for review; merge or close
PR #1 first if you want them separate.

## Part 2: the prompt (start a fresh session on branch `night`, after loading `.env` into the shell)

```text
You are the final pre-merge orchestrator for RentOrKnot (rentorknot.us). Read CLAUDE.md, docs/WAKEUP.md,
docs/STATUS.md and the "Safety rules" in docs/NIGHT.md. You're on branch night (draft PR #2 into Setup).
Work unattended until step 8, then stop and wait for "go".

Keys are environment variables. Never read or print .env, never run env, printenv or set, never echo a
variable that holds a key or a connection string. Until I say go: never push to Setup or main, never merge
PR #2, never change deploy.yml, GitHub secrets or the server. Keep docs/STATUS.md current (new "Final run"
section). If the same error repeats twice, stop that thread and note it.

My decisions:
- Zillow schedule: ____ (e.g. "twice a day at 02:00 and 14:00 UTC")
- Facebook terms_checked_on: ____ ("keep" or "clear")
- Penal Code 396 160% rule: ____ ("verified" or "not verified")
- Google sign-in keys: ____ ("set" or "not set")

1. Connectivity. Check the database connection (8-second timeout). If it fails, stop and tell me.
2. Facebook. Save the paid full run without scraping again:
   uv run python -m worker.facebook collect --snapshot sd_mwhxcv0l15owbti9eg
   Report groups, posts, usable share, whole units, rooms, sublets and unusual prices. Apply the
   terms_checked_on decision (clearing it is the only sources change allowed). Never replay to shared yet.
3. Zillow cost. Change docker/worker.crontab to the schedule above (the cron runs only after the deploy). Put
   the new monthly estimate in WAKEUP.md, computed from Bright Data's snapshot list (dataset_size), not from
   limit_per_input.
4. Live-query safety. Before any replay to shared, the live API must not leak areas outside data/zips.txt: add
   a ZIP filter for the 12 ZIPs to the zip_features view usage and to the market, listing, median and
   comparable queries in api/db.py (the index tier is in staging_area_metrics; keep it there). Add a test.
5. Penal Code 396: if "verified", set FMR_RULE_VERIFIED = True in api/rules/gouging.py and update the tests
   and MORNING.md; otherwise leave it.
6. Checks, all must pass:
   - ./scripts/preflight.sh (report its output; don't change what it checks)
   - uv run pytest api/tests -q
   - cd frontend && npm run build && npx tsc --noEmit
   - API on :8000 with RENTORKNOT_READ_STAGING=1 and the production build on :3000, in the background (PIDs
     in STATUS.md), then node scripts/ui-check.mjs against http://localhost:3000. Fix what fails, smallest
     change first, and rerun until every load passes. Look at the screenshots for Find filtered to Facebook,
     a Facebook apartment page, a ZIP page with Facebook data and the gouging page.
   - Google sign-in: if the keys are "set", restart the frontend with them and do steps 2 to 8 of
     docs/ACCOUNTS.md "Manual test" that don't need a real Google login: /auth/session answers with no email
     or name, the button appears, a wrong ACCOUNT_API_TOKEN fails quietly. Update step 2 there: with sign-in
     off, /auth/session now answers {"enabled": false} instead of 404. Leave the real sign-in to me.
7. Stop the local servers, commit, push night, mark PR #2 ready for review (do not merge), and update
   docs/WAKEUP.md with the results and a short "ready to merge" checklist.
8. Stop and wait.

When I say go:
   a. Merge PR #2 into Setup.
   b. Fetch, then follow the deploy with ./scripts/watch-deploy.sh $(git rev-parse origin/Setup) until the
      smoke test passes.
   c. Only then: uv run python -m worker.facebook replay --target shared --confirm-shared (12 ZIPs only).
   d. Run ./scripts/smoke.sh https://rentorknot.us and node scripts/ui-check.mjs https://rentorknot.us.
   e. Fix forward on Setup. If the live site isn't passing within 30 minutes or two fix attempts, revert the
      merge on Setup (git revert -m 1), push, confirm the previous site is back, and report.
   f. Tell me to sign in with Google on the live site once (ACCOUNTS.md steps 3 to 7).

Rules: the app only reads and analyzes; never post to any site. Stay within BRIGHTDATA_BUDGET_USD and
Gemini's free tier. This run should need no new Bright Data scrape.
```
