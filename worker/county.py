"""County-tier Zillow rentals (zillow_rent_county): one batched Bright Data trigger, raw_records, then staging.

uv run python -m worker.county --zips 92037,92014,92106 --sample     # 20-record sample (needed once)
uv run python -m worker.county [--zips ...] [--limit 10] [--max-age-days 7] [--dry-run]

Reads ZIPs from data/zips_county.txt unless --zips is given. Core ZIPs (data/zips.txt) are refused: the live
worker already scrapes them. Every run goes through worker.bd (estimate, budget guard, scrape_runs). Rows land
in raw_records under zillow_rent_county and are mapped into staging_listings only; nothing reaches the shared
tables (the morning merge replays them with worker.replay --target shared).
"""
import argparse
import logging
import sys

from worker import bd, load
from worker.mapping import ROOT, load_template
from worker.replay import staging_insert
from worker.run import process_listing_payloads
from worker.llm_extract import LlmBudget

log = logging.getLogger("worker.county")
SOURCE = "zillow_rent_county"


def _zip_csv(name: str) -> list[str]:
    zips = (line.split(",")[0].strip() for line in (ROOT / "data" / name).read_text().splitlines())
    return [z for z in zips if z.isdigit()]


def core_zips() -> set[str]:
    return set(_zip_csv("zips.txt"))


def county_zips() -> list[str]:
    return _zip_csv("zips_county.txt")


def to_staging(conn, template: dict, rows: list[dict], trust: float, gemini_budget: int) -> dict:
    from datetime import datetime, timezone
    t = dict(template, source_key=template.get("loads_as") or template["source_key"])
    budget = LlmBudget(gemini_budget)
    listings, stats = process_listing_payloads(t, rows, datetime.now(timezone.utc), budget)
    for l in listings:
        staging_insert(conn, l, trust, None)
    conn.commit()
    return {"staged": len(listings), "gemini_calls": budget.used, **stats}


def run(conn, zips: list[str], *, sample: bool, limit: int | None, dry_run: bool, max_age_days: int,
        gemini_budget: int = 10, client=None) -> dict:
    template = load_template(SOURCE)
    core = core_zips()
    refused = [z for z in zips if z in core]
    zips = [z for z in zips if z not in core]
    if max_age_days and not sample:
        zips = bd.stale_zips(conn, zips, max_age_days)
    limit = limit or template["fetch"].get("limit_per_input") or 10
    if sample:
        limit = max(1, bd.SAMPLE_RECORDS // max(1, len(zips)))       # whole sample stays at 20 records
    est_records, est_usd = bd.estimate(len(zips), limit)
    out = {"zips": zips, "refused_core": refused, "limit": limit, "est_records": est_records, "est_usd": est_usd,
           "spent_24h": bd.spent_usd(conn), "budget": bd.budget_usd()}
    if dry_run or not zips:
        return out
    inputs = bd.zillow_zip_inputs(template, zips)
    res = bd.run_batch(conn, template, inputs, limit=limit, sample=sample, client=client, note="county " + ",".join(zips))
    bd.mark_scraped(conn, zips)
    trust = float(load.enabled_sources(conn).get(SOURCE, {}).get("trust_weight", 1.0))
    import orjson
    from worker import fast
    stats = fast.run_pipeline(fast.chunk_lines(orjson.dumps(r) for r in res["rows"]), template_key=SOURCE,
                              connect=load.connect, trust=trust, snapshot_id=res["snapshot_id"])
    out.update({"run_id": res["run_id"], "snapshot_id": res["snapshot_id"], "records": res["records"],
                "usd": res["usd"], **stats})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zips", help="comma list; default data/zips_county.txt")
    ap.add_argument("--sample", action="store_true", help="20-record sample (required once before bulk)")
    ap.add_argument("--limit", type=int, help="records per ZIP (default from the template)")
    ap.add_argument("--max-age-days", type=int, default=7, help="skip ZIPs scraped more recently")
    ap.add_argument("--gemini-budget", type=int, default=10)
    ap.add_argument("--dry-run", action="store_true", help="estimate only; spend nothing")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    zips = [z.strip() for z in a.zips.split(",")] if a.zips else county_zips()
    conn = load.connect()
    print(run(conn, zips, sample=a.sample, limit=a.limit, dry_run=a.dry_run, max_age_days=a.max_age_days,
              gemini_budget=a.gemini_budget))
    return 0


if __name__ == "__main__":
    sys.exit(main())
