# Tiger Data capacity study

Written overnight with **no database access** (no secrets were available to any agent), so every database
figure is marked **E** (estimated from row counts and typical Postgres row widths) or **M** (measured, from
files in this repo or public downloads). Section "Measure in the morning" has the exact commands that turn the
E figures into measurements. Limits come from `docs/reference/tigerdata.md`, whose "Missing" list says our
console's real storage and compute caps were never copied.

## Plan limits
- Free trial of the Performance plan: $1,000 credit, about 30 days (ends around Dec 14, 2026; confirm in the console).
- Performance plan ceiling: 8 CPU, 32 GB RAM, 16 TB per service, 4 services. Our trial service's own caps: **unknown**.
- Not stated in the docs: connection limits and write behavior past a limit. Keep one API pool under 20 connections.
- PostGIS availability unknown, so geometry stays in GeoJSON files (`frontend/public/geo/`), not in the database.
- Storage is billed by average GB-hour. At the sizes below, storage is a rounding error against the credit.

## Row projections
Assumptions: raw payload after dropping personal and bulk fields about 4 KB compressed in TOAST; `listings` row
about 1 KB with redacted text; `price_observations` and `area_metrics` rows about 140 bytes with their indexes.
Bright Data records come from the run plans in `sources/*.yaml` (limits per input) and the per-record price of
$1.50 per 1,000.

| Tier / source | Rows per year | Where | Size per year (E) | Notes |
| --- | --- | --- | --- | --- |
| core (12 ZIPs, today) | tens of thousands of observations | shared tables | under 20 MB | unchanged |
| index: Zillow ZORI + ZHVI, last 72 months | **180,500 (M)**: 952 ZIPs ZORI x 72, 1,541 ZIPs ZHVI x 72 | raw_records (3 MB of JSON in `data/index_ca_zillow.jsonl.gz`, 1.0 MB gzipped) then `staging_area_metrics` | about 25 MB, about 3 MB compressed | refreshed monthly: about 2,500 new rows a month |
| index: Census ACS | 3,600 | same | under 1 MB | once a year |
| county listings (103 non-core San Diego County ZIPs) | at most 1,030 records a weekly run: 54,000 raw rows, about 54,000 observations plus about 5 observations of history per new listing | raw_records, staging_listings | raw about 215 MB a year if every record were new, about 65 MB with content-hash dedupe (E); observations about 10 MB a year | $1.55 a run, about $80 a year at weekly cadence |
| on-demand | at most 25 records per ZIP, 6 ZIPs per request, $1.00 a day: 667 records a day | raw_records, staging_listings | about 100 MB a year at the daily cap | the cap, not demand, sets this |
| Facebook groups (10 localities, none confirmed public yet) | 10 groups x 50 posts x weekly = 26,000 | raw_records | about 40 MB a year | only rental offers with a price become listings |
| Total, all tiers at full cadence | about 0.4 million rows a year | | **about 250 to 450 MB a year (E)** | |

`raw_records` is the largest item: it is a plain table (not a hypertable), so retention is a scheduled
`DELETE`, not a policy (see below).

## Fit
All three tiers fit comfortably: even the pessimistic 450 MB a year is 0.003% of the 16 TB ceiling, and the trial
credit ($1,000) dwarfs storage cost. **The constraint is not Tiger; it is Bright Data spend** ($1.50 per 1,000
records) and **query cost once the live queries stop filtering by ZIP**.

The live market queries (`median_rent_by_beds`, `zip_features`, `latest_index_values`) do not filter by the
12 core ZIPs. After the morning merge they will scan every ZIP in the shared tables:
- `area_metrics` grows from about 4,000 rows to about 185,000 (46x). `latest_index_values` uses `DISTINCT ON
  (geo_id, metric)` over `area_metrics`: tens of ms on a primary-key range, fine, but the `zip_features` view
  reads all of `area_metrics`; add `WHERE geo_id = ANY(...)` or a materialized latest table when the index tier
  merges. Estimated about 50 to 150 ms (E) at 185,000 rows, well inside the API's 3 s pool timeout.
- `price_observations` for county adds about 10x the core volume; `median_rent_by_beds` reads the last 30 days
  (about 1 to 2 chunks) so stays flat: estimated 20 to 80 ms (E).
Do not merge the index tier into the shared `area_metrics` without that filter or a latest-value table.

