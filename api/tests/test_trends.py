"""Trend metrics and signals, with a mocked database."""
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api import db
from api.main import app
from api.ml import trends

client = TestClient(app)


def monthly(growth, n=30, start=2000.0):
    idx = pd.date_range("2024-01-01", periods=n, freq="MS")
    return pd.Series(start * (1 + growth) ** np.arange(n), index=idx)


def test_series_metrics_values():
    m = trends.series_metrics(monthly(0.01))
    assert m["yoy_pct"] == pytest.approx((1.01 ** 12 - 1) * 100, abs=0.05)
    assert m["momentum_3m_pct"] == pytest.approx((1.01 ** 12 - 1) * 100, abs=0.2)
    assert m["acceleration_pp"] == pytest.approx(0, abs=0.01)
    assert m["volatility_pct"] == pytest.approx(0, abs=0.01)
    assert trends.series_metrics(monthly(0.01, n=10)) is None


def test_acceleration_positive_when_growth_speeds_up():
    idx = pd.date_range("2024-01-01", periods=30, freq="MS")
    g = np.where(np.arange(30) < 24, 0.002, 0.012)
    s = pd.Series(2000 * np.cumprod(1 + g), index=idx)
    assert trends.series_metrics(s)["acceleration_pp"] > 1.5


def test_zip_signals():
    m = {"yoy_pct": 9.0, "county_percentile": 95.0, "acceleration_pp": 2.0, "volatility_pct": 2.0}
    kinds = [s["kind"] for s in trends.zip_signals("zori", m, 0.5)]
    assert kinds == ["fast_rise", "accelerating", "volatile"]
    low = {"yoy_pct": -2.0, "county_percentile": 5.0, "acceleration_pp": -2.0, "volatility_pct": 0.4}
    assert [s["kind"] for s in trends.zip_signals("zhvi", low, 0.5)] == ["fast_fall", "decelerating"]


def obs(*items):
    return [{"listing_id": 1, "observed_at": datetime(2026, m, d, tzinfo=timezone.utc), "event": e, "price_usd": p}
            for m, d, e, p in items]


def test_price_changes_cut_raise_and_relist_jump():
    o = obs((7, 1, "posted", 2500), (7, 20, "seen", 2500), (8, 10, "price_change", 2400),
            (8, 30, "removed", 2400), (10, 1, "posted", 2600), (10, 20, "price_change", 2550))
    ch = trends.price_changes(o)
    assert [c["kind"] for c in ch] == ["cut", "relist_jump", "cut"]
    assert ch[0]["change_pct"] == -4.0 and ch[0]["days_since_previous"] == 40
    assert ch[1]["from_usd"] == 2400 and ch[1]["to_usd"] == 2600


def test_listing_signals_repeated_cuts_and_below_zip():
    ch = [{"kind": "cut", "change_pct": -3.0}, {"kind": "cut", "change_pct": -2.0}]
    kinds = [s["kind"] for s in trends.listing_signals(ch, -6.0, 1.0, -5.0)]
    assert kinds == ["repeated_cuts", "below_zip_trend"]
    assert trends.listing_signals([], 1.0, 1.0, 2.0) == []


@pytest.fixture
def mock_db(monkeypatch):
    rows = []
    for z, g in (("92104", 0.01), ("92101", 0.004), ("92103", 0.002)):
        for metric in ("zori", "zhvi"):
            for d, v in monthly(g).items():
                rows.append({"zip": z, "metric": metric, "period": d.date(), "value": v})
    monkeypatch.setattr(db, "fetch", lambda sql, p=None: rows)


def test_zip_trends_endpoint(mock_db):
    r = client.get("/zips/92104/trends")
    assert r.status_code == 200
    j = r.json()
    assert j["rent"]["county_percentile"] == 100.0
    assert j["signals"][0]["kind"] == "fast_rise"
    assert "not legal findings" in j["disclaimer"]
    assert client.get("/zips/00000/trends").status_code == 404


def test_listing_trends_endpoint(monkeypatch):
    monkeypatch.setattr(db, "listing_one", lambda i: {"listing_id": i, "zip": "92104"} if i == 1 else None)
    monkeypatch.setattr(db, "listing_observations", lambda ids: obs((7, 1, "posted", 2500), (8, 10, "price_change", 2300),
                                                                    (9, 10, "price_change", 2200)))
    monkeypatch.setattr(db, "zori_monthly", lambda z: [{"month": d.date(), "value": v}
                                                         for d, v in monthly(0.004, n=14).items()])
    j = client.get("/listings/1/trends").json()
    assert j["first_price_usd"] == 2500 and j["current_price_usd"] == 2200
    assert j["total_change_pct"] == -12.0 and j["n_observations"] == 3
    assert [c["kind"] for c in j["changes"]] == ["cut", "cut"]
    kinds = [s["kind"] for s in j["signals"]]
    assert "repeated_cuts" in kinds and "below_zip_trend" in kinds
    assert client.get("/listings/2/trends").status_code == 404
