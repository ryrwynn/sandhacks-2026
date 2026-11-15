"""Replay raw_records into tables without scraping again (night-data).

uv run python -m worker.replay --source <key> --target shared|staging|dev [--limit N] [--gemini-budget N]

  staging  DATABASE_URL, staging_listings / staging_area_metrics (nothing reaches the live site)
  dev      DEV_DATABASE_URL, the normal tables (a scratch database)
  shared   DATABASE_URL, the normal tables; for the morning merge only, needs --confirm-shared

Area sources (zillow_research_ca, census_acs_ca) are stored under their canonical key (the template's
`loads_as`, e.g. zillow_research) so the live queries read them unchanged. Listing sources go through the
same map, Gemini-fill and clean steps as worker.run. Idempotent: re-running changes nothing.
"""
import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone

from worker import load
from worker.llm_extract import LlmBudget
from worker.mapping import load_template
from worker.run import process_listing_payloads

log = logging.getLogger("worker.replay")
CHUNK = 500


def area_rows(payload: dict) -> list[tuple[str, str, float]]:
    """(period, metric...) rows from either payload shape: a series (Zillow) or one value (ACS)."""
    if "series" in payload:
        return [(p, payload["geo_id"], v) for p, v in payload["series"].items()]
    return [(payload["period"], payload["geo_id"], payload["value"])]


def replay_area(conn, template: dict, target: str) -> int:
    key = template.get("loads_as") or template["source_key"]
    table = "staging_area_metrics" if target == "staging" else "area_metrics"
    n = 0
    cur = conn.execute("SELECT payload FROM raw_records WHERE source_key = %s ORDER BY id", (template["source_key"],))
    batch = []
    for (payload,) in cur.fetchall():
        for period, geo, value in area_rows(payload):
            batch.append((period, geo, payload["metric"], value, key))
        if len(batch) >= CHUNK * 10:
            n += _flush_area(conn, table, batch)
            batch = []
    n += _flush_area(conn, table, batch)
    conn.commit()
    return n


def _flush_area(conn, table: str, batch: list) -> int:
    if not batch:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            f"INSERT INTO {table} (period, geo_type, geo_id, metric, value, source_key) VALUES (%s,'zip',%s,%s,%s,%s) "
            "ON CONFLICT (geo_type, geo_id, metric, source_key, period) DO UPDATE SET value = EXCLUDED.value", batch)
    return len(batch)


def staging_insert(conn, l, trust: float, raw_id: int | None) -> None:
    """A listing into staging_listings. No properties table in staging, so the address facts ride in extras
    (a shared-target replay re-maps from raw_records and resolves properties then)."""
    extras = dict(l.extras)
    extras.update({k: v for k, v in {"address_norm": l.address_norm, "unit_label": l.unit_label, "lat": l.lat,
                                     "lng": l.lng, "year_built": l.year_built, "property_type": l.property_type,
                                     "price_history": l.price_history, "trust_weight": trust}.items() if v})
    conn.execute(
        "INSERT INTO staging_listings (source_key, external_id_hash, listing_type, zip, neighborhood, location_precision, "
        "beds, baths, sqft, text_redacted, extras, field_confidence, extraction, price_usd, observed_at, raw_record_id) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
        "ON CONFLICT (source_key, external_id_hash) DO UPDATE SET last_seen = now(), price_usd = EXCLUDED.price_usd, "
        " observed_at = EXCLUDED.observed_at, extras = staging_listings.extras || EXCLUDED.extras",
        (l.source_key, l.external_id_hash, l.listing_type, l.zip, l.neighborhood, l.location_precision, l.beds, l.baths,
         l.sqft, l.text_redacted, json.dumps(extras, default=str), json.dumps(l.field_confidence), l.extraction,
         l.price_usd, l.observed_at, raw_id))


def replay_listings(conn, template: dict, target: str, trust: float, gemini_budget: int, limit: int | None) -> dict:
    key = template["source_key"]
    sql = "SELECT id, payload FROM raw_records WHERE source_key = %s ORDER BY id" + (" LIMIT %s" if limit else "")
    rows = conn.execute(sql, (key, limit) if limit else (key,)).fetchall()
    template = dict(template, source_key=template.get("loads_as") or key)   # canonical key in the output tables
    budget = LlmBudget(gemini_budget)
    now = datetime.now(timezone.utc)
    listings, stats = process_listing_payloads(template, [p for _, p in rows], now, budget)
    for l in listings:
        if target == "staging":
            staging_insert(conn, l, trust, None)
        else:
            load.load_listing(conn, l, trust)
    conn.commit()
    return {"raw": len(rows), "listings": len(listings), "gemini_calls": budget.used, **stats}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--target", required=True, choices=["shared", "staging", "dev"])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--gemini-budget", type=int, default=40)
    ap.add_argument("--confirm-shared", action="store_true", help="required for --target shared (morning merge)")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    if a.target == "shared" and not a.confirm_shared:
        print("--target shared writes the live tables; add --confirm-shared after the morning merge", file=sys.stderr)
        return 2
    if a.target == "dev":
        url = os.environ.get("DEV_DATABASE_URL")
        if not url:
            print("DEV_DATABASE_URL is not set", file=sys.stderr)
            return 2
        os.environ["DATABASE_URL"] = url
    conn = load.connect()
    template = load_template(a.source)
    srcs = load.enabled_sources(conn)
    if a.source not in srcs:
        print(f"unknown source {a.source}", file=sys.stderr)
        return 2
    if template["kind"] in ("area_index", "area_stats"):
        res = {"area_rows": replay_area(conn, template, a.target)}
    else:
        res = replay_listings(conn, template, a.target, srcs[a.source]["trust_weight"], a.gemini_budget, a.limit)
    print(res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