## Policies that keep it small
- `price_observations`: columnstore after 7 days (`segmentby = zip`, `orderby = observed_at DESC`); the docs claim
  90 to 98% compression, we will quote only our own ratio from `hypertable_compression_stats`.
- `area_metrics`: columnstore after 60 days, `segmentby = geo_id, metric`.
- Retention: `add_retention_policy('price_observations', INTERVAL '2 years')` for county, on-demand and Facebook
  observations; core keeps its history. Index metrics keep 72 months.
- `raw_records` (not a hypertable): nightly `DELETE FROM raw_records WHERE fetched_at < now() - interval '90 days'
  AND source_key IN ('zillow_rent_county','zillow_rent_ondemand','facebook_groups_sd')` after replay has
  moved them. Raw payloads are only needed for replay and the 30-day Bright Data snapshot window.
- Continuous aggregate `listing_weekly_zip` already buckets by ZIP and week; it covers new ZIPs without changes.

## Caps set from this study
| Cap | Value | Why |
| --- | --- | --- |
| Records per on-demand ZIP | 25 (`worker.bd.ONDEMAND_LIMIT`) | about $0.04 a ZIP |
| ZIPs per on-demand request | 6 (`ONDEMAND_MAX_ZIPS`) | a big city never fans out |
| On-demand budget per day | $1.00 (`ONDEMAND_DAILY_USD`) | about 26 ZIPs a day; extra requests queue |
| On-demand ZIPs kept | 200 | LRU by `areas.last_scraped_at`; about 5,000 listings |
| County refresh | weekly, skipping ZIPs scraped in the last 6 days | `bd.stale_zips` |
| Facebook posts per group | 50, high-water mark on `date_posted` | brightdata.md |
| Bright Data total | `BRIGHTDATA_BUDGET_USD` (default $10) | refused before any trigger |

## Conclusion
- **Index tier (all California ZIPs): fits** easily (about 185,000 rows, 25 MB, about 3 MB compressed); load it
  into `staging_area_metrics` first and add a ZIP filter to the latest-value queries before merging.
- **County tier: fits** (about 65 MB a year of raw data, about 10 MB of observations). Cost is $1.55 per weekly run.
- **On-demand: fits** under the $1.00 a day cap and 200-ZIP retention (about 100 MB a year at most).
- **Facebook groups: fits**, but no public group URL is confirmed yet (see `sources/facebook_groups/groups.yaml`).
- The limit that matters is Bright Data cost, not Tiger storage. Query timings are **estimates** until measured.

## Measure in the morning (needs `DATABASE_URL`)
```bash
# 1. Size and rows now
psql "$DATABASE_URL" -c "SELECT pg_size_pretty(pg_database_size(current_database()))"
psql "$DATABASE_URL" -c "SELECT relname, pg_size_pretty(pg_total_relation_size(oid)), reltuples::bigint FROM pg_class WHERE relkind='r' AND relnamespace='public'::regnamespace ORDER BY pg_total_relation_size(oid) DESC LIMIT 15"
# 2. Query timings now (live size), then again after loading the index tier into staging
psql "$DATABASE_URL" -c "EXPLAIN (ANALYZE, BUFFERS) SELECT DISTINCT ON (geo_id, metric) geo_id, metric, value FROM area_metrics WHERE geo_type='zip' AND metric IN ('zori','zhvi') AND source_key='zillow_research' ORDER BY geo_id, metric, period DESC"
psql "$DATABASE_URL" -c "EXPLAIN (ANALYZE, BUFFERS) SELECT zip, beds, percentile_cont(0.5) WITHIN GROUP (ORDER BY price_usd) FROM (SELECT DISTINCT ON (po.listing_id) po.zip, po.beds, po.price_usd FROM price_observations po WHERE po.listing_type='rent' AND po.observed_at >= now() - interval '30 days' ORDER BY po.listing_id, po.observed_at DESC) t GROUP BY zip, beds"
# 3. Scaled sample in a scratch schema (dropped afterwards): 200k area_metrics-like rows
psql "$DATABASE_URL" <<'SQL'
CREATE SCHEMA scratch_cap;
CREATE TABLE scratch_cap.am (LIKE public.area_metrics INCLUDING ALL);
INSERT INTO scratch_cap.am SELECT (date '2020-01-01' + (g % 72) * interval '1 month')::date, 'zip', (90000 + g % 1800)::text,
  CASE WHEN g % 2 = 0 THEN 'zori' ELSE 'zhvi' END, 1000 + g % 900, 'zillow_research' FROM generate_series(1, 200000) g
  ON CONFLICT DO NOTHING;
EXPLAIN (ANALYZE) SELECT DISTINCT ON (geo_id, metric) geo_id, metric, value FROM scratch_cap.am ORDER BY geo_id, metric, period DESC;
SELECT pg_size_pretty(pg_total_relation_size('scratch_cap.am'));
DROP SCHEMA scratch_cap CASCADE;
SQL
# 4. Compression ratio on the real hypertable (after enabling columnstore on a dev copy only)
psql "$DATABASE_URL" -c "SELECT * FROM hypertable_compression_stats('price_observations')"
```
After steps 1 to 3, replace each **E** above with the measured value and record the console's storage and
connection limits.

