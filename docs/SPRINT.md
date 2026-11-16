# Sprint: more data, served areas, card and Saved fixes, MCP form tools

Written 2026-11-15 for a fast orchestrated run with parallel lane agents. The prompt is in `docs/SPRINT_PROMPT.md`.
This file is the spec the lanes read. Rules from CLAUDE.md and the "Safety rules" in docs/NIGHT.md still apply.

## Fill in before you paste the prompt

| Setting | Default | Notes |
| --- | --- | --- |
| Bright Data budget for this sprint | $40 | At $1.50 per 1,000 records, that's about 26,000 records. The run stops before it would go over. |
| Areas to add | All of `data/zips_county.txt` (104 San Diego County ZIPs), every ZIP in a queued "Add this area" request, and 95014 (Cupertino) | The 104 county ZIPs cost about $23; each extra ZIP adds about $0.22 at the same ratio. The data lane lists the queued requests with their estimate before triggering. |
| County refresh after the backfill | Monthly | Estimated from today's ratio (1,777 records for 12 ZIPs at limit 10, so about 148 per ZIP): one county pass ≈ 15,400 records ≈ $23. Weekly would be about $100 a month; monthly is about $23. |
| Contact for /privacy and /terms | none | An email or URL to show instead of the personal Gmail address, or `none`. With `none`, the pages show no address (see W2). |
| Apartments.com collector ID | none | Only if you created a Bright Data AI Scraper Studio collector that outputs Zillow field names (see D4). Otherwise D4 is skipped. |

Tiger Data trial credit: $1,000, ending about Dec 14. Vultr credit covers a 2 GB resize if you want the worker to do county refreshes on the server.

## Lanes

Each lane is its own subagent in its own worktree (branch `sprint/<lane>` from `night`). Lanes own the files listed, so their merges don't collide. Shared contracts (`contracts/api_models.py`, `frontend/src/lib/api.generated.ts`) change only in step 0, made by the orchestrator before the lanes start.

| Lane | Owns | Depends on |
| --- | --- | --- |
| data | `worker/`, `sources/`, `data/`, `db/migrations/004_sprint.sql` | step 0 |
| api | `api/db.py`, `api/routers/` (not `mcp`), `api/tests/` for those | step 0 |
| models | `api/ml/`, `worker/train.py`, their tests | none (fixtures first; the real retrain runs after the data lane) |
| web | `frontend/src/` except `frontend/src/advisor/`, `frontend/public/` | step 0 |
| mcp | `api/mcp/` (new), `api/main.py` mount line, `frontend/src/advisor/`, `docs/MCP.md` | step 0 |

## Step 0 (orchestrator, before lanes): contracts

- `GET /zips` returns every **served** area, not the fixed 12: `zip`, `name`, `tier` (`core` | `county` | `on_demand`), `listings_30d`, plus the existing fields. "Served" means `areas.tier` is core, county or on_demand **and** the ZIP has at least 5 active listings in the shared tables.
- Prefill query parameters for every form (the table below). The web lane implements them and the mcp lane builds links with them, so both use this table and nothing else.
- Regenerate the frontend types and commit on `night` before starting the lanes.

### Prefill parameters

Values are plain strings. Dates are `YYYY-MM-DD`. Yes/no/unsure answers are `yes`, `no`, `unsure`. Home type is `apartment`, `condo`, `townhouse`, `single_family` or `unknown`. A page only fills its fields from these parameters; **it never submits on its own**. The person presses the button.

| Page | Parameters |
| --- | --- |
| `/renter` (Check my increase) | Keep the names `/renter` already reads for the apartment-page prefill; add any missing ones from: `address`, `zip`, `lowest`, `new`, `effective`, `year`, `type`, `increases`, `notice`, `corp` |
| `/renter?tab=listing` (Check this price) | `zip`, `beds`, `asking`, `baths`, `sqft`, `type`, `text` |
| `/gouging` | `zip`, `beds`, `new`, `date`, `before` |
| `/owner` | `zip`, `beds`, `target`, `sqft`, `year`, `type`, `lowest`, `effective`, `notice`, `corp` |
| `/owner/reach` | `zip`, `beds`, `ask`, `text` |
| `/buyer` | `budget`, `beds` |
| `/find` | `zip`, `beds`, `type`, `max`, `source`, `unit`, `sort`, `page`, `per`, and `starter_budget` + `starter_beds` to open and fill the Starter finder panel |
| `/advisor` | `needs` (Find by needs box), `ask` (advisor question, typed in but not sent) |

