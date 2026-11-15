# Decisions and known issues

Newest at the bottom of each section. The orchestrator writes here; lanes report to the orchestrator.

## Phase 0: preflight (2026-11-14)

`./scripts/preflight.sh`: 6 FAILs, all deploy-side; the Vultr server isn't set up yet.

| Check | Result | What happens instead |
| --- | --- | --- |
| VULTR_HOST | empty | Deploy steps skipped; the stack is tested locally (uvicorn + `npm start`) |
| Deploy key `~/.ssh/rentwatch_deploy` | missing | Same |
| Domain rentorknot.us | resolves to the registrar's parking IP, not the server | Same; add the A record once the server exists |
| GitHub secrets VULTR_HOST, VULTR_SSH_KEY, PUBLIC_URL | missing | The deploy workflow is disabled (`gh workflow enable deploy` when ready) |

Everything else passed: Tiger Cloud connects with timescaledb_toolkit 1.26.0; PARSE_MODEL and LETTER_MODEL
are both gemini-3.1-flash-lite (200) and the fallback gemini-3.5-flash-lite (200); the Bright Data token,
Census key and Mapbox public token are valid. No local Docker, so `docker compose` is only checked for syntax here.

## Phase 1: M1

- **llm_cache table** (in 001_init.sql): caches every Gemini answer that passed validation, keyed by
  sha256(job + prompt + schema), so repeat page loads, tests and smoke runs spend none of the free-tier
  quota (about 500 requests a day on Flash Lite).
- **001_init.sql is re-runnable** (IF NOT EXISTS everywhere, `if_not_exists => true` on hypertables and
  the aggregate policy), and the continuous aggregate is created `WITH NO DATA` so it applies on an empty
  database. `scripts/migrate.sh` applies the migration and both seeds; applied to Tiger on 2026-11-14.
