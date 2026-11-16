"""Daily training job: `python -m worker.train`. Owner: lane C.

Reads DATABASE_URL. Writes forecasts (one run_id per run), model_runs rows for 'forecast' and
'fair_rent', and models/fair_rent.joblib. Exits cleanly with a message when there is no data yet.

`python -m worker.train --dry-run [--read-staging]` (or RENTORKNOT_READ_STAGING=1): the same selection and
forecasts computed in memory on a read-only connection, plus staging_listings / staging_area_metrics when
--read-staging is given. Prints a compact JSON summary and writes nothing (no rows, no model file).
Fair rent: with enough rentals the gradient-boosted model is served only if its held-out median error is lower
than the median method's and its 80% coverage is at least fair_rent.MIN_COVERAGE; both are recorded.
Forecasts and scenarios cover every served ZIP (areas.tier core, county or on_demand) with 36+ months.
"""
import json
import os
import sys
import uuid
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from api.ml import fair_rent
from api.ml import macro as mc
from api.ml import scenario_model, scenario_run
from api.ml.forecast import MIN_MONTHS, backtest, forecast_12

MODEL_PATH = os.environ.get("FAIR_RENT_MODEL_PATH", "models/fair_rent.joblib")
RENT_SOURCES = ("zillow_rent", "apartments_com")

SERIES_SQL = """
SELECT geo_id AS zip, period, value::float8 AS value FROM area_metrics
WHERE geo_type = 'zip' AND metric = %s AND source_key = 'zillow_research'
ORDER BY geo_id, period
"""
LONG_MONTHS, SHORT_MONTHS = 96, 60
STAGING_SERIES_SQL = SERIES_SQL.replace("FROM area_metrics", "FROM staging_area_metrics")

RENTALS_SQL = """
SELECT DISTINCT ON (po.listing_id)
       po.price_usd::float8 AS rent, po.trust_weight::float8 AS trust_weight, po.source_key,
       l.external_id_hash, l.beds, l.baths::float8 AS baths, l.sqft, COALESCE(p.zip, l.zip) AS zip,
       p.year_built, lower(p.property_type) AS property_type, p.lat, p.lng, p.address_norm AS building_id
FROM price_observations po
JOIN listings l ON l.listing_id = po.listing_id
JOIN properties p ON p.property_id = l.property_id
WHERE po.listing_type = 'rent' AND po.source_key = ANY(%s) AND po.source_key NOT LIKE 'facebook%%'
  AND l.location_precision = 'address' AND po.price_usd > 0
ORDER BY po.listing_id, po.observed_at DESC
"""

# Staged rentals carry their property fields in extras (there is no staging properties table).
STAGING_RENTALS_SQL = """
SELECT sl.price_usd::float8 AS rent, COALESCE(NULLIF(sl.extras->>'trust_weight', '')::float8, 1.0) AS trust_weight,
       sl.source_key, sl.external_id_hash, sl.beds, sl.baths::float8 AS baths, sl.sqft, sl.zip,
       sl.extras->>'year_built' AS year_built, lower(sl.extras->>'property_type') AS property_type,
       sl.extras->>'lat' AS lat, sl.extras->>'lng' AS lng, sl.extras->>'address_norm' AS building_id
FROM staging_listings sl
WHERE sl.listing_type = 'rent' AND sl.source_key = ANY(%s) AND sl.source_key NOT LIKE 'facebook%%'
  AND sl.location_precision = 'address' AND sl.price_usd > 0 AND sl.extras->>'address_norm' IS NOT NULL
"""


def served_zips(conn) -> set[str]:
    """The API's served set (db.served_areas: tier core, county or on_demand with enough active listings; staged
    listings count when RENTORKNOT_READ_STAGING=1); data/zips.txt when the database is unreachable."""
    from api import db
    return set(db.served_zips())


def core_zips() -> set[str]:
    from api import db
    return set(db.load_zip_names())