## Data lane

**D1. Speed pipeline.** The goal is to get fresh data from trigger to the live pages as fast as possible. Build D1 first, and benchmark it on rows already in `raw_records` (free) before triggering any new scrape.

*Fetch: run everything at once.*

- Split the inputs into parallel triggers of about 15 ZIPs each, so Bright Data collects them concurrently. Each trigger still goes through `worker.bd.plan_run`, and their sum is held to the sprint budget. Zillow and Facebook run at the same time.
- Poll all snapshots concurrently with `httpx` async, backing off from 5 s to a 30 s cap instead of sleeping a fixed interval. Download each snapshot as soon as it's ready; don't wait for the others.
- Download as NDJSON (`format=ndjson`), streamed, compressed if the API offers it. Start parsing while the download is still running.

*Format: vectorized and on every core.*

- The Bright Data Zillow output is the conversion format: `zpid`, `price`, `bedrooms`, `bathrooms`, `livingArea`, `yearBuilt`, `homeType`, `streetAddress`, `zipcode`, `latitude`, `longitude`, `description`, `homeStatus`. Every listing-site source maps through the same `map:` block as `sources/zillow_rent.yaml`. There's no per-source parsing code and no Gemini call for Zillow rows.
- Parse lines with `orjson`. Map chunks of 2,000 records as columns, with `polars`, never row by row. Neither is a dependency yet: add both with `uv add orjson polars` and check that the worker image still builds. That covers `map` (first non-null of `a|b`), `keep_if`, `drop_fields`, `property_types`, the description redaction (regex over the whole column) and the content hash (after `hash_ignore` fields are removed).
- Run chunks in a process pool sized by a `WORKER_PROCS` variable (default: CPU count, capped at 8 on the laptop, 1 on the 1 GB server). Use a pipeline: download, then map in parallel, then load, with bounded queues between the stages so memory stays flat.

*Load: set-based, a few connections at once.*

- Binary `COPY` (psycopg 3 `cursor.copy`) of each chunk into an unlogged temp table. Then one `INSERT ... SELECT ... ON CONFLICT` per target: `raw_records`, `staging_listings` and `staging_price_observations`.
- Resolve properties in SQL (one join on normalized address and ZIP), not per row.
- Up to 4 loader connections in parallel. Each owns a partition of rows by hash of the listing's external ID, so two loaders never touch the same row and can't deadlock.
- During the backfill, don't refresh the continuous aggregate or compress per chunk. Do one `refresh_continuous_aggregate` over the affected time range at the end, then compression (D5).
- The replay to shared after "go" is set-based too: `INSERT ... SELECT` from staging into the shared tables in one transaction per source, instead of re-mapping `raw_records` row by row.

*Make it show up fast.*

- After each load, the loader bumps a `data_version` row. The API checks it at most every 30 seconds and clears its caches (served areas, comparables, market) when it changes, so new data appears within a minute instead of after a 5-minute cache.
- Pages that show listings revalidate within 60 seconds.

*Facebook posts.*

- Gemini requests run in parallel, with 4 at a time by default and 10–20 posts per request. Concurrency halves on a 429 and recovers slowly. Answers stay cached, so a re-run costs nothing.

*Proof.*

- Correctness: the fast path and the current path, run on the same 200-record fixture, produce identical staging rows.
- Speed: report each stage's records per second (fetch, map, load), plus the time from trigger to staged and from "go" to live. Measure the current path and the fast path on the same `raw_records` rows.
- Optional: Tiger Cloud lets you raise the service's compute in its console for the backfill and lower it afterward; the trial credit covers it. Resizing Vultr to 2 GB lets the server run `WORKER_PROCS=2`. Both are console steps for the human; note them in the report, don't do them.

