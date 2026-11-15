-- db/seed_sources.sql  (social and custom-scraper sources start disabled)
INSERT INTO sources (source_key, kind, fetch_method, template_path, trust_weight, enabled) VALUES
  ('zillow_rent',     'listing_site', 'brightdata_dataset',   'sources/zillow_rent.yaml',     1.0, true),
  ('zillow_sale',     'listing_site', 'brightdata_dataset',   'sources/zillow_sale.yaml',     1.0, true),
  ('apartments_com',  'listing_site', 'brightdata_collector', 'sources/apartments_com.yaml',  0.9, false),
  ('facebook_groups', 'social',       'brightdata_dataset',   'sources/facebook_groups.yaml', 0.5, false),
  ('zillow_research', 'area_index',   'csv',                  'sources/zillow_research.yaml', 1.0, true),
  ('census_acs',      'area_stats',   'api',                  'sources/census_acs.yaml',      1.0, true),
  ('osm_amenities',   'area_stats',   'api',                  'sources/osm_amenities.yaml',   1.0, true)
ON CONFLICT (source_key) DO NOTHING;
