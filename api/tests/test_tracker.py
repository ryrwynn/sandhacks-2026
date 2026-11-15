"""Tracker endpoint tests: db functions are monkeypatched; no database, no Gemini."""
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from api import db
from api.main import app
from api.routers import _common
from api.routers import tracker
from contracts.api_models import ListingDetail, ListingsResponse, MarketResponse

client = TestClient(app)


def T(y, m, d):
    return datetime(y, m, d, 12, tzinfo=timezone.utc)


RUN = UUID("6f1f8a52-3c3e-4d4c-9a51-0b9a4b6f2a10")


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(_common, "_model_cache", {"loaded": True, "models": None})
    tracker._label_cache.clear()


def row(i=101, **kw):
    r = {"listing_id": i, "zip": "92104", "listing_type": "rent", "beds": 1, "baths": Decimal("1.0"),
         "sqft": 453, "last_seen": T(2026, 11, 14), "address_norm": "2519 EL CAJON BLVD", "unit_label": "210",
         "property_type": "apartment", "year_built": 1980, "source_kind": "listing_site",
         "source_url": "https://example.com/x", "active": True, "n": 4, "cur": 2395, "first_price": 2670,
         "first_observed": date(2024, 9, 25), "total": 1}
    return {**r, **kw}


OBS = [{"listing_id": 101, "observed_at": T(2024, 9, 25), "event": "history", "price_usd": 2670},
       {"listing_id": 101, "observed_at": T(2024, 11, 23), "event": "history", "price_usd": 2195},
       {"listing_id": 101, "observed_at": T(2024, 11, 28), "event": "price_change", "price_usd": 2250},
       {"listing_id": 101, "observed_at": T(2026, 11, 14), "event": "seen", "price_usd": 2395}]


def patch_listings(monkeypatch, rows, comps=(2000.0, 2200, 2300, 2400, 2500, 2600)):
    monkeypatch.setattr(db, "listing_page", lambda *a, **k: rows)
    monkeypatch.setattr(db, "listing_one", lambda i: rows[0] if rows else None)
    monkeypatch.setattr(db, "listing_observations", lambda ids: OBS)
    monkeypatch.setattr(db, "comparable_rents", lambda z, b, days=90: list(comps))
    monkeypatch.setattr(db, "fair_rent_metrics", lambda: {})
    monkeypatch.setattr(db, "listing_coords", lambda i: {})


def test_openapi_lists_tracker_endpoints():
    paths = client.get("/openapi.json").json()["paths"]
    for p in ("/listings", "/listings/{listing_id}", "/market"):
        assert p in paths


def test_listings_summary(monkeypatch):
    patch_listings(monkeypatch, [row()])
    j = client.get("/listings?zip=92104&beds=1").json()
    ListingsResponse.model_validate(j)
    it = j["items"][0]
    assert it["id"] == 101 and it["address"] == "2519 El Cajon Blvd" and it["neighborhood"] == "North Park"
    assert it["current_price_usd"] == 2395.0 and it["n_observations"] == 4
    assert [p["month"] for p in it["sparkline"]] == ["2024-09-01", "2024-11-01", "2026-11-01"]
    assert it["sparkline"][1]["price_usd"] == 2250.0       # last observation in the month, nothing invented
    assert it["fair_rent_label"] == "in_range" and it["source_url"] == "https://example.com/x"
    assert j["total"] == 1 and j["limit"] == 24 and j["offset"] == 0


def test_listings_social_source_hides_url_and_few_comps_null_label(monkeypatch):
    patch_listings(monkeypatch, [row(source_kind="social")], comps=(2000.0, 2100))
    it = client.get("/listings").json()["items"][0]
    assert it["source_url"] is None and it["fair_rent_label"] is None


def test_listings_validation(monkeypatch):
    patch_listings(monkeypatch, [row()])
    assert client.get("/listings?type=mansion").status_code == 422
    assert client.get("/listings?sort=bogus").status_code == 422
    assert client.get("/listings?limit=101").status_code == 422
    assert client.get("/listings?ids=" + ",".join(map(str, range(51)))).status_code == 422
    assert client.get("/listings?ids=a,b").status_code == 422
    assert client.get("/listings?ids=101").status_code == 200


def test_labels_cached_per_group(monkeypatch):
    calls = []
    patch_listings(monkeypatch, [row(i=i) for i in range(1, 6)])
    monkeypatch.setattr(db, "comparable_rents", lambda z, b, days=90: calls.append(1) or [2000.0] * 6)
    client.get("/listings")
    assert len(calls) == 1


def test_listings_db_down_is_empty():
    j = client.get("/listings").json()
    assert j["items"] == [] and j["total"] == 0


