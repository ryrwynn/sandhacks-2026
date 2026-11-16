# Sprint report: more data, served areas, card and Saved fixes, MCP form tools

Run 2026-11-15 to 11-16 on branch `night` (spec: docs/SPRINT.md). Nothing was pushed to Setup or main, nothing was
replayed into the shared tables, and deploy.yml, GitHub secrets and the server are unchanged. Waiting for **"go"**.

Settings used: Bright Data budget $40; areas = all of `data/zips_county.txt`, every queued "Add this area" request, and
95014; county refresh monthly; contact `none`; no Apartments.com collector (D4 skipped).

## What changed

| Lane | Change |
| --- | --- |
| Step 0 (orchestrator) | `/zips` rows carry `tier` (core, county, on_demand) and `county`. The prefill table is one constant, `contracts/prefill.py`, with a generated `frontend/src/lib/prefill.ts` and a test that keeps them equal. orjson, polars and mcp 2.3 added once on night. |
| api | The fixed 12 ZIPs are replaced by the **served set**: `areas.tier` in core, county or on_demand **and** at least 5 active listings, one query, cached 5 minutes, `data/zips.txt` as the fallback. Every listing, median, comparables, market, ZIP-page and map query uses it. `RENTORKNOT_READ_STAGING=1` (local only) also reads staged rows of every source. The API checks `data_version` at most every 30 s and clears its caches when it changes. |
| data | Fast path (`worker/fast.py`, `worker/sprint.py`): parallel triggers of about 15 ZIPs, async polling with 5 s to 30 s backoff, streamed compressed NDJSON, orjson plus polars mapping in a process pool (`WORKER_PROCS`), binary COPY and one set-based INSERT per target over 4 partitioned loaders, one aggregate refresh at the end. Set-based replay from staging to shared (`worker/staged_replay.py`). Migration 004 (`data_version`, a `(zip, beds, observed_at DESC)` index), applied. Migration 005 (compression policy), **not** applied. Monthly county cron. |
| models | Fair rent: from 1,000 address-level rentals the boosted model trains and both methods get a held-out check. The model is served only if its median absolute error is lower **and** its 80% coverage is at least 0.78. Both methods' metrics and the reason go to `model_runs.metrics`. Forecasts cover every ZIP series with 36+ months (`zillow_research` and `zillow_research_ca`). Scenarios cover the served ZIPs, grouped by history length. `worker.train --dry-run [--read-staging]` writes nothing. |
| web | W1 sidebar flush left. W2 no contact address; "Report this listing" placeholder pointing to /api/health (`TODO(report)`). W3 Facebook link in the round top-right button, badge in the tags. W4 "Open sources in new tabs" and "Remove from saved" with undo. W5 `useAreas()` from `/zips`, grouped Core areas / San Diego County / Added on request. W6 every form fills from the prefill parameters without submitting. W7 Find page navigation, 15/30/60 per page. W8 "Rent Cap" and "Emergency Rent Limits", sidebar order, Max price always on Find. |
| mcp | MCP server at `/mcp` (public `https://rentorknot.us/api/mcp`), stateless streamable HTTP, read-only, no auth, 32 KB request limit, 30 tool calls a minute per IP and 150 overall. Ten tools, each returning its result plus a `form_url` built only from the prefill table. Rent checks made through MCP are not stored. The advisor has a `prefillForm` tool and shows "Open the rent check with these numbers" buttons. `docs/MCP.md`, one sentence on /about. |
| orchestrator fixes | **Active listings are now judged per (source, ZIP)**, capped at 45 days. The county ZIPs share the `zillow_rent` key with the weekly core scrape; with one window per source, the first weekly scrape after "go" would have made every county listing inactive and dropped the county ZIPs off `/zips`. Scenario series for a served ZIP without a scenario run return its history instead of a 404. `--mark-areas` only touches county-tier ZIPs (never promotes an index ZIP). The personal address is removed from docs/FINAL.md. |

The personal Gmail address is gone from the working tree (`grep -rnE "[a-z0-9.]+@gmail\.com" frontend/src api docs`
finds nothing). It still exists in two earlier commits; removing it from history would mean rewriting published
branches, which I didn't do.

