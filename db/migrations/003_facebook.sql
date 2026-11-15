-- Morning run (2026-11-15): Facebook group posts become listings with price history.
-- Additive only. staging_price_observations mirrors price_observations so Facebook reposts can be
-- staged (with their price history) without touching the shared tables until the morning merge.
CREATE TABLE IF NOT EXISTS staging_price_observations (LIKE price_observations INCLUDING DEFAULTS);
CREATE UNIQUE INDEX IF NOT EXISTS staging_po_uniq ON staging_price_observations (listing_id, observed_at, event);
CREATE INDEX IF NOT EXISTS staging_po_listing_idx ON staging_price_observations (listing_id);
-- Facebook dedupe lookups: same normalized text, beds and ZIP within 30 days is one listing.
CREATE INDEX IF NOT EXISTS listings_fb_dedupe_idx ON listings ((extras->>'dedupe_key'))
  WHERE source_key = 'facebook_groups_sd';
CREATE INDEX IF NOT EXISTS staging_listings_fb_dedupe_idx ON staging_listings ((extras->>'dedupe_key'))
  WHERE source_key = 'facebook_groups_sd';
