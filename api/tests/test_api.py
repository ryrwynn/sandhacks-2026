"""Endpoint tests. The DB and the engine are monkeypatched; no test calls Gemini or a database."""
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from api import db
from api.llm import gemini
from api.main import app
from api.ml import fair_rent, listing_analysis, scoring
from api.routers import checks as checks_router
from api.routers import _common
from api.rules import ab1482

F = Path(__file__).resolve().parents[2] / "contracts" / "fixtures"
client = TestClient(app)


def fx(name: str):
    return json.loads((F / name).read_text())


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(_common, "_model_cache", {"loaded": True, "models": None})
    checks_router._recent.clear()
    # Any Gemini call in a test is a bug unless the test patches it.
    for name in ("explain_verdict", "draft_letter", "zip_summary", "explain_gaps", "parse_listing"):
        monkeypatch.setattr(gemini, name, lambda *a, **k: None)


def test_openapi_lists_every_endpoint():
    paths = client.get("/openapi.json").json()["paths"]
    for p in ("/health", "/zips", "/zips/{zip}", "/zips/{zip}/series", "/checks", "/checks/{check_id}/letter",
              "/units/search", "/listings/evaluate", "/neighborhoods/rank", "/owner/price-position",
              "/owner/listing-analysis"):
        assert p in paths, p
    assert app.root_path == "/api"


def test_health_degraded_when_db_down():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "degraded" and r.json()["database"] is False


def test_health_ok(monkeypatch):
    f = fx("health.json")
    monkeypatch.setattr(db, "ping", lambda: True)
    monkeypatch.setattr(db, "health_info", lambda: {k: f[k] for k in ("row_counts", "last_scrape_at", "model_runs")})
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok" and r.json()["row_counts"]["listings"] == 1840


def test_zips_without_data_returns_names_and_nulls():
    r = client.get("/zips")
    assert r.status_code == 200
    zs = r.json()["zips"]
    assert len(zs) == 12 and zs[0]["typical_rent_usd"] is None and zs[0]["listings_30d"] == 0


def _zip_db(monkeypatch):
    monkeypatch.setattr(db, "latest_index_values", lambda: {("92104", "zori"): 2000.0, ("92104", "zhvi"): 800000.0})
    monkeypatch.setattr(db, "forecast_end_values", lambda: {("92104", "zori"): 2100.0, ("92104", "zhvi"): 840000.0})
    monkeypatch.setattr(db, "median_rent_by_beds", lambda days=30: {"92104": {1: (1800, 4), 2: (2500, 6)}})
    monkeypatch.setattr(db, "zip_features", lambda: {"92104": {"median_income_usd": 90000.0, "groceries": 12.0,
                                                                 "transit_stops": 40.0, "area_km2": 6.5}})
    monkeypatch.setattr(db, "zhvi_volatility", lambda: {"92104": 0.8})


def test_zips_and_profile(monkeypatch):
    _zip_db(monkeypatch)
    z = next(x for x in client.get("/zips").json()["zips"] if x["zip"] == "92104")
    assert z["median_rent_by_beds"] == {"0": None, "1": 1800, "2": 2500, "3": None}
    assert z["rent_forecast_change_pct"] == 5.0 and z["value_forecast_change_pct"] == 5.0
    assert z["listings_30d"] == 10 and z["name"] == "North Park"
    monkeypatch.setattr(scoring, "score_zips", lambda rows, persona, budget, weights=None: {
        "weights": {}, "stretch": [], "ranked": [{"zip": "92104", "score": 71.26, "price_usd": 2000.0,
                                                    "top_contributions": []}]})
    p = client.get("/zips/92104").json()
    assert p["persona_scores"] == {"starter": 71.3, "wealth": 71.3}
    assert p["gross_yield_pct"] == 3.0 and p["rent_burden_pct"] == 26.7
    assert p["amenities"]["groceries"] == 12
    assert client.get("/zips/99999").status_code == 404


def _not_implemented(*a, **k):
    raise NotImplementedError


