"""Database access: a lazy psycopg 3 pool from DATABASE_URL, plus every SQL query the routers use.

Routers call the functions here; tests monkeypatch them. Anything that can't reach the database
raises DBUnavailable, which routers turn into empty data or a 503.
"""
import logging
import os
import threading
from datetime import date
from decimal import Decimal
from pathlib import Path

log = logging.getLogger("rentorknot.db")

ZIPS_FILE = Path(__file__).resolve().parents[1] / "data" / "zips.txt"
LISTING_SITE_FILTER = "s.kind = 'listing_site'"

_pool = None
_lock = threading.Lock()


class DBUnavailable(RuntimeError):
    pass


def load_zip_names() -> dict[str, str]:
    names: dict[str, str] = {}
    for line in ZIPS_FILE.read_text().splitlines()[1:]:
        if "," in line:
            z, n = line.split(",", 1)
            names[z.strip()] = n.strip()
    return names


ZIP_NAMES = load_zip_names()


def get_pool():
    global _pool
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise DBUnavailable("DATABASE_URL is not set")
    with _lock:
        if _pool is None:
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool
            _pool = ConnectionPool(url, min_size=0, max_size=5, open=False, timeout=3,
                                   kwargs={"row_factory": dict_row, "connect_timeout": 3})
            _pool.open(wait=False)
    return _pool


def fetch(sql: str, params: dict | tuple | None = None) -> list[dict]:
    try:
        with get_pool().connection() as conn:
            return list(conn.execute(sql, params).fetchall())
    except DBUnavailable:
        raise
    except Exception as e:  # pool timeout, connection refused, SQL error
        raise DBUnavailable(str(e)) from e


def execute(sql: str, params: dict | tuple | None = None) -> list[dict]:
    """Run a write; returns rows when the statement has RETURNING."""
    try:
        with get_pool().connection() as conn:
            cur = conn.execute(sql, params)
            return list(cur.fetchall()) if cur.description else []
    except DBUnavailable:
        raise
    except Exception as e:
        raise DBUnavailable(str(e)) from e


def num(v):
    return float(v) if isinstance(v, Decimal) else v


# ---------- health ----------
def health_info() -> dict:
    counts: dict[str, int] = {}
    for t in ("listings", "price_observations", "area_metrics", "forecasts"):
        counts[t] = fetch(f"SELECT count(*) AS n FROM {t}")[0]["n"]
    for r in fetch("SELECT source_key, count(*) AS n FROM listings GROUP BY source_key"):
        counts[r["source_key"]] = r["n"]
    last = fetch("SELECT max(last_seen) AS t FROM listings")[0]["t"]
    runs = fetch("SELECT DISTINCT ON (kind) run_id, kind, trained_at, n_rows, metrics "
                 "FROM model_runs ORDER BY kind, trained_at DESC")
    return {"row_counts": counts, "last_scrape_at": last,
            "model_runs": [{**r, "metrics": r["metrics"] or {}} for r in runs]}


def ping() -> bool:
    fetch("SELECT 1")
    return True


# ---------- ZIP data ----------
def latest_index_values() -> dict[tuple[str, str], float]:
    rows = fetch("SELECT DISTINCT ON (geo_id, metric) geo_id, metric, value FROM area_metrics "
                 "WHERE geo_type = 'zip' AND metric IN ('zori','zhvi') AND source_key = 'zillow_research' "
                 "ORDER BY geo_id, metric, period DESC")
    return {(r["geo_id"], r["metric"]): float(r["value"]) for r in rows}


def forecast_end_values() -> dict[tuple[str, str], float]:
    """Mean forecast for the last (12th) forecast month of the latest forecast run."""
    rows = fetch("SELECT DISTINCT ON (zip, metric) zip, metric, mean_usd FROM forecasts "
                 "WHERE run_id = (SELECT run_id FROM model_runs WHERE kind = 'forecast' "
                 "ORDER BY trained_at DESC LIMIT 1) ORDER BY zip, metric, month DESC")
    return {(r["zip"], r["metric"]): float(r["mean_usd"]) for r in rows}


