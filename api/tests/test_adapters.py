"""Golden tests for the source adapters. Gemini is always mocked: no test sends a real request.

Set UPDATE_GOLDEN=1 to rewrite contracts/fixtures/sources/<key>/expected.json after an intended change.
"""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from api.llm.gemini import ListingFields
from contracts.canonical import CanonicalListing
from worker import llm_extract
from worker.adapters import get_adapter
from worker.clean import beds_from, normalize_address, redact_text
from worker.llm_extract import LlmBudget
from worker.mapping import load_template, load_zips
from worker.run import process_listing_payloads
from worker.zip_boundaries import area_km2, contains

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "contracts" / "fixtures" / "sources"
NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
LISTING_SOURCES = ["zillow_rent", "zillow_sale", "apartments_com", "facebook_groups"]
ALL_SOURCES = LISTING_SOURCES + ["zillow_research", "census_acs", "osm_amenities"]
PHONE_OR_EMAIL = re.compile(r"\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}|[\w.+-]+@[\w-]+\.\w+")


def fixture_rows(key):
    return [json.loads(p.read_text()) for p in sorted((FIX / key).glob("rec*.json"))]


def leaves(o):
    if isinstance(o, dict):
        for v in o.values():
            yield from leaves(v)
    elif isinstance(o, list):
        for v in o:
            yield from leaves(v)
    elif isinstance(o, str):
        yield o


def all_keys(o):
    if isinstance(o, dict):
        for k, v in o.items():
            yield k
            yield from all_keys(v)
    elif isinstance(o, list):
        for v in o:
            yield from all_keys(v)


@pytest.fixture
def fake_gemini(monkeypatch):
    """Replace parse_listing in the worker; records every text it is asked to read."""
    calls = []

    def fake(text):
        calls.append(text)
        m = re.search(r"built in (\d{4})", text, re.I)
        if "looking for a room" in text.lower():
            return ListingFields(is_rental_offer=False)
        price = re.search(r"\$([\d,]+)", text)
        beds = 0 if "studio" in text.lower() else (2 if "2BR" in text else None)
        zip_ = re.search(r"\b(9\d{4})\b", text)
        return ListingFields(year_built=int(m.group(1)) if m else None, is_rental_offer=True,
                             price_usd=int(price.group(1).replace(",", "")) if price else None, beds=beds,
                             zip=zip_.group(1) if zip_ else None,
                             neighborhood="North Park" if "North Park" in text else None)

    monkeypatch.setattr(llm_extract, "parse_listing", fake)
    return calls


def run_source(key, rows=None, budget=None):
    t = load_template(key)
    adapter = get_adapter(t)
    payloads = [adapter.clean_payload(r) for r in (rows if rows is not None else fixture_rows(key))]
    return t, payloads, process_listing_payloads(t, payloads, NOW, budget or LlmBudget(40))


# ---- templates ----------------------------------------------------------------------------------
def test_every_source_has_a_template_matching_the_seed():
    seed = (ROOT / "db" / "seed_sources.sql").read_text()
    for key in ALL_SOURCES:
        t = load_template(key)
        assert t["source_key"] == key
        m = re.search(rf"'{key}',\s*'(\w+)',\s*'(\w+)',\s*'sources/{key}.yaml',\s*([\d.]+),\s*(true|false)", seed)
        assert m, key
        assert float(m.group(3)) == t["trust_weight"]
    for key in ("apartments_com", "facebook_groups"):
        assert re.search(rf"'{key}'.*false\)", seed)
        assert len(list((FIX / key).glob("rec*.json"))) == 3


def test_worker_never_imports_google_genai():
    for p in (ROOT / "worker").rglob("*.py"):
        assert "google.genai" not in p.read_text() and "from google" not in p.read_text(), p


# ---- golden: every fixture maps to a valid listing with nothing personal left ---------------------------
@pytest.mark.parametrize("key", LISTING_SOURCES)
def test_golden(key, fake_gemini):
    rows = fixture_rows(key)
    assert len(rows) == 3
    t, payloads, (listings, _) = run_source(key, rows)
    assert listings, key
    for l in listings:
        assert isinstance(l, CanonicalListing) and l.source_key == key and l.price_usd > 0
    got = [l.model_dump(mode="json") for l in listings]
    golden = FIX / key / "expected.json"
    if os.environ.get("UPDATE_GOLDEN"):
        golden.write_text(json.dumps(got, indent=1, sort_keys=True) + "\n")
    assert got == json.loads(golden.read_text())