def test_profile_without_scoring_engine(monkeypatch):
    _zip_db(monkeypatch)
    monkeypatch.setattr(scoring, "score_zips", _not_implemented)
    p = client.get("/zips/92104").json()
    assert p["persona_scores"] == {"starter": None, "wealth": None}


def test_series(monkeypatch):
    run = "6f1f8a52-3c3e-4d4c-9a51-0b9a4b6f2a10"
    monkeypatch.setattr(db, "series", lambda z, m: [
        {"month": date(2026, 10, 1), "value": Decimal("2000"), "lo80": None, "hi80": None, "kind": "actual",
         "run_id": None, "backtest_mape": None},
        {"month": date(2026, 11, 1), "value": Decimal("2010"), "lo80": Decimal("1950"), "hi80": Decimal("2070"),
         "kind": "forecast", "run_id": UUID(run), "backtest_mape": Decimal("2.1")}])
    monkeypatch.setattr(db, "forecast_run_metrics", lambda r: {"naive_mape": 3.0})
    j = client.get("/zips/92104/series?metric=zori").json()
    assert [p["kind"] for p in j["points"]] == ["actual", "forecast"]
    assert j["run_id"] == run and j["backtest_mape"] == 2.1 and j["beats_naive"] is True
    assert client.get("/zips/92104/series?metric=bogus").status_code == 422


def test_demo_check_max_legal_rent(monkeypatch):
    seen = {}

    def fake_check(inp, caps):
        seen["caps"] = caps
        assert inp.lowest_rent_12mo == Decimal("2100.0") and inp.new_rent == Decimal("2350.0")
        return ab1482.CheckResult(
            verdict="over_cap", cap_pct=Decimal("8.20"), max_legal_rent=Decimal("2272.20"),
            overage_monthly=Decimal("77.80"), overage_yearly=Decimal("933.60"), increase_pct=Decimal("11.9"),
            reasons=["Over the 8.2% cap."], figures=["$2,272.20", "8.2%"])

    inserted = {}

    def fake_insert(*a):
        inserted["args"] = a
        return UUID("11111111-1111-1111-1111-111111111111")

    monkeypatch.setattr(ab1482, "check_increase", fake_check)
    monkeypatch.setattr(db, "insert_check", fake_insert)
    monkeypatch.setattr(checks_router, "load_caps", lambda: [ab1482.RentCap(
        "san_diego_county", date(2026, 8, 1), date(2027, 7, 31), Decimal("8.20"), "x")])
    r = client.post("/checks", json=fx("requests/checks.json"))
    assert r.status_code == 200
    j = r.json()
    assert j["max_legal_rent"] == 2272.2 and "2272.2" in r.text
    assert j["verdict"] == "over_cap" and j["overage_monthly"] == 77.8 and j["overage_yearly"] == 933.6
    assert j["increase_pct"] == 11.9 and j["check_id"] == "11111111-1111-1111-1111-111111111111"
    assert inserted["args"][-1] is True            # is_demo carried through
    assert seen["caps"][0].cap_pct == Decimal("8.20")


def test_check_503_when_engine_missing(monkeypatch):
    monkeypatch.setattr(ab1482, "check_increase", _not_implemented)
    r = client.post("/checks", json=fx("requests/checks.json"))
    assert r.status_code == 503 and "not available" in r.json()["detail"]


def test_check_survives_db_down(monkeypatch):
    monkeypatch.setattr(ab1482, "check_increase", lambda inp, caps: ab1482.CheckResult(
        verdict="within_cap", cap_pct=Decimal("8.2"), max_legal_rent=Decimal("2272.20"), overage_monthly=None,
        reasons=[]))
    r = client.post("/checks", json=fx("requests/checks.json"))
    assert r.status_code == 200 and r.json()["increase_pct"] == 11.9
    UUID(r.json()["check_id"])


