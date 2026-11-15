"""Helpers shared by routers: ZIP metric assembly, fair-rent estimate, small number utilities."""
import logging
import os
import statistics
from pathlib import Path

from api import db
from api.ml import fair_rent, listing_analysis

log = logging.getLogger("rentorknot.api")
MODEL_PATH = os.environ.get(
    "FAIR_RENT_MODEL", str(Path(__file__).resolve().parents[2] / "models" / "fair_rent.joblib"))
BEDS = ("0", "1", "2", "3")
_model_cache: dict = {"loaded": False, "models": None}


def safe(fn, *args, default=None, **kw):
    """Call fn; return default when the database is down or an engine function isn't implemented yet."""
    try:
        return fn(*args, **kw)
    except (db.DBUnavailable, NotImplementedError) as e:
        log.warning("%s unavailable: %s", getattr(fn, "__name__", fn), e)
        return default


def pct_change(forecast, latest):
    if forecast is None or not latest:
        return None
    return round((forecast / latest - 1) * 100, 2)


def zip_data(listing_sites_only: bool = False) -> dict[str, dict]:
    """One dict per ZIP with everything the ZIP endpoints and ranking need; missing data is None.
    Medians include whole-unit Facebook listings at half weight unless listing_sites_only."""
    latest = safe(db.latest_index_values, default={})
    fc = safe(db.forecast_end_values, default={})
    meds = (safe(db.median_rent_by_beds, 30, True, default={}) if listing_sites_only
            else safe(db.median_rent_by_beds, default={}))
    feats = safe(db.zip_features, default={})
    vol = safe(db.zhvi_volatility, default={})
    out = {}
    for z, name in db.ZIP_NAMES.items():
        m = meds.get(z, {})
        zori, zhvi = latest.get((z, "zori")), latest.get((z, "zhvi"))
        out[z] = {
            "zip": z, "name": name, "zori": zori, "zhvi": zhvi,
            "median_rent_by_beds": {b: (m[int(b)][0] if int(b) in m else None) for b in BEDS},
            "listings_30d": sum(n for _, n in m.values()),
            "rent_fc": pct_change(fc.get((z, "zori")), zori),
            "value_fc": pct_change(fc.get((z, "zhvi")), zhvi),
            "features": feats.get(z, {}), "volatility": vol.get(z),
        }
    return out


def score_rows(data: dict[str, dict], beds: int | None) -> list[dict]:
    rows = []
    for z, d in data.items():
        f = d["features"]
        rent = d["median_rent_by_beds"].get(str(beds)) if beds is not None else None
        rows.append({
            "zip": z, "typical_rent": rent if rent is not None else d["zori"],
            "rent_forecast_change_pct": d["rent_fc"], "groceries": f.get("groceries"),
            "transit_stops": f.get("transit_stops"), "parks": f.get("parks"),
            "food_drink": f.get("food_drink"), "gyms": f.get("gyms"), "area_km2": f.get("area_km2"),
            "listings_30d": d["listings_30d"], "typical_home_value": d["zhvi"],
            "value_forecast_change_pct": d["value_fc"], "value_volatility_5y": d["volatility"],
        })
    return rows


# ---------- fair rent (engine first, plain local fallback while lane C is unmerged) ----------
def _percentile(sorted_vals: list[float], q: float) -> float:
    k = (len(sorted_vals) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def _local_fallback(rents: list[float]) -> dict | None:
    if not rents:
        return None
    s = sorted(rents)
    return {"low": _percentile(s, .1), "expected": statistics.median(s), "high": _percentile(s, .9)}


def percentile_of(value, comps):
    try:
        return listing_analysis.percentile_of(value, comps)
    except NotImplementedError:
        return 100.0 * sum(c < value for c in comps) / len(comps) if comps else None


def label_for(asking, est):
    try:
        return fair_rent.label(asking, est)
    except NotImplementedError:
        if asking > est["high"]:
            return "above_typical_range"
        return "below_typical_range" if asking < est["low"] else "in_range"


def _models():
    if not _model_cache["loaded"]:
        try:
            _model_cache["models"] = fair_rent.load(MODEL_PATH)
        except Exception as e:  # not implemented yet, or no file
            log.info("no fair-rent model loaded: %s", e)
            _model_cache["models"] = None
        _model_cache["loaded"] = True
    return _model_cache["models"]


MIN_COMPS = 5   # fewer same-ZIP, same-bedroom rentals than this: no median estimate


def _run_metrics() -> dict:
    """Latest fair_rent run's error, reported as the plan's median absolute error when available."""
    m = dict(safe(db.fair_rent_metrics, default={}) or {})
    if m.get("median_ae_usd") is not None:
        m["mae_usd"] = m["median_ae_usd"]
    return m


def estimate(row: dict) -> tuple[dict | None, list[float], dict]:
    """Returns (estimate dict incl. method, comparable rents, model metrics). estimate None when no data."""
    comps = safe(db.comparable_rents, row["zip"], row.get("beds"), default=[])
    models = _models()
    if models:
        try:
            est = fair_rent.predict(models, row)
            return {**est, "method": "model"}, comps, _run_metrics()
        except Exception as e:
            log.warning("model predict failed, using median: %s", e)
    if len(comps) < MIN_COMPS:
        return None, comps, {}
    try:
        est = fair_rent.median_fallback(comps, _run_metrics().get("spread"))
    except NotImplementedError:
        est = _local_fallback(comps)
    return (None if est is None else {**est, "method": "zip_bed_median"}), comps, _run_metrics()