def load_series(conn, metric: str, staging: bool = False) -> dict[str, pd.Series]:
    """Monthly series per ZIP from shared area_metrics; with staging=True also staging_area_metrics for months
    the shared table lacks (shared wins)."""
    pts: dict[str, dict] = {}
    for sql in (SERIES_SQL, STAGING_SERIES_SQL) if staging else (SERIES_SQL,):
        with conn.cursor() as cur:
            cur.execute(sql, (metric,))
            for z, period, value in cur.fetchall():
                pts.setdefault(z, {}).setdefault(pd.Timestamp(period), value)
    series = {}
    for z, d in pts.items():
        s = pd.Series(d).sort_index()
        series[z] = s.asfreq("MS").interpolate(limit_area="inside")
    return series


def _summ(vals: list[dict]) -> dict:
    if not vals:
        return {"series": 0}
    mapes = [v["mape"] for v in vals]
    beat = sum(1 for v in vals if v["beats_naive"])
    return {"series": len(vals), "median_mape": round(float(np.median(mapes)), 2),
            "mean_mape": round(float(np.mean(mapes)), 2), "share_beats_naive": round(beat / len(vals), 3)}


def compute_forecasts(conn, run_id, made_at, staging: bool = False, zips: set[str] | None = None):
    """Forecast and backtest every served ZIP with 36+ months of ZORI or ZHVI. Returns (rows, metrics) or None."""
    zips = served_zips(conn) if zips is None else zips
    mapes, beat, n_series, skipped = [], 0, 0, 0
    by_series = {}   # "zip:metric" -> backtest; the series endpoint reads naive_mape from here
    rows = []
    for metric in ("zori", "zhvi"):
        for z, s in load_series(conn, metric, staging).items():
            if z not in zips:
                continue
            try:
                bt = backtest(s)
                fc = forecast_12(s)
            except Exception as exc:  # one bad series must not stop the run (e.g. under 36 months)
                skipped += 1
                print(f"skip {metric} {z}: {exc}", file=sys.stderr)
                continue
            n_series += 1
            mapes.append(bt["mape"])
            beat += bt["beats_naive"]
            by_series[f"{z}:{metric}"] = {k: (bool(v) if k == "beats_naive" else round(float(v), 2))
                                          for k, v in bt.items()}
            for month, r in fc.iterrows():
                rows.append((str(run_id), made_at, month.date(), z, metric, round(r["mean"], 2),
                             round(r["pi_lower"], 2), round(r["pi_upper"], 2), round(bt["mape"], 2)))
    if not rows:
        return None
    metrics = {"series": n_series, "skipped": skipped, "zips": len({k.split(":")[0] for k in by_series}),
               "median_mape": float(np.median(mapes)), "mean_mape": float(np.mean(mapes)),
               "beats_naive": int(beat), "share_beats_naive": beat / n_series, "by_series": by_series}
    return rows, metrics


def train_forecasts(conn, run_id: uuid.UUID, made_at: datetime) -> dict | None:
    out = compute_forecasts(conn, run_id, made_at)
    if out is None:
        return None
    rows, metrics = out
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO forecasts (run_id, made_at, month, zip, metric, mean_usd, lo80_usd, hi80_usd,"
            " backtest_mape) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", rows)
    record_run(conn, run_id, "forecast", len(rows), ["zillow_research"], metrics, None)
    return metrics


def _fetch_df(conn, sql: str) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(sql, (list(RENT_SOURCES),))
        cols = [d.name for d in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=cols)


def load_rentals(conn, staging: bool = False) -> pd.DataFrame:
    """Address-level rentals from shared tables; with staging=True also staged rentals not already shared."""
    df = _fetch_df(conn, RENTALS_SQL)
    if staging:
        st = _fetch_df(conn, STAGING_RENTALS_SQL)
        if len(st):
            seen = set(zip(df["source_key"], df["external_id_hash"]))
            st = st[[(a, b) not in seen for a, b in zip(st["source_key"], st["external_id_hash"])]]
            df = pd.concat([df, st], ignore_index=True)
    return df.drop(columns=["external_id_hash"])


def fair_rent_metrics(sel: dict) -> dict:
    """model_runs.metrics for the served method (top-level keys as before, incl. spread for the median method),
    plus both methods' held-out numbers and the reason for the choice."""
    served = sel["model"] if sel["decision"] == "model" else sel["median"]
    return {**served, "method": sel["decision"], "reason": sel["reason"], "n": sel["n"],
            "model": sel["model"], "median": {k: v for k, v in sel["median"].items() if k != "spread"}}


