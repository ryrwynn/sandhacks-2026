"""Run one or all enabled sources: python -m worker.run [--source KEY] [--zips 92104,92105] [--snapshot ID]

fetch -> (store raw) -> map -> Gemini for empty fields -> clean -> resolve -> load. Reads only.
"""
import argparse
import logging
import sys
import time
from datetime import datetime, timezone

from worker import load, mapping
from worker.adapters import get_adapter
from worker.llm_extract import LlmBudget, fill_missing, needs_llm
from worker.mapping import build_listing, drop_building_level_history, explode, load_template, map_payload

log = logging.getLogger("worker.run")


def _age(d) -> float:
    v = d["extras"].get("days_on_zillow")
    return float(v) if isinstance(v, (int, float)) else 1e9      # 0 days is the newest


def process_listing_payloads(template, payloads, observed_at, budget, already_parsed=frozenset()):
    """Map + Gemini-fill + validate a batch of cleaned payloads. Pure of the database: used by run and tests.
    Newest listings first so the Gemini budget goes to them."""
    drafts = []
    for p in payloads:
        for sub in explode(template, p):
            d = map_payload(template, sub, observed_at)
            if d is not None:
                drafts.append(d)
    drafts.sort(key=lambda d: (-d["observed_at"].timestamp(), _age(d)))
    out, stats = [], {"mapped_only": 0, "llm_called": 0, "dropped": 0}
    for d in drafts:
        before = budget.used
        if d["external_id_hash"] in already_parsed:
            ok = True
        else:
            ok = fill_missing(template, d, budget)
        stats["llm_called"] += budget.used - before
        l = build_listing(d) if ok else None
        if l is None:
            stats["dropped"] += 1
            continue
        out.append(l)
    if template.get("history", {}).get("building_level_check"):
        stats["history_dropped_building_level"] = drop_building_level_history(out)
    return out, stats


def run_listing_source(conn, key, template, trust, args) -> dict:
    adapter = get_adapter(template)
    f = template["fetch"]
    if args.zips and f.get("input_url"):
        inputs = [{"url": f["input_url"].format(zip=z)} for z in args.zips.split(",")]
    else:
        inputs = None
    kw = {"snapshot_id": args.snapshot} if args.snapshot else {}
    records = list(adapter.fetch(inputs, **kw))
    new_raw = sum(load.store_raw(conn, key, r.snapshot_id, r.content_hash, r.payload) for r in records)
    conn.commit()
    budget = LlmBudget()
    now = datetime.now(timezone.utc)
    listings, stats = process_listing_payloads(template, [r.payload for r in records], now, budget,
                                               load.llm_parsed_hashes(conn, key))
    for l in listings:
        load.load_listing(conn, l, trust)
    filled = load.backfill_year_built(conn) if template["kind"] == "listing_site" else 0
    conn.commit()
    return {"raw_fetched": len(records), "raw_new": new_raw, "listings": len(listings),
            "gemini_calls": budget.used, "gemini_empty": budget.empty, "year_built_backfilled": filled, **stats}


def run_area_source(conn, key, template) -> dict:
    adapter = get_adapter(template)
    rows = [r.payload for r in adapter.fetch()]
    n = load.load_area(conn, key, rows)
    conn.commit()
    return {"area_rows": n}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source")
    ap.add_argument("--zips", help="comma list to restrict the Bright Data search inputs")
    ap.add_argument("--snapshot", help="load an already-triggered Bright Data snapshot instead of triggering a new run")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    conn = load.connect()
    sources = load.enabled_sources(conn)
    keys = [args.source] if args.source else [k for k, v in sources.items() if v["enabled"]]
    rc = 0
    for key in keys:
        if key not in sources:
            log.error("unknown source %s", key)
            return 2
        if not sources[key]["enabled"] and not args.source:
            continue
        if not sources[key]["enabled"]:
            log.error("source %s is disabled in the sources table", key)
            return 2
        t0 = time.time()
        template = load_template(key)
        try:
            if sources[key]["kind"] in ("listing_site", "social"):
                res = run_listing_source(conn, key, template, sources[key]["trust_weight"], args)
            else:
                res = run_area_source(conn, key, template)
            log.info("source %s ok in %.1fs: %s", key, time.time() - t0, res)
        except Exception as e:      # one source failing must not stop the others
            conn.rollback()
            log.exception("source %s failed: %s", key, e)
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
