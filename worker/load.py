"""Resolve and load steps: properties, listings, price observations, area metrics, raw records."""
import json
import os
from datetime import datetime, timezone

import psycopg

from contracts.canonical import CanonicalListing


def connect() -> psycopg.Connection:
    return psycopg.connect(os.environ["DATABASE_URL"], autocommit=False)


def enabled_sources(conn) -> dict[str, dict]:
    rows = conn.execute("SELECT source_key, kind, trust_weight, enabled FROM sources").fetchall()
    return {r[0]: {"kind": r[1], "trust_weight": float(r[2]), "enabled": r[3]} for r in rows}


def store_raw(conn, source_key: str, snapshot_id: str | None, content_hash: str, payload: dict) -> bool:
    cur = conn.execute(
        "INSERT INTO raw_records (source_key, snapshot_id, content_hash, payload) VALUES (%s,%s,%s,%s) "
        "ON CONFLICT (source_key, content_hash) DO NOTHING RETURNING id",
        (source_key, snapshot_id, content_hash, json.dumps(payload, default=str)))
    return cur.fetchone() is not None


def llm_parsed_hashes(conn, source_key: str) -> set[str]:
    rows = conn.execute("SELECT external_id_hash FROM listings WHERE source_key=%s AND extras ? 'llm_parsed'",
                        (source_key,)).fetchall()
    return {r[0] for r in rows}


def resolve_property(conn, l: CanonicalListing) -> int | None:
    """Same normalized address + unit + beds is one property, whichever site reported it.
    Listings without a street address stay unattached and count only toward ZIP-level numbers."""
    if l.location_precision != "address" or not l.address_norm or not l.zip:
        return None
    row = conn.execute(
        "INSERT INTO properties (address_norm, unit_label, zip, lat, lng, beds, year_built, property_type) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
        "ON CONFLICT (address_norm, unit_label, beds) DO UPDATE SET "
        " year_built = COALESCE(properties.year_built, EXCLUDED.year_built), "
        " lat = COALESCE(properties.lat, EXCLUDED.lat), lng = COALESCE(properties.lng, EXCLUDED.lng), "
        " property_type = COALESCE(properties.property_type, EXCLUDED.property_type) "
        "RETURNING property_id",
        (l.address_norm, l.unit_label, l.zip, l.lat, l.lng, l.beds, l.year_built, l.property_type)).fetchone()
    return row[0]


def _obs(conn, listing_id, property_id, l: CanonicalListing, trust, when, price, price_max, event):
    conn.execute(
        "INSERT INTO price_observations (observed_at, listing_id, property_id, source_key, listing_type, zip, beds, "
        "price_usd, price_max_usd, trust_weight, event) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
        "ON CONFLICT (listing_id, observed_at, event) DO NOTHING",
        (when, listing_id, property_id, l.source_key, l.listing_type, l.zip, l.beds, price, price_max, trust, event))


def load_listing(conn, l: CanonicalListing, trust: float) -> int:
    pid = resolve_property(conn, l)
    row = conn.execute(
        "INSERT INTO listings (source_key, external_id_hash, property_id, listing_type, zip, neighborhood, "
        "location_precision, beds, baths, sqft, text_redacted, extras, field_confidence, extraction) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
        "ON CONFLICT (source_key, external_id_hash) DO UPDATE SET last_seen = now(), "
        " property_id = COALESCE(EXCLUDED.property_id, listings.property_id), "
        " zip = COALESCE(EXCLUDED.zip, listings.zip), beds = COALESCE(EXCLUDED.beds, listings.beds), "
        " baths = COALESCE(EXCLUDED.baths, listings.baths), sqft = COALESCE(EXCLUDED.sqft, listings.sqft), "
        " text_redacted = COALESCE(EXCLUDED.text_redacted, listings.text_redacted), "
        " extras = listings.extras || EXCLUDED.extras, "
        " field_confidence = listings.field_confidence || EXCLUDED.field_confidence, "
        " extraction = CASE WHEN EXCLUDED.extraction = 'mapped' THEN listings.extraction ELSE EXCLUDED.extraction END "
        "RETURNING listing_id",
        (l.source_key, l.external_id_hash, pid, l.listing_type, l.zip, l.neighborhood, l.location_precision, l.beds,
         l.baths, l.sqft, l.text_redacted, json.dumps(l.extras, default=str), json.dumps(l.field_confidence),
         l.extraction)).fetchone()
    lid = row[0]
    day = l.observed_at.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    prev = conn.execute("SELECT price_usd FROM price_observations WHERE listing_id=%s AND event IN ('seen','price_change') "
                        "ORDER BY observed_at DESC LIMIT 1", (lid,)).fetchone()
    event = "posted" if l.location_precision in ("zip", "neighborhood", "city") else "seen"   # social posts
    _obs(conn, lid, pid, l, trust, day, l.price_usd, l.price_max_usd, event)
    if prev and prev[0] != l.price_usd:
        _obs(conn, lid, pid, l, trust, day, l.price_usd, l.price_max_usd, "price_change")
    for h in l.price_history:      # the source's own history, never invented
        when = datetime.fromisoformat(h["date"]).replace(tzinfo=timezone.utc)
        _obs(conn, lid, pid, l, trust, when, h["price_usd"], None, "history")
    return lid


def backfill_year_built(conn) -> int:
    """Rentals carry no yearBuilt: copy it from a for-sale or other record at the same normalized address and ZIP."""
    cur = conn.execute(
        "UPDATE properties p SET year_built = s.yb FROM ("
        " SELECT address_norm, zip, max(year_built) AS yb FROM properties WHERE year_built IS NOT NULL GROUP BY 1,2) s "
        "WHERE p.year_built IS NULL AND p.address_norm = s.address_norm AND p.zip = s.zip")
    return cur.rowcount


def load_area(conn, source_key: str, rows: list[dict]) -> int:
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO area_metrics (period, geo_type, geo_id, metric, value, source_key) "
            "VALUES (%s,'zip',%s,%s,%s,%s) "
            "ON CONFLICT (geo_type, geo_id, metric, source_key, period) DO UPDATE SET value = EXCLUDED.value",
            [(r["period"], r["geo_id"], r["metric"], r["value"], source_key) for r in rows])
    return len(rows)