## Measured (final run, 2026-11-15, read-only)

Steps 1, 2 and 4 above, run in a read-only transaction. Step 3 (scratch schema) was skipped: it writes to the shared
database.

| What | Measured |
| --- | --- |
| Database size | **126 MB** |
| Largest tables | `raw_records` 31 MB (10,964 rows), `staging_area_metrics` 23 MB (163,178 rows: the index tier), hypertables `price_observations` 20 MB, `area_metrics` 15 MB, `forecasts` 984 kB; `listings` 4.9 MB (2,051), `properties` 720 kB, `staging_listings` 392 kB (203), `listing_embeddings` 800 kB (140) |
| Latest ZORI/ZHVI per ZIP (`area_metrics`, live size) | 17 ms execution, 23 ms planning |
| 30-day rent medians (`price_observations`) | 3 ms execution, 1 ms planning |
| Compression (`hypertable_compression_stats('price_observations')`) | no compressed chunks (columnstore not enabled) |

The index tier landed at 23 MB, in line with the 25 MB estimate above. Both hot queries are well under 50 ms. Storage
is not the constraint; Bright Data cost is (docs/WAKEUP.md).

## Sprint measurements (2026-11-16, data lane, shared Tiger service, TimescaleDB 2.32.0)

| What | Measured |
| --- | --- |
| Database size | 126 MB before the sprint backfill, **208 MB** after (raw_records 87 MB / 22,241 rows, staging_listings 16 MB / 8,478 rows, staging_price_observations 2 MB / 11,330 rows) |
| Shared tables | unchanged: listings 2,103, price_observations 3,342 (the backfill only touched raw_records and the staging tables) |
| Bytes per record | raw_records about 4.0 KB per stored payload (87 MB − 31 MB over 11,300 new rows is about 5 KB incl. index); staging_listings about 1.9 KB per row |
| Backfill yield | 11,628 Bright Data records billed (about $17.44) became 8,371 staged Zillow listings; the rest were repeats, errors (building pages the crawl aborted) or non-rentals |
| Load speed | current row-by-row path about 10 rows/s (one round trip per row over the WAN); fast path about 620 rows/s with 4 loader connections (binary COPY plus one set-based INSERT per target), end to end 550 rows/s including a cold 8-process pool |
| Connections | the loaders use 4 plus one for the end-of-run steps; `max_connections` is 105 with about 20 in use during a run. The API pool stays under 20, so 5 loader connections are not a limit |
| Replay to shared (tested in a scratch schema, not the shared tables) | 2,161 listings, 2,132 properties and 2,349 observations in one transaction |
| Compression | 005_sprint_compression.sql (not applied). Compressed chunks accept INSERT, UPDATE, DELETE and INSERT ... ON CONFLICT on 2.32.0 (tested on a scratch hypertable). price_observations has 423 weekly chunks for 20 MB, so most chunks are tiny: the gain is chunk count and old history, not size |
| Tiger console | raising compute for a backfill is not needed at this size (the loads ran in seconds); both are console steps for a human if a much larger run is planned |

Cost model learned this sprint: `limit_per_input` is not a cap and is not linear. At the same limit the city-style search URL
(`/{city}-ca-{zip}/rentals/`) returned 5 to 60 records per ZIP while the ZIP-only URL
(`/homes/for_rent/{zip}_rb/`) returned about 130 per ZIP at limit 10 and about 415 at limit 40, with no aborted building
pages. A wrong city in the city URL 404s (billed as one record). The county monthly refresh therefore uses the ZIP form:
about 100 ZIPs x about 90 records = about 9,000 records, about $13 a month.
