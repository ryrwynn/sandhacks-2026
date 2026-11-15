-- db/migrations/002_night.sql
-- Overnight run (docs/NIGHT.md "Phase 1"). Additive only: new tables, indexes and extensions with
-- IF NOT EXISTS. No drops, renames or type changes to 001's objects, because the live site reads
-- this database. New areas and new sources land here (and in raw_records), never in the shared tables.
CREATE EXTENSION IF NOT EXISTS vector;

-- Coverage tiers: 'core' (data/zips.txt), 'county' (San Diego County), 'index' (California, ZORI/ZHVI/ACS
-- only), 'on_demand' (user-requested). geo_type is 'zip' or 'city'.
CREATE TABLE IF NOT EXISTS areas (
  geo_type         TEXT NOT NULL,
  geo_id           TEXT NOT NULL,              -- '92037' or 'la-jolla' (slug for a city)
  name             TEXT NOT NULL,
  county           TEXT,                       -- 'San Diego'
  state            CHAR(2) NOT NULL DEFAULT 'CA',
  tier             TEXT NOT NULL CHECK (tier IN ('core', 'county', 'index', 'on_demand')),
  centroid_lat     DOUBLE PRECISION,
  centroid_lng     DOUBLE PRECISION,
  last_scraped_at  TIMESTAMPTZ,
  PRIMARY KEY (geo_type, geo_id)
);
CREATE INDEX IF NOT EXISTS areas_tier_idx ON areas (tier);
CREATE INDEX IF NOT EXISTS areas_county_idx ON areas (county);

-- A user's "Add this area" request. Status: queued -> scraping -> loaded | failed | over_budget.
CREATE TABLE IF NOT EXISTS area_requests (
  request_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  geo_type            TEXT NOT NULL,
  geo_id              TEXT NOT NULL,
  query               TEXT NOT NULL,           -- what the user typed
  status              TEXT NOT NULL DEFAULT 'queued'
                      CHECK (status IN ('queued', 'scraping', 'loaded', 'failed', 'over_budget')),
  est_records         INTEGER,
  est_cost_usd        NUMERIC(8,2),
  requested_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at          TIMESTAMPTZ,
  finished_at         TIMESTAMPTZ,
  note                TEXT
);
CREATE INDEX IF NOT EXISTS area_requests_status_idx ON area_requests (status, requested_at);

-- One row per Bright Data trigger (or other paid run), for budget accounting.
CREATE TABLE IF NOT EXISTS scrape_runs (
  run_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_key     TEXT NOT NULL,
  started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at    TIMESTAMPTZ,
  snapshot_id    TEXT,
  inputs         JSONB NOT NULL DEFAULT '[]',  -- the batched inputs (URLs, ZIPs); no personal data
  n_inputs       INTEGER,
  records        INTEGER,                      -- delivered records (what is billed)
  est_usd        NUMERIC(8,2),                 -- records x price per record
  status         TEXT NOT NULL DEFAULT 'running'
                 CHECK (status IN ('estimated', 'refused', 'running', 'ready', 'failed')),
  note           TEXT
);
CREATE INDEX IF NOT EXISTS scrape_runs_started_idx ON scrape_runs (started_at);

-- Public Facebook rental groups by locality. The URL is stored only as a hash; the display name is
-- the group's public title. Collected only when the scraper reports the group as public.
CREATE TABLE IF NOT EXISTS fb_groups (
  url_hash              TEXT PRIMARY KEY,
  display_name          TEXT NOT NULL,
  locality              TEXT NOT NULL,         -- 'La Jolla', 'North Park', ...
  zips                  TEXT[] NOT NULL DEFAULT '{}',
  is_public             BOOLEAN,
  checked_on            DATE,
  last_post_date_seen   TIMESTAMPTZ           -- date_posted high-water mark
);

