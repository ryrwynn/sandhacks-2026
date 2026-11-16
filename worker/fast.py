"""Fast path (sprint D1): NDJSON lines -> cleaned raw records + staging rows, vectorized, on every core, with a
few loader connections. Read-only toward sources; writes only raw_records, staging_listings and
staging_price_observations (never the shared tables).

Stages (bounded queues between them, so memory stays flat):
  lines (2,000 per chunk) -> process pool: orjson parse, drop personal fields, redact, content hash, map as
  polars columns -> main thread: ordered results, split by hash of the external id -> up to 4 loader threads:
  binary COPY into temp tables, then one INSERT ... SELECT ... ON CONFLICT per target.

What is vectorized (polars): numeric casts, bedroom parsing, address and unit normalization, ZIP slice, property
types, status and ZIP filters, price filter. What stays Python over a whole column: the phone/name redaction
(Rust regex has no lookaround) and the nested lookups (`a.b.c`, `a|b`, price history). Same output as the
row-by-row path (worker.mapping.map_payload + worker.replay.staging_args), checked by test_fast_path.py.
No Gemini on this path: Zillow rows are fully mapped.

Building-level price history (identical history on several units of one address) needs every chunk, so it is
settled after the last chunk: the history rows are written at the end, the flagged listings lose their
extras.price_history in one UPDATE.
"""
import hashlib
import json
import logging
import os
import queue
import threading
import time
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from functools import lru_cache

import orjson
import polars as pl

from worker.clean import ABBREV, redact_text, sha256_text
from worker.mapping import get_path, load_template, load_zips, map_history

log = logging.getLogger("worker.fast")
CHUNK = 2000
MAX_LOADERS = 4
INT4 = 2_000_000_000


def default_procs() -> int:
    env = os.environ.get("WORKER_PROCS")
    if env:
        return max(1, int(env))
    return max(1, min(os.cpu_count() or 1, 8))


# ------------------------------------------------------------------ clean (per line)
def content_hash_fast(payload: dict, ignore) -> str:
    """Same value as worker.clean.content_hash; orjson when its output is ASCII-only, json otherwise."""
    drop = set(ignore or [])
    p = {k: v for k, v in payload.items() if k not in drop} if drop else payload
    try:
        b = orjson.dumps(p, option=orjson.OPT_SORT_KEYS)
        if b.isascii():
            return hashlib.sha256(b).hexdigest()
    except TypeError:
        pass
    return sha256_text(json.dumps(p, sort_keys=True, default=str, separators=(",", ":")))


def clean_lines(template: dict, lines: list) -> tuple[list[dict], int, int]:
    """NDJSON lines -> cleaned payload dicts (personal fields dropped, text redacted). Returns
    (payloads, billed_records, error_records)."""
    drop = set(template.get("drop_fields") or [])
    redact = template.get("redact_fields") or []
    out, billed, errors = [], 0, 0
    for ln in lines:
        if not ln or not ln.strip():
            continue
        try:
            row = orjson.loads(ln)
        except orjson.JSONDecodeError:
            errors += 1
            continue
        billed += 1
        if not isinstance(row, dict) or row.get("error"):
            errors += 1
            continue
        p = {k: v for k, v in row.items() if k not in drop}
        for f in redact:
            if isinstance(p.get(f), str):
                p[f] = redact_text(p[f])
        out.append(p)
    return out, billed, errors


# ------------------------------------------------------------------ map (polars)
@lru_cache(maxsize=8)
def _zip_set(path: str) -> frozenset:
    return frozenset(load_zips(path))


def _s(v):
    return None if v is None else (v if isinstance(v, str) else str(v))


def _num(col: str, dtype) -> pl.Expr:
    x = pl.col(col).str.replace_all(r"[^\d.\-]", "").cast(pl.Float64, strict=False)
    return x.cast(dtype, strict=False) if dtype != pl.Float64 else x


def _norm_address(col: str) -> pl.Expr:
    a = pl.col(col).str.strip_chars().str.to_lowercase()
    a = a.str.replace(r"(?i)[\s,]+(?:apt|apartment|unit|ste|suite|#)\s*[\w-]+$", "")
    a = a.str.replace_all(r"[.,]", " ").str.replace(r"\s+#\S*$", "")
    a = a.str.replace_all(r"\s+", " ").str.strip_chars()
    a = a.str.split(" ").list.eval(pl.element().replace(ABBREV)).list.join(" ")
    return pl.when(a == "").then(None).otherwise(a)


