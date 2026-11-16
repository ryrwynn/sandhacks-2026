"""Sprint backfill driver: parallel Bright Data triggers, concurrent async polling, streamed NDJSON, fast path.

uv run python -m worker.sprint plan  --template zillow_rent_county --zips 92037,92014 --limit 10
uv run python -m worker.sprint run   --template zillow_rent_county --zips ... --limit 10 [--group 15] [--note label]
uv run python -m worker.sprint resume --template zillow_rent_county --snapshots sd_abc,sd_def     # never re-triggers
uv run python -m worker.sprint spent

Budget: SPRINT_BUDGET_USD (default 40) for everything tagged "sprint" in scrape_runs, all time, not a 24 h
window. Every trigger is planned first with worker.bd.plan_run and an expected-records estimate from observed
ratios (Zillow overshoots limit_per_input; default 15 records per unit of limit, ~148 per ZIP at limit 10).
Nothing here posts or submits anywhere; it asks Bright Data to read public pages and downloads the result.
Output goes to raw_records and staging only.
"""
import argparse
import asyncio
import logging
import os
import queue
import random
import sys
import threading
import time
import zlib
from pathlib import Path

from worker import bd, fast, load
from worker.mapping import ROOT, load_template

log = logging.getLogger("worker.sprint")
TAG = "sprint"
GROUP = 15
RATIO = 15                      # expected records per unit of limit_per_input (1,777 records / 12 ZIPs at limit 10)
CACHE = ROOT / "data" / ".cache"
POLL = (5, 10, 20, 30)          # seconds; the last repeats
API = bd.API


def sprint_budget() -> float:
    return float(os.environ.get("SPRINT_BUDGET_USD") or 40)


def sprint_spent(conn) -> float:
    """Everything tagged sprint that was or may be billed (running, ready, and failed after a trigger)."""
    r = conn.execute("SELECT COALESCE(sum(est_usd), 0) FROM scrape_runs WHERE note LIKE %s AND "
                     "(status IN ('running','ready') OR (status = 'failed' AND snapshot_id IS NOT NULL))",
                     (f"%{TAG}%",)).fetchone()
    return float(r[0])


def triggered_urls(conn) -> set[str]:
    out = set()
    for (inputs,) in conn.execute("SELECT inputs FROM scrape_runs WHERE note LIKE %s AND snapshot_id IS NOT NULL",
                                  (f"%{TAG}%",)).fetchall():
        out |= {i.get("url") for i in inputs if isinstance(i, dict)}
    return out