## Data and cost

**Bright Data: 11,628 records, $17.44 of the $40 budget** (24 runs tagged "sprint"; $22.56 left unspent on purpose).

- The county template's city-style URL was wrong: it hard-coded `san-diego`, so any ZIP outside the city 404s. City
  slugs now come from `data/areas_ca.csv`. The ZIP-only URL (`/homes/for_rent/{zip}_rb/`) works for every ZIP and
  returned far more per dollar: about 130 records per ZIP at limit 10 and about 415 at limit 40, against 5 to 60 for
  the city URL. That URL is what the county refresh uses.
- Cost per ZIP: about $0.17 for a county ZIP (limit 10), about $0.50 for a core ZIP (limit 40).
- Monthly county refresh: about 100 ZIPs x 90 records ≈ 9,000 records ≈ **$13 a month** (the spec estimated $23).
- Usable share: the 11,628 billed records became **8,371 distinct staged Zillow listings** (72%). The rest were repeats
  across snapshots, about 650 billed error pages from the city-URL runs, and non-rentals. Every staged row has price,
  beds, ZIP and an address.
- Requested areas: the only queued request was 92620 (Irvine), already scraped on 11-15 (72 staged), so it was marked
  `loaded` without a new scrape. 95014 (Cupertino, Santa Clara County) got 175 listings, an `areas` row (tier
  on_demand, name, county, centroid) and an audit request row.

**Listings per ZIP in staging (Zillow)**

| Group | ZIPs | Listings | ZIPs with ≥ 5 |
| --- | --- | --- | --- |
| Core 12 (deeper pass, limit 40) | 12 | 4,288 | 12 |
| San Diego County | 78 of 103 | 3,730 | 64 |
| Added on request | 4 | 353 | 4 |

- Core: 92101 Downtown 1,393, 92103 Hillcrest 818, 92108 Mission Valley 361, 92122 University City 357, 92111 Linda Vista 338, 92126 Mira Mesa 240, 92104 North Park 212, 91910 Chula Vista 190, 92117 Clairemont 135, 92109 Pacific Beach 122, 92107 Ocean Beach 69, 92105 City Heights 53.
- County (top): 92078 San Marcos 250, 92056 Oceanside 207, 91915 Chula Vista 191, 91913 Chula Vista 166, 92130 Carmel Valley 140, 92025 Escondido 138, 92123 129, 92129 123, 91942 La Mesa 104, 92128 102, 92054 Oceanside 100, … down to 92024 Encinitas 5. 25 county ZIPs (rural, PO box, military, campus) have fewer than 5 or none.
- On request: 95014 Cupertino 175, 92620 Irvine 72, 95405 Santa Rosa 57, 95620 Dixon 49.
- By bedrooms, county: studio 142, 1 bd 1,324, 2 bd 1,801, 3 bd 407, 4+ bd 56. Core: studio 569, 1 bd 1,953, 2 bd 1,534, 3 bd 213, 4+ bd 19.
- Not done: a bedroom-split pass. The ZIP URL didn't hit Bright Data's cap, so it wasn't needed.

## Served areas after "go"

With `RENTORKNOT_READ_STAGING=1` (what "go" will make real), `/zips` lists **81 areas: 12 core, 65 county, 4 added on
request**. Today, without the flag, it lists the 12 core ZIPs, as the live site does. Three county ZIPs (92067, 91902,
92003) have no Census place name and show as the bare ZIP.

## Fair-rent model decision

Dry run on shared plus staged data (`worker.train --dry-run --read-staging`, nothing written), **8,371 address-level rentals**:

| Method | Median abs. error | Mean abs. error | 80% coverage |
| --- | --- | --- | --- |
| Gradient-boosted model | **$275** | $463 | 0.56 |
| ZIP × bedrooms median (served now) | $402 | $611 | **0.81** |

