"""Fair-rent model: expected rent with an 80% range. Owner: lane C.

Train only on address-level listing-site rentals (zillow_rent, apartments_com), weighted by trust.
Under MIN_ROWS_FOR_MODEL rows, callers use median_fallback on ZIP-and-bedroom comparables instead.
Labels never say "illegal"; that word belongs to the rules engine.
"""
import os
from typing import Literal

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import GroupKFold
from threadpoolctl import threadpool_limits

FEATURES = ["beds", "baths", "log_sqft", "zip_code", "year_built", "ptype_code", "lat", "lng"]
MIN_ROWS_FOR_MODEL = 1000
QUANTILES = (0.1, 0.5, 0.9)
Label = Literal["above_typical_range", "in_range", "below_typical_range"]


def _encode(df: pd.DataFrame, enc: dict) -> pd.DataFrame:
    sqft = pd.to_numeric(df["sqft"], errors="coerce")
    out = pd.DataFrame({
        "beds": pd.to_numeric(df["beds"], errors="coerce"),
        "baths": pd.to_numeric(df["baths"], errors="coerce"),
        "log_sqft": np.log(sqft.where(sqft > 0)),
        "zip_code": df["zip"].astype(str).map(enc["zips"]).astype(float),
        "year_built": pd.to_numeric(df["year_built"], errors="coerce"),
        "ptype_code": df["property_type"].map(enc["ptypes"]).astype(float),
        "lat": pd.to_numeric(df["lat"], errors="coerce"),
        "lng": pd.to_numeric(df["lng"], errors="coerce"),
    })
    return out[FEATURES].astype(float)


def fit(df) -> dict:
    """df has columns beds, baths, sqft, zip, year_built, property_type, lat, lng, rent, building_id,
    trust_weight. Returns {0.1: model, 0.5: model, 0.9: model} plus whatever encoders predict needs."""
    enc = {"zips": {z: i for i, z in enumerate(sorted(df["zip"].dropna().astype(str).unique()))},
           "ptypes": {p: i for i, p in enumerate(sorted(df["property_type"].dropna().unique()))}}
    X, y = _encode(df, enc), np.log(df["rent"].astype(float))
    w = df["trust_weight"].astype(float).to_numpy() if "trust_weight" in df else None
    cat = [FEATURES.index("zip_code"), FEATURES.index("ptype_code")]
    with threadpool_limits(limits=1):  # OpenMP oversubscription made small fits take 40s+
        models = {q: HistGradientBoostingRegressor(
            loss="quantile", quantile=q, categorical_features=cat, max_iter=300,
            learning_rate=0.05, random_state=0).fit(X, y, sample_weight=w) for q in QUANTILES}
    models["encoders"] = enc
    return models


def _predict_frame(models: dict, df: pd.DataFrame) -> np.ndarray:
    X = _encode(df, models["encoders"])
    with threadpool_limits(limits=1):
        p = np.exp(np.column_stack([models[q].predict(X) for q in QUANTILES]))
    return np.sort(p, axis=1)  # guard against crossing quantiles


def cross_validate(df, folds: int = 5) -> dict:
    """Grouped by building_id. Returns {"mae_usd": float, "coverage_80": float, "n": int}."""
    df = df.reset_index(drop=True)
    groups = df["building_id"]
    folds = max(2, min(folds, groups.nunique()))
    pred = np.zeros((len(df), 3))
    for tr, te in GroupKFold(n_splits=folds).split(df, groups=groups):
        pred[te] = _predict_frame(fit(df.iloc[tr]), df.iloc[te])
    rent = df["rent"].astype(float).to_numpy()
    err = np.abs(pred[:, 1] - rent)
    return {"mae_usd": float(err.mean()), "median_ae_usd": float(np.median(err)),
            "coverage_80": float(np.mean((rent >= pred[:, 0]) & (rent <= pred[:, 2]))),
            "n": int(len(df))}


def predict(models: dict, row: dict) -> dict:
    """row: beds, baths, sqft, zip, year_built, property_type, lat, lng (any may be None).
    Returns {"low": float, "expected": float, "high": float} in dollars."""
    cols = ["beds", "baths", "sqft", "zip", "year_built", "property_type", "lat", "lng"]
    df = pd.DataFrame([{c: row.get(c) for c in cols}])
    lo, mid, hi = _predict_frame(models, df)[0]
    return {"low": float(lo), "expected": float(mid), "high": float(hi)}


def median_fallback(comparable_rents: list[float], spread: dict | None = None) -> dict | None:
    """ZIP-and-bedroom comparables -> {"low", "expected": median, "high"}; None if empty.
    With a calibrated `spread` ({"lo_mult", "hi_mult"}, from calibrate_spread) the range is the median times
    those multipliers; without one it is the plain 10th to 90th percentile of the comparables, which is too
    narrow for held-out rents because listings in one building share a rent."""
    if len(comparable_rents) == 0:
        return None
    arr = np.asarray(comparable_rents, dtype=float)
    mid = float(np.percentile(arr, 50))
    if spread:
        return {"low": mid * spread["lo_mult"], "expected": mid, "high": mid * spread["hi_mult"]}
    lo, _, hi = np.percentile(arr, [10, 50, 90])
    return {"low": float(lo), "expected": mid, "high": float(hi)}


