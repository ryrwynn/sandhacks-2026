"""Matching, embeddings and owner reach. The network and database are mocked."""
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

from api import db
from api.llm import gemini as g
from api.main import app
from api.match import embed, needs, rank, reach, store
from api.routers import tracker
from contracts.api_models import MatchRequest, OwnerReachRequest


def row(i, price, beds=1, zip_="92104", active=True, ptype="apartment"):
    return {"listing_id": i, "zip": zip_, "listing_type": "rent", "beds": beds, "baths": 1, "sqft": 600,
            "last_seen": datetime(2026, 11, 14), "address_norm": f"{i} MAIN ST", "unit_label": None,
            "property_type": ptype, "source_kind": "listing_site", "source_url": None, "active": active,
            "n": 2, "cur": price, "first_price": price, "first_observed": date(2026, 10, 1), "total": 3}


REAL_EMBED_QUERY = g.embed_query
TEXTS = {1: "Quiet 1BR, cats ok, garage parking, near UCSD.", 2: "Bright 1BR with laundry. No details.",
         3: "Pricey 1BR with pets and parking."}


@pytest.fixture(autouse=True)
def mocks(monkeypatch):
    g._reset_state()
    monkeypatch.setattr(db, "ZIP_NAMES", {"92104": "North Park", "92122": "University City"})
    monkeypatch.setattr(store, "candidates", lambda limit=2000: [row(1, 2000), row(2, 1700), row(3, 3500),
                                                                 row(4, 1500, active=False), row(5, 1900, beds=2)])
    monkeypatch.setattr(store, "texts", lambda ids: {i: TEXTS.get(i, "") for i in ids})
    monkeypatch.setattr(db, "zip_features", lambda: {"92104": {"transit_stops": 10, "groceries": 5},
                                                     "92122": {"transit_stops": 2, "groceries": 1}})
    monkeypatch.setattr(db, "listing_observations", lambda ids: [])
    monkeypatch.setattr(tracker, "group_label", lambda z, b, p: "in_range")
    monkeypatch.setattr(g, "parse_needs", lambda text: None)       # rules parser
    monkeypatch.setattr(g, "embed_query", lambda text: None)


def test_rules_parser():
    n = needs.rules_parse("quiet 1BR under $2,400 in North Park near UCSD, cat ok, parking")
    assert n.budget_max_usd == 2400 and n.beds_min == 1 and n.beds_max == 1
    assert "92104" in n.zips and set(n.must_haves) == {"pets", "parking"} and "quiet" in n.nice_to_haves
    assert n.commute_anchors == ["UCSD"] and n.parsed_by == "rules"


def test_gemini_parse_is_checked(monkeypatch):
    monkeypatch.setattr(g, "parse_needs", lambda t: {"budget_max_usd": 9999, "beds_min": 2, "zips": ["x", "92122"],
                                                     "must_haves": ["Dogs"], "areas": ["North Park"]})
    n = needs.parse_needs("2 bed under $2,000 with a dog")
    assert n.parsed_by == "gemini" and n.budget_max_usd == 2000   # 9999 isn't in the text
    assert n.zips[0] == "92122" and "92104" in n.zips and n.must_haves == ["pets"]


def test_match_filters_and_ranks():
    r = rank.match(MatchRequest(text="1BR under $2,400 with pets and parking"))
    ids = [x.listing.id for x in r.results]
    assert r.method == "keywords" and r.n_after_filters == 2
    assert ids == [1, 2]            # 3 is over budget, 4 inactive, 5 wrong beds
    top, second = r.results
    assert top.unconfirmed == [] and second.unconfirmed == ["pets", "parking"]
    assert 0 <= top.score <= 100 and set(top.components) == {"price_fit", "amenity_fit", "fair_rent", "semantic"}
    assert any("pets" in s for s in top.reasons)


def test_budget_override_and_limit():
    r = rank.match(MatchRequest(text="1BR with pets", budget_max_usd=1800, limit=1))
    assert [x.listing.id for x in r.results] == [2]


def test_embeddings_used_when_available(monkeypatch):
    monkeypatch.setattr(g, "embed_query", lambda t: [1.0] + [0.0] * 767)
    monkeypatch.setattr(store, "cosines", lambda q, ids, m: {1: 0.5, 2: 0.9})
    r = rank.match(MatchRequest(text="1BR under $2,400"))
    assert r.method == "embeddings"
    by = {x.listing.id: x for x in r.results}
    assert by[2].components["semantic"] == 25.0 and by[1].components["semantic"] == 0.0


def test_no_demographic_inputs():
    import inspect
    src = inspect.getsource(rank).lower()
    assert "median_income" not in src and "race" not in src and "ethnic" not in src


# ---- embeddings and quota ----
class FakeEmb:
    def __init__(self, values):
        self.values = values


class FakeModels:
    def __init__(self, exc=None):
        self.calls = []
        self.exc = exc

    def embed_content(self, model, contents, config):
        self.calls.append(len(contents))
        if self.exc:
            raise self.exc
        return type("R", (), {"embeddings": [FakeEmb([0.1] * 768) for _ in contents]})()