def median_rent_by_beds(days: int = 30) -> dict[str, dict[int, tuple[int, int]]]:
    """zip -> beds -> (median rent, n listings); latest price per rental listing on listing sites."""
    rows = fetch(
        "SELECT zip, beds, percentile_cont(0.5) WITHIN GROUP (ORDER BY price_usd) AS med, count(*) AS n "
        "FROM (SELECT DISTINCT ON (po.listing_id) po.listing_id, po.zip, po.beds, po.price_usd "
        "      FROM price_observations po JOIN sources s ON s.source_key = po.source_key "
        f"      WHERE po.listing_type = 'rent' AND {LISTING_SITE_FILTER} AND po.zip IS NOT NULL "
        "        AND po.event <> 'removed' AND po.observed_at >= now() - make_interval(days => %s) "
        "      ORDER BY po.listing_id, po.observed_at DESC) t "
        "GROUP BY zip, beds", (days,))
    out: dict[str, dict[int, tuple[int, int]]] = {}
    for r in rows:
        if r["beds"] is not None:
            out.setdefault(r["zip"].strip(), {})[int(r["beds"])] = (round(float(r["med"])), int(r["n"]))
    return out


def zip_features() -> dict[str, dict]:
    rows = fetch("SELECT * FROM zip_features")
    return {r["zip"].strip(): {k: num(v) for k, v in r.items()} for r in rows}


def zhvi_volatility() -> dict[str, float]:
    """Std of monthly % changes of ZHVI over the last 5 years, per ZIP."""
    import statistics
    rows = fetch("SELECT geo_id, value FROM area_metrics WHERE geo_type = 'zip' AND metric = 'zhvi' "
                 "AND source_key = 'zillow_research' AND period >= now() - INTERVAL '5 years' "
                 "ORDER BY geo_id, period")
    series: dict[str, list[float]] = {}
    for r in rows:
        series.setdefault(r["geo_id"], []).append(float(r["value"]))
    out = {}
    for z, vals in series.items():
        ch = [(b / a - 1) * 100 for a, b in zip(vals, vals[1:]) if a]
        if len(ch) >= 2:
            out[z] = statistics.pstdev(ch)
    return out


def series(zip_: str, metric: str) -> list[dict]:
    return fetch(
        "WITH latest AS (SELECT run_id FROM model_runs WHERE kind = 'forecast' ORDER BY trained_at DESC LIMIT 1) "
        "SELECT period AS month, value, NULL::numeric AS lo80, NULL::numeric AS hi80, 'actual' AS kind, "
        "NULL::uuid AS run_id, NULL::numeric AS backtest_mape FROM area_metrics "
        "WHERE geo_type = 'zip' AND geo_id = %(zip)s AND metric = %(metric)s "
        "AND source_key = 'zillow_research' AND period >= now() - INTERVAL '5 years' "
        "UNION ALL "
        "SELECT f.month, f.mean_usd, f.lo80_usd, f.hi80_usd, 'forecast', f.run_id, f.backtest_mape "
        "FROM forecasts f JOIN latest USING (run_id) WHERE f.zip = %(zip)s AND f.metric = %(metric)s "
        "ORDER BY month", {"zip": zip_, "metric": metric})


def forecast_run_metrics(run_id) -> dict:
    rows = fetch("SELECT metrics FROM model_runs WHERE run_id = %s", (run_id,))
    return (rows[0]["metrics"] or {}) if rows else {}


def fair_rent_metrics() -> dict:
    rows = fetch("SELECT metrics FROM model_runs WHERE kind = 'fair_rent' ORDER BY trained_at DESC LIMIT 1")
    return (rows[0]["metrics"] or {}) if rows else {}


# ---------- comparables ----------
_comp_cache: dict = {"at": 0.0, "groups": {}}
COMP_TTL_S = 300


