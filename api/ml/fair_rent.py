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


def median_fallback(comparable_rents: list[float]) -> dict | None:
    """ZIP-and-bedroom comparables -> {"low": p10, "expected": median, "high": p90}; None if empty."""
    if len(comparable_rents) == 0:
        return None
    lo, mid, hi = np.percentile(np.asarray(comparable_rents, dtype=float), [10, 50, 90])
    return {"low": float(lo), "expected": float(mid), "high": float(hi)}


def fallback_cross_validate(df) -> dict:
    """Leave-one-building-out check of the ZIP-and-bedroom median method (same metric keys)."""
    errs, hits = [], []
    for _, r in df.iterrows():
        pool = df[(df["zip"] == r["zip"]) & (df["beds"] == r["beds"])
                  & (df["building_id"] != r["building_id"])]
        est = median_fallback(pool["rent"].tolist())
        if est is None:
            continue
        errs.append(abs(est["expected"] - r["rent"]))
        hits.append(est["low"] <= r["rent"] <= est["high"])
    if not errs:
        return {"mae_usd": None, "median_ae_usd": None, "coverage_80": None, "n": int(len(df))}
    return {"mae_usd": float(np.mean(errs)), "median_ae_usd": float(np.median(errs)),
            "coverage_80": float(np.mean(hits)), "n": int(len(df))}


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