@pytest.mark.parametrize("key", LISTING_SOURCES)
def test_personal_fields_never_stored(key, fake_gemini):
    rows = fixture_rows(key)
    t, payloads, (listings, _) = run_source(key, rows)
    stored = json.dumps(payloads, default=str) + json.dumps([l.model_dump(mode="json") for l in listings])
    drop = set(t["drop_fields"])
    assert drop, "template must name its personal fields"
    for p in payloads:
        assert not drop & set(all_keys(p))
    dropped_values = {v for r in rows for k, val in r.items() if k in drop for v in leaves(val) if len(v) >= 7}
    dropped_values -= {"Leasing Agent"}
    for v in dropped_values:
        assert v not in stored, f"personal value survived: {v}"
    assert not PHONE_OR_EMAIL.search(stored)
    assert "facebook.com/user" not in stored


def test_facebook_keeps_hash_not_post_id_or_url(fake_gemini):
    _, _, (listings, _) = run_source("facebook_groups")
    for l in listings:
        assert re.fullmatch(r"[0-9a-f]{64}", l.external_id_hash)
        assert l.location_precision in ("zip", "neighborhood")
        assert l.address_norm is None


# ---- Zillow specifics ------------------------------------------------------------------------------
def test_zillow_rent_fields_and_no_gemini_when_nothing_to_read(fake_gemini):
    _, _, (listings, stats) = run_source("zillow_rent")
    assert fake_gemini == [] and stats["llm_called"] == 0
    l = next(x for x in listings if x.address_norm == "2519 el cajon blvd")
    assert (l.price_usd, l.beds, l.baths, l.sqft, l.zip, l.unit_label) == (2395, 1, 1.0, 453, "92104", "210")
    assert l.year_built is None and l.extraction == "mapped" and l.location_precision == "address"
    assert l.property_type == "apartment" and l.field_confidence["price_usd"] == 1.0


def test_zillow_sale_maps_year_built_and_history(fake_gemini):
    _, _, (listings, _) = run_source("zillow_sale")
    assert fake_gemini == []
    by_zpid = {l.address_norm: l for l in listings}
    a = by_zpid["3445 29th st"]
    assert a.year_built == 1911 and a.sqft == 2243 and a.price_usd == 2000000
    assert all(h["event"] in ("listed_for_sale", "price_change") for h in a.price_history)
    null_hist = [l for l in listings if l.price_history == []]
    assert null_hist, "a null priceHistory stays empty; history is never invented"


def test_building_level_history_is_dropped_but_unit_history_kept(fake_gemini):
    _, _, (listings, stats) = run_source("zillow_rent")
    unique = next(l for l in listings if l.address_norm == "2519 el cajon blvd")
    shared = [l for l in listings if l.address_norm == "2020 el cajon blvd"]
    assert len(shared) == 2 and all(l.price_history == [] for l in shared)
    assert stats["history_dropped_building_level"] == 2
    assert unique.price_history == sorted(unique.price_history, key=lambda h: h["date"]) and len(unique.price_history) >= 3
    assert {h["event"] for h in unique.price_history} <= {"listed_for_rent", "price_change", "listing_removed"}


def test_listing_outside_the_12_zips_is_skipped(fake_gemini):
    rows = fixture_rows("zillow_rent")
    rows[0]["zipcode"] = "92116"
    _, _, (listings, _) = run_source("zillow_rent", rows)
    assert len(listings) == 2


# ---- Gemini budget and fallback ------------------------------------------------------------------------
def rent_rows_with_text(n):
    rows = fixture_rows("zillow_rent")[:1] * 1
    out = []
    for i in range(n):
        r = json.loads(json.dumps(rows[0]))
        r["zpid"] = 7000 + i
        r["days_on_zillow"] = i                 # lower = newer
        r["description"] = f"Lovely unit {i}. Built in 19{50 + i}."
        out.append(r)
    return out


def test_gemini_fills_only_empty_fields_with_lower_confidence(fake_gemini):
    rows = rent_rows_with_text(1)
    _, _, (listings, stats) = run_source("zillow_rent", rows)
    l = listings[0]
    assert len(fake_gemini) == 1 and stats["llm_called"] == 1
    assert l.year_built == 1950 and l.field_confidence["year_built"] < 1.0 and l.extraction == "mixed"
    assert l.price_usd == 2395 and l.field_confidence["price_usd"] == 1.0      # mapped fields untouched
    assert l.extras["llm_parsed"] is True


def test_gemini_cap_and_newest_first(fake_gemini, monkeypatch):
    monkeypatch.setenv("LLM_EXTRACT_MAX_PER_RUN", "3")
    rows = rent_rows_with_text(8)
    t = load_template("zillow_rent")
    adapter = get_adapter(t)
    payloads = [adapter.clean_payload(r) for r in rows]
    budget = LlmBudget()
    assert budget.max_calls == 3
    listings, stats = process_listing_payloads(t, payloads, NOW, budget)
    assert len(fake_gemini) == 3 and len(listings) == 8          # the rest still load, unparsed
    parsed = sorted(l.year_built for l in listings if l.year_built)
    assert parsed == [1950, 1951, 1952]                            # newest three (days_on_zillow 0..2)