def _comp_groups() -> dict[tuple[str, int], list[float]]:
    import time
    if time.monotonic() - _comp_cache["at"] > COMP_TTL_S or not _comp_cache["groups"]:
        rows = fetch(
            "SELECT DISTINCT ON (po.listing_id) po.zip, po.beds, po.price_usd FROM price_observations po "
            "JOIN sources s ON s.source_key = po.source_key "
            f"WHERE po.listing_type = 'rent' AND {LISTING_SITE_FILTER} AND po.zip IS NOT NULL "
            "AND po.beds IS NOT NULL AND po.event <> 'removed' AND po.observed_at >= now() - interval '90 days' "
            "ORDER BY po.listing_id, po.observed_at DESC")
        groups: dict[tuple[str, int], list[float]] = {}
        for r in rows:
            groups.setdefault((r["zip"].strip(), int(r["beds"])), []).append(float(r["price_usd"]))
        _comp_cache.update(at=time.monotonic(), groups=groups)
    return _comp_cache["groups"]
def comparable_rents(zip_: str, beds: int | None, days: int = 90) -> list[float]:
    """Latest price per rental listing in the last `days`; same ZIP and, when given, same beds.
    Never widened across bedroom counts: a studio isn't a comparable for a 2-bedroom.
    The default 90-day window is served from one bulk query kept for a few minutes (listing pages ask per group)."""
    if days == 90:
        groups = _comp_groups()
        if beds is not None:
            return list(groups.get((zip_, int(beds)), []))
        return [r for (z, _), rs in groups.items() if z == zip_ for r in rs]
    base = ("SELECT DISTINCT ON (po.listing_id) po.price_usd FROM price_observations po "
            "JOIN sources s ON s.source_key = po.source_key "
            f"WHERE po.listing_type = 'rent' AND {LISTING_SITE_FILTER} AND po.zip = %s AND po.event <> 'removed' "
            "AND po.observed_at >= now() - make_interval(days => %s)")
    if beds is not None:
        rows = fetch(base + " AND po.beds = %s ORDER BY po.listing_id, po.observed_at DESC", (zip_, days, beds))
        return [float(r["price_usd"]) for r in rows]
    rows = fetch(base + " ORDER BY po.listing_id, po.observed_at DESC", (zip_, days))
    return [float(r["price_usd"]) for r in rows]


def comparable_texts(zip_: str, beds: int, limit: int = 200) -> list[str]:
    rows = fetch("SELECT text_redacted FROM listings WHERE listing_type = 'rent' AND zip = %s AND beds = %s "
                 "AND text_redacted IS NOT NULL ORDER BY last_seen DESC LIMIT %s", (zip_, beds, limit))
    return [r["text_redacted"] for r in rows]


def listing_text(listing_id: int) -> str | None:
    rows = fetch("SELECT text_redacted FROM listings WHERE listing_id = %s", (listing_id,))
    return rows[0]["text_redacted"] if rows else None


def days_on_market(zip_: str, beds: int) -> list[tuple[float, float]]:
    """(last price, days from first_seen to removal) for removed rental listings in the ZIP and beds."""
    rows = fetch(
        "SELECT lp.price_usd, EXTRACT(EPOCH FROM (rm.removed_at - l.first_seen)) / 86400 AS days "
        "FROM listings l "
        "JOIN LATERAL (SELECT min(observed_at) AS removed_at FROM price_observations "
        "              WHERE listing_id = l.listing_id AND event = 'removed') rm ON rm.removed_at IS NOT NULL "
        "JOIN LATERAL (SELECT price_usd FROM price_observations WHERE listing_id = l.listing_id "
        "              AND event <> 'removed' ORDER BY observed_at DESC LIMIT 1) lp ON true "
        "WHERE l.listing_type = 'rent' AND l.zip = %s AND l.beds = %s", (zip_, beds))
    return [(float(r["price_usd"]), float(r["days"])) for r in rows if r["days"] is not None]