**D2. Backfill.** Estimate first (`worker.bd.plan_run`); refuse anything over the sprint budget.

- County: the areas from the fill-in, through `worker.county` on the fast path, into staging. If a ZIP comes back at Bright Data's cap, split its input by bedroom count (`/1-bedrooms/` etc. search URLs) on the next pass.
- Core 12: one deeper pass with a higher `limit_per_input` (start at 40) so more units and buildings appear. Sample 2 ZIPs first and extrapolate the cost before the full pass.
- Requested areas: every ZIP in a queued "Add this area" request, plus 95014. Run them in the same batched trigger.
    - Build their Zillow search URLs the way `worker/ondemand.py` does, with the right city slug (95014 is `cupertino`, not `san-diego`).
    - This run alone skips the $1-a-day on-demand cap; the spend still counts against the sprint budget.
    - Set each request's status (`loaded`, `failed` or `over_budget`) the way the on-demand worker would.
    - Add an `areas` row for each with tier `on_demand`, its county (95014 is Santa Clara), name and centroid.
- Report records, cost, usable share, listings per ZIP and per bedroom count.
- Never replay to shared before the human says "go".

**D3. Served areas.** After "go": `worker.replay --source zillow_rent_county --target shared --confirm-shared`, then set `areas.tier = 'county'` for every county ZIP that ended with at least 5 active listings, and fill `name`, `county` and centroids. ZIP names come from `data/zips_county.txt`; a row whose name is just the ZIP gets a real place name from the Census ZCTA-to-place file or stays the ZIP. Add the county source to the fair-rent training sources.

**D4. Apartments.com (only with a collector ID).** `sources/apartments_com.yaml` gets the same `map:` block as `sources/zillow_rent.yaml`, with the collector set to output those field names. Sample 20 records, check the mapping, stage. Skip D4 entirely without a collector ID.

**D5. Schedule and Tiger Data.** `docker/worker.crontab`: county refresh on the schedule from the fill-in. `db/migrations/004_sprint.sql` (additive only):

- an index on `price_observations (zip, beds, observed_at DESC)`;
- a compression policy on `price_observations` chunks older than 30 days, only if the service's TimescaleDB version supports updates on compressed chunks (check the version and say which);
- refresh `listing_weekly_zip` after the backfill.

Record the capacity numbers in `docs/TIGER_CAPACITY.md`.

## API lane

- **A1.** Replace the fixed `CORE_ZIPS` with the served-area set from step 0, read from `areas` plus active-listing counts, cached for 5 minutes, falling back to `data/zips.txt` if the query fails. Every query that filtered by `CORE_ZIPS` uses the served set. Update `api/tests/test_zip_filter.py`: a staged-only or index-only ZIP must still never appear.
- **A2.** `/zips` per step 0. Market, listings, ZIP page and map endpoints accept any served ZIP.
- **A3.** No report endpoint in this sprint. The "Report this listing" link is a placeholder (W2).

## Models lane

- **M1.** Fair rent: at 1,000 or more address-level rentals `worker/train.py` trains the gradient-boosted model, **and** still runs the median method's held-out check. Serve the model only if its held-out median absolute error is lower **and** its 80% coverage is at least 0.78; otherwise keep the median method. Record both in `model_runs.metrics` with the reason. Tests on fixtures first, so this is ready before the data lands.
- **M2.** Forecasts and scenarios cover every served ZIP that has 36 or more months of ZORI or ZHVI (the index tier already holds most county ZIPs). Report how many ZIPs got forecasts and the backtest summary for the new ones.

## Web lane

