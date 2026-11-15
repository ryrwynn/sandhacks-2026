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

log = logging.getLogger("rentwatch.db")

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
def comparable_rents(zip_: str, beds: int | None, days: int = 90) -> list[float]:
    """Latest price per rental listing in the last `days`; same ZIP and, when given, same beds.
    Never widened across bedroom counts: a studio isn't a comparable for a 2-bedroom."""
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
