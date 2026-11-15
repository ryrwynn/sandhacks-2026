"""On-demand area job (night-data): scrape queued area_requests within the daily budget.

uv run python -m worker.ondemand [--dry-run]      # needs DATABASE_URL and BRIGHTDATA_API_TOKEN

Takes queued requests oldest first while their estimates fit today's on-demand budget
(ONDEMAND_DAILY_USD, default 1.00) and the overall Bright Data budget, batches every ZIP into ONE trigger,
stores raw records under the disabled source zillow_rent_ondemand, replays them into staging_listings, and
marks the ZIPs tier 'on_demand' with last_scraped_at. Requests that do not fit stay queued for tomorrow.
Never touches the shared listing tables.

Repeats: a ZIP added within FRESH_DAYS counts as covered (the API answers "already added", and this job
skips it); after that a new request refreshes it. Runs daily from docker/worker.crontab.
"""
import argparse
import logging
import sys
import time

from worker import bd, load
from worker.mapping import load_template

log = logging.getLogger("worker.ondemand")
FRESH_DAYS = 30           # keep in step with api/routers/coverage.py
# ZIPs that still need a scrape: index tier, or added on request longer than FRESH_DAYS ago.
NEEDS_SCRAPE = ("(tier = 'index' OR (tier = 'on_demand' AND (last_scraped_at IS NULL "
                f"OR last_scraped_at < now() - interval '{FRESH_DAYS} days')))")


def zips_for_request(conn, geo_type: str, geo_id: str, name: str) -> list[str]:
    """ZIPs that still need scraping for a request (core and county ZIPs are covered elsewhere)."""
    if geo_type == "zip":
        rows = conn.execute(f"SELECT geo_id FROM areas WHERE geo_type='zip' AND geo_id=%s AND {NEEDS_SCRAPE}",
                            (geo_id,)).fetchall()
    else:
        rows = conn.execute("SELECT geo_id FROM areas WHERE geo_type='zip' AND lower(name)=lower(%s) "
                            f"AND {NEEDS_SCRAPE} ORDER BY geo_id LIMIT %s",
                            (name, bd.ONDEMAND_MAX_ZIPS)).fetchall()
    return [r[0] for r in rows]


def pick(requests: list[dict], remaining_usd: float) -> tuple[list[dict], list[dict]]:
    """Oldest first; a request is taken only if its whole estimate still fits. Returns (taken, deferred)."""
    taken, deferred, left = [], [], remaining_usd
    for r in requests:
        if r["est_usd"] <= left + 1e-9:
            taken.append(r)
            left -= r["est_usd"]
        else:
            deferred.append(r)
    return taken, deferred


def stage(conn, template: dict) -> int:
    """Raw on-demand records -> staging_listings (idempotent; no Gemini). The live listing queries never read these."""
    from worker.replay import replay_listings
    return replay_listings(conn, template, "staging", float(template.get("trust_weight", 1.0)), 0, None)["listings"]


def process_queue(conn, client=None, sleep=time.sleep, dry_run: bool = False) -> dict:
    template = load_template(bd.ONDEMAND_SOURCE)
    daily_left = bd.ondemand_daily_usd() - bd.spent_usd(conn, bd.ONDEMAND_SOURCE)
    total_left = bd.budget_usd() - bd.spent_usd(conn)
    rows = conn.execute("SELECT request_id, geo_type, geo_id, query, COALESCE(est_cost_usd, 0) FROM area_requests "
                        "WHERE status = 'queued' ORDER BY requested_at").fetchall()
    reqs = []
    for rid, gt, gid, q, usd in rows:
        zips = zips_for_request(conn, gt, gid, q)
        if not zips:
            conn.execute("UPDATE area_requests SET status='loaded', finished_at=now(), note='already covered' "
                         "WHERE request_id=%s", (rid,))
            continue
        reqs.append({"id": rid, "zips": zips, "est_usd": bd.estimate(len(zips), bd.ONDEMAND_LIMIT)[1]})
    conn.commit()
    taken, deferred = pick(reqs, min(daily_left, total_left))
    out = {"taken": len(taken), "deferred": len(deferred), "records": 0, "usd": 0.0}
    if not taken or dry_run:
        return out
    zips = sorted({z for r in taken for z in r["zips"]})
    ids = [r["id"] for r in taken]
    conn.execute("UPDATE area_requests SET status='scraping', started_at=now() WHERE request_id = ANY(%s)", (ids,))
    conn.commit()
    cities = dict(conn.execute("SELECT zip, city_slug FROM (SELECT geo_id AS zip, lower(regexp_replace(name,'[^a-zA-Z0-9]+','-','g')) "
                               "AS city_slug FROM areas WHERE geo_type='zip' AND geo_id = ANY(%s)) t", (zips,)).fetchall())
    inputs = bd.zillow_inputs(template, zips, cities)
    try:
        if not bd.sample_done(conn, bd.ONDEMAND_SOURCE):
            s = bd.run_batch(conn, template, inputs, limit=bd.ONDEMAND_LIMIT, sample=True, client=client, sleep=sleep,
                             note="on-demand")
            bd.store_rows(conn, template, s["snapshot_id"], s["rows"])
            out["records"] += s["records"]
            out["usd"] += s["usd"]
        res = bd.run_batch(conn, template, inputs, limit=bd.ONDEMAND_LIMIT, client=client, sleep=sleep, note="on-demand")
        bd.store_rows(conn, template, res["snapshot_id"], res["rows"])
        bd.mark_scraped(conn, zips)
        out["records"] += res["records"]
        out["usd"] += res["usd"]
        out["staged"] = stage(conn, template)
        conn.execute("UPDATE areas SET tier = 'on_demand' WHERE geo_type = 'zip' AND geo_id = ANY(%s) AND tier = 'index'",
                     (zips,))
        conn.execute("UPDATE area_requests SET status='loaded', finished_at=now() WHERE request_id = ANY(%s)", (ids,))
    except bd.BudgetExceeded as e:
        conn.execute("UPDATE area_requests SET status='queued', started_at=NULL, note=%s WHERE request_id = ANY(%s)",
                     (str(e)[:200], ids))
    except Exception as e:
        conn.rollback()
        conn.execute("UPDATE area_requests SET status='failed', finished_at=now(), note=%s WHERE request_id = ANY(%s)",
                     (str(e)[:200], ids))
        log.exception("on-demand run failed")
    conn.commit()
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="show what would be taken; spend nothing")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    conn = load.connect()
    print(process_queue(conn, dry_run=a.dry_run))
    return 0


if __name__ == "__main__":
    sys.exit(main())
