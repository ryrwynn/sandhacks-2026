"""Sprint A1/A2: served-area set (areas.tier + active listings), staging flag, fallback, GET /zips."""
import time

import pytest
from fastapi.testclient import TestClient

from api import db
from api.main import app


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setitem(db._version, "checked", time.monotonic())   # no data_version query in these tests
    db._served_cache.update(at=0.0, areas={})
    yield
    db._served_cache.update(at=0.0, areas={})


def _rows():
    return [
        {"zip": "92104", "name": "North Park", "county": "San Diego", "tier": "core", "lat": 32.7, "lng": -117.1, "listings": 40},
        {"zip": "92037", "name": "La Jolla", "county": "San Diego", "tier": "county", "lat": 32.8, "lng": -117.2, "listings": 12},
        {"zip": "91901", "name": "Alpine", "county": "San Diego", "tier": "on_demand", "lat": 32.8, "lng": -116.7, "listings": 6},
        {"zip": "92101", "name": "Downtown", "county": "San Diego", "tier": "core", "lat": 32.7, "lng": -117.1, "listings": 30},
    ]


def test_served_set_comes_from_one_query_ordered_by_tier(monkeypatch):
    calls = []
    monkeypatch.setattr(db, "fetch", lambda sql, params=None: calls.append((sql, params)) or _rows())
    a = db.served_areas()
    assert list(a) == ["92101", "92104", "92037", "91901"]          # core by name, then county, then on_demand
    assert a["92037"]["county"] == "San Diego" and a["92104"]["lat"] == 32.7
    db.served_areas()
    list(db.ZIP_NAMES)
    assert "92104" in db.ZIP_NAMES
    assert len(calls) == 1                                            # cached
    sql, params = calls[0]
    assert "areas a" in sql and "staging_listings" not in sql        # shared tables only by default
    assert params["tiers"] == ["core", "county", "on_demand"] and params["min"] == 5


def test_staging_flag_counts_staged_listings_only_when_set(monkeypatch):
    monkeypatch.setenv("RENTORKNOT_READ_STAGING", "1")
    assert "staging_listings" in db._served_sql()
    monkeypatch.delenv("RENTORKNOT_READ_STAGING")
    assert "staging_listings" not in db._served_sql()


def test_falls_back_to_zips_txt_when_the_query_fails_or_is_empty(monkeypatch):
    def boom(sql, params=None):
        raise db.DBUnavailable("down")
    monkeypatch.setattr(db, "fetch", boom)
    a = db.served_areas()
    assert set(a) == set(db.load_zip_names()) and len(a) == 12 and all(v["tier"] == "core" for v in a.values())
    db._served_cache.update(at=0.0, areas={})
    monkeypatch.setattr(db, "fetch", lambda sql, params=None: [])
    assert len(db.served_areas()) == 12


def test_zips_endpoint_lists_served_areas_with_tier_and_county(monkeypatch):
    monkeypatch.setattr(db, "fetch", lambda sql, params=None: _rows() if "areas a" in sql else [{"t": None}] if sql.startswith("SELECT max(last_seen)") else [])
    c = TestClient(app)
    zs = c.get("/zips").json()["zips"]
    assert [z["zip"] for z in zs] == ["92101", "92104", "92037", "91901"]
    assert [z["tier"] for z in zs] == ["core", "core", "county", "on_demand"] and zs[2]["county"] == "San Diego"
    assert c.get("/zips/92037").status_code == 200 and c.get("/zips/91901").status_code == 200
    r = c.get("/zips/95014")
    assert r.status_code == 404 and "12" not in r.json()["detail"]
    assert c.get("/market?zip=92037").status_code == 200
    assert c.get("/market?zip=95014").status_code == 404


_STAGING_CALLS = [
    lambda: db.listing_page(),
    lambda: db.median_rent_by_beds(),
    lambda: db.comparable_rents("92104", 1),
    lambda: db.comparable_rents("92104", 1, days=30),
    lambda: db.source_counts(),
    lambda: db.active_rent_count(),
    lambda: db.active_by_source(),
    lambda: db.listing_monthly_medians(None, None, None),
    lambda: db.served_areas(),
]


@pytest.mark.parametrize("flag", [False, True])
def test_staged_rows_of_any_source_only_with_the_local_flag(monkeypatch, flag):
    if flag:
        monkeypatch.setenv("RENTORKNOT_READ_STAGING", "1")
    else:
        monkeypatch.delenv("RENTORKNOT_READ_STAGING", raising=False)
    seen = []
    monkeypatch.setattr(db, "fetch", lambda sql, params=None: seen.append(" ".join(sql.split())) or ([{"n": 0}] if "count(*) AS n" in sql else []))
    for call in _STAGING_CALLS:
        db._comp_cache.update(at=0.0, groups={})
        db._served_cache.update(at=0.0, areas={})
        db._served_cache["areas"] = {}
        call()
    assert seen
    for sql in seen:
        assert ("staging_" in sql) == flag, sql
        assert "source_key = 'facebook_groups_sd')" not in sql      # staged rows aren't limited to Facebook


def test_scenario_series_without_scenario_rows_returns_history(monkeypatch):
    """Sprint: a served ZIP with history but no scenario run yet gets history only, not a 404."""
    from datetime import date

    from api.routers import forecasts

    monkeypatch.setattr(forecasts.db, "fetch", lambda sql, args=(): [])
    monkeypatch.setattr(forecasts.db, "series", lambda z, m: [
        {"month": date(2026, 9, 1), "value": 3000.0, "kind": "actual"},
        {"month": date(2026, 10, 1), "value": 3010.0, "kind": "actual"},
        {"month": date(2026, 11, 1), "value": 3020.0, "kind": "forecast"}])
    r = forecasts.scenario_series("92037", "zori", "baseline")
    assert [p.kind for p in r.points] == ["actual", "actual"] and r.scenarios == [] and r.scenario == "baseline"