def train_fair_rent(conn) -> dict | None:
    df = load_rentals(conn)
    if df.empty:
        return None
    sel = fair_rent.select_method(df)
    metrics = fair_rent_metrics(sel)
    if sel["decision"] == "model":
        fair_rent.save(fair_rent.fit(df), MODEL_PATH)
        path = MODEL_PATH
    else:
        path = None
        if os.path.exists(MODEL_PATH):   # a stale model file would still be served by the API
            os.remove(MODEL_PATH)
    record_run(conn, uuid.uuid4(), "fair_rent", len(df), sorted(df["source_key"].unique()), metrics, path)
    return metrics


def record_run(conn, run_id, kind, n_rows, sources, metrics, artifact_path) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO model_runs (run_id, kind, n_rows, sources_used, metrics, artifact_path)"
            " VALUES (%s,%s,%s,%s,%s,%s)",
            (str(run_id), kind, n_rows, sources, json.dumps(metrics), artifact_path))


MACRO_SQL = "SELECT series_id, period, value::float8 AS value FROM macro_series WHERE series_id = ANY(%s) ORDER BY period"


def load_macro(conn) -> pd.DataFrame:
    """Monthly ur, lhpi, mort from macro_series; falls back to the committed snapshot when the table is empty."""
    ids = mc.SERIES_IDS
    with conn.cursor() as cur:
        cur.execute(MACRO_SQL, (list(ids.values()),))
        rows = cur.fetchall()
    if not rows:
        return mc.to_model_frame(mc.load_snapshot())
    inv = {v: k for k, v in ids.items()}
    df = pd.DataFrame(rows, columns=["sid", "period", "value"])
    df["period"] = pd.to_datetime(df["period"])
    wide = df.pivot_table(index="period", columns=df["sid"].map(inv), values="value")
    return mc.to_model_frame(wide[["ur", "hpi", "mort"]])


def compute_scenarios(conn, run_id, made_at, staging: bool = False, zips: set[str] | None = None):
    """Scenario backtest and forecasts for served ZIPs with 36+ months. Returns (rows, metrics) or None."""
    core = served_zips(conn) if zips is None else zips
    macro_frame = load_macro(conn)
    rows, by_series, summary = [], {}, {}
    for metric in ("zori", "zhvi"):
        series = {z: s for z, s in load_series(conn, metric, staging).items()
                  if z in core and len(s.dropna()) >= MIN_MONTHS}
        # The pooled model needs every ZIP in one panel with complete months, so ZIPs are grouped by history:
        # long (96+ months, the usual backtest) and short (60-95 months, a backtest with earlier origins and
        # fewer test origins). ZIPs with 36-59 months, or not current to the latest month, get the ETS
        # forecasts only (the `forecasts` table); history is never padded.
        last = max((s.dropna().index[-1] for s in series.values()), default=None)
        groups = {"": {}, "_short": {}}
        for z, s in series.items():
            n = len(s.dropna())
            if s.dropna().index[-1] == last:
                if n >= LONG_MONTHS:
                    groups[""][z] = s
                elif n >= SHORT_MONTHS:
                    groups["_short"][z] = s
        for suffix, grp in groups.items():
            if len(grp) < 2:
                continue
            panel = scenario_model.panel_from_series(grp)
            n = len(panel)
            if n < SHORT_MONTHS:
                continue
            min_origin = min(scenario_model.MIN_ORIGIN, max(24, n - 42))
            res = scenario_run.run_metric(panel, macro_frame, min_origin=min_origin)
            rows += scenario_run.forecast_rows(metric, res, str(run_id), made_at, core)
            summary[metric + suffix] = res["summary"]
            for z, r in res["by_series"].items():
                by_series[f"{z}:{metric}"] = r
    if not rows:
        return None
    return rows, {"by_series": by_series, "summary": summary}


