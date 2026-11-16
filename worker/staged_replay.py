"""Set-based replay of staged listings into the shared tables (sprint D1/D3). Run only after "go".

uv run python -m worker.staged_replay --source zillow_rent --confirm-shared [--mark-areas county]
uv run python -m worker.staged_replay --source zillow_rent --scratch      # test against throwaway copies

--source is the canonical key staged by the fast path (zillow_rent for both the county and core templates:
`loads_as`). One transaction per source:
  1. properties: one INSERT ... SELECT DISTINCT ON (address, unit, beds) ... ON CONFLICT (resolved in SQL),
  2. listings: INSERT ... SELECT with the property joined on normalized address + unit + beds,
  3. price_observations: INSERT ... SELECT from staging_price_observations joined to the new listing ids,
  4. year_built backfill, data_version bump.
Idempotent (every INSERT is ON CONFLICT). --scratch copies the target tables into a throwaway schema
(sprint_scratch) and runs the same SQL there, so it never touches the shared tables.
"""
import argparse
import sys

from worker import fast, load

PROPERTIES_SQL = """
INSERT INTO properties (address_norm, unit_label, zip, lat, lng, beds, year_built, property_type)
SELECT DISTINCT ON (address_norm, unit_label, beds) address_norm, unit_label, zip, lat, lng, beds, year_built, ptype
FROM (SELECT extras->>'address_norm' AS address_norm, extras->>'unit_label' AS unit_label, zip,
             (extras->>'lat')::float8 AS lat, (extras->>'lng')::float8 AS lng, beds,
             (extras->>'year_built')::smallint AS year_built, extras->>'property_type' AS ptype, observed_at
      FROM staging_listings
      WHERE source_key = %s AND location_precision = 'address' AND extras ? 'address_norm' AND zip IS NOT NULL) s
ORDER BY address_norm, unit_label, beds, observed_at DESC
ON CONFLICT (address_norm, unit_label, beds) DO UPDATE SET
  year_built = COALESCE(properties.year_built, EXCLUDED.year_built),
  lat = COALESCE(properties.lat, EXCLUDED.lat), lng = COALESCE(properties.lng, EXCLUDED.lng),
  property_type = COALESCE(properties.property_type, EXCLUDED.property_type)
"""

LISTINGS_SQL = """
INSERT INTO listings (source_key, external_id_hash, property_id, listing_type, zip, neighborhood,
                      location_precision, beds, baths, sqft, text_redacted, extras, field_confidence, extraction)
SELECT s.source_key, s.external_id_hash, p.property_id, s.listing_type, s.zip, s.neighborhood, s.location_precision,
       s.beds, s.baths, s.sqft, s.text_redacted,
       s.extras - ARRAY['address_norm','unit_label','lat','lng','year_built','property_type','price_history','trust_weight'],
       s.field_confidence, s.extraction
FROM staging_listings s
LEFT JOIN properties p ON s.location_precision = 'address' AND p.address_norm = s.extras->>'address_norm'
     AND p.unit_label IS NOT DISTINCT FROM s.extras->>'unit_label' AND p.beds IS NOT DISTINCT FROM s.beds
WHERE s.source_key = %s
ON CONFLICT (source_key, external_id_hash) DO UPDATE SET last_seen = now(),
  property_id = COALESCE(EXCLUDED.property_id, listings.property_id),
  zip = COALESCE(EXCLUDED.zip, listings.zip), beds = COALESCE(EXCLUDED.beds, listings.beds),
  baths = COALESCE(EXCLUDED.baths, listings.baths), sqft = COALESCE(EXCLUDED.sqft, listings.sqft),
  text_redacted = COALESCE(EXCLUDED.text_redacted, listings.text_redacted),
  extras = listings.extras || EXCLUDED.extras,
  field_confidence = listings.field_confidence || EXCLUDED.field_confidence
"""

OBS_SQL = """
INSERT INTO price_observations (observed_at, listing_id, property_id, source_key, listing_type, zip, beds,
                                price_usd, price_max_usd, trust_weight, event)
SELECT o.observed_at, l.listing_id, l.property_id, o.source_key, o.listing_type, o.zip, o.beds, o.price_usd,
       o.price_max_usd, o.trust_weight, o.event
FROM staging_price_observations o
JOIN staging_listings s ON s.listing_id = o.listing_id
JOIN listings l ON l.source_key = s.source_key AND l.external_id_hash = s.external_id_hash
WHERE s.source_key = %s
ON CONFLICT (listing_id, observed_at, event) DO NOTHING
"""

MARK_AREAS_SQL = """
UPDATE areas a SET tier = %s, last_scraped_at = COALESCE(a.last_scraped_at, now())
WHERE a.geo_type = 'zip' AND a.tier IN ('county', 'index') AND a.geo_id IN (
  SELECT zip FROM listings WHERE source_key = %s AND zip IS NOT NULL AND last_seen > now() - interval '30 days'
  GROUP BY zip HAVING count(*) >= 5)
"""


def replay(conn, source: str, *, mark_areas: str | None = None) -> dict:
    """One transaction: staging -> shared for `source`. Returns row counts."""
    out = {}
    with conn.transaction():
        out["properties"] = conn.execute(PROPERTIES_SQL, (source,)).rowcount
        out["listings"] = conn.execute(LISTINGS_SQL, (source,)).rowcount
        out["observations"] = conn.execute(OBS_SQL, (source,)).rowcount
        out["year_built_backfilled"] = load.backfill_year_built(conn)
        if mark_areas:
            out["areas_marked"] = conn.execute(MARK_AREAS_SQL, (mark_areas, source)).rowcount
    out["data_version"] = fast.bump_data_version(conn)
    return out


TABLES = ["properties", "listings", "price_observations", "areas", "data_version"]


def scratch_schema(conn) -> None:
    """Throwaway copies of the shared tables (data, constraints and indexes included) in schema sprint_scratch,
    searched before public, so replay() runs unchanged without touching shared rows."""
    conn.execute("DROP SCHEMA IF EXISTS sprint_scratch CASCADE")
    conn.execute("CREATE SCHEMA sprint_scratch")
    for t in TABLES:
        conn.execute(f"CREATE TABLE sprint_scratch.{t} (LIKE public.{t} INCLUDING ALL)")
        if t in ("areas", "data_version"):
            conn.execute(f"INSERT INTO sprint_scratch.{t} SELECT * FROM public.{t}")
    conn.execute("SET search_path = sprint_scratch, public")
    conn.commit()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--confirm-shared", action="store_true")
    ap.add_argument("--scratch", action="store_true", help="run against throwaway copies; never the shared tables")
    ap.add_argument("--mark-areas", choices=["county", "core", "on_demand"],
                    help="set areas.tier for ZIPs of this source with at least 5 listings seen in 30 days")
    a = ap.parse_args(argv)
    if not (a.confirm_shared or a.scratch):
        print("this writes the shared tables: add --confirm-shared after the human says go (or --scratch to test)",
              file=sys.stderr)
        return 2
    conn = load.connect()
    if a.scratch:
        scratch_schema(conn)
    print(replay(conn, a.source, mark_areas=a.mark_areas))
    if a.scratch:
        conn.execute("DROP SCHEMA sprint_scratch CASCADE")
        conn.commit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
