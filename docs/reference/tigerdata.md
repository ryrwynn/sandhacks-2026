# Tiger Data (Tiger Cloud): reference for RentOrKnot

Sources: `docs/reference/raw/tigerdata/public-docs-notes.md` and `account.md` (paraphrased, read 2026-11-15), plus the public docs pages listed below. Docs index links ending in `/index.md` return 404; use the URLs without that suffix.

## Account and plan
- Plan: **free trial** of the Performance plan. New signups get **$1,000 in credits, valid 30 days**, no card.
- Service created around Nov 14, 2026, so credits likely end around **Dec 14, 2026**. Confirm the exact date in the console.
- No permanent free tier was found in the public docs.
- Performance plan from **$30/month**: 4 services; up to 8 CPU, 32 GB RAM and 16 TB per service.
- Scale plan from **$36/month**: unlimited services, read replicas, tiered storage.
- Billing: compute hourly; storage by average GB per hour.
- Plan limits on our console (storage, compute, connections): NOT copied yet (see Missing).

## Pricing claims to use
- Columnstore (hypercore) compression: docs say **90 to 98%**, and "up to 95%" on the pricing page. One docs example shrinks 194 MB to 24 MB.
- The MLH track text says "90%+ compression on free-tier instances." Measure our own ratio, do not quote the docs as ours.

## Quickstart and hypertables
Create a service in Tiger Console. The password is shown once; download the config. The project's `conditions` table is the quickstart sample.

```sql
CREATE TABLE conditions (
  time timestamptz NOT NULL, location text NOT NULL, device text NOT NULL,
  temperature double precision, humidity double precision)
WITH (tsdb.hypertable, tsdb.segmentby = 'device', tsdb.orderby = 'time DESC');
```

## Columnstore (hypercore)
Enable on an existing hypertable, then add an automatic policy:
```sql
ALTER TABLE listing_obs SET (timescaledb.enable_columnstore,
  timescaledb.segmentby = 'zip', timescaledb.orderby = 'observed_at DESC');
CALL add_columnstore_policy('listing_obs', after => INTERVAL '7 days');
```
Other policy functions: `remove_columnstore_policy()`, `add_compaction_policy()`, `remove_compaction_policy()`.

Measure before and after: `hypertable_compression_stats('listing_obs')` (also `chunk_compression_stats`).

## Continuous aggregates
Create with a materialized view and `timescaledb.continuous`, using `time_bucket()`:
```sql
CREATE MATERIALIZED VIEW zip_monthly WITH (timescaledb.continuous) AS
SELECT time_bucket('1 month', month) AS bucket, zip, avg(zori) AS zori
FROM zip_metrics GROUP BY bucket, zip;
SELECT add_continuous_aggregate_policy('zip_monthly',
  start_offset => INTERVAL '3 years', end_offset => INTERVAL '1 month',
  schedule_interval => INTERVAL '1 day');
```
- Refresh policy: `add_continuous_aggregate_policy()`.
- Real-time aggregation is **off by default** from TimescaleDB 2.13 on. Set it per view if the charts need the newest rows before a refresh.

## Retention and tiering
```sql
SELECT add_retention_policy('listing_obs', drop_after => INTERVAL '6 months');
```
Remove with `remove_retention_policy()`. The retention page does not mention tiered storage; tiered storage is on the Scale plan per the pricing page (see Missing).

## Toolkit (time-series analysis)
TimescaleDB Toolkit functions include: approximate count distinct, percentile approximation, `time_weight`, downsampling, counters and gauges, `timevector`, frequency analysis, state tracking, statistical and regression analysis, min/max, and `candlestick_agg` (financial). No DiskANN or pgvectorscale mention on the toolkit page.

## Vectors and extensions
- pgvector and pgvectorscale (DiskANN index) are documented under "AI and vectors" (`learn/search/pgvector-pgvectorsearch`). Use `vector(768)` to match Gemini embeddings (see `gemini.md`).
- `pg_textsearch` is documented for full-text search.
- Extension availability on our service: check with preflight section 10 (postgis, vector, vectorscale). Do not assume from the docs.

## Other
- Tiger CLI, Tiger MCP, and a REST API to create or resize services are documented.
- Connections and pooling: not stated in the docs read.

## Sizing (inference, not from the docs)
- All-California monthly index data: about 1,700 ZIPs x 2 to 4 metrics x 12 months per year, roughly **50,000 to 100,000 rows a year**.
- Listing observations: tens of thousands of rows. Storage is not the constraint; compute and query patterns are.
- A dev copy fits within the 4 services of the Performance plan (check the trial's limits in the console).

## Prize angle (MLH "Best Use of Tiger Data")
Judges want innovative, impactful, performance-driven use. Show: hypertables for every observation; continuous aggregates for the charts; columnstore compression ratios (before and after from `hypertable_compression_stats`); retention and tiering for old data; vector search in the same database; query timings in `docs/TIGER_CAPACITY.md`.

## Missing
- **Our plan's exact limits** (storage, compute, connections) from the console. Fallback: assume the Performance plan's published ceiling (8 CPU, 32 GB, 16 TB per service) and size tiers to fit the trial's credits; record the real limit in `TIGER_CAPACITY.md`.
- **Write behavior past a limit, connection limits, and pooling.** Fallback: keep connections low (a single pool in the API, under 20), and retry on connection errors.
- **PostGIS support and availability.** Fallback: store ZCTA geometry in GeoJSON files (`frontend/public/geo/`) and not in the database; check the extension with preflight section 10.
- **Forking a service.** Not found in the pages read. Fallback: create a dev copy by dumping and restoring a scratch schema, not by forking.
- **Exact trial end date.** Fallback: plan around Dec 14, 2026, and check the console.
- **Tiered storage availability on the trial.** Fallback: do not depend on it; use retention policies instead.
- **Real-time aggregation setting for our version.** Fallback: refresh the continuous aggregate on a short schedule and show "as of" times on charts.