def search_units(query: str, limit: int = 10) -> list[dict]:
    like = "%" + " ".join(query.split()) + "%"
    return fetch("SELECT property_id, address_norm, unit_label, zip, beds, year_built, property_type "
                 "FROM properties WHERE address_norm ILIKE %s ORDER BY address_norm, unit_label LIMIT %s",
                 (like, limit))


# ---------- rent caps and checks ----------
def read_rent_caps() -> list[dict]:
    return fetch("SELECT region, period_start, period_end, cap_pct, source_url FROM rent_caps "
                 "WHERE region = 'san_diego_county' ORDER BY period_start")


def insert_check(address: str, zip_: str | None, lowest: float, new: float, effective: date,
                 year_built: int | None, verdict: str, max_legal: float | None, is_demo: bool):
    rows = execute(
        "INSERT INTO rent_checks (address, zip, lowest_rent_12mo, new_rent, effective_date, year_built, "
        "verdict, max_legal_rent, is_demo) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING check_id",
        (address, zip_, round(lowest), round(new), effective, year_built, verdict,
         None if max_legal is None else int(max_legal), is_demo))
    return rows[0]["check_id"]


def get_check(check_id) -> dict | None:
    rows = fetch("SELECT * FROM rent_checks WHERE check_id = %s", (str(check_id),))
    return rows[0] if rows else None


# ---------- tracker: listings, observations, market ----------
PROPERTY_TYPES = {"apartment": ("apartment",), "condo": ("condo",), "house": ("single_family", "townhouse")}
_SORTS = {
    "recent": "t.last_seen DESC, t.listing_id DESC",
    "price_asc": "t.cur ASC, t.listing_id",
    "price_desc": "t.cur DESC, t.listing_id",
    "biggest_drop": "(t.cur - t.first_price) ASC, t.listing_id",
}
_WIN = ("win AS (SELECT source_key, max(last_seen) - interval '36 hours' AS cutoff "
        "FROM listings GROUP BY source_key)")
_ACTIVE_SQL = "l.last_seen >= w.cutoff"


def _listing_filters(zip_, beds, type_, ids) -> tuple[str, dict]:
    where, p = [], {}
    if ids is not None:
        where.append("l.listing_id = ANY(%(ids)s)")
        p["ids"] = ids
    else:
        where.append("l.listing_type = 'rent'")
    if zip_:
        where.append("l.zip = %(zip)s")
        p["zip"] = zip_
    if beds is not None:
        where.append("l.beds = %(beds)s")
        p["beds"] = beds
    if type_:
        where.append("p.property_type = ANY(%(ptypes)s)")
        p["ptypes"] = list(PROPERTY_TYPES[type_])
    return " AND ".join(where), p


def listing_page(zip_=None, beds=None, type_=None, max_price=None, sort="recent", limit=24, offset=0,
                 ids: list[int] | None = None) -> list[dict]:
    """One row per listing with first/current price, observation count and active flag; total in `total`."""
    where, p = _listing_filters(zip_, beds, type_, ids)
    having = ""
    if max_price is not None:
        having = "WHERE t.cur <= %(max_price)s"
        p["max_price"] = max_price
    p.update(limit=limit, offset=offset)
    sql = f"""
    WITH {_WIN}
    SELECT t.*, count(*) OVER () AS total FROM (
      SELECT l.listing_id, l.zip, l.listing_type, l.beds, l.baths, l.sqft, l.last_seen, p.address_norm,
             p.unit_label, p.property_type, p.year_built, s.kind AS source_kind,
             l.extras->>'source_url' AS source_url, {_ACTIVE_SQL} AS active,
             o.n, o.cur, o.first_price, o.first_observed
      FROM listings l
      JOIN sources s ON s.source_key = l.source_key
      JOIN win w ON w.source_key = l.source_key
      LEFT JOIN properties p ON p.property_id = l.property_id
      JOIN (SELECT listing_id, count(*) AS n,
                   (array_agg(price_usd ORDER BY observed_at DESC) FILTER (WHERE event <> 'removed'))[1] AS cur,
                   (array_agg(price_usd ORDER BY observed_at) FILTER (WHERE event <> 'removed'))[1] AS first_price,
                   min(observed_at)::date AS first_observed
            FROM price_observations GROUP BY listing_id) o ON o.listing_id = l.listing_id AND o.cur IS NOT NULL
      WHERE {where}) t
    {having}
    ORDER BY {_SORTS[sort]} LIMIT %(limit)s OFFSET %(offset)s"""
    return fetch(sql, p)


