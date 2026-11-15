"""Penal Code 396 rent-gouging check. Uses injected data so the tests don't depend on the live declarations."""
from datetime import date
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from api.rules import gouging

REAL_EMERGENCIES, REAL_FMR, REAL_ZIPS = gouging.load_emergencies, gouging.load_fmr, gouging.load_zip_county

EMERG = [{
    "id": "test-storm", "title": "Test storm", "counties": ["San Diego"], "declared_on": date(2026, 10, 15),
    "protections_until": date(2026, 11, 14), "extensions": [], "rental_covered": True,
    "source_url": "https://www.gov.ca.gov/", "verified": True,
}]
EXTENDED = [{**EMERG[0], "protections_until": date(2026, 12, 14), "extensions": [date(2026, 12, 14)]}]
FMR = {
    "county_fmr": {"San Diego": {"fy": 2026, "source": "HUD FMR FY2026 (test)", "verified": True,
                                 "rents": {0: D("2000"), 1: D("2500"), 2: D("3000"), 3: D("4000"), 4: D("4800")}}},
    "safmr": {"92104": {"fy": 2026, "source": "HUD SAFMR FY2026 (test)", "verified": True,
                        "rents": {0: D("1900"), 1: D("2600"), 2: D("3100"), 3: D("4100"), 4: D("4900")}}},
}
ZIPS = {"92104": "San Diego", "92011": "San Diego", "90026": "Los Angeles"}
IN = date(2026, 10, 20)


@pytest.fixture(autouse=True)
def data(monkeypatch):
    monkeypatch.setattr(gouging, "load_emergencies", lambda: EMERG)
    monkeypatch.setattr(gouging, "load_fmr", lambda: FMR)
    monkeypatch.setattr(gouging, "load_zip_county", lambda: ZIPS)


def chk(new, d=IN, **kw):
    kw.setdefault("zip_", "92104")
    kw.setdefault("pre_emergency_rent", D("2000"))
    return gouging.check_gouging(D(str(new)), d, **kw)


def test_inside_window_over_limit():
    r = chk("2300")
    assert r["verdict"] == "likely_violation" and r["county"] == "San Diego"
    assert r["basis"] == "pre_emergency_plus_10" and r["limit_usd"] == D("2200.00")
    assert r["increase_pct"] == D("15.00") and r["emergency"]["title"] == "Test storm"
    assert r["reasons"]


def test_exactly_ten_percent_allowed():
    assert chk("2200.00")["verdict"] == "within_limit"


def test_one_cent_over_is_violation():
    assert chk("2200.01")["verdict"] == "likely_violation"


def test_limit_rounds_down_to_cent():
    r = chk("2000", pre_emergency_rent=D("1999.99"))
    assert r["limit_usd"] == D("2199.98")  # 2199.989 rounded down
    assert chk("2199.99", pre_emergency_rent=D("1999.99"))["verdict"] == "likely_violation"


def test_increase_pct_rounds_down():
    assert chk("2100.99")["increase_pct"] == D("5.04")


def test_before_declaration_not_covered():
    r = chk("2600", d=date(2026, 10, 14))
    assert r["verdict"] == "not_covered" and r["emergency"] is None and r["reasons"]


def test_window_end_inclusive_and_after_not_covered():
    assert chk("2600", d=date(2026, 11, 14))["verdict"] == "likely_violation"
    assert chk("2600", d=date(2026, 11, 15))["verdict"] == "not_covered"


def test_extension_keeps_protection(monkeypatch):
    monkeypatch.setattr(gouging, "load_emergencies", lambda: EXTENDED)
    r = chk("2600", d=date(2026, 12, 1))
    assert r["verdict"] == "likely_violation" and r["emergency"]["extensions"] == [date(2026, 12, 14)]
    assert r["emergency"]["protections_until"] == date(2026, 12, 14)


def test_county_without_declaration():
    r = chk("2600", zip_="90026")
    assert r["verdict"] == "not_covered" and r["county"] == "Los Angeles"