def test_letter(monkeypatch):
    monkeypatch.setattr(ab1482, "check_increase", lambda inp, caps: ab1482.CheckResult(
        verdict="over_cap", cap_pct=Decimal("8.2"), max_legal_rent=Decimal("2272.20"),
        overage_monthly=Decimal("77.80"), reasons=["r"]))
    cid = client.post("/checks", json=fx("requests/checks.json")).json()["check_id"]
    calls = []
    monkeypatch.setattr(gemini, "explain_verdict", lambda c, lang: calls.append(lang) or "Explicacion")
    monkeypatch.setattr(gemini, "draft_letter", lambda c, addr: "Dear [Landlord name]")
    j = client.post(f"/checks/{cid}/letter?lang=es").json()
    assert j["lang"] == "es" and j["explanation"] == "Explicacion" and j["letter_en"].startswith("Dear")
    assert "$2,272.20" in j["figures"] and calls == ["es"]
    assert client.post(f"/checks/{cid}/letter?lang=xx").status_code == 422
    assert client.post("/checks/22222222-2222-2222-2222-222222222222/letter").status_code == 404


def test_letter_text_null_when_gemini_gives_nothing(monkeypatch):
    monkeypatch.setattr(ab1482, "check_increase", lambda inp, caps: ab1482.CheckResult(
        verdict="within_cap", cap_pct=None, max_legal_rent=None, overage_monthly=None, reasons=[]))
    cid = client.post("/checks", json=fx("requests/checks.json")).json()["check_id"]
    j = client.post(f"/checks/{cid}/letter").json()
    assert j["explanation"] is None and j["letter_en"] is None


def test_units_search(monkeypatch):
    monkeypatch.setattr(db, "search_units", lambda q, limit=10: [
        {"property_id": 1, "address_norm": "4200 FAIRMOUNT AVE", "unit_label": None, "zip": "92105", "beds": 2,
         "year_built": 1978, "property_type": "apartment"}])
    j = client.get("/units/search?address=4200 fairmount").json()
    assert j["results"][0]["year_built"] == 1978
    assert client.get("/units/search").status_code == 422
    monkeypatch.setattr(db, "search_units", lambda q, limit=10: (_ for _ in ()).throw(db.DBUnavailable("down")))
    assert client.get("/units/search?address=abc").json()["results"] == []


COMPS = [2200.0, 2300.0, 2400.0, 2500.0, 2600.0, 2700.0, 2800.0, 3000.0]


def test_listing_evaluate_median_fallback(monkeypatch):
    monkeypatch.setattr(db, "comparable_rents", lambda z, b, days=90: COMPS)
    j = client.post("/listings/evaluate", json=fx("requests/listings_evaluate.json")).json()
    assert j["estimate"]["method"] == "zip_bed_median" and j["n_comparables"] == 8
    assert j["estimate"]["expected"] == 2550.0 and j["label"] == "in_range"
    assert j["percentile"] == 75.0


def test_listing_evaluate_uses_model_and_parses_text(monkeypatch):
    monkeypatch.setattr(_common, "_model_cache", {"loaded": True, "models": {"m": 1}})
    monkeypatch.setattr(db, "comparable_rents", lambda z, b, days=90: COMPS)
    monkeypatch.setattr(db, "fair_rent_metrics", lambda: {"mae_usd": 212.0, "coverage_80": 0.79})
    monkeypatch.setattr(fair_rent, "predict", lambda m, row: {"low": 2000.0, "expected": 2400.0, "high": 2800.0})
    monkeypatch.setattr(fair_rent, "label", lambda a, e: "above_typical_range")
    monkeypatch.setattr(gemini, "parse_listing", lambda t: gemini.ListingFields(sqft=900, beds=2))
    body = {**fx("requests/listings_evaluate.json"), "sqft": None, "text": "2 bed 900 sqft"}
    j = client.post("/listings/evaluate", json=body).json()
    assert j["estimate"]["method"] == "model" and j["estimate"]["mae_usd"] == 212.0
    assert j["label"] == "above_typical_range" and j["parsed_fields"] == {"beds": 2, "sqft": 900}


def test_listing_evaluate_503_without_data():
    r = client.post("/listings/evaluate", json=fx("requests/listings_evaluate.json"))
    assert r.status_code == 503


