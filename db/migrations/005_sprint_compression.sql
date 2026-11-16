-- db/migrations/005_sprint_compression.sql
-- NOT applied during the sprint. The orchestrator applies it after "go" and after the replay and the
-- listing_weekly_zip refresh, so the replay's price_observations writes land in plain chunks first.
--
-- TimescaleDB on the Tiger service is 2.32.0. Since 2.11 compressed chunks accept INSERT, UPDATE and DELETE,
-- including INSERT ... ON CONFLICT against the unique index (listing_id, observed_at, event), which the loaders
-- and worker.replay use. Checked on a scratch hypertable in the same service (insert, upsert, update, delete
-- on a compressed chunk all succeeded; scratch table dropped). So compressing chunks older than 30 days is
-- safe for this workload; a late history row for an old date just writes into a compressed chunk (slower
-- than a plain insert, still fine at this volume).
-- Columnstore syntax (2.18+); `timescaledb.compress*` and add_compression_policy are the older spellings.
-- segmentby zip, beds matches the comparables query (zip, beds, newest first).
ALTER TABLE price_observations SET (
  timescaledb.enable_columnstore = true,
  timescaledb.segmentby = 'zip, beds',
  timescaledb.orderby = 'observed_at DESC'
);
CALL add_columnstore_policy('price_observations', after => INTERVAL '30 days', if_not_exists => true);

-- The continuous aggregate reads price_observations; a refresh over compressed chunks works, so refresh
-- listing_weekly_zip after the replay, before this runs:
--   CALL refresh_continuous_aggregate('listing_weekly_zip', NULL, NULL);
