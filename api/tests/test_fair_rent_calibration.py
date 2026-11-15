"""Calibrated spread for the ZIP-and-bedroom median method (RentOrKnot phase 2)."""
import numpy as np
import pandas as pd

from api.ml import fair_rent


def clustered(n_buildings=40, units=8, seed=1):
    """Units in one building share a rent, so the spread across buildings is wider than across all units."""
    rng = np.random.default_rng(seed)
    rows = []
    for b in range(n_buildings):
        base = 2400 * np.exp(rng.normal(0, 0.15))
        for _ in range(units):
            rows.append({"zip": "92104", "beds": 1, "building_id": f"b{b}", "rent": base * np.exp(rng.normal(0, 0.02))})
    return pd.DataFrame(rows)


def test_calibrated_spread_widens_range_and_reaches_target_coverage():
    df = clustered()
    spread = fair_rent.calibrate_spread(df)
    assert spread is not None and spread["lo_mult"] < 1 < spread["hi_mult"]
    plain = fair_rent.median_fallback(df["rent"].tolist())
    wide = fair_rent.median_fallback(df["rent"].tolist(), spread)
    assert wide["low"] < plain["low"] and wide["high"] > plain["high"]
    r = fair_rent.fallback_cross_validate(df)
    assert r["coverage_80"] >= 0.75       # the plain p10-p90 range would cover far less on held-out buildings
    assert r["spread"]["tail"] <= 0.1


def test_calibrate_spread_needs_enough_buildings():
    assert fair_rent.calibrate_spread(clustered(n_buildings=2)) is None


def test_median_fallback_without_spread_is_unchanged():
    est = fair_rent.median_fallback(list(range(1000, 2001, 100)))
    assert est["expected"] == 1500 and est["low"] == 1100 and est["high"] == 1900