**Decision: keep the median method.** The model's error is lower, but its 80% range covers only 56% of held-out rents,
below the 0.78 rule. (With yesterday's 2,085 rentals it was $323 vs $408 and 0.42 coverage.) A calibrated interval for
the model (for example conformal residuals per ZIP) is the next step if we want to serve it.

Forecasts in the dry run: 1,541 ZIPs from 2,258 series (235 series under 36 months skipped); median backtest MAPE 1.50%,
51% beat naive. The 69 newly served ZIPs: 129 series, median MAPE 1.52%, 46% beat naive. Scenarios: 81 served ZIPs.
The dry run took about 2 minutes on the laptop; the write run after "go" reads only shared tables.

## Zillow fast path timings

Benchmark on 5,036 `zillow_rent` rows already in `raw_records` (no scrape), shared Tiger over the laptop's WAN link,
10-core laptop, staging only:

| Stage | Current path | Fast path |
| --- | --- | --- |
| Map | 10,088 rows/s (map only) | 4,818 rows/s (8 processes; also cleans, hashes and serialises, cold pool) |
| Load | 10 rows/s (one INSERT per row) | 623 rows/s over 4 loaders (about 60x) |
| End to end | not measured | 550 rows/s: 5,036 rows in 9.2 s |

- Trigger to staged: 45 s to 13 min, almost all of it Bright Data's collection time. Our side takes 3 to 19 s after a
  snapshot is ready (up to 2,500 records).
- Identity proof: on a 200-record fixture, fast and current paths give identical staging rows, hashes and raw payloads
  at chunk sizes 9 and 2,000 (`api/tests/test_fast_path.py`).
- "Go" to live: the replay is set-based (scratch-schema test: 2,161 listings, 2,132 properties and 2,349 observations in
  one transaction). The API notices `data_version` within 30 s and pages revalidate within 60 s.
- Console steps for you, if you want them (not done): Tiger compute can be raised for a much bigger backfill (not
  needed at this size). A 2 GB Vultr resize would let the server run `WORKER_PROCS=2`; on 1 GB set `WORKER_PROCS=1`.

## Checks before "go"

CHECKS_PLACEHOLDER

## Skipped, and why

- **D4 Apartments.com**: no collector ID.
- **Bedroom-split pass**: not needed; the ZIP URL didn't hit the cap.
- **Census ZCTA-to-place names** for the county ZIPs whose name is the bare ZIP: not done; they stay the ZIP, as the spec allows.
- **Weekly core scrape URL**: `docker/worker.crontab` still runs the live weekly `zillow_rent` job with the city URL
  at limit 10. Switching it to the ZIP URL would give about 130 records per ZIP instead of about 40, for about $10 a
  month more. That's your call, not changed.
- **Sprint deep pass on the core 12 is a one-off**: after the next weekly core scrape, listings that the weekly job
  doesn't see go inactive, so core listing counts settle back toward the weekly job's size.
- No new Facebook scrape (not in the settings); the parallel Gemini extraction path is built and tested with mocks.

## What "go" will do (in this order)

1. **Replay staging to shared** (D3), from the main checkout:
   `uv run --env-file .env python -m worker.staged_replay --source zillow_rent --confirm-shared --mark-areas county`
   (core deeper pass, county and on-request Zillow rows, one transaction; county ZIPs with at least 5 listings seen in
   30 days stay tier county). Then refresh the continuous aggregate:
   `CALL refresh_continuous_aggregate('listing_weekly_zip', NULL, NULL);`
   The staged Facebook rows are not part of this (they wait for `worker.facebook replay`, as in docs/WAKEUP.md).
2. **Retrain** (M1, M2): `uv run --env-file .env python -m worker.train`, which writes model_runs (median method expected),
   forecasts for every series with 36+ months, and scenarios for the served ZIPs.
3. **Merge `night` into `Setup`** and push. This deploys rentorknot.us: images rebuild with polars, orjson and mcp, and
   `scripts/deploy.sh` runs `scripts/migrate.sh`, which applies **005 (compression policy on price_observations
   chunks older than 30 days)** after the replay. Follow it with `./scripts/watch-deploy.sh`, then `./scripts/smoke.sh`.
4. **Live checks**: the home dropdown lists the new areas, a county ZIP page (92078 San Marcos) loads with listings,
   and `uv run python scripts/mcp-check.py https://rentorknot.us/api/mcp https://rentorknot.us` answers every tool.