@pytest.mark.parametrize("persona", ["starter", "wealth"])
def test_rank_summaries_for_top_three_only(monkeypatch, persona):
    fixture = fx(f"neighborhoods_rank_{persona}.json")
    pool = [dict(r, top_contributions=r["top_contributions"]) for r in fixture["ranked"]]
    while len(pool) < 5:
        pool.append({**pool[0], "zip": f"9210{len(pool)}", "score": 40.0 - len(pool)})
    monkeypatch.setattr(scoring, "score_zips", lambda rows, p, b, w=None: {
        "weights": fixture["weights"], "ranked": pool, "stretch": fixture["stretch"]})
    asked = []
    monkeypatch.setattr(gemini, "zip_summary", lambda name, p, c: asked.append(name) or f"{name} is good")
    r = client.post("/neighborhoods/rank", json=fx(f"requests/neighborhoods_rank_{persona}.json"))
    assert r.status_code == 200
    j = r.json()
    assert len(asked) == 3 and sum(1 for x in j["ranked"] if x["summary"]) == 3
    assert [x["rank"] for x in j["ranked"]] == list(range(1, len(j["ranked"]) + 1))
    assert all(x["summary"] is None for x in j["stretch"]) and j["weights"] == fixture["weights"]


def test_rank_503_without_scoring_engine(monkeypatch):
    monkeypatch.setattr(scoring, "score_zips", _not_implemented)
    r = client.post("/neighborhoods/rank", json=fx("requests/neighborhoods_rank_starter.json"))
    assert r.status_code == 503


def test_owner_price_position_with_legal(monkeypatch):
    monkeypatch.setattr(db, "comparable_rents", lambda z, b, days=90: COMPS)
    monkeypatch.setattr(db, "days_on_market", lambda z, b: [(2300.0, 10.0), (2400.0, 14.0), (2500.0, 20.0),
                                                              (2700.0, 30.0), (2800.0, 40.0), (3000.0, 50.0)])
    monkeypatch.setattr(ab1482, "check_increase", lambda inp, caps: ab1482.CheckResult(
        verdict="over_cap", cap_pct=Decimal("8.2"), max_legal_rent=Decimal("2488.60"), overage_monthly=Decimal("111.4"),
        reasons=["over"]))
    j = client.post("/owner/price-position", json=fx("requests/owner_price_position.json")).json()
    assert [p["label"] for p in j["points"]] == ["low", "expected", "high", "target"]
    assert j["legal"]["max_legal_rent"] == 2488.6 and j["days_on_market"]["n_listings"] == 6
    assert j["days_on_market"]["below_expected_median_days"] == 14.0


def test_owner_price_position_unoccupied_no_legal(monkeypatch):
    monkeypatch.setattr(db, "comparable_rents", lambda z, b, days=90: COMPS)
    body = {**fx("requests/owner_price_position.json"), "occupied": False}
    j = client.post("/owner/price-position", json=body).json()
    assert j["legal"] is None and j["days_on_market"] is None


def test_owner_listing_analysis(monkeypatch):
    monkeypatch.setattr(db, "comparable_texts", lambda z, b, limit=200: ["a", "b"])
    monkeypatch.setattr(db, "comparable_rents", lambda z, b, days=90: COMPS)
    monkeypatch.setattr(listing_analysis, "analyze_listing", lambda t, c, p=None: {
        "completeness": 55.0, "readability": 80.0, "reach_score": 48.0, "stated": {"pets": False},
        "gaps": [{"fact": "pets", "share_of_comparables": 0.7}]})
    monkeypatch.setattr(gemini, "explain_gaps", lambda t, g: "Most comparables mention pets.")
    j = client.post("/owner/listing-analysis", json=fx("requests/owner_listing_analysis.json")).json()
    assert j["gaps"][0]["fact"] == "pets" and j["explanation"].startswith("Most") and j["n_comparables"] == 2
    r = client.post("/owner/listing-analysis", json={"zip": "92104", "beds": 2})
    assert r.status_code == 422