def _norm_unit(col: str) -> pl.Expr:
    u = (pl.col(col).str.strip_chars().str.replace(r"(?i)^(apt|apartment|unit|ste|suite|#)\s*", "")
         .str.to_uppercase())
    return pl.when(u == "").then(None).otherwise(u)


def _in32(v):
    return None if v is None or abs(v) > INT4 else v


def map_chunk(template: dict, payloads: list[dict], observed_at: datetime, trust: float) -> dict:
    """Cleaned payloads -> {'rows': staging row tuples, 'hist': history rows, 'dropped': n}.

    A row is replay.staging_args(...) with json columns as Python objects. observed_at is one value per run.
    """
    m = template["map"]
    key = template.get("loads_as") or template["source_key"]
    n = len(payloads)
    if not n:
        return {"rows": [], "hist": [], "dropped": 0}
    keep_if = template.get("keep_if") or {}
    keep = [all(p.get(f) in allowed for f, allowed in keep_if.items()) for p in payloads]
    ext = [get_path(p, m["external_id"]) for p in payloads]
    keep = [k and e is not None for k, e in zip(keep, ext)]

    def col(field):
        return [_s(get_path(p, m[field])) if field in m else None for p in payloads]

    df = pl.DataFrame({
        "keep": keep,
        "price": pl.Series(col("price_usd"), dtype=pl.String), "beds": pl.Series(col("beds"), dtype=pl.String),
        "baths": pl.Series(col("baths"), dtype=pl.String), "sqft": pl.Series(col("sqft"), dtype=pl.String),
        "yb": pl.Series(col("year_built"), dtype=pl.String), "ptype": pl.Series(col("property_type"), dtype=pl.String),
        "addr": pl.Series(col("address_norm"), dtype=pl.String), "unit": pl.Series(col("unit_label"), dtype=pl.String),
        "zip": pl.Series(col("zip"), dtype=pl.String), "lat": pl.Series(col("lat"), dtype=pl.String),
        "lng": pl.Series(col("lng"), dtype=pl.String),
        "nbh": pl.Series([get_path(p, m["neighborhood"]) if "neighborhood" in m else None for p in payloads],
                         dtype=pl.String),
    })
    pt_map = template.get("property_types") or {}
    ptype = pl.col("ptype")
    ptype_e = (ptype.replace_strict(pt_map, default=ptype.str.to_lowercase(), return_dtype=pl.String)
               if pt_map else ptype.str.to_lowercase())
    beds_l = pl.col("beds").str.strip_chars().str.to_lowercase()
    df = df.with_columns(
        _num("price", pl.Int64).alias("price"),
        pl.when(beds_l.str.contains("studio")).then(0).otherwise(beds_l.str.extract(r"(\d+)", 1).cast(pl.Int64, strict=False))
        .alias("beds"),
        _num("baths", pl.Float64).alias("baths"), _num("sqft", pl.Int64).alias("sqft"),
        _num("yb", pl.Int64).alias("yb"), ptype_e.alias("ptype"),
        _norm_address("addr").alias("addr"), _norm_unit("unit").alias("unit"),
        pl.col("zip").str.slice(0, 5).alias("zip"),
        _num("lat", pl.Float64).alias("lat"), _num("lng", pl.Float64).alias("lng"))
    zf = template.get("zip_filter")
    zip_ok = (pl.col("zip").is_null() | pl.col("zip").is_in(list(_zip_set(zf)))) if zf else pl.lit(True)
    df = df.with_columns(pl.col("keep") & zip_ok & pl.col("price").is_not_null() & (pl.col("price") != 0))
    texts = [redact_text(_s(get_path(p, m["text"]))) if "text" in m else None for p in payloads]
    df = df.with_columns(pl.Series("text", texts, dtype=pl.String), pl.Series("i", range(n), dtype=pl.Int64))
    kept = df.filter(pl.col("keep"))
    dropped = n - kept.height
    loc_default = template["location_precision"]
    rows, hist, seen = [], [], {}
    em = template.get("extras_map") or {}
    hist_cfg = template.get("history")
    for (i, price, beds, baths, sqft, yb, ptype_v, addr, unit, zp, lat, lng, nbh, text) in kept.select(
            "i", "price", "beds", "baths", "sqft", "yb", "ptype", "addr", "unit", "zip", "lat", "lng", "nbh",
            "text").iter_rows():
        p = payloads[i]
        ext_hash = sha256_text(str(ext[i]))
        beds, sqft, yb, price = _in32(beds), _in32(sqft), _in32(yb), _in32(price)
        if beds is not None and abs(beds) > 32000:
            beds = None
        vals = {"price_usd": price, "beds": beds, "baths": baths, "sqft": sqft, "year_built": yb,
                "property_type": ptype_v, "address_norm": addr, "unit_label": unit, "zip": zp, "neighborhood": nbh,
                "lat": lat, "lng": lng, "text_redacted": text}
        conf = {k: 1.0 for k, v in vals.items() if v is not None and k != "neighborhood"}
        if nbh is not None:
            conf["neighborhood"] = 1.0
        extras = {}
        for name, path in em.items():
            v = get_path(p, path)
            if v is not None:
                extras[name] = v
        history = map_history(template, p) if hist_cfg else []
        precision = loc_default if addr or loc_default != "address" else "zip"
        extras_all = dict(extras)
        extras_all.update({k: v for k, v in {"address_norm": addr, "unit_label": unit, "lat": lat, "lng": lng,
                                             "year_built": yb, "property_type": ptype_v, "price_history": history,
                                             "trust_weight": trust}.items() if v})
        row = (key, ext_hash, template["listing_type"], zp, nbh, precision, beds, baths, sqft, text, extras_all, conf,
               "mapped", price, observed_at, None)
        seen[ext_hash] = row                      # a repeat within a chunk: the later row wins
        if history:
            hist.append((ext_hash, (zp, addr, tuple((h["date"], h["price_usd"], h["event"]) for h in history))
                         if addr else None, [(h["date"], h["price_usd"]) for h in history]))
    rows = list(seen.values())
    live = {r[1] for r in rows}
    return {"rows": rows, "hist": [h for h in hist if h[0] in live], "dropped": dropped}