def fake_client(monkeypatch, exc=None):
    m = FakeModels(exc)
    monkeypatch.setattr(g, "_get_client", lambda: type("C", (), {"models": m})())
    monkeypatch.setattr(g, "_connect", lambda: None)
    return m


def test_embed_budget_stops(monkeypatch):
    m = fake_client(monkeypatch)
    monkeypatch.setenv("EMBED_REQUEST_BUDGET", "2")
    assert len(g.embed_texts(["a", "b"])) == 2
    assert g.embed_texts(["c"]) is not None
    assert g.embed_texts(["d"]) is None and len(m.calls) == 2


def test_embed_quota_error_not_retried(monkeypatch):
    from google.genai import errors
    m = fake_client(monkeypatch, errors.ClientError(429, {"error": {"message": "quota", "details": []}}))
    assert g.embed_texts(["a"]) is None and g.embed_texts(["a"]) is None
    assert len(m.calls) == 1


def test_embed_missing_skips_stored_and_batches(monkeypatch):
    rows = [{"listing_id": i, "zip": "92104", "beds": 1, "baths": 1, "sqft": 500, "property_type": "apartment",
             "text_redacted": f"Nice unit number {i} with parking"} for i in range(1, 8)]
    monkeypatch.setattr(store, "embeddable", lambda n: rows)
    import hashlib
    done = {1: hashlib.sha256(embed.listing_doc(rows[0]).encode()).hexdigest()}
    monkeypatch.setattr(store, "stored_hashes", lambda m: done)
    put = []
    monkeypatch.setattr(store, "put_embedding", lambda *a: put.append(a[0]))
    monkeypatch.setattr(embed, "BATCH", 3)
    m = fake_client(monkeypatch)
    out = embed.embed_missing()
    assert out["pending"] == 6 and out["stored"] == 6 and m.calls == [3, 3] and 1 not in put


def test_query_embedding_cached(monkeypatch):
    m = fake_client(monkeypatch)
    cache = {}
    monkeypatch.setattr(g, "_cache_get", lambda k: cache.get(k))
    monkeypatch.setattr(g, "_cache_put", lambda k, j, mo, r: cache.__setitem__(k, r))
    monkeypatch.setattr(g, "embed_query", REAL_EMBED_QUERY)
    assert len(g.embed_query("quiet 1br")) == 768 and len(g.embed_query("quiet 1br")) == 768
    assert m.calls == [1]


# ---- owner reach ----
RENTS = [1800, 1900, 2000, 2100, 2200, 2300, 2400, 2500, 2600, 2800]
COMP_TEXTS = ["pets ok, parking included"] * 4 + ["laundry on site"] * 3 + ["nice place"] * 3


@pytest.fixture
def comps(monkeypatch):
    monkeypatch.setattr(db, "comparable_rents", lambda z, b, days=90: list(RENTS))
    monkeypatch.setattr(db, "comparable_texts", lambda z, b, limit=200: COMP_TEXTS)


def test_reach_price_and_facts(comps):
    r = reach.owner_reach(OwnerReachRequest(zip="92104", beds=1, target_rent=2500, stated={}))
    assert r.n_comparables == 10 and 0 <= r.current_reach_pct <= 100
    reaches = [p.reach_pct for p in r.curve]
    assert reaches == sorted(reaches, reverse=True)        # a higher rent never reaches more
    assert abs(sum(p.weight for p in r.profiles) - 1.0) < 1e-6
    assert r.best_changes and r.best_changes == sorted(r.best_changes, key=lambda c: -c.gain_pts)
    assert all(c.gain_pts > 0 for c in r.best_changes)
    assert any(c.kind == "fact" for c in r.best_changes) and any(c.kind == "price" for c in r.best_changes)


def test_reach_stated_facts_raise_reach(comps):
    a = reach.owner_reach(OwnerReachRequest(zip="92104", beds=1, target_rent=2300, stated={}))
    b = reach.owner_reach(OwnerReachRequest(zip="92104", beds=1, target_rent=2300,
                                            stated={"pets": True, "parking": True, "laundry": True}))
    assert b.current_reach_pct > a.current_reach_pct and not [c for c in b.best_changes if c.kind == "fact"]


def test_reach_parses_text_and_few_comps(monkeypatch):
    monkeypatch.setattr(db, "comparable_rents", lambda z, b, days=90: [])
    monkeypatch.setattr(db, "comparable_texts", lambda z, b, limit=200: [])
    r = reach.owner_reach(OwnerReachRequest(zip="92104", beds=0, target_rent=1500, text="Studio, pets welcome"))
    assert "Too few comparables" in r.method_note and r.n_comparables == 0


def test_routes(comps):
    c = TestClient(app)
    assert c.post("/match", json={"text": "1BR under $2,400 with pets"}).status_code == 200
    assert c.post("/owner/reach", json={"zip": "92104", "beds": 1, "target_rent": 2400}).status_code == 200


def test_reach_route_refuses_without_comparables(monkeypatch):
    monkeypatch.setattr(db, "comparable_rents", lambda z, b, days=90: [])
    monkeypatch.setattr(db, "comparable_texts", lambda z, b, limit=200: [])
    r = TestClient(app).post("/owner/reach", json={"zip": "92104", "beds": 1, "target_rent": 2500})
    assert r.status_code == 422 and "comparable" in r.json()["detail"]