-- Macro inputs (FRED etc.) and scenario paths (Fed supervisory baseline / severely adverse, growth).
CREATE TABLE IF NOT EXISTS macro_series (
  series_id  TEXT NOT NULL,                    -- 'MORTGAGE30US', 'SAND706UR', ...
  period     DATE NOT NULL,
  value      NUMERIC(14,4) NOT NULL,
  source     TEXT NOT NULL,                    -- 'fred', 'fed_scenarios'
  PRIMARY KEY (series_id, period)
);

CREATE TABLE IF NOT EXISTS scenario_paths (
  scenario   TEXT NOT NULL CHECK (scenario IN ('baseline', 'recession', 'growth')),
  series_id  TEXT NOT NULL,
  period     DATE NOT NULL,
  value      NUMERIC(14,4) NOT NULL,
  source     TEXT,                             -- 'fed_2026_baseline', 'fed_2026_severely_adverse', 'p80_12m_change'
  PRIMARY KEY (scenario, series_id, period)
);

-- Like forecasts, plus scenario and model.
CREATE TABLE IF NOT EXISTS scenario_forecasts (
  run_id         UUID NOT NULL,
  made_at        TIMESTAMPTZ NOT NULL,
  scenario       TEXT NOT NULL CHECK (scenario IN ('baseline', 'recession', 'growth')),
  model          TEXT NOT NULL,                -- 'sarimax_x' | 'pooled_x' | 'ets'
  month          DATE NOT NULL,
  zip            CHAR(5) NOT NULL,
  metric         TEXT NOT NULL,                -- 'zori' | 'zhvi'
  mean_usd       NUMERIC(12,2) NOT NULL,
  lo80_usd       NUMERIC(12,2),
  hi80_usd       NUMERIC(12,2),
  backtest_mape  NUMERIC(5,2),
  coverage_80    NUMERIC(4,3),                 -- held-out share inside the 80% band
  PRIMARY KEY (run_id, scenario, zip, metric, month)
);
CREATE INDEX IF NOT EXISTS scenario_forecasts_lookup_idx ON scenario_forecasts (zip, metric, scenario, made_at DESC);

-- Listing text embeddings: gemini-embedding-2 at 768 dimensions.
CREATE TABLE IF NOT EXISTS listing_embeddings (
  listing_id   BIGINT NOT NULL,
  model        TEXT NOT NULL,
  text_hash    TEXT NOT NULL,                  -- sha256 of the embedded text, to skip unchanged listings
  embedding    vector(768) NOT NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (listing_id, model)
);

-- Server-side saves for signed-in users, keyed by a hash of the identity provider's subject ID only.
CREATE TABLE IF NOT EXISTS user_saves (
  subject_hash   TEXT NOT NULL,
  listing_id     BIGINT NOT NULL,
  saved_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  price_at_save  INTEGER,
  target         INTEGER,                      -- the user's target rent alert, dollars
  PRIMARY KEY (subject_hash, listing_id)
);

-- Staging copies of the shared tables for new areas when there is no DEV_DATABASE_URL.
-- worker.replay --target staging writes here; --target shared moves them after the morning merge.
CREATE TABLE IF NOT EXISTS staging_listings (LIKE listings INCLUDING DEFAULTS);
ALTER TABLE staging_listings ADD COLUMN IF NOT EXISTS price_usd INTEGER;      -- latest observed price
ALTER TABLE staging_listings ADD COLUMN IF NOT EXISTS observed_at TIMESTAMPTZ;
ALTER TABLE staging_listings ADD COLUMN IF NOT EXISTS raw_record_id BIGINT;
CREATE UNIQUE INDEX IF NOT EXISTS staging_listings_src_ext_idx ON staging_listings (source_key, external_id_hash);
CREATE INDEX IF NOT EXISTS staging_listings_zip_idx ON staging_listings (zip);

CREATE TABLE IF NOT EXISTS staging_area_metrics (LIKE area_metrics INCLUDING DEFAULTS);
CREATE UNIQUE INDEX IF NOT EXISTS staging_area_metrics_pk ON staging_area_metrics (geo_type, geo_id, metric, source_key, period);