- **W1. Sidebar flush left.** In `frontend/src/app/layout.tsx` the sidebar and content sit in `mx-auto max-w-7xl`, so on wide screens the sidebar floats in from the edge. Make the sidebar sit against the left edge of the window at every width from `md` up, and keep the page content in its own centered container. The phone drawer stays as it is. Check 768, 1280 and 1920 px wide.
- **W2. Contact.** Remove the personal Gmail address everywhere (`frontend/src/components/LegalDoc.tsx` has it as `CONTACT`; `grep -rnE "[a-z0-9.]+@gmail\.com" frontend/src api docs` for the rest). Show the contact from the fill-in, or with `none`, no address.
    - Add a "Report this listing" link on apartment pages and in the cards' menus. **For now it points to `/api/health`** in a new tab, as a placeholder until a report endpoint exists. Mark it with a `TODO(report)` comment.
    - /privacy must not say that reports or removal requests are received. Say that a way to report a listing is coming.
- **W3. Facebook cards.** The "Facebook group · lower confidence" badge moves into the tags row as a normal tag (same chip size as the other tags; keep the text). The post link moves to the round link button at the top right of the card, the same button Zillow cards use for `source_url`, with `aria-label="Open the Facebook post for {title} in a new tab"`. Remove the "View post on Facebook" text link at the bottom. Same order on the apartment page header. Update `docs/DESIGN.md`, which currently says the button is never shown for social posts.
- **W4. Saved multi-select.**
    - "Open selected in new tabs" becomes **"Open sources in new tabs"** and opens each selected apartment's source: `source_url` for listing sites, `post_url` for Facebook. Items with neither open their apartment page, and the toast says how many did. Keep the one-click loop and the list of links the browser blocked.
    - "Remove selected" becomes **"Remove from saved"**, shown in the action bar whenever at least one card is selected (shift/Ctrl/Cmd-click or Select mode), with the undo toast.
- **W5. Dynamic area dropdown.** `ZIP_OPTIONS` in `frontend/src/lib/format.ts` is a fixed list of 12 used by `FilterBar`, `ui.tsx` and `/find`. Replace it with a `useAreas()` hook that reads `/zips` (cached; the static 12 are the first render and the fallback). Group with `<optgroup>`: "Core areas", "San Diego County", "Added on request", each sorted by name, showing `Name (ZIP)`. The home page, Find, and every other area picker use it, so a newly served ZIP appears without a code change. The home map gets shapes for every served ZIP (use `worker/zip_boundaries.py` to add missing ZIP polygons under `frontend/public/geo/`).
- **W6. Prefill.** Every form reads the step 0 parameters on load and fills its fields without submitting.
- **W7. Find pages instead of "Load more".**
    - Replace the "Load more" button on `/find` with page navigation: Previous, numbered pages (with … for gaps), Next. Show "Showing 16–30 of 1,863" above the grid.
    - Add a "Per page" select with 15, 30 and 60. The default is 15.
    - Use the API's `limit` and `offset`. Keep `page` and `per` in the URL so Back and shared links work.
    - Changing any filter or the sort goes back to page 1. Changing the page scrolls to the top of the results, and focus moves to the results heading so keyboard and screen-reader users land there.
    - Keep 44 px tap targets, and the controls fit at 375 px without sideways scrolling.
- **W8. Tool names, order and the price filter.**
    - **"Rent increase check" becomes "Rent Cap"**, written exactly that way. Change it in the sidebar label (hint "AB 1482"), the `/renter` h1 and page title ("Rent Cap | RentOrKnot"), the apartment page's "Renting here already?" button ("Check the Rent Cap"), and the /privacy heading ("Rent Cap checks").
    - **"Gouging check" becomes "Emergency Rent Limits".** Change it in the sidebar label (hint "Penal Code 396"), the `/gouging` h1 (currently "Price gouging check") and page title ("Emergency Rent Limits | RentOrKnot").
    - Leave URLs, API routes and advisor tool IDs unchanged. Update `docs/DESIGN.md` and `docs/PLAN.md` where they name these tools.
    - **"Find by needs" moves to the top** of `TOOLS` in `frontend/src/components/ToolsSidebar.tsx`. The order is: Find by needs, Rent Cap, Emergency Rent Limits, then the rest as they are.
    - **Show the price filter on Find.** On `/find`, the Max price select is always visible in the filter row; there's no "More filters" toggle there. Give `FilterBar` a prop for this so the home page keeps its toggle. The row still fits at 375 px with no sideways scrolling.
    - The Starter panel's "Rank the 12 areas" text no longer names a number, since W5 makes the area count change.