def building_level(hist_all: list) -> set[str]:
    """External-id hashes whose history is shared by another unit at the same address (see
    worker.mapping.drop_building_level_history)."""
    groups: dict = {}
    for ext, key, _ in hist_all:
        if key is not None:
            groups.setdefault(key, set()).add(ext)
    return {e for members in groups.values() if len(members) > 1 for e in members}


def strip_building_level(rows: list[tuple], bl: set[str]) -> list[tuple]:
    out = []
    for r in rows:
        if r[1] in bl and "price_history" in r[10]:
            r = r[:10] + ({k: v for k, v in r[10].items() if k != "price_history"},) + r[11:]
        out.append(r)
    return out


# ------------------------------------------------------------------ process pool entry
_TEMPLATES: dict = {}


def process_chunk(template_key: str, lines: list, observed_iso: str, trust: float) -> dict:
    """Runs in a pool process. Returns raw rows (content hash, json bytes) and mapped staging rows."""
    t0 = time.perf_counter()
    t = _TEMPLATES.get(template_key)
    if t is None:
        t = _TEMPLATES[template_key] = load_template(template_key)
    payloads, billed, errors = clean_lines(t, lines)
    ign = t.get("hash_ignore")
    raw, seen = [], set()
    for p in payloads:
        h = content_hash_fast(p, ign)
        if h in seen:
            continue
        seen.add(h)
        raw.append((h, orjson.dumps(p)))
    res = map_chunk(t, payloads, datetime.fromisoformat(observed_iso), trust)
    res.update({"raw": raw, "billed": billed, "errors": errors, "n": len(payloads), "secs": time.perf_counter() - t0})
    return res


# ------------------------------------------------------------------ load
_STG_TYPES = ["text", "text", "text", "text", "text", "int2", "float8", "int4", "text", "bytea", "bytea", "text",
              "int4", "timestamptz"]
_STG_DDL = ("CREATE TEMP TABLE IF NOT EXISTS _stg (ext text, listing_type text, zip text, neighborhood text, "
            "precision text, beds int2, baths float8, sqft int4, text text, extras bytea, conf bytea, extraction text, "
            "price int4, observed_at timestamptz) ON COMMIT DELETE ROWS")
_RAW_DDL = ("CREATE TEMP TABLE IF NOT EXISTS _raw (content_hash text, snapshot_id text, payload bytea) "
            "ON COMMIT DELETE ROWS")


def part_of(h: str, n: int) -> int:
    return int(h[:8], 16) % n