def listing_one(listing_id: int) -> dict | None:
    rows = listing_page(ids=[listing_id], limit=1)
    return rows[0] if rows else None


def listing_observations(ids: list[int]) -> list[dict]:
    return fetch("SELECT listing_id, observed_at, event, price_usd FROM price_observations "
                 "WHERE listing_id = ANY(%s) ORDER BY listing_id, observed_at, event", (ids,))


def listing_coords(listing_id: int) -> dict:
    rows = fetch("SELECT p.lat, p.lng FROM listings l JOIN properties p ON p.property_id = l.property_id "
                 "WHERE l.listing_id = %s", (listing_id,))
    return rows[0] if rows else {}


def last_scrape_at():
    return fetch("SELECT max(last_seen) AS t FROM listings")[0]["t"]


def active_rent_count(zip_=None, beds=None, type_=None) -> int:
    where, p = _listing_filters(zip_, beds, type_, None)
    return fetch(f"WITH {_WIN} SELECT count(*) AS n FROM listings l JOIN win w ON w.source_key = l.source_key "
                 f"LEFT JOIN properties p ON p.property_id = l.property_id WHERE {where} AND {_ACTIVE_SQL}",
                 p)[0]["n"]


def zori_monthly(zip_: str | None) -> list[dict]:
    """ZORI by month for a ZIP, or the mean across ZIPs; [{month, value}] oldest first."""
    return fetch("SELECT period AS month, avg(value) AS value FROM area_metrics WHERE geo_type = 'zip' "
                 "AND metric = 'zori' AND source_key = 'zillow_research' "
                 "AND (%(z)s::text IS NULL OR geo_id = %(z)s) GROUP BY period ORDER BY period", {"z": zip_})


def listing_monthly_medians(zip_, beds, type_) -> list[dict]:
    """Per month: median of each listing's last non-removed observation in that month, and listing count."""
    where, p = _listing_filters(zip_, beds, type_, None)
    return fetch(
        "SELECT month, percentile_cont(0.5) WITHIN GROUP (ORDER BY price_usd) AS value, count(*) AS n FROM ("
        " SELECT DISTINCT ON (po.listing_id, date_trunc('month', po.observed_at)) "
        "  date_trunc('month', po.observed_at)::date AS month, po.price_usd "
        " FROM price_observations po JOIN listings l ON l.listing_id = po.listing_id "
        " JOIN sources s ON s.source_key = l.source_key "
        f" LEFT JOIN properties p ON p.property_id = l.property_id WHERE {where} AND {LISTING_SITE_FILTER} "
        "  AND po.event <> 'removed' "
        " ORDER BY po.listing_id, date_trunc('month', po.observed_at), po.observed_at DESC) t "
        "GROUP BY month ORDER BY month", p)


def forecast_latest(zip_: str | None) -> list[dict]:
    """Latest forecast run's ZORI forecast by month (mean across ZIPs when zip_ is None)."""
    return fetch(
        "SELECT f.month, avg(f.mean_usd) AS value, avg(f.lo80_usd) AS lo80, avg(f.hi80_usd) AS hi80, "
        "avg(f.backtest_mape) AS backtest_mape, (array_agg(f.run_id))[1] AS run_id FROM forecasts f "
        "WHERE f.run_id = (SELECT run_id FROM model_runs WHERE kind = 'forecast' ORDER BY trained_at DESC LIMIT 1) "
        "AND f.metric = 'zori' AND (%(z)s::text IS NULL OR f.zip = %(z)s) GROUP BY f.month ORDER BY f.month",
        {"z": zip_})
