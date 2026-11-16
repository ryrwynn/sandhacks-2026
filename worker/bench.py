"""Benchmark the current (row-by-row) path against the fast path on rows already in raw_records (free: no scrape).

uv run python -m worker.bench --source zillow_rent [--limit 5000] [--slow-load-rows 400]

Targets staging only (staging_listings, staging_price_observations); both paths are idempotent upserts. Stages:
  fetch  skipped (rows come from raw_records; the network is not measured here)
  map    payloads -> staging rows, no database
  load   staging rows -> staging_listings (current: one INSERT per row; fast: binary COPY + set-based)
"""
import argparse
import logging
import time
from datetime import datetime, timezone

import orjson

from worker import fast, load
from worker.llm_extract import LlmBudget
from worker.mapping import load_template
from worker.replay import staging_insert
from worker.run import process_listing_payloads


def rate(n: int, s: float) -> str:
    return f"{n / s:,.0f}/s" if s > 0 else "n/a"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="zillow_rent")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--slow-load-rows", type=int, default=400, help="rows the current path loads (it is slow)")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    conn = load.connect()
    sql = "SELECT payload FROM raw_records WHERE source_key = %s ORDER BY id" + (f" LIMIT {a.limit}" if a.limit else "")
    t_fetch = time.perf_counter()
    payloads = [p for (p,) in conn.execute(sql, (a.source,)).fetchall()]
    t_fetch = time.perf_counter() - t_fetch
    n = len(payloads)
    print(f"rows from raw_records: {n} (read {t_fetch:.1f}s, not counted)")
    template = load_template(a.source)
    now = datetime.now(timezone.utc)

    # ---- current path: map
    t = time.perf_counter()
    listings, _ = process_listing_payloads(template, payloads, now, LlmBudget(0))
    slow_map = time.perf_counter() - t
    print(f"current map : {n} records -> {len(listings)} listings in {slow_map:.2f}s = {rate(n, slow_map)}")
    # ---- current path: load (first N listings)
    sub = listings[: a.slow_load_rows]
    t = time.perf_counter()
    for l in sub:
        staging_insert(conn, l, 1.0, None)
    conn.commit()
    slow_load = time.perf_counter() - t
    print(f"current load: {len(sub)} listings in {slow_load:.2f}s = {rate(len(sub), slow_load)}")

    # ---- fast path: map alone (pool), then whole pipeline
    lines = [orjson.dumps(p) for p in payloads]
    procs = fast.default_procs()
    from concurrent.futures import ProcessPoolExecutor
    t = time.perf_counter()
    rows_n = 0
    with ProcessPoolExecutor(max_workers=procs) as ex:
        futs = [ex.submit(fast.process_chunk, a.source, ch, now.isoformat(), 1.0) for ch in fast.chunk_lines(lines)]
        for f in futs:
            rows_n += len(f.result()["rows"])
    fast_map = time.perf_counter() - t
    print(f"fast map    : {n} records -> {rows_n} listings in {fast_map:.2f}s = {rate(n, fast_map)} ({procs} procs)")
    t = time.perf_counter()
    stats = fast.run_pipeline(fast.chunk_lines(lines), template_key=a.source, connect=load.connect, observed_at=now,
                              procs=procs, snapshot_id="bench", bump=False)
    e2e = time.perf_counter() - t
    print(f"fast e2e    : {n} records in {e2e:.2f}s = {rate(n, e2e)} (map wall {stats['map_wall_s']:.1f}s, "
          f"load busy {stats['load_s']:.1f}s over {stats['loaders']} loaders); "
          f"staged {stats['staged']} raw_new {stats['raw_new']} history_rows {stats['history_rows']}")
    # ---- fast load alone is e2e minus map: report load busy per loader-second
    print(f"fast load   : {stats['staged']} rows, {rate(stats['staged'], stats['load_s'])} per loader-second, "
          f"{rate(stats['staged'], stats['load_s'] / stats['loaders'])} aggregate if loaders overlap")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