def load_batch(conn, raw_source: str, key: str, trust: float, snapshot_id: str | None, raw: list, rows: list) -> dict:
    """One transaction: COPY into temp tables, then one set-based INSERT per target."""
    out = {"raw_new": 0, "staged": 0}
    with conn.cursor() as cur:
        cur.execute(_RAW_DDL)
        cur.execute(_STG_DDL)
        if raw:
            with cur.copy("COPY _raw (content_hash, snapshot_id, payload) FROM STDIN (FORMAT BINARY)") as cp:
                cp.set_types(["text", "text", "bytea"])
                for h, b in raw:
                    cp.write_row((h, snapshot_id, b))
            cur.execute("INSERT INTO raw_records (source_key, snapshot_id, content_hash, payload) "
                        "SELECT %s, snapshot_id, content_hash, convert_from(payload, 'UTF8')::jsonb FROM _raw "
                        "ON CONFLICT (source_key, content_hash) DO NOTHING", (raw_source,))
            out["raw_new"] = cur.rowcount
        if rows:
            with cur.copy("COPY _stg (ext, listing_type, zip, neighborhood, precision, beds, baths, sqft, text, extras, "
                          "conf, extraction, price, observed_at) FROM STDIN (FORMAT BINARY)") as cp:
                cp.set_types(_STG_TYPES)
                for r in rows:
                    cp.write_row((r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9],
                                  orjson.dumps(r[10], default=str), orjson.dumps(r[11]), r[12], r[13], r[14]))
            cur.execute(
                "INSERT INTO staging_listings (source_key, external_id_hash, listing_type, zip, neighborhood, "
                "location_precision, beds, baths, sqft, text_redacted, extras, field_confidence, extraction, "
                "price_usd, observed_at) "
                "SELECT %s, ext, listing_type, zip, neighborhood, precision, beds, baths, sqft, text, "
                "convert_from(extras, 'UTF8')::jsonb, convert_from(conf, 'UTF8')::jsonb, extraction, price, observed_at "
                "FROM _stg ON CONFLICT (source_key, external_id_hash) DO UPDATE SET last_seen = now(), "
                "price_usd = EXCLUDED.price_usd, observed_at = EXCLUDED.observed_at, "
                "extras = staging_listings.extras || EXCLUDED.extras", (key,))
            out["staged"] = cur.rowcount
            cur.execute(
                "INSERT INTO staging_price_observations (observed_at, listing_id, property_id, source_key, "
                "listing_type, zip, beds, price_usd, price_max_usd, trust_weight, event) "
                "SELECT (date_trunc('day', t.observed_at AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'), s.listing_id, NULL, "
                "%s, t.listing_type, t.zip, t.beds, t.price, NULL, %s, "
                "CASE WHEN t.precision IN ('zip','neighborhood','city') THEN 'posted' ELSE 'seen' END "
                "FROM _stg t JOIN staging_listings s ON s.source_key = %s AND s.external_id_hash = t.ext "
                "ON CONFLICT (listing_id, observed_at, event) DO NOTHING", (key, round(trust, 2), key))
    conn.commit()
    return out


def load_history(conn, key: str, trust: float, hist: list, bl: set[str]) -> int:
    """After the last chunk: history observations for listings whose history is the unit's own; the flagged
    (building-level) listings lose extras.price_history."""
    rows = [(e, d, p) for e, _, hs in hist if e not in bl for d, p in hs]
    n = 0
    with conn.cursor() as cur:
        if bl:
            cur.execute("UPDATE staging_listings SET extras = extras - 'price_history' WHERE source_key = %s "
                        "AND external_id_hash = ANY(%s)", (key, list(bl)))
        if rows:
            cur.execute("CREATE TEMP TABLE IF NOT EXISTS _hist (ext text, d text, price int4) ON COMMIT DROP")
            with cur.copy("COPY _hist (ext, d, price) FROM STDIN (FORMAT BINARY)") as cp:
                cp.set_types(["text", "text", "int4"])
                for r in rows:
                    cp.write_row(r)
            cur.execute(
                "INSERT INTO staging_price_observations (observed_at, listing_id, property_id, source_key, "
                "listing_type, zip, beds, price_usd, price_max_usd, trust_weight, event) "
                "SELECT (h.d::date::timestamp AT TIME ZONE 'UTC'), s.listing_id, NULL, s.source_key, s.listing_type, "
                "s.zip, s.beds, h.price, NULL, %s, 'history' "
                "FROM _hist h JOIN staging_listings s ON s.source_key = %s AND s.external_id_hash = h.ext "
                "ON CONFLICT (listing_id, observed_at, event) DO NOTHING", (round(trust, 2), key))
            n = cur.rowcount
    conn.commit()
    return n