def test_county_given_directly():
    r = chk("2600", zip_=None, county="san diego")
    assert r["county"] == "San Diego" and r["verdict"] == "likely_violation"


def test_unknown_county_unclear():
    assert chk("2600", zip_="99999")["verdict"] == "unclear"
    assert chk("2600", zip_=None)["verdict"] == "unclear"


def test_emergency_not_covering_rent_is_not_covered(monkeypatch):
    monkeypatch.setattr(gouging, "load_emergencies", lambda: [{**EMERG[0], "rental_covered": False}])
    assert chk("2600")["verdict"] == "not_covered"


def test_fmr_160_uses_zip_safmr(monkeypatch):
    monkeypatch.setattr(gouging, "FMR_RULE_VERIFIED", True)
    r = chk("4160.00", pre_emergency_rent=None, beds=1)  # 160% of 2600
    assert r["verdict"] == "within_limit" and r["basis"] == "fmr_160"
    assert r["limit_usd"] == D("4160.00") and r["fmr_usd"] == D("2600")
    assert "SAFMR" in r["fmr_source"]
    assert chk("4160.01", pre_emergency_rent=None, beds=1)["verdict"] == "likely_violation"


def test_fmr_160_falls_back_to_county_fmr(monkeypatch):
    monkeypatch.setattr(gouging, "FMR_RULE_VERIFIED", True)
    r = chk("4000.01", zip_="92011", pre_emergency_rent=None, beds=1)  # county 2500 * 1.6 = 4000
    assert r["verdict"] == "likely_violation" and r["limit_usd"] == D("4000.00")
    assert r["fmr_usd"] == D("2500")


def test_unverified_rule_or_data_answers_unclear_and_says_so(monkeypatch):
    r = chk("4160.01", pre_emergency_rent=None, beds=1)            # statute's 160% rule not verified yet
    assert r["verdict"] == "unclear" and r["limit_usd"] == D("4160.00")
    assert any("160%" in u for u in r["unverified"]) and "not verified" in r["reasons"][-1]
    monkeypatch.setattr(gouging, "load_emergencies", lambda: [{**EMERG[0], "verified": False}])
    r = chk("2600")
    assert r["verdict"] == "unclear" and r["unverified"] == ["the emergency declaration"]


def test_fmr_needs_beds():
    assert chk("4000", pre_emergency_rent=None, beds=None)["verdict"] == "unclear"
    assert chk("4000", pre_emergency_rent=None, beds=9)["verdict"] == "unclear"


def test_unverified_fmr_is_unclear(monkeypatch):
    bad = {"county_fmr": {"San Diego": {**FMR["county_fmr"]["San Diego"], "verified": False}}, "safmr": {}}
    monkeypatch.setattr(gouging, "load_fmr", lambda: bad)
    r = chk("9000", zip_="92011", pre_emergency_rent=None, beds=1)
    assert r["verdict"] == "unclear" and r["fmr_usd"] == D("2500")


def test_result_keys_match_contract():
    from contracts.api_models import GougingResponse
    GougingResponse(**chk("2300"))


def test_router_end_to_end():
    from api.main import app
    body = {"zip": "92104", "new_rent": 2300, "offer_date": "2026-10-20", "pre_emergency_rent": 2000}
    j = TestClient(app).post("/checks/gouging", json=body).json()
    assert j["verdict"] == "likely_violation" and "not legal advice" in j["disclaimer"].lower()
    assert "https://www.lassd.org/" in {x["url"] for x in j["links"]}


def test_real_data_files_are_sourced():
    em = REAL_EMERGENCIES()
    assert em and all(e["source_url"].startswith("https://") and e.get("accessed") for e in em)
    assert REAL_ZIPS()["92104"] == "San Diego"
    fmr = REAL_FMR()
    assert "San Diego" in fmr["county_fmr"] and fmr["county_fmr"]["San Diego"]["source_url"].startswith("https://")