## MCP lane

"MCP tooling to fill in the forms" means an MCP server for Rent or Knot. An assistant like Claude can run the site's checks and get back a link that opens the right form already filled in. It stays analysis-only: the tools call our own engine and never post to, message or submit anything on another site.

- **P1. Server.** The official `mcp` Python SDK (FastMCP), streamable HTTP, mounted in FastAPI at `/mcp` (public URL `https://rentorknot.us/api/mcp`, since Caddy strips `/api`). Read-only, no auth, request size limit, and a per-IP rate limit (e.g. 30 calls a minute).
- **P2. Tools** (each returns the result plus `form_url`, built only from the prefill table):

  | Tool | Calls | `form_url` |
  | --- | --- | --- |
  | `check_rent_increase` | AB 1482 rules engine (not stored) | `/renter?...` |
  | `check_gouging` | Penal Code 396 engine (not stored) | `/gouging?...` |
  | `check_listing_price` | fair-rent estimate and label | `/renter?tab=listing&...` |
  | `owner_price_position` | owner price position and AB 1482 guardrail | `/owner?...` |
  | `owner_reach` | reach | `/owner/reach?...` |
  | `search_listings` | listings query | `/find?...` |
  | `find_by_needs` | matching | `/advisor?needs=...` |
  | `rank_areas` | Starter or Wealth builder ranking | `/find?starter_...` or `/buyer?...` |
  | `zip_profile` | typical rent, value, forecasts, scores | `/zip/{zip}` |
  | `prefill_form` | nothing; builds a link for any form from given fields | that form |

- **P3. Advisor.** The Mastra advisor gets the `prefill_form` tool, and its answers show a button such as "Open the rent check with these numbers".
- **P4. Docs.** `docs/MCP.md`: what each tool does, the prefill table, and how to connect (`claude mcp add --transport http rentorknot https://rentorknot.us/api/mcp`). Mention the MCP server on /about.

## Checks before "go" (all must pass)

- `uv run pytest api/tests -q` (new tests for the fast path, served areas, requested areas, model selection and every MCP tool), `cd frontend && npm run build && npx tsc --noEmit`, `./scripts/preflight.sh`.
- `node scripts/ui-check.mjs` and `node scripts/e2e.mjs` against the local production build, plus:
    - the sidebar touches the left edge at 1280 and 1920 px;
    - a Facebook card has its link button at the top right and the badge in the tags;
    - Saved: "Open sources in new tabs" opens source URLs; "Remove from saved" plus Undo restores both;
    - every form fills from its prefill link and doesn't submit;
    - the sidebar reads Find by needs, Rent Cap, Emergency Rent Limits first, and those two pages' headings and tab titles use the new names;
    - Max price is visible on Find without opening anything;
    - Find shows 15 per page by default, the Per page select changes it, page 2 shows different listings, and a filter change goes back to page 1;
    - the area dropdown lists the staged county ZIPs when `RENTORKNOT_READ_STAGING=1`;
    - an MCP client lists the tools and gets a result and a working `form_url` from each.
- `grep -rnE "[a-z0-9.]+@gmail\.com" frontend/src api docs` finds nothing.
- `docs/SPRINT_REPORT.md`: what changed, data counts and cost, model decision, anything skipped, and what "go" will do.

## After "go"

1. Replay county and core staging to shared (D3) and mark the served areas.
2. Retrain (M1, M2).
3. Merge `night` into `Setup` (this deploys rentorknot.us), then `scripts/smoke.sh`.
4. Live checks: the home dropdown lists the new areas, a county ZIP page loads with listings, and `https://rentorknot.us/api/mcp` answers a tool call.
