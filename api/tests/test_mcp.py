"""MCP server: every tool through an in-process client, the guards, and that form links use only prefill params.
The DB and Gemini are never touched (db has no DATABASE_URL here; Gemini functions are stubbed)."""
import asyncio
import json
from urllib.parse import parse_qsl, urlsplit

import pytest
from fastapi.testclient import TestClient
from mcp.client import Client

from api import db
from api.llm import gemini
from api.mcp import server as srv
from api.mcp import tools
from api.routers import _common, checks as checks_router, listings as listings_router, owner as owner_router
from contracts.api_models import MatchResponse, OwnerReachResponse
from contracts.prefill import PREFILL

EST = {"low": 1900.0, "expected": 2200.0, "high": 2500.0, "method": "zip_bed_median"}
COMPS = [2000.0, 2100.0, 2200.0, 2300.0, 2400.0]


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(_common, "_model_cache", {"loaded": True, "models": None})
    for name in ("explain_verdict", "draft_letter", "zip_summary", "explain_gaps", "parse_listing"):
        monkeypatch.setattr(gemini, name, lambda *a, **k: None)
    monkeypatch.setattr(listings_router, "estimate", lambda row: (EST, COMPS, {}))
    monkeypatch.setattr(owner_router, "estimate", lambda row: (EST, COMPS, {}))
    monkeypatch.setattr(owner_router, "_days_on_market", lambda *a, **k: None)
    # a check must never be stored
    monkeypatch.setattr(db, "insert_check", lambda *a, **k: pytest.fail("MCP stored a check"))


def call(name, args):
    async def go():
        async with Client(srv.make_server()) as c:
            r = await c.call_tool(name, args)
            if r.is_error:
                return True, r.content[0].text
            return False, (r.structured_content or json.loads(r.content[0].text))
    return asyncio.run(go())


def ok(name, args):
    err, out = call(name, args)
    assert not err, out
    return out


def check_url(url, form):
    """The link uses the table's path and only that form's parameter names."""
    u = urlsplit(url)
    spec = PREFILL[form]
    assert f"{u.scheme}://{u.netloc}" == tools.BASE_URL and u.path == spec["path"]
    names = {k for k, _ in parse_qsl(u.query)}
    assert names <= set(spec["params"]) | set(spec.get("fixed", {})), names
    return dict(parse_qsl(u.query))


def test_lists_all_ten_tools():
    async def go():
        async with Client(srv.make_server()) as c:
            return {t.name: t for t in (await c.list_tools()).tools}
    got = asyncio.run(go())
    assert set(got) == set(srv.TOOLS) and len(got) == 10
    assert all(t.annotations and t.annotations.read_only_hint for t in got.values())


def test_check_rent_increase_not_stored():
    out = ok("check_rent_increase", {"lowest_rent_12mo": 2000, "new_rent": 2400, "effective_date": "2026-03-01",
                                     "zip": "92104", "owner_is_corporate": "yes"})
    assert out["result"]["verdict"] and out["result"]["increase_pct"] == 20.0
    q = check_url(out["form_url"], "renter")
    assert q["lowest"] == "2000" and q["new"] == "2400" and q["corp"] == "yes" and q["effective"] == "2026-03-01"


def test_check_rent_increase_bad_input():
    err, out = call("check_rent_increase", {"lowest_rent_12mo": 2000, "new_rent": 2400, "effective_date": "soon"})
    assert err


def test_check_gouging():
    out = ok("check_gouging", {"new_rent": 3000, "offer_date": "2025-01-15", "zip": "90001",
                               "pre_emergency_rent": 2000, "beds": 2})
    assert "verdict" in out["result"]
    q = check_url(out["form_url"], "gouging")
    assert q["before"] == "2000" and q["date"] == "2025-01-15"


def test_check_listing_price():
    out = ok("check_listing_price", {"zip": "92104", "beds": 1, "asking_rent": 2600, "sqft": 600})
    assert out["result"]["label"] and out["result"]["estimate"]["expected"] == 2200.0
    q = check_url(out["form_url"], "listing")
    assert q["tab"] == "listing" and q["asking"] == "2600"


def test_owner_price_position_with_legal_guardrail():
    out = ok("owner_price_position", {"zip": "92104", "beds": 1, "target_rent": 2300, "lowest_rent_12mo": 2000,
                                      "effective_date": "2026-03-01", "got_exemption_notice": "no"})
    assert len(out["result"]["points"]) == 4 and out["result"]["legal"]["verdict"]
    q = check_url(out["form_url"], "owner")
    assert q["target"] == "2300" and q["notice"] == "no"


