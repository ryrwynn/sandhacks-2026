"""The live API answers for data/zips.txt ZIPs only: every market, listing, median, comparable and feature query in
api/db.py filters to that list, so rows for other areas can't leak into the live site (final run, 2026-11-15)."""
import pytest

from api import db

CORE = sorted(db.ZIP_NAMES)
OUTSIDE = "92037"            # La Jolla: staged by the county sample, not one of the 12


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
    return any(v == CORE for v in vals)


def test_core_list_is_the_twelve_zips():
    assert len(db.CORE_ZIPS) == 12 and db.CORE_ZIPS == CORE and OUTSIDE not in CORE


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
def test_every_live_query_filters_to_core_zips(calls, call):
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
def test_zip_outside_the_list_gets_nothing_without_a_query(calls, call):
    assert call() == []
    assert calls == []


def test_comparables_drop_rows_outside_core_from_the_bulk_cache(monkeypatch):
    rows = [{"zip": "92104", "beds": 1, "price_usd": 2400}, {"zip": OUTSIDE, "beds": 1, "price_usd": 9000}]
    monkeypatch.setattr(db, "fetch", lambda sql, params=None: rows if "ANY(" in sql else [])
    db._comp_cache.update(at=0.0, groups={})
    assert db.comparable_rents("92104", 1) == [2400.0]
    assert db.comparable_rents(OUTSIDE, 1) == []
