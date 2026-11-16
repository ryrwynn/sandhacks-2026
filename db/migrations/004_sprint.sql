-- db/migrations/004_sprint.sql
-- Data sprint (docs/SPRINT.md D1, D5). Additive only: IF NOT EXISTS, no drops, renames or type changes,
-- because the live site reads this database. The compression policy is NOT here: see 005_sprint_compression.sql.

-- One row. Loaders bump `version` after each load; the API checks it at most every 30 seconds and clears its
-- caches (served areas, comparables, market) when it changes.
CREATE TABLE IF NOT EXISTS data_version (
  id         smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  version    bigint NOT NULL DEFAULT 0,
  updated_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO data_version (id, version) VALUES (1, 0) ON CONFLICT (id) DO NOTHING;

-- ZIP + bedroom comparables ("what else rents for this at this size") read newest observations first.
CREATE INDEX IF NOT EXISTS price_observations_zip_beds_idx ON price_observations (zip, beds, observed_at DESC);
