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