def test_default_cap_is_40(monkeypatch):
    monkeypatch.delenv("LLM_EXTRACT_MAX_PER_RUN", raising=False)
    assert LlmBudget().max_calls == 40


def test_parse_returning_nothing_stores_mapped_fields_and_does_not_retry(monkeypatch):
    calls = []
    monkeypatch.setattr(llm_extract, "parse_listing", lambda text: calls.append(text) or None)
    _, _, (listings, stats) = run_source("zillow_rent", rent_rows_with_text(2))
    assert len(listings) == 2 and len(calls) == 2              # one attempt each, never a loop
    assert all(l.year_built is None and l.extraction == "mapped" for l in listings)
    assert all("llm_parsed" not in l.extras for l in listings)  # unparsed, so a later run may try again


def test_already_parsed_listings_are_not_asked_again(fake_gemini):
    t = load_template("zillow_rent")
    adapter = get_adapter(t)
    payloads = [adapter.clean_payload(r) for r in rent_rows_with_text(2)]
    _, stats = process_listing_payloads(t, payloads, NOW, LlmBudget(40))
    first = len(fake_gemini)
    from worker.clean import sha256_text
    done = frozenset(sha256_text(str(p["zpid"])) for p in payloads)
    process_listing_payloads(t, payloads, NOW, LlmBudget(40), done)
    assert len(fake_gemini) == first


def test_facebook_extracts_price_and_skips_non_offers(fake_gemini):
    _, _, (listings, stats) = run_source("facebook_groups")
    assert len(listings) == 2 and stats["dropped"] == 1           # "looking for a room" is skipped
    prices = sorted(l.price_usd for l in listings)
    assert prices == [1350, 1725]
    assert all(l.extraction == "llm" and l.field_confidence["price_usd"] < 1.0 for l in listings)
    assert all(PHONE_OR_EMAIL.search(t) is None for t in fake_gemini)    # redacted text only goes to Gemini


def test_facebook_without_gemini_stores_nothing(monkeypatch):
    monkeypatch.setattr(llm_extract, "parse_listing", lambda text: None)
    _, _, (listings, _) = run_source("facebook_groups")
    assert listings == []                                           # no price, no row


def test_apartments_com_explodes_floor_plans(fake_gemini):
    _, _, (listings, _) = run_source("apartments_com")
    assert len(listings) == 4                                       # 1 + 2 + 1 floor plans
    studio = next(l for l in listings if l.address_norm == "1530 upas st")
    assert studio.beds == 0 and (studio.price_usd, studio.price_max_usd) == (1795, 1895)
    assert len({l.external_id_hash for l in listings}) == 4


# ---- clean --------------------------------------------------------------------------------------------
def test_redaction_and_normalization():
    t = redact_text("Call Dana Reyes at (619) 555-0142 or dana@x.com, see https://x.co/a")
    assert "Dana" not in t and "555" not in t and "@" not in t and "x.co" not in t
    assert normalize_address("2519 El Cajon Boulevard, Unit 210") == "2519 el cajon blvd"
    assert beds_from("Studio") == 0 and beds_from("2 bd") == 2 and beds_from(None) is None


# ---- area sources ---------------------------------------------------------------------------------------
def test_zip_boundaries_cover_12_zips_and_amenities_use_them():
    gj = json.loads((ROOT / "data" / "zips.geojson").read_text())
    zips = {f["properties"]["zip"] for f in gj["features"]}
    assert zips == set(load_zips())
    f92104 = next(f for f in gj["features"] if f["properties"]["zip"] == "92104")
    assert contains(f92104["geometry"], -117.1307, 32.7419) and not contains(f92104["geometry"], -117.25, 32.80)
    assert abs(area_km2(f92104["geometry"]) - f92104["properties"]["area_km2"]) < 0.01


def test_area_extracts_load_first_of_month_for_all_zips():
    t = load_template("zillow_research")
    got = list(get_adapter(t).fetch())
    metrics = {r.payload["metric"] for r in got}
    assert metrics == {"zori", "zhvi"}
    assert all(r.payload["period"].endswith("-01") for r in got)
    for m in metrics:
        assert {r.payload["geo_id"] for r in got if r.payload["metric"] == m} <= set(load_zips())


def test_cached_census_and_osm_use_the_names_the_api_reads():
    c = json.loads((ROOT / "data" / "census_acs.json").read_text())
    assert set(c["rows"]) <= set(load_zips()) and c["rows"]
    a = json.loads((ROOT / "data" / "amenities.json").read_text())
    assert set(a["zips"]) == set(load_zips())
    for counts in a["zips"].values():
        assert set(counts) == {"groceries", "transit_stops", "parks", "food_drink", "gyms", "area_km2"}
    rows = [r.payload for r in get_adapter(load_template("osm_amenities")).fetch()]
    assert {r["metric"] for r in rows} == {"groceries", "transit_stops", "parks", "food_drink", "gyms", "area_km2"}
