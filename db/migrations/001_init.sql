-- db/migrations/001_init.sql
-- RentWatch schema (docs/PLAN.md "Data model"), plus llm_cache (see docs/DECISIONS.md).
-- Written to be re-runnable: every object uses IF NOT EXISTS.
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS timescaledb_toolkit;

CREATE TABLE IF NOT EXISTS sources (
  source_key        TEXT PRIMARY KEY,          -- 'zillow_rent', 'apartments_com', 'facebook_groups', ...
  kind              TEXT NOT NULL,             -- 'listing_site' | 'social' | 'area_index' | 'area_stats'
  fetch_method      TEXT NOT NULL,             -- 'brightdata_dataset' | 'brightdata_collector' | 'csv' | 'api'
  template_path     TEXT NOT NULL,             -- sources/<key>.yaml
  trust_weight      NUMERIC(3,2) NOT NULL DEFAULT 1.0,
  enabled           BOOLEAN NOT NULL DEFAULT false,
  terms_checked_on  DATE
);

CREATE TABLE IF NOT EXISTS raw_records (
  id            BIGSERIAL PRIMARY KEY,
  source_key    TEXT NOT NULL REFERENCES sources,
  fetched_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  snapshot_id   TEXT,
  content_hash  TEXT NOT NULL,
  payload       JSONB NOT NULL,              -- personal fields already dropped
  UNIQUE (source_key, content_hash)
);

CREATE TABLE IF NOT EXISTS properties (      -- one physical unit, resolved across sources
  property_id    BIGSERIAL PRIMARY KEY,
  address_norm   TEXT NOT NULL,
  unit_label     TEXT,
  zip            CHAR(5) NOT NULL,
  lat            DOUBLE PRECISION,
  lng            DOUBLE PRECISION,
  beds           SMALLINT,                   -- 0 = studio
  year_built     SMALLINT,                   -- decides AB 1482 coverage
  property_type  TEXT,                       -- 'apartment' | 'condo' | 'single_family'
  UNIQUE NULLS NOT DISTINCT (address_norm, unit_label, beds)
);

CREATE TABLE IF NOT EXISTS listings (        -- one row per source listing or post
  listing_id          BIGSERIAL PRIMARY KEY,
  source_key          TEXT NOT NULL REFERENCES sources,
  external_id_hash    TEXT NOT NULL,
  property_id         BIGINT REFERENCES properties,   -- NULL when the location is too vague
  listing_type        TEXT NOT NULL,         -- 'rent' | 'sale'
  zip                 CHAR(5),
  neighborhood        TEXT,
  location_precision  TEXT NOT NULL,         -- 'address' | 'street' | 'zip' | 'neighborhood' | 'city'
  beds                SMALLINT,
  baths               NUMERIC(3,1),
  sqft                INTEGER,
  text_redacted       TEXT,
  extras              JSONB NOT NULL DEFAULT '{}',
  field_confidence    JSONB NOT NULL DEFAULT '{}',
  extraction          TEXT NOT NULL,         -- 'mapped' | 'llm' | 'mixed'
  first_seen          TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen           TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (source_key, external_id_hash)
);

CREATE TABLE IF NOT EXISTS price_observations (
  observed_at    TIMESTAMPTZ NOT NULL,
  listing_id     BIGINT NOT NULL REFERENCES listings,
  property_id    BIGINT,
  source_key     TEXT NOT NULL,
  listing_type   TEXT NOT NULL,
  zip            CHAR(5),
  beds           SMALLINT,
  price_usd      INTEGER NOT NULL,           -- monthly rent or sale price; low end of a range
  price_max_usd  INTEGER,
  trust_weight   NUMERIC(3,2) NOT NULL,
  event          TEXT NOT NULL,              -- 'history' | 'seen' | 'price_change' | 'removed' | 'posted'
  UNIQUE (listing_id, observed_at, event)
);
SELECT create_hypertable('price_observations', by_range('observed_at'), if_not_exists => true);

CREATE TABLE IF NOT EXISTS area_metrics (    -- any number about an area, from any source
  period      DATE NOT NULL,
  geo_type    TEXT NOT NULL,                 -- 'zip' today; 'tract' or 'neighborhood' later
  geo_id      TEXT NOT NULL,                 -- '92104'
  metric      TEXT NOT NULL,                 -- 'zori', 'zhvi', 'median_income', 'groceries', ...
  value       NUMERIC(14,2) NOT NULL,
  source_key  TEXT NOT NULL REFERENCES sources,
  PRIMARY KEY (geo_type, geo_id, metric, source_key, period)
);
SELECT create_hypertable('area_metrics', by_range('period'), if_not_exists => true);