MIN_POOL = 5                       # same-ZIP, same-bedroom rentals from other buildings needed for an estimate
TAILS = tuple(round(float(t), 3) for t in np.arange(0.10, 0.009, -0.005))   # tail mass per side, widening


def _group_index(df: pd.DataFrame) -> dict:
    """(zip, beds) -> (rents, building ids) arrays."""
    out = {}
    for (z, b), g in df.groupby(["zip", "beds"]):
        out[(z, b)] = (g["rent"].to_numpy(float), g["building_id"].to_numpy())
    return out


def _log_ratios(df: pd.DataFrame, pools: pd.DataFrame | None = None) -> np.ndarray:
    """log(rent / median of the other buildings' rents) for each row of df, using `pools` (default df) as the
    comparables. Rows whose pool is smaller than MIN_POOL are skipped."""
    idx = _group_index(df if pools is None else pools)
    out = []
    for z, b, rent, bld in zip(df["zip"], df["beds"], df["rent"], df["building_id"]):
        rents, blds = idx.get((z, b), (np.array([]), np.array([])))
        keep = rents[blds != bld]
        if len(keep) >= MIN_POOL:
            out.append(np.log(float(rent) / np.median(keep)))
    return np.asarray(out)


def _fold_coverage(df: pd.DataFrame, tail: float, folds: int) -> float:
    """Held-out coverage of the range at `tail`, quantiles taken from the training folds only."""
    df = df.reset_index(drop=True)
    hits = []
    n_splits = max(2, min(folds, df["building_id"].nunique()))
    for tr, te in GroupKFold(n_splits=n_splits).split(df, groups=df["building_id"]):
        train, test = df.iloc[tr], df.iloc[te]
        r_train = _log_ratios(train)
        if len(r_train) < 20:
            continue
        lo, hi = np.quantile(r_train, [tail, 1 - tail])
        r_test = _log_ratios(test, pools=train)          # new buildings against comparables seen in training
        hits.extend(((r_test >= lo) & (r_test <= hi)).tolist())
    return float(np.mean(hits)) if hits else float("nan")


def calibrate_spread(df, target: float = 0.80, folds: int = 5) -> dict | None:
    """Widen the median-method range from the empirical spread of rents across buildings.
    For each candidate tail mass, narrowest range first, it measures held-out coverage with building-grouped
    folds, quantiles taken from the training folds only, and keeps the first tail that reaches `target`.
    Returns {"lo_mult", "hi_mult", "tail", "target"} fitted on all rows at that tail, or None with too little data."""
    df = df.dropna(subset=["zip", "beds", "building_id"]).reset_index(drop=True)
    ratios = _log_ratios(df)
    if len(ratios) < 30 or df["building_id"].nunique() < 3:
        return None
    chosen = TAILS[-1]
    for tail in TAILS:                                    # 0.10 (narrowest range) down to 0.01 (widest)
        c = _fold_coverage(df, tail, folds)
        if c == c and c >= target:
            chosen = tail
            break
    lo, hi = np.quantile(ratios, [chosen, 1 - chosen])
    return {"lo_mult": float(np.exp(lo)), "hi_mult": float(np.exp(hi)), "tail": float(chosen), "target": target}


def fallback_cross_validate(df, folds: int = 5) -> dict:
    """Held-out check of the ZIP-and-bedroom median method with a calibrated range (same metric keys, plus
    "spread" for the API). Calibration runs inside each training fold, so coverage_80 is an honest held-out number;
    the spread stored for the API is calibrated on all rows."""
    df = df.dropna(subset=["zip", "beds", "building_id"]).reset_index(drop=True)
    empty = {"mae_usd": None, "median_ae_usd": None, "coverage_80": None, "n": int(len(df)), "spread": None}
    if df.empty or df["building_id"].nunique() < 3:
        return empty
    errs, hits = [], []
    n_splits = max(2, min(folds, df["building_id"].nunique()))
    for tr, te in GroupKFold(n_splits=n_splits).split(df, groups=df["building_id"]):
        train, test = df.iloc[tr], df.iloc[te]
        spread = calibrate_spread(train, folds=4)
        idx = _group_index(train)
        for z, b, rent in zip(test["zip"], test["beds"], test["rent"]):
            rents = idx.get((z, b), (np.array([]), None))[0]
            if len(rents) < MIN_POOL:
                continue
            est = median_fallback(rents.tolist(), spread)
            errs.append(abs(est["expected"] - rent))
            hits.append(est["low"] <= rent <= est["high"])
    if not errs:
        return empty
    return {"mae_usd": float(np.mean(errs)), "median_ae_usd": float(np.median(errs)),
            "coverage_80": float(np.mean(hits)), "n": int(len(df)), "n_scored": len(errs),
            "spread": calibrate_spread(df, folds=folds)}


def label(asking_rent: float, estimate: dict) -> Label:
    if asking_rent > estimate["high"]:
        return "above_typical_range"
    if asking_rent < estimate["low"]:
        return "below_typical_range"
    return "in_range"


def save(models: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    joblib.dump(models, path)


def load(path: str) -> dict | None:
    """Returns None when no trained model exists at path."""
    return joblib.load(path) if os.path.exists(path) else None