def split(inputs: list, size: int = GROUP) -> list[list]:
    k = max(1, -(-len(inputs) // size))
    step = -(-len(inputs) // k)
    return [inputs[i:i + step] for i in range(0, len(inputs), step)]


def plan_and_trigger(conn, template: dict, inputs: list[dict], limit: int, *, note: str, client=None,
                     ratio: int = RATIO, group: int = GROUP, allow_repeat: bool = False,
                     dry_run: bool = False) -> list[dict]:
    """Parallel triggers of about `group` inputs each. Refuses before the first trigger when the whole batch
    (expected records) plus what the sprint has spent would pass the sprint budget."""
    key = template["source_key"]
    dup = [i["url"] for i in inputs if i["url"] in triggered_urls(conn)]
    if dup and not allow_repeat:
        raise RuntimeError(f"{len(dup)} inputs were already triggered this sprint (e.g. {dup[0]}); not repeating them")
    groups = split(inputs, group)
    per_input = max(1, limit * ratio)
    est = bd.estimate(len(inputs), per_input)[1]
    spent = sprint_spent(conn)
    cap = sprint_budget()
    if spent + est > cap + 1e-9:
        raise bd.BudgetExceeded(f"{key}: expected ${est:.2f} + sprint spent ${spent:.2f} would pass ${cap:.2f}")
    if dry_run:
        return [{"inputs": len(g), "est_records": len(g) * per_input, "est_usd": bd.estimate(len(g), per_input)[1]}
                for g in groups]
    client = client or bd.BrightDataClient()
    runs = []
    for g, grp in enumerate(groups):
        # plan_run compares 24 h spend with its budget; make it equivalent to the sprint's remaining budget
        remaining = cap - sprint_spent(conn)
        plan = bd.plan_run(conn, key, grp, limit, note=f"{TAG} bulk {note} g{g + 1}/{len(groups)}",
                           budget=bd.spent_usd(conn) + remaining, est_per_input=per_input)
        conn.execute("UPDATE scrape_runs SET status = 'running' WHERE run_id = %s", (plan["run_id"],))
        conn.commit()
        try:
            snap = client.trigger(template["fetch"]["dataset_id"], grp, limit, template["fetch"].get("mode", "discover"))
        except Exception as e:
            conn.execute("UPDATE scrape_runs SET status = 'failed', finished_at = now(), note = left(note || %s, 400) "
                         "WHERE run_id = %s", (f" | {e}"[:150], plan["run_id"]))
            conn.commit()
            raise
        conn.execute("UPDATE scrape_runs SET snapshot_id = %s WHERE run_id = %s", (snap, plan["run_id"]))
        conn.commit()
        print(f"triggered {snap}: {len(grp)} inputs, expected ~{len(grp) * per_input} records", flush=True)
        runs.append({"run_id": plan["run_id"], "snapshot_id": snap, "inputs": grp})
    return runs


# ------------------------------------------------------------------ async fetch
class Download:
    def __init__(self, snapshot_id: str):
        self.snapshot_id = snapshot_id
        self.path = CACHE / f"{snapshot_id}.ndjson"
        self.done = threading.Event()
        self.error: str | None = None
        self.lines = 0
        self.started = time.time()


async def _poll_ready(http, snap: str) -> str:
    i = 0
    while True:
        r = await http.get(f"{API}/progress/{snap}")
        if r.status_code == 429:
            await asyncio.sleep(float(r.headers.get("Retry-After", 10)) + random.random())
            continue
        if r.status_code >= 400:
            return f"progress HTTP {r.status_code}"
        st = r.json().get("status", "")
        if st == "ready":
            return "ready"
        if st in ("failed", "canceled"):
            return st
        await asyncio.sleep(POLL[min(i, len(POLL) - 1)] + random.random())
        i += 1


async def _stream_one(http, d: Download) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    st = await _poll_ready(http, d.snapshot_id)
    if st != "ready":
        d.error = st
        d.done.set()
        return
    part = d.path.with_suffix(".part")
    for attempt in range(30):
        async with http.stream("GET", f"{API}/snapshot/{d.snapshot_id}", params={"format": "ndjson", "compress": "true"}) as r:
            if r.status_code in (202, 409):
                await asyncio.sleep(10)
                continue
            if r.status_code != 200:
                d.error = f"download HTTP {r.status_code}"
                break
            dec, first = None, True
            with open(part, "wb") as f:
                async for chunk in r.aiter_raw():
                    if first:
                        first = False
                        if chunk[:2] == b"\x1f\x8b":
                            dec = zlib.decompressobj(16 + zlib.MAX_WBITS)
                    f.write(dec.decompress(chunk) if dec else chunk)
                    f.flush()
                if dec:
                    f.write(dec.flush())
            part.rename(d.path)
            break
    else:
        d.error = "still building after 30 tries"
    d.done.set()


def start_downloads(snapshots: list[str]) -> list[Download]:
    """All snapshots polled and downloaded concurrently on one event loop in a background thread. Each
    download writes data/.cache/<id>.ndjson.part as it streams and renames it when complete."""
    downloads = [Download(s) for s in snapshots]
    for d in downloads:
        if d.path.exists():                         # a finished earlier download: never fetch (or pay) twice
            d.done.set()

    def runner():
        import httpx

        async def main():
            headers = {"Authorization": f"Bearer {os.environ['BRIGHTDATA_API_TOKEN']}"}
            async with httpx.AsyncClient(headers=headers, timeout=httpx.Timeout(120, read=300)) as http:
                await asyncio.gather(*[_stream_one(http, d) for d in downloads if not d.done.is_set()])
        asyncio.run(main())
    threading.Thread(target=runner, daemon=True).start()
    return downloads


def follow(d: Download):
    """Lines of a download as they arrive (parsing starts while the download is still running)."""
    part = d.path.with_suffix(".part")
    while not (d.path.exists() or part.exists() or d.done.is_set()):
        time.sleep(1)
    path = d.path if d.path.exists() else part
    buf = b""
    f = None
    while True:
        if f is None:
            try:
                f = open(path, "rb")
            except FileNotFoundError:
                path = d.path
                continue
        data = f.read(1 << 20)
        if data:
            buf += data
            *lines, buf = buf.split(b"\n")
            for ln in lines:
                if ln.strip():
                    d.lines += 1
                    yield ln
            continue
        if d.done.is_set():
            if buf.strip():
                d.lines += 1
                yield buf
            return
        if not path.exists() and d.path.exists():     # renamed after the last write: continue from the same offset
            pos = f.tell()
            f.close()
            f = open(d.path, "rb")
            f.seek(pos)
            path = d.path
        time.sleep(0.3)


# ------------------------------------------------------------------ run
def process_snapshots(conn, template_key: str, runs: list[dict], *, procs: int | None = None, trust: float = 1.0) -> list[dict]:
    """Poll+download all runs concurrently; as each one's data starts to arrive, stage it with the fast path."""
    template = load_template(template_key)
    t_trigger = time.time()
    downloads = start_downloads([r["snapshot_id"] for r in runs])
    out = []
    pending = list(zip(runs, downloads))
    while pending:
        # the first one that is ready (or already downloading); the others keep downloading in the background
        pick = next(((r, d) for r, d in pending if d.path.exists() or d.path.with_suffix(".part").exists()
                     or d.done.is_set()), None)
        if pick is None:
            time.sleep(2)
            continue
        pending.remove(pick)
        r, d = pick
        if d.done.is_set() and d.error:
            conn.execute("UPDATE scrape_runs SET status = 'failed', finished_at = now(), note = left(note || %s, 400) "
                         "WHERE run_id = %s", (f" | {d.error}"[:150], r["run_id"]))
            conn.commit()
            out.append({"snapshot_id": r["snapshot_id"], "error": d.error})
            continue
        stats = fast.run_pipeline(fast.chunk_lines(follow(d)), template_key=template_key, connect=load.connect,
                                  trust=trust, snapshot_id=r["snapshot_id"], procs=procs)
        if d.error:
            conn.execute("UPDATE scrape_runs SET status = 'failed', finished_at = now(), note = left(note || %s, 400) "
                         "WHERE run_id = %s", (f" | {d.error}"[:150], r["run_id"]))
            out.append({"snapshot_id": r["snapshot_id"], "error": d.error, **stats})
            conn.commit()
            continue
        billed = stats["billed"]
        conn.execute("UPDATE scrape_runs SET status = 'ready', finished_at = now(), records = %s, est_usd = %s "
                     "WHERE run_id = %s", (billed, bd.cost_of(billed), r["run_id"]))
        conn.commit()
        res = {"snapshot_id": r["snapshot_id"], "records": billed, "usd": bd.cost_of(billed),
               "trigger_to_staged_s": round(time.time() - t_trigger, 1), **stats}
        print({k: (round(v, 2) if isinstance(v, float) else v) for k, v in res.items()}, flush=True)
        out.append(res)
    return out


def counts_per_zip(conn, zips: list[str]) -> dict:
    rows = conn.execute("SELECT zip, count(*) FROM staging_listings WHERE zip = ANY(%s) GROUP BY 1", (zips,)).fetchall()
    return {z: n for z, n in rows}


def list_requests(conn) -> list[tuple]:
    return conn.execute("SELECT request_id, geo_type, geo_id, query, status, est_records, est_cost_usd FROM area_requests "
                        "WHERE status = 'queued' ORDER BY requested_at").fetchall()


EXTRA_ZIPS = {"95014": {"name": "Cupertino", "county": "Santa Clara"}}      # added to the requested areas by the sprint


def finish_requests(conn) -> dict:
    """After the requested-areas run: areas rows (tier on_demand, county, name, centroid) and request statuses the way
    worker.ondemand sets them: loaded (the ZIP has staged listings, or was already covered), failed (none came back)."""
    import csv
    ca = {}
    with open(ROOT / "data" / "areas_ca.csv") as fh:
        ca = {r["zip"]: r for r in csv.DictReader(fh)}
    out = {"areas": [], "requests": []}
    zips = set(EXTRA_ZIPS)
    queued = conn.execute("SELECT request_id, geo_type, geo_id, query FROM area_requests WHERE status = 'queued'").fetchall()
    for rid, gt, gid, q in queued:
        z = gid if gt == "zip" else None
        if z:
            zips.add(z)
    for z in sorted(zips):
        n = conn.execute("SELECT count(*) FROM staging_listings WHERE zip = %s", (z,)).fetchone()[0]
        row = ca.get(z, {})
        name = EXTRA_ZIPS.get(z, {}).get("name") or row.get("name") or z
        county = EXTRA_ZIPS.get(z, {}).get("county") or row.get("county")
        if n:
            conn.execute(
                "INSERT INTO areas (geo_type, geo_id, name, county, tier, centroid_lat, centroid_lng, last_scraped_at) "
                "VALUES ('zip', %s, %s, %s, 'on_demand', %s, %s, now()) ON CONFLICT (geo_type, geo_id) DO UPDATE SET "
                "tier = CASE WHEN areas.tier IN ('core','county') THEN areas.tier ELSE 'on_demand' END, "
                "name = EXCLUDED.name, county = COALESCE(areas.county, EXCLUDED.county), "
                "centroid_lat = COALESCE(areas.centroid_lat, EXCLUDED.centroid_lat), "
                "centroid_lng = COALESCE(areas.centroid_lng, EXCLUDED.centroid_lng), last_scraped_at = now()",
                (z, name, county, float(row["lat"]) if row.get("lat") else None, float(row["lng"]) if row.get("lng") else None))
            out["areas"].append((z, name, county, n))
    for rid, gt, gid, q in queued:
        n = conn.execute("SELECT count(*) FROM staging_listings WHERE zip = %s", (gid,)).fetchone()[0] if gt == "zip" else 0
        status, note = ("loaded", "sprint backfill") if n else ("failed", "no listings came back in the sprint backfill")
        conn.execute("UPDATE area_requests SET status = %s, finished_at = now(), note = %s WHERE request_id = %s",
                     (status, note, rid))
        out["requests"].append((str(rid), gid, status, n))
    for z in EXTRA_ZIPS:                                  # an audit row for the ZIPs the sprint added itself
        if not conn.execute("SELECT 1 FROM area_requests WHERE geo_id = %s AND status = 'loaded'", (z,)).fetchone() \
                and conn.execute("SELECT 1 FROM staging_listings WHERE zip = %s LIMIT 1", (z,)).fetchone():
            conn.execute("INSERT INTO area_requests (geo_type, geo_id, query, status, finished_at, note) "
                         "VALUES ('zip', %s, %s, 'loaded', now(), 'added by the sprint')", (z, EXTRA_ZIPS[z]["name"]))
    conn.commit()
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["plan", "run", "resume", "spent", "requests", "list-requests"])
    ap.add_argument("--template")
    ap.add_argument("--zips")
    ap.add_argument("--urls", help="file with one search URL per line (instead of --zips)")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--group", type=int, default=GROUP)
    ap.add_argument("--ratio", type=int, default=RATIO)
    ap.add_argument("--note", default="")
    ap.add_argument("--snapshots", help="comma list of already-triggered snapshot ids (resume)")
    ap.add_argument("--zip-form", action="store_true", help="ZIP-only search URLs (template zip_url)")
    ap.add_argument("--cities", help="zip=slug,zip=slug overrides for the search URL city")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    conn = load.connect()
    if a.cmd == "spent":
        print({"sprint_spent_usd": sprint_spent(conn), "budget": sprint_budget()})
        return 0
    if a.cmd == "list-requests":
        print(list_requests(conn))
        return 0
    if a.cmd == "requests":
        print(finish_requests(conn))
        return 0
    template = load_template(a.template)
    if a.cmd == "resume":
        runs = []
        for s in a.snapshots.split(","):
            row = conn.execute("SELECT run_id FROM scrape_runs WHERE snapshot_id = %s", (s,)).fetchone()
            runs.append({"run_id": row[0], "snapshot_id": s})
        process_snapshots(conn, a.template, runs)
        return 0
    if a.urls:
        inputs = [{"url": u.strip()} for u in Path(a.urls).read_text().splitlines() if u.strip()]
    else:
        slugs = dict(kv.split("=") for kv in a.cities.split(",")) if a.cities else {}
        zl = [z.strip() for z in a.zips.split(",")]
        inputs = bd.zillow_zip_inputs(template, zl) if a.zip_form else bd.zillow_inputs(template, zl, slugs)
    runs = plan_and_trigger(conn, template, inputs, a.limit, note=a.note, ratio=a.ratio, group=a.group,
                            dry_run=a.cmd == "plan")
    if a.cmd == "plan":
        print({"groups": runs, "sprint_spent": sprint_spent(conn), "budget": sprint_budget()})
        return 0
    process_snapshots(conn, a.template, runs)
    print({"sprint_spent_usd": sprint_spent(conn)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
