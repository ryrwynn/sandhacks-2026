"""Daily training job: `python -m worker.train`. Owner: lane C.

Reads DATABASE_URL. Writes forecasts (one run_id per run), model_runs rows for 'forecast' and
'fair_rent', and models/fair_rent.joblib. Exits cleanly with a message when there is no data yet.
"""
import json
import os
import sys
import uuid
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from api.ml import fair_rent
from api.ml.forecast import MIN_MONTHS, backtest, forecast_12

MODEL_PATH = os.environ.get("FAIR_RENT_MODEL_PATH", "models/fair_rent.joblib")
RENT_SOURCES = ("zillow_rent", "apartments_com")

SERIES_SQL = """
SELECT geo_id AS zip, period, value::float8 AS value FROM area_metrics
WHERE geo_type = 'zip' AND metric = %s AND source_key = 'zillow_research'
ORDER BY geo_id, period
"""

RENTALS_SQL = """
SELECT DISTINCT ON (po.listing_id)
       po.price_usd::float8 AS rent, po.trust_weight::float8 AS trust_weight, po.source_key,
       l.beds, l.baths::float8 AS baths, l.sqft, COALESCE(p.zip, l.zip) AS zip,
       p.year_built, p.property_type, p.lat, p.lng, p.address_norm AS building_id
FROM price_observations po
JOIN listings l ON l.listing_id = po.listing_id
JOIN properties p ON p.property_id = l.property_id
WHERE po.listing_type = 'rent' AND po.source_key = ANY(%s)
  AND l.location_precision = 'address' AND po.price_usd > 0
ORDER BY po.listing_id, po.observed_at DESC
"""


def load_series(conn, metric: str) -> dict[str, pd.Series]:
    with conn.cursor() as cur:
        cur.execute(SERIES_SQL, (metric,))
        rows = cur.fetchall()
    out: dict[str, list] = {}
    for z, period, value in rows:
        out.setdefault(z, []).append((pd.Timestamp(period), value))
    series = {}
    for z, pts in out.items():
        s = pd.Series({d: v for d, v in pts}).sort_index()
        series[z] = s.asfreq("MS").interpolate(limit_area="inside")
    return series


def train_forecasts(conn, run_id: uuid.UUID, made_at: datetime) -> dict | None:
    mapes, beat, n_series, skipped = [], 0, 0, 0
    rows = []
    for metric in ("zori", "zhvi"):
        for z, s in load_series(conn, metric).items():
            try:
                bt = backtest(s)
                fc = forecast_12(s)
            except Exception as exc:  # one bad series must not stop the run
                skipped += 1
                print(f"skip {metric} {z}: {exc}", file=sys.stderr)
                continue
            n_series += 1
            mapes.append(bt["mape"])
            beat += bt["beats_naive"]
            for month, r in fc.iterrows():
                rows.append((str(run_id), made_at, month.date(), z, metric, round(r["mean"], 2),
                             round(r["pi_lower"], 2), round(r["pi_upper"], 2), round(bt["mape"], 2)))
    if not rows:
        return None
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO forecasts (run_id, made_at, month, zip, metric, mean_usd, lo80_usd, hi80_usd,"
            " backtest_mape) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", rows)
    metrics = {"series": n_series, "skipped": skipped, "median_mape": float(np.median(mapes)),
               "mean_mape": float(np.mean(mapes)), "beats_naive": int(beat),
               "share_beats_naive": beat / n_series}
    record_run(conn, run_id, "forecast", len(rows), ["zillow_research"], metrics, None)
    return metrics


def load_rentals(conn) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(RENTALS_SQL, (list(RENT_SOURCES),))
        cols = [d.name for d in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=cols)


def train_fair_rent(conn) -> dict | None:
    df = load_rentals(conn)
    if df.empty:
        return None
    if len(df) >= fair_rent.MIN_ROWS_FOR_MODEL:
        metrics = fair_rent.cross_validate(df)
        fair_rent.save(fair_rent.fit(df), MODEL_PATH)
        metrics["method"], path = "model", MODEL_PATH
    else:
        metrics = fair_rent.fallback_cross_validate(df)
        metrics["method"], path = "zip_bed_median", None
    record_run(conn, uuid.uuid4(), "fair_rent", len(df), sorted(df["source_key"].unique()),
               metrics, path)
    return metrics


def record_run(conn, run_id, kind, n_rows, sources, metrics, artifact_path) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO model_runs (run_id, kind, n_rows, sources_used, metrics, artifact_path)"
            " VALUES (%s,%s,%s,%s,%s,%s)",
            (str(run_id), kind, n_rows, sources, json.dumps(metrics), artifact_path))


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set; nothing to train.")
        return 0
    import psycopg

    made_at = datetime.now(timezone.utc)
    with psycopg.connect(url) as conn:
        fm = train_forecasts(conn, uuid.uuid4(), made_at)
        print("forecast:", fm if fm else f"no zori/zhvi series with {MIN_MONTHS}+ months yet; skipped")
        rm = train_fair_rent(conn)
        print("fair_rent:", rm if rm else "no address-level rentals yet; skipped")
        conn.commit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