def test_owner_reach(monkeypatch):
    from api.match import reach
    fake = OwnerReachResponse.model_construct(n_comparables=12, points=[], note="x")
    monkeypatch.setattr(reach, "owner_reach", lambda req: fake)
    out = ok("owner_reach", {"zip": "92104", "beds": 1, "target_rent": 2300})
    assert out["result"]["n_comparables"] == 12
    assert check_url(out["form_url"], "owner_reach")["ask"] == "2300"


def test_search_listings():
    out = ok("search_listings", {"zip": "92104", "beds": 1, "max_price": 2500, "property_type": "house"})
    assert out["result"]["items"] == [] and out["result"]["limit"] == 10
    q = check_url(out["form_url"], "find")
    assert q == {"zip": "92104", "beds": "1", "max": "2500", "type": "single_family"}


def test_find_by_needs(monkeypatch):
    from api.match import rank
    fake = MatchResponse.model_construct(needs=None, results=[], n_after_filters=0, method="rules", disclaimer="")
    monkeypatch.setattr(rank, "match", lambda req: fake)
    out = ok("find_by_needs", {"needs": "quiet 1BR under $2,400, cat ok"})
    assert check_url(out["form_url"], "advisor")["needs"] == "quiet 1BR under $2,400, cat ok"


def test_rank_areas_links_by_persona():
    for persona, form, key in (("starter", "find", "starter_budget"), ("wealth", "buyer", "budget")):
        err, out = call("rank_areas", {"persona": persona, "budget_usd": 2500, "beds": 1})
        if not err:   # no DB: the ranking itself may be unavailable, the link is what this checks
            assert check_url(out["form_url"], form)[key] == "2500"
    assert check_url(tools.link("find", starter_budget=2500, starter_beds=1), "find")["starter_beds"] == "1"


def test_zip_profile():
    out = ok("zip_profile", {"zip": "92104"})
    assert out["form_url"] == "https://rentorknot.us/zip/92104"
    assert call("zip_profile", {"zip": "abc"})[0]


def test_prefill_form_only_known_params():
    out = ok("prefill_form", {"form": "gouging", "values": {"zip": "92104", "new": 3000}})
    assert check_url(out["form_url"], "gouging") == {"zip": "92104", "new": "3000"}
    err, msg = call("prefill_form", {"form": "gouging", "values": {"rent": 3000}})
    assert err and "zip" in json.dumps(msg)
    assert call("prefill_form", {"form": "nope"})[0]


def test_every_form_link_uses_the_table():
    for form, spec in PREFILL.items():
        vals = {k: "1" for k in spec["params"]}
        check_url(ok("prefill_form", {"form": form, "values": vals})["form_url"], form)


# ---- guards ----
def _post(client, method, ip="1.2.3.4", extra=None):
    body = {"jsonrpc": "2.0", "id": 1, "method": method,
            "params": {"name": "prefill_form", "arguments": {"form": "find"}} if method == "tools/call" else {}}
    return client.post("/mcp", json=body, headers={"x-forwarded-for": ip, "accept": "application/json, text/event-stream",
                                                   **(extra or {})})


def test_rate_limit_per_ip_counts_tool_calls_only():
    app, lifespan = srv.build_app(per_ip=3)
    from starlette.applications import Starlette
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def life(_):
        async with lifespan():
            yield
    wrapped = Starlette(lifespan=life)
    wrapped.mount("/", app)
    with TestClient(wrapped) as c:
        assert [_post(c, "tools/call").status_code for _ in range(3)] == [200, 200, 200]
        r = _post(c, "tools/call")
        assert r.status_code == 429 and r.headers["retry-after"] == "60"
        assert _post(c, "tools/call", ip="9.9.9.9").status_code == 200       # another IP is unaffected
        assert _post(c, "tools/list").status_code == 200                     # listing is free
        # a spoofed first X-Forwarded-For entry does not dodge the limit: the last entry (Caddy's) counts
        assert _post(c, "tools/call", ip="7.7.7.7, 1.2.3.4").status_code == 429


def test_request_size_limit():
    app, lifespan = srv.build_app(max_body=200)
    from starlette.applications import Starlette
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def life(_):
        async with lifespan():
            yield
    wrapped = Starlette(lifespan=life)
    wrapped.mount("/", app)
    with TestClient(wrapped) as c:
        r = c.post("/mcp", content=b"x" * 500, headers={"content-type": "application/json"})
        assert r.status_code == 413


def test_mounted_in_fastapi_with_lifespan():
    from api.main import app
    with TestClient(app) as c:   # runs FastAPI's lifespan, which must start the MCP session manager
        r = _post(c, "tools/list")
        assert r.status_code == 200 and len(r.json()["result"]["tools"]) == 10
        assert c.get("/health").status_code == 200