CREATE OR REPLACE VIEW zip_features AS       -- latest value of each metric, one row per ZIP
SELECT geo_id AS zip,
  max(value) FILTER (WHERE metric = 'median_income')   AS median_income_usd,
  max(value) FILTER (WHERE metric = 'acs_median_rent') AS acs_median_rent_usd,
  max(value) FILTER (WHERE metric = 'groceries')       AS groceries,
  max(value) FILTER (WHERE metric = 'transit_stops')   AS transit_stops,
  max(value) FILTER (WHERE metric = 'parks')           AS parks,
  max(value) FILTER (WHERE metric = 'food_drink')      AS food_drink,
  max(value) FILTER (WHERE metric = 'gyms')            AS gyms,
  max(value) FILTER (WHERE metric = 'area_km2')        AS area_km2
FROM (SELECT DISTINCT ON (geo_id, metric) geo_id, metric, value
      FROM area_metrics WHERE geo_type = 'zip'
      ORDER BY geo_id, metric, period DESC) latest
GROUP BY geo_id;

CREATE TABLE IF NOT EXISTS forecasts (
  run_id         UUID NOT NULL,
  made_at        TIMESTAMPTZ NOT NULL,
  month          DATE NOT NULL,              -- the month being forecast
  zip            CHAR(5) NOT NULL,
  metric         TEXT NOT NULL,              -- an area_metrics metric: 'zori' | 'zhvi'
  mean_usd       NUMERIC(12,2) NOT NULL,
  lo80_usd       NUMERIC(12,2),
  hi80_usd       NUMERIC(12,2),
  backtest_mape  NUMERIC(5,2),
  PRIMARY KEY (run_id, zip, metric, month)
);
SELECT create_hypertable('forecasts', by_range('month'), if_not_exists => true);

CREATE MATERIALIZED VIEW IF NOT EXISTS listing_weekly_zip
WITH (timescaledb.continuous) AS
SELECT time_bucket('7 days', observed_at) AS week,
       zip, beds, listing_type, source_key,
       percentile_agg(price_usd) AS price_pct,
       count(*) AS n
FROM price_observations
WHERE zip IS NOT NULL
GROUP BY week, zip, beds, listing_type, source_key
WITH NO DATA;

SELECT add_continuous_aggregate_policy('listing_weekly_zip',
  start_offset => INTERVAL '3 years',
  end_offset => INTERVAL '1 hour',
  schedule_interval => INTERVAL '30 minutes',
  if_not_exists => true);

CREATE TABLE IF NOT EXISTS model_runs (
  run_id         UUID PRIMARY KEY,
  kind           TEXT NOT NULL,              -- 'fair_rent' | 'forecast'
  trained_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  n_rows         INTEGER,
  sources_used   TEXT[],                     -- which source_keys trained it
  metrics        JSONB,                      -- MAE, MAPE, coverage of the 80% range
  artifact_path  TEXT
);

CREATE TABLE IF NOT EXISTS rent_caps (
  region        TEXT NOT NULL,               -- 'san_diego_county'
  period_start  DATE NOT NULL,
  period_end    DATE NOT NULL,
  cap_pct       NUMERIC(4,2) NOT NULL,       -- 8.20 means 8.2%
  source_url    TEXT NOT NULL,
  PRIMARY KEY (region, period_start)
);

CREATE TABLE IF NOT EXISTS rent_checks (
  check_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  address           TEXT NOT NULL,
  zip               CHAR(5),
  lowest_rent_12mo  INTEGER NOT NULL,
  new_rent          INTEGER NOT NULL,
  effective_date    DATE NOT NULL,
  year_built        SMALLINT,
  verdict           TEXT NOT NULL,           -- 'over_cap' | 'within_cap' | 'not_covered' | 'unclear'
  max_legal_rent    INTEGER,
  is_demo           BOOLEAN NOT NULL DEFAULT false
);

CREATE TABLE IF NOT EXISTS listing_analyses (  -- Owner mode, read-only analysis
  analysis_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  input        JSONB NOT NULL,               -- unit facts, the owner's listing text, target rent
  results      JSONB NOT NULL,               -- price position, completeness, gaps vs. comparables
  is_demo      BOOLEAN NOT NULL DEFAULT false
);

-- Gemini answers that passed validation, so a repeat request spends no free-tier quota.
-- key = sha256(job name + prompt + schema); the model isn't part of the key.
CREATE TABLE IF NOT EXISTS llm_cache (
  key         TEXT PRIMARY KEY,
  job         TEXT NOT NULL,                 -- 'parse_listing' | 'explain_verdict' | 'draft_letter' | 'zip_summary' | 'listing_gaps'
  model       TEXT NOT NULL,                 -- the model that produced the answer
  response    JSONB NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
