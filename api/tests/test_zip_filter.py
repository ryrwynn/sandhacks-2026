"""The API answers for the served-area set only: every market, listing, median, comparable and feature query in
api/db.py filters to it (areas.tier core/county/on_demand with enough active listings), so staged-only or
index-only ZIPs can't leak into the live site. Sprint A1."""
import time

import pytest

from api import db

CORE = ["92104", "92122", "92037"]
OUTSIDE = "95014"            # Cupertino: an index-only or staged-only ZIP, never served


@pytest.fixture(autouse=True)
def served(monkeypatch):
    areas = {z: {"zip": z, "name": z, "county": "San Diego", "tier": "core", "lat": None, "lng": None,
                 "listings": 9} for z in CORE}
    monkeypatch.setitem(db._served_cache, "areas", areas)
    monkeypatch.setitem(db._served_cache, "at", time.monotonic())
    monkeypatch.setitem(db._served_cache, "ttl", 300)
    monkeypatch.setitem(db._version, "checked", time.monotonic())


@pytest.fixture
def calls(monkeypatch):
    seen: list[tuple[str, object]] = []

    def fake_fetch(sql, params=None):
        seen.append((" ".join(sql.split()), params))
        return [{"n": 0}] if "count(*) AS n" in sql else []
    monkeypatch.setattr(db, "fetch", fake_fetch)
    db._comp_cache.update(at=0.0, groups={})
    return seen


def _has_core(params) -> bool:
    vals = params.values() if isinstance(params, dict) else (params or ())
    return any(v == sorted(CORE) for v in vals)


def test_queries_use_the_served_set_not_a_fixed_list():
    assert db.served_zips() == sorted(CORE) and OUTSIDE not in db.ZIP_NAMES


@pytest.mark.parametrize("call", [
    lambda: db.zip_features(),
    lambda: db.latest_index_values(),
    lambda: db.forecast_end_values(),
    lambda: db.zhvi_volatility(),
    lambda: db.median_rent_by_beds(),
    lambda: db.median_rent_by_beds(listing_sites_only=True),
    lambda: db.comparable_rents("92104", 1),
    lambda: db.listing_page(),
    lambda: db.listing_page(ids=[1]),
    lambda: db.listing_page(zip_="92104", source="facebook", unit_type="room"),
    lambda: db.active_rent_count(),
    lambda: db.active_by_source(),
    lambda: db.listing_monthly_medians(None, 2, None),
    lambda: db.zori_monthly(None),
    lambda: db.forecast_latest(None),
    lambda: db.source_counts(),
    lambda: db.search_units("main st"),
], ids=["zip_features", "index", "forecast_end", "volatility", "medians", "medians_sites", "comparables",
        "listing_page", "listing_by_id", "listing_filtered", "active_count", "active_by_source", "monthly_medians",
        "zori_mean", "forecast_mean", "source_counts", "search_units"])
def test_every_live_query_filters_to_served_zips(calls, call):
    call()
    assert calls, "expected a query"
    for sql, params in calls:
        assert "ANY(" in sql and _has_core(params), sql


@pytest.mark.parametrize("call", [
    lambda: db.comparable_rents(OUTSIDE, 1),
    lambda: db.comparable_rents(OUTSIDE, 1, days=30),
    lambda: db.comparable_texts(OUTSIDE, 1),
    lambda: db.days_on_market(OUTSIDE, 1),
    lambda: db.series(OUTSIDE, "zori"),
])
def test_zip_outside_the_served_set_gets_nothing_without_a_query(calls, call):
    assert call() == []
    assert calls == []


def test_comparables_drop_rows_outside_the_served_set_from_the_bulk_cache(monkeypatch):
    rows = [{"zip": "92104", "beds": 1, "price_usd": 2400}, {"zip": OUTSIDE, "beds": 1, "price_usd": 9000}]
    monkeypatch.setattr(db, "fetch", lambda sql, params=None: rows if "ANY(" in sql else [])
    db._comp_cache.update(at=0.0, groups={})
    assert db.comparable_rents("92104", 1) == [2400.0]
    assert db.comparable_rents(OUTSIDE, 1) == []