def train_scenarios(conn, run_id: uuid.UUID, made_at: datetime, zips: set[str] | None = None) -> dict | None:
    """Scenario forecasts for served ZIPs; writes scenario_forecasts and a model_runs row."""
    out = compute_scenarios(conn, run_id, made_at, zips=zips)
    if out is None:
        return None
    rows, metrics = out
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO scenario_forecasts (run_id, made_at, scenario, model, month, zip, metric, mean_usd, "
            "lo80_usd, hi80_usd, backtest_mape, coverage_80) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", rows)
    record_run(conn, run_id, "scenario_forecast", len(rows), ["zillow_research", "fred", "fed_scenarios"], metrics, None)
    return metrics


def _rnd(d: dict | None) -> dict | None:
    keep = ("mae_usd", "median_ae_usd", "coverage_80", "n", "n_scored")
    return None if d is None else {k: (round(v, 3) if isinstance(v, float) else v) for k, v in d.items() if k in keep}


def dry_run(conn, staging: bool) -> dict:
    """Everything in memory on a read-only connection; returns the compact summary. Writes nothing."""
    made_at, run_id = datetime.now(timezone.utc), uuid.uuid4()
    served = served_zips(conn)
    new = served - core_zips()
    out: dict = {"dry_run": True, "read_staging": staging, "served_zips": len(served), "new_zips": len(new)}
    rentals = load_rentals(conn, staging)
    out["rentals_used"] = int(len(rentals))
    if rentals.empty:
        out["fair_rent"] = None
    else:
        fm = fair_rent_metrics(fair_rent.select_method(rentals))
        out["fair_rent"] = {"decision": fm["method"], "reason": fm["reason"], "model": _rnd(fm["model"]),
                            "median_method": _rnd(fm["median"])}
    fc = compute_forecasts(conn, run_id, made_at, staging)
    if fc:
        rows, m = fc
        vals = [(k.split(":")[0], v) for k, v in m["by_series"].items()]
        out["forecasts"] = {"zips": m["zips"], "series": m["series"], "skipped_short": m["skipped"], "rows": len(rows),
                            "backtest_all": _summ([v for _, v in vals]),
                            "new_zips_forecast": len({z for z, _ in vals if z in new}),
                            "backtest_new_zips": _summ([v for z, v in vals if z in new])}
    else:
        out["forecasts"] = None
    sc = compute_scenarios(conn, run_id, made_at, staging)
    keep = ("naive", "ets", "baseline", "n_test_origins", "selected_baseline")
    out["scenarios"] = None if not sc else {
        "rows": len(sc[0]), "zips": len({k.split(":")[0] for k in sc[1]["by_series"]}),
        "new_zips": len({k.split(":")[0] for k in sc[1]["by_series"] if k.split(":")[0] in new}),
        "summary": {mt: {k: v for k, v in s.items() if k in keep} for mt, s in sc[1]["summary"].items()}}
    return out


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set; nothing to train.")
        return 0
    import psycopg

    args = sys.argv[1:]
    staging = "--read-staging" in args or os.environ.get("RENTORKNOT_READ_STAGING") == "1"
    if "--dry-run" in args:
        if staging:
            os.environ["RENTORKNOT_READ_STAGING"] = "1"   # the API's served set counts staged listings too
        with psycopg.connect(url) as conn:
            conn.read_only = True      # the database refuses any write on this connection
            print(json.dumps(dry_run(conn, staging), default=str, separators=(",", ":")))
        return 0
    if staging:
        print("staging rows are read only in --dry-run; write mode trains on shared tables.", file=sys.stderr)
    made_at = datetime.now(timezone.utc)
    with psycopg.connect(url) as conn:
        if "scenarios" in args:   # python -m worker.train scenarios: scenario forecasts only
            sm = train_scenarios(conn, uuid.uuid4(), made_at)
            print("scenarios:", sm["summary"] if sm else "no series; skipped")
            conn.commit()
            return 0
        fm = train_forecasts(conn, uuid.uuid4(), made_at)
        print("forecast:", {k: v for k, v in fm.items() if k != "by_series"} if fm else
              f"no zori/zhvi series with {MIN_MONTHS}+ months yet; skipped")
        rm = train_fair_rent(conn)
        print("fair_rent:", rm if rm else "no address-level rentals yet; skipped")
        conn.commit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