- **The 12 ZIP codes** (the plan doesn't list them), in `data/zips.txt`: 91910 Chula Vista, 92101 Downtown,
  92103 Hillcrest, 92104 North Park, 92105 City Heights (the demo renter), 92107 Ocean Beach, 92108 Mission
  Valley, 92109 Pacific Beach, 92111 Linda Vista, 92117 Clairemont, 92122 University City, 92126 Mira Mesa.
- **Money in the API is JSON numbers**, not Decimal strings: the rules engine works in Decimal and the router
  converts, so `max_legal_rent` is `2272.2` in JSON and the web client gets plain numbers.
- **The letter has placeholders** (`[Tenant name]`, `[Landlord name]`) instead of taking names, so no names
  reach Gemini or the cache, and one cached letter serves every tenant with the same numbers. The page fills
  the names in on the user's screen.
- **CanonicalListing gained `price_history`** (list of {date, price_usd, event}) so the loader can write the
  source's own history as `price_observations` with event='history'. Nothing is ever invented.
- **CheckResult gained optional fields** (`overage_yearly`, `increase_pct`, `third_increase`, `figures`) that
  the API response needs; the plan's five fields are unchanged.
- **Gemini stubs return None** until lane B lands, so the API's "numbers without text" path works from day one.
  Rules and ML stubs raise NotImplementedError.

### Bright Data sample scrape

Dataset `gd_lfqkr8wm13ixtbd8f5` (Zillow properties listing information), the one linked for this project.

- Discovery by input filters (`discover_by=input_filters`, location + listingCategory) is refused with
  HTTP 400 "Customer is not active". Collect-by-URL works, and so does `discover_by=url` with a Zillow
  search URL (e.g. `https://www.zillow.com/san-diego-ca-92104/rentals/`), so the worker uses search URLs.
- A collect-by-URL test (an off-market condo in 92122): **yearBuilt came back (1993); priceHistory was null.**
- `discover_by=url` snapshot sd_mwh78b0y24gbxr2vwq (92104, limit 2 per input) returned 13 records in about
  4 minutes: 11 rentals and 2 for sale.
  - **For sale: priceHistory came back (1 to 12 events, including past sales) and yearBuilt came back (1911, 2012).**
  - **Rentals: priceHistory came back (10 or 11 events, with "Listed for rent", "Price change", "Listing removed")
    but yearBuilt was missing on every rental**, and nowhere else in the record. Ten units at one address shared
    the identical history, so for multi-unit buildings it describes the building's listing, not each unit.
  - Consequences: (1) the loader keeps a rental's history only when no other unit at the same address in the
    snapshot carries the same history; otherwise it's dropped, never attributed to a unit. (2) Year built for
    AB 1482 comes from a for-sale or off-market record at the same address (collect-by-URL returns yearBuilt)
    or from the tenant on the check form; when unknown, the verdict is `unclear` and the form asks for it.
    (3) Days on market in Owner mode can use the "Listed for rent" / "Listing removed" events where they exist.
  - `limit_per_input` is not a hard per-input cap: 2 requested, 11 rentals returned. Budget runs accordingly.

## Phase 3: integration

- **Merged:** lane/rules (54 tests), lane/models (73 tests total after merge).
- **Rent check with unknown year built:** lane B's engine treats the building as covered when `year_built`
  is null (the plan's decision order only exempts known-new buildings). This replaces the earlier note that an
  unknown year gives `unclear`; the form still asks for year built and prefills it from /units/search.
- **First real forecast run (2026-11-14):** 24 series (12 ZIPs × ZORI, ZHVI), median 12-month backtest MAPE
  1.38% (mean 1.65%), but the model beat the naive "next year equals this month" forecast on only 7 of 24.
  Per the plan, the UI shows the band and the backtest error under every chart, describes it as a trend
  range, and only says "beats naive" on the series where it does. Fair rent: skipped until rentals load.
- **Merged:** lane/data (864 rentals, 240 for-sale, ZORI/ZHVI/Census/amenities for all 12 ZIPs) and lane/api.
  Four API tests assumed engine stubs; they now patch a missing engine explicitly.
- **Per-series backtests:** worker/train.py now stores each series' mape, naive_mape and beats_naive in
  model_runs.metrics.by_series, and GET /zips/{zip}/series reads them, so "beats naive" is per ZIP and metric.
- **Fair rent (2026-11-14):** 864 rentals < 1,000, so the ZIP-and-bedroom median fallback is used. Leave-one-
  building-out: median absolute error $343, mean $439, and only 47% of held-out rents inside the 80% range
  (target 80%). Shown on screen with every estimate; the label stays "typical range", never "illegal".
- **Thin rentals:** 92101 has 0, 92105 has 1 and 92126 has 2 rentals. Bright Data runs ended with "Crawl
  aborted on job cancel" twice, so lane A stopped (same-error-twice rule). A retry with
  `python -m worker.run --source zillow_rent --zips 92101,92105,92126` may fill them; it costs credit, so it's
  left for a person to decide. The rent check (the demo) doesn't depend on listings.
- **Merged:** lane/web. All five lanes are now in Setup.
- **Generated types:** `npx openapi-typescript` was blocked in this environment (it downloads a package at run
  time), so `scripts/gen-api-types.py` (no downloads) writes `frontend/src/lib/api.generated.ts` from
  /api/openapi.json. `frontend/src/lib/contract.ts` now re-exports those types (same names the components use)
  and keeps the enum aliases and disclaimers; `api.ts` imports the generated types. Rerun the script after any
  change to contracts/api_models.py: `python3 scripts/gen-api-types.py [URL_OR_FILE]`.
- **Comparables never mix bedroom counts.** The orchestrator's lane D brief said to widen to the whole ZIP under
  5 comparables, which mixed studios into a 2-bedroom estimate. Now: same ZIP and beds only, at least 5, else
  HTTP 503 "Not enough comparable listings in <zip>". 92105 (1 rental) hits this until more rentals load.
  Estimates report the fair-rent run's median absolute error and 80% coverage.
- **POST errors are never replaced by sample data.** The web client used to serve fixture data on any non-OK
  answer, which could have shown a tenant the demo verdict for their own numbers. Now a POST error shows the
  API's message; fixtures are used only when the API is unreachable (labeled "Showing sample data").
- **Starter persona at the plan's $1,900 budget, 1 bedroom:** 0 ZIPs within budget, all 12 in the stretch list
  (real typical 1-bedroom rents are above $1,900). Pick a higher demo budget or present the stretch list.
- **Gemini text:** the listing-gap explanation came back empty on the first real call; the numbers still show.
  Not retried (quota rules).

### Deploy steps skipped (Vultr server not set up)

- Pushing Setup to deploy and `./scripts/watch-deploy.sh` for the skeleton and the integrated build.
- `./scripts/server-logs.sh api 200` on failures.
- `./scripts/smoke.sh` against PUBLIC_URL. Instead it passed locally:
  `SMOKE_API_URL=http://localhost:8000 ./scripts/smoke.sh http://localhost:3000` (uvicorn + `npm start`).
- `docker compose` build and run (no Docker on this laptop); the compose file is only syntax-checked.
- When the server is ready: docs/ORCHESTRATOR.md "Before you start" steps 2 to 4, `gh workflow enable deploy`,
  push Setup, `./scripts/watch-deploy.sh`.

## Phase 2: RentOrKnot apartment tracker (2026-11-14)

### Step 1: merge of origin/main

- Merged origin/main into Setup. Conflicts: `.gitignore` (union of both), `frontend/README.md` (kept Setup's text,
  heading now "RentOrKnot web"), `frontend/src/app/layout.tsx` (Setup's layout plus rynn's `SavedProvider`, title
  "RentOrKnot"), `frontend/src/app/page.tsx` (rynn's market overview is now `/`).
- Main's code imported `@/src/...`; Setup's tsconfig maps `@/*` to `./src/*`, so those imports were rewritten to `@/...`.
- The previous mode-picker home (ZIP map and three mode cards) is kept as `/tools` until lane-web folds it into
  the new navigation. rynn's `NavBar` is kept but unused; `ModeNav` is still the site nav.
- `frontend/public/*.svg` boilerplate was deleted by main; nothing referenced it.
- Not merged: origin/pipeline. It is Django-era scaffolding by a teammate: `pipeline/` (config, run, schema,
  clean modules for Zillow, Trulia, Facebook and ZORI, plus committed `.pyc` files), `scrapper/brightdata.py`
  (Bright Data job runner) and `scrapper/price_refresh.py` (collect-by-URL refresh of only the price of known zpids,
  one credit per URL, accepting a result only if its zpid was requested), and it deletes `sandhacks/`, `django_app/`
  and `.env.example`. It overlaps lane A's `worker/` (which already fetches, cleans and loads these sources), and
  it posts to a Django prices endpoint we don't run. Idea worth borrowing later: the price-only refresh by zpid for
  saved apartments, which is a cheaper way to extend price history than rerunning whole ZIP searches.
- Lane A's work (`lane/data`: worker pipeline, source templates, fixtures, data caches) is also merged into Setup.

### Step 3: engine fixes while the lanes build the tracker

- **Starter ranking at $1,900 is correct, not a bug.** The filter is a hard budget cut on the ZIP's typical rent for the
  chosen bedroom count (median of our listing prices, ZORI when a ZIP has no listings of that size). Real 1-bedroom
  medians in the 12 ZIPs run from $2,247 (92105, ZORI fallback) to $3,266 (92103), so nothing is within $1,900 and all 12
  land in "stretch". Studios: only 92105 qualifies, from a single listing. Proposed demo budget: **1 bedroom at $2,500**,
  which ranks 5 ZIPs (92126, 92107, 92105, 91910, 92117; 92126 rests on only 2 listings); $2,700 ranks 6. The plan's
  Maria rent check is a different flow and is unaffected. Smoke test only needs ranked + stretch > 0, so it is unchanged.
- **Fair-rent 80% range.** The median method's p10 to p90 of pooled comparables covered only 47% of held-out rents
  because units in one building share a rent: 864 rentals come from just 58 buildings, so the pooled spread is far
  narrower than the spread between buildings. `api/ml/fair_rent.py` now calibrates the range from the empirical
  spread of log(rent / median of the other buildings in the same ZIP and bedroom group). The tail mass is chosen on
  the training folds (building-grouped inner folds) as the narrowest one that reaches 80% held-out coverage, then
  fitted on all rows; the multipliers are stored in the fair_rent run's metrics (`spread`) and the API applies them.
  Result after retraining on 919 rentals (a last Bright Data run for 92101, 92105, 92126, 92107 and 92117 added only 56
  rentals, so the 1,000-row model threshold was not reached and I stopped scraping): held-out 80% coverage 0.845,
  median absolute error $278, range about 0.83x to 1.24x of the median. Estimates for groups with fewer than 5
  comparables are still refused.
- **Forecasts.** After retraining, 7 of 24 series beat the naive baseline (4 of 12 rent, 3 of 12 value). The API already
  returns `backtest_mape`, `naive_mape` and `beats_naive`; the web lane was told no page may claim accuracy or
  superiority and that every chart shows its 80% band and backtest error.
