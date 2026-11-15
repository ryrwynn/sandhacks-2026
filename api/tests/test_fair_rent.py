import numpy as np
import pandas as pd
import pytest

from api.ml import fair_rent


def synth(n=600, seed=0):
    rng = np.random.default_rng(seed)
    zips = ["92101", "92104", "92105", "92037", "92109"]
    zip_base = dict(zip(zips, [1.0, 0.95, 0.8, 1.4, 1.2]))
    nb = n // 4
    b_zip = rng.choice(zips, nb)
    b_lat = rng.uniform(32.6, 32.9, nb)
    b_lng = rng.uniform(-117.25, -117.05, nb)
    b_year = rng.integers(1950, 2022, nb)
    b = rng.integers(0, nb, n)
    beds = rng.integers(0, 4, n)
    baths = np.clip(beds, 1, None) * rng.choice([1.0, 1.5], n)
    sqft = 350 + beds * 280 + rng.normal(0, 40, n)
    rent = (1100 + 520 * beds + 0.6 * sqft) * np.array([zip_base[z] for z in b_zip[b]]) \
        * np.exp(rng.normal(0, 0.06, n))
    return pd.DataFrame({
        "beds": beds, "baths": baths, "sqft": sqft, "zip": b_zip[b], "year_built": b_year[b],
        "property_type": rng.choice(["apartment", "condo"], n), "lat": b_lat[b], "lng": b_lng[b],
        "rent": rent, "building_id": b, "trust_weight": rng.choice([1.0, 0.9], n)})


def test_fit_predict_cv_and_roundtrip(tmp_path):
    df = synth()
    cv = fair_rent.cross_validate(df)
    assert cv["n"] == len(df)
    assert cv["mae_usd"] < 400
    assert 0.6 <= cv["coverage_80"] <= 0.95
    models = fair_rent.fit(df)
    row = {"beds": 2, "baths": 2, "sqft": 900, "zip": "92037", "year_built": 2005,
           "property_type": "apartment", "lat": 32.75, "lng": -117.15}
    est = fair_rent.predict(models, row)
    assert est["low"] <= est["expected"] <= est["high"]
    assert 1500 < est["expected"] < 4500
    path = str(tmp_path / "m.joblib")
    fair_rent.save(models, path)
    assert fair_rent.predict(fair_rent.load(path), row) == est


def test_predict_handles_missing_and_unknown_values():
    models = fair_rent.fit(synth())
    est = fair_rent.predict(models, {"beds": 1, "zip": "99999"})
    assert est["low"] <= est["expected"] <= est["high"]


def test_load_missing_returns_none(tmp_path):
    assert fair_rent.load(str(tmp_path / "nope.joblib")) is None


def test_median_fallback_and_label():
    assert fair_rent.median_fallback([]) is None
    est = fair_rent.median_fallback(list(range(1000, 2001, 100)))
    assert est["expected"] == pytest.approx(1500)
    assert est["low"] < est["expected"] < est["high"]
    assert fair_rent.label(est["high"] + 1, est) == "above_typical_range"
    assert fair_rent.label(est["low"] - 1, est) == "below_typical_range"
    assert fair_rent.label(est["expected"], est) == "in_range"


def test_fallback_cross_validate():
    r = fair_rent.fallback_cross_validate(synth(200))
    assert r["mae_usd"] is not None and 0 <= r["coverage_80"] <= 1