def bump_data_version(conn) -> int:
    """The API clears its caches when this changes (checked at most every 30 s)."""
    v = conn.execute("INSERT INTO data_version (id, version) VALUES (1, 1) ON CONFLICT (id) DO UPDATE SET "
                     "version = data_version.version + 1, updated_at = now() RETURNING version").fetchone()[0]
    conn.commit()
    return v


# ------------------------------------------------------------------ the pipeline
def run_pipeline(chunks, *, template_key: str, connect, trust: float = 1.0, snapshot_id: str | None = None,
                 procs: int | None = None, loaders: int = MAX_LOADERS, observed_at: datetime | None = None,
                 bump: bool = True) -> dict:
    """chunks: iterable of lists of NDJSON lines (bytes). connect(): a new psycopg connection.
    Returns counts and per-stage seconds."""
    procs = procs or default_procs()
    t = load_template(template_key)
    key = t.get("loads_as") or t["source_key"]
    observed_at = observed_at or datetime.now(timezone.utc)
    t0 = time.perf_counter()
    qs = [queue.Queue(maxsize=4) for _ in range(loaders)]
    stats = {"records": 0, "billed": 0, "errors": 0, "mapped": 0, "dropped": 0, "raw_new": 0, "staged": 0,
             "map_cpu_s": 0.0, "load_s": 0.0}
    lock = threading.Lock()
    failures: list = []

    def loader(i):
        conn = connect()
        try:
            while True:
                item = qs[i].get()
                if item is None:
                    return
                if failures:
                    continue
                t1 = time.perf_counter()
                try:
                    o = load_batch(conn, template_key, key, trust, snapshot_id, *item)
                except Exception as e:     # noqa: BLE001
                    conn.rollback()
                    failures.append(e)
                    continue
                with lock:
                    stats["raw_new"] += o["raw_new"]
                    stats["staged"] += o["staged"]
                    stats["load_s"] += time.perf_counter() - t1
        finally:
            conn.close()

    threads = [threading.Thread(target=loader, args=(i,), daemon=True) for i in range(loaders)]
    for th in threads:
        th.start()
    hist_all: list = []
    pending: deque = deque()

    def route(res):
        stats["billed"] += res["billed"]
        stats["errors"] += res["errors"]
        stats["records"] += res["n"]
        stats["mapped"] += len(res["rows"])
        stats["dropped"] += res["dropped"]
        stats["map_cpu_s"] += res["secs"]
        hist_all.extend(res["hist"])
        raws = [[] for _ in range(loaders)]
        stgs = [[] for _ in range(loaders)]
        for h, b in res["raw"]:
            raws[part_of(h, loaders)].append((h, b))
        for r in res["rows"]:
            stgs[part_of(r[1], loaders)].append(r)
        for i in range(loaders):
            if raws[i] or stgs[i]:
                qs[i].put((raws[i], stgs[i]))

    t_map0 = time.perf_counter()
    try:
        with ProcessPoolExecutor(max_workers=procs) as ex:
            for lines in chunks:
                if failures:
                    break
                pending.append(ex.submit(process_chunk, template_key, lines, observed_at.isoformat(), trust))
                while len(pending) >= procs * 2:
                    route(pending.popleft().result())
            while pending:
                route(pending.popleft().result())
    finally:
        for q in qs:
            q.put(None)
        for th in threads:
            th.join()
    if failures:
        raise failures[0]
    stats["map_wall_s"] = time.perf_counter() - t_map0
    conn = connect()
    try:
        bl = building_level(hist_all)
        stats["history_rows"] = load_history(conn, key, trust, hist_all, bl)
        stats["building_level_dropped"] = len(bl)
        if bump:
            stats["data_version"] = bump_data_version(conn)
    finally:
        conn.close()
    stats["total_s"] = time.perf_counter() - t0
    stats["procs"], stats["loaders"] = procs, loaders
    return stats


def chunk_lines(lines, size: int = CHUNK):
    """Group an iterable of NDJSON lines into chunks of `size`."""
    buf = []
    for ln in lines:
        buf.append(ln)
        if len(buf) >= size:
            yield buf
            buf = []
    if buf:
        yield buf
