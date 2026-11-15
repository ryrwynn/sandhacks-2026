"""Fair-rent model: expected rent with an 80% range. Owner: lane C.

Train only on address-level listing-site rentals (zillow_rent, apartments_com), weighted by trust.
Under MIN_ROWS_FOR_MODEL rows, callers use median_fallback on ZIP-and-bedroom comparables instead.
Labels never say "illegal"; that word belongs to the rules engine.
"""
from typing import Literal

FEATURES = ["beds", "baths", "log_sqft", "zip_code", "year_built", "ptype_code", "lat", "lng"]
MIN_ROWS_FOR_MODEL = 1000
Label = Literal["above_typical_range", "in_range", "below_typical_range"]


def fit(df) -> dict:
    """df has columns beds, baths, sqft, zip, year_built, property_type, lat, lng, rent, building_id,
    trust_weight. Returns {0.1: model, 0.5: model, 0.9: model} plus whatever encoders predict needs."""
    raise NotImplementedError("lane C: fair_rent.fit")


def cross_validate(df, folds: int = 5) -> dict:
    """Grouped by building_id. Returns {"mae_usd": float, "coverage_80": float, "n": int}."""
    raise NotImplementedError("lane C: fair_rent.cross_validate")


def predict(models: dict, row: dict) -> dict:
    """row: beds, baths, sqft, zip, year_built, property_type, lat, lng (any may be None).
    Returns {"low": float, "expected": float, "high": float} in dollars."""
    raise NotImplementedError("lane C: fair_rent.predict")


def median_fallback(comparable_rents: list[float]) -> dict | None:
    """ZIP-and-bedroom comparables -> {"low": p10, "expected": median, "high": p90}; None if empty."""
    raise NotImplementedError("lane C: fair_rent.median_fallback")


def label(asking_rent: float, estimate: dict) -> Label:
    raise NotImplementedError("lane C: fair_rent.label")


def save(models: dict, path: str) -> None:
    raise NotImplementedError("lane C: fair_rent.save")


def load(path: str) -> dict | None:
    """Returns None when no trained model exists at path."""
    raise NotImplementedError("lane C: fair_rent.load")
