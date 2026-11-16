# Sprint prompt

Before you paste: fill in the five values on the "My settings" lines, load `.env` into a fresh terminal
(`set -a; source .env; set +a`), check out `night`, and start `claude`. Copy the prompt with
`sed -n '/^```text$/,/^```$/p' docs/SPRINT_PROMPT.md | sed '1d;$d' | pbcopy`.

```text
You are the sprint orchestrator for RentOrKnot (rentorknot.us). Work fast: run the lanes in parallel.

Read CLAUDE.md, docs/SPRINT.md (the spec; follow it exactly), the "Safety rules" in docs/NIGHT.md,
docs/DESIGN.md and docs/WAKEUP.md. Read other docs only when a step needs them. You are on branch night.

My settings:
- Bright Data budget for this sprint: $40
- Areas to add: all of data/zips_county.txt, every ZIP in a queued "Add this area" request, and 95014
- County refresh after the backfill: monthly
- Contact for /privacy and /terms: none
- Apartments.com collector ID: none

Hard rules:
- Keys are environment variables. Never read or print .env, never run env, printenv or set, never echo a
  variable that holds a key or a connection string.
- The app only reads and analyzes. Nothing may post, message or submit anything to another site; the MCP
  tools call our own engine only.
- Facebook: public groups only; never read author fields, names, profile links or photos; never store post text.
- Stay inside the Bright Data budget: estimate with worker.bd before every trigger and refuse anything over it.
- Until I say "go": no replay to shared tables, no push to Setup or main, no merge of night into Setup, no
  change to deploy.yml, GitHub secrets or the server.
- Do not put the personal Gmail address in any file, commit message or doc; find it with grep and remove it.
- If the same error repeats twice, stop that thread, note it in docs/STATUS.md, and continue the others.
- Keep docs/STATUS.md current with a "Sprint" section and a heartbeat.

Plan:
0. Preflight and the database check (8-second connect timeout); stop and tell me if the database is
   unreachable. Then do docs/SPRINT.md step 0 yourself: the /zips served-area contract, the prefill
   parameter table as a shared constant, regenerated frontend types. Commit on night.
1. Start five lane subagents at once with the Agent tool, each with isolation: worktree, on Sonnet, on
   branch sprint/<lane> from night: data, api, models, web, mcp. Give each lane its section of
   docs/SPRINT.md, the file ownership table, the hard rules above, and the instruction to commit small and
   push its branch. Lanes don't edit files they don't own; if one needs a change elsewhere, it tells you and
   you make it on night and tell the others to merge night.
   - The data lane builds the D1 speed pipeline first and benchmarks it on rows already in raw_records
     (no new scrape), then runs its Bright Data sample (2 ZIPs), reports the cost per ZIP, then the full
     parallel backfill into staging only. Speed is a priority: parallel triggers, concurrent downloads,
     vectorized mapping on every core, COPY-based loads.
   - The web lane does W1–W8, the MCP lane P1–P4, the api lane A1–A3, the models lane M1–M2 on fixtures.
2. While they run, check on each lane and merge each one into night as soon as its tests pass. Re-run
   pytest, tsc and the build after every merge.
3. When the data lane's staging load finishes, run the models lane's retrain against staging
   (RENTORKNOT_READ_STAGING=1) and report the fair-rent model decision.
4. Run every check in "Checks before go" in docs/SPRINT.md: pytest, tsc, build, preflight, ui-check.mjs,
   e2e.mjs, the extra browser checks, the MCP client check and the grep. Fix failures with the owning lane.
5. Write docs/SPRINT_REPORT.md: what changed, records and dollars spent, listings per ZIP, served areas
   after "go", the fair-rent decision with both methods' numbers, timings for the Zillow fast path,
   anything skipped and why, and exactly what "go" will do. Push night. Then stop and wait for "go".

After I say "go", do "After go" in docs/SPRINT.md, in order, and report each live check's result.
```