def test_detail(monkeypatch):
    patch_listings(monkeypatch, [row()])
    monkeypatch.setattr(db, "series", lambda z, m: [
        {"month": date(2026, 10, 1), "value": Decimal("2600"), "lo80": None, "hi80": None, "kind": "actual",
         "run_id": None, "backtest_mape": None},
        {"month": date(2027, 10, 1), "value": Decimal("2700"), "lo80": Decimal("2500"), "hi80": Decimal("2900"),
         "kind": "forecast", "run_id": RUN, "backtest_mape": Decimal("3.1")}])
    monkeypatch.setattr(db, "forecast_run_metrics", lambda r: {"by_series": {"92104:zori": {"naive_mape": 2.4}}})
    j = client.get("/listings/101").json()
    ListingDetail.model_validate(j)
    assert [o["event"] for o in j["observations"]] == ["history", "history", "price_change", "seen"]
    assert j["estimate"]["method"] == "zip_bed_median" and j["n_comparables"] == 6
    assert j["year_built"] == 1980 and j["percentile"] is not None
    f = j["forecast"]
    assert f["change_pct"] == 3.85 and f["beats_naive"] is False and f["naive_mape"] == 2.4


def test_detail_not_enough_comps_and_404(monkeypatch):
    patch_listings(monkeypatch, [row()], comps=(2000.0,))
    j = client.get("/listings/101").json()
    assert j["estimate"] is None and j["n_comparables"] == 1 and j["forecast"]["zip"] == "92104"
    patch_listings(monkeypatch, [])
    assert client.get("/listings/999").status_code == 404


def patch_market(monkeypatch):
    zori = [{"month": date(2026, m, 1), "value": Decimal(2500 + m * 10)} for m in range(1, 11)]
    monkeypatch.setattr(db, "zori_monthly", lambda z: zori)
    monkeypatch.setattr(db, "listing_monthly_medians", lambda z, b, t, *a: [
        {"month": date(2026, 8, 1), "value": Decimal("2590"), "n": 12},
        {"month": date(2026, 9, 1), "value": Decimal("2605"), "n": 3},
        {"month": date(2026, 11, 1), "value": Decimal("2650"), "n": 9}])
    monkeypatch.setattr(db, "forecast_latest", lambda z: [
        {"month": date(2026, 11, 1), "value": Decimal("2618"), "lo80": Decimal("2500"), "hi80": Decimal("2740"),
         "backtest_mape": Decimal("3.1"), "run_id": RUN}])
    monkeypatch.setattr(db, "forecast_run_metrics", lambda r: {"by_series": {"92104:zori": {"naive_mape": 2.4}}})
    monkeypatch.setattr(db, "active_by_source", lambda z, b, t: [
        {"kind": "listing_site", "source_key": "zillow_rent", "unit_type": None, "unusual": False, "cur": 2600,
         "w": 1.0}] * 136)
    monkeypatch.setattr(db, "last_scrape_at", lambda: T(2026, 11, 14))


def test_market_zori_only(monkeypatch):
    patch_market(monkeypatch)
    j = client.get("/market?zip=92104&range=3m").json()
    MarketResponse.model_validate(j)
    assert {p["basis"] for p in j["points"]} == {"zori"}
    assert [p["month"] for p in j["points"]] == ["2026-07-01", "2026-08-01", "2026-09-01", "2026-10-01"]
    assert j["current_value"] == 2600.0 and j["change_since"] == "2026-07-01" and j["change_pct"] == 1.17
    assert j["forecast"][0]["lo80"] == 2500.0 and j["beats_naive"] is False and j["active_listings"] == 136


def test_market_beds_fallback(monkeypatch):
    patch_market(monkeypatch)
    j = client.get("/market?zip=92104&beds=1&range=all").json()
    by = {p["month"]: p for p in j["points"]}
    assert by["2026-08-01"]["basis"] == "listings" and by["2026-08-01"]["n_listings"] == 12
    assert by["2026-09-01"]["basis"] == "zori" and by["2026-09-01"]["value"] == 2590.0
    assert by["2026-11-01"]["basis"] == "listings"          # newer than ZORI's last month
    assert "2026-12-01" not in by and j["notes"] and "ZORI" in j["notes"][0]


def test_market_validation_and_db_down():
    assert client.get("/market?zip=99999").status_code == 404
    assert client.get("/market?range=2y").status_code == 422
    j = client.get("/market").json()
    assert j["points"] == [] and j["current_value"] is None and j["forecast"] == []


def test_pretty_address():
    assert tracker.pretty_address("1234 W 5TH ST") == "1234 W 5th St"
    assert tracker.pretty_address(None) is None
