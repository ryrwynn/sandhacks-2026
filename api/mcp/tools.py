"""MCP tool logic. Every tool calls our own engine in-process (never HTTP to ourselves), stores nothing, and
returns {"result": ..., "form_url": ...} where form_url is built only with contracts.prefill.form_url.

The tools are plain functions so tests can call them directly; api/mcp/server.py registers them.
"""
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import HTTPException
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel

from api.routers import checks, gouging, listings, match, neighborhoods, owner, owner_reach, tracker, zips
from api.rules import ab1482
from contracts.api_models import (GougingRequest, ListingEvalRequest, MatchRequest, OwnerReachRequest,
                                  PricePositionRequest, RankRequest)
from contracts.prefill import PREFILL, form_url

BASE_URL = "https://rentorknot.us"   # absolute, so a link works outside the site (an assistant's chat window)

YesNo = Literal["yes", "no", "unsure"]
HomeType = Literal["apartment", "condo", "townhouse", "single_family", "unknown"]


def link(form: str, **values) -> str:
    return form_url(form, base=BASE_URL, **values)


def _tri(v: str | None) -> bool | None:
    return {"yes": True, "no": False}.get(v)


def _known(t: str) -> str | None:
    return None if t == "unknown" else t


def _build(model, **kw):
    try:
        return model(**kw)
    except ValueError as e:   # pydantic ValidationError is a ValueError
        raise ToolError(f"Invalid input: {e}") from None


def _run(fn, *args, **kw) -> dict:
    """Run an engine function; turn its HTTP errors into a readable tool error and dump the pydantic result."""
    try:
        r = fn(*args, **kw)
    except HTTPException as e:
        raise ToolError(str(e.detail)) from None
    return r.model_dump(mode="json") if isinstance(r, BaseModel) else r


def _out(result, url: str) -> dict:
    return {"result": result, "form_url": url}


def check_rent_increase(lowest_rent_12mo: float, new_rent: float, effective_date: str, zip: str | None = None,
                        address: str | None = None, year_built: int | None = None,
                        property_type: HomeType = "unknown", increases_last_12mo: int = 0,
                        got_exemption_notice: YesNo | None = None, owner_is_corporate: YesNo | None = None) -> dict:
    """Check a California rent increase against AB 1482 (the statewide cap). Nothing is stored."""
    if lowest_rent_12mo <= 0 or new_rent <= 0:
        raise ToolError("Invalid input: rents must be positive")
    try:
        inp = ab1482.CheckInput(
            lowest_rent_12mo=Decimal(str(lowest_rent_12mo)), new_rent=Decimal(str(new_rent)),
            effective_date=date.fromisoformat(effective_date), year_built=year_built, property_type=property_type,
            got_exemption_notice=_tri(got_exemption_notice), owner_is_corporate=_tri(owner_is_corporate),
            other_exemption=False, increases_last_12mo=increases_last_12mo)
        r = ab1482.check_increase(inp, checks.load_caps())
    except NotImplementedError:
        raise ToolError("The rent-cap check is not available yet") from None
    except ValueError as e:
        raise ToolError(f"Invalid input: {e}") from None

    def f(v):
        return None if v is None else float(v)

    inc = f(r.increase_pct)
    if inc is None:
        inc = round((new_rent - lowest_rent_12mo) / lowest_rent_12mo * 100, 1)
    res = {"verdict": r.verdict, "cap_pct": f(r.cap_pct), "max_legal_rent": f(r.max_legal_rent), "increase_pct": inc,
           "overage_monthly": f(r.overage_monthly), "overage_yearly": f(r.overage_yearly),
           "third_increase": r.third_increase, "reasons": r.reasons}
    return _out(res, link("renter", address=address, zip=zip, lowest=lowest_rent_12mo, new=new_rent,
                          effective=effective_date, year=year_built, type=_known(property_type),
                          increases=increases_last_12mo or None, notice=got_exemption_notice,
                          corp=owner_is_corporate))


def check_gouging(new_rent: float, offer_date: str, zip: str | None = None, county: str | None = None,
                  pre_emergency_rent: float | None = None, beds: int | None = None) -> dict:
    """Check a rent price against California's rent-gouging rule (Penal Code 396) during a declared emergency."""
    req = _build(GougingRequest, zip=zip, county=county, new_rent=new_rent, offer_date=offer_date,
                 pre_emergency_rent=pre_emergency_rent, beds=beds)
    return _out(_run(gouging.check_gouging, req),
                link("gouging", zip=zip, beds=beds, new=new_rent, date=offer_date, before=pre_emergency_rent))


def check_listing_price(zip: str, beds: int, asking_rent: float, baths: float | None = None, sqft: int | None = None,
                        property_type: HomeType = "unknown", text: str | None = None) -> dict:
    """Is an asking rent fair? Returns the fair-rent range, a label and the percentile among comparable listings."""
    req = _build(ListingEvalRequest, zip=zip, beds=beds, asking_rent=asking_rent, baths=baths, sqft=sqft,
                 property_type=property_type, text=text)
    return _out(_run(listings.evaluate_listing, req),
                link("listing", zip=zip, beds=beds, asking=asking_rent, baths=baths, sqft=sqft,
                     type=_known(property_type), text=text))


def owner_price_position(zip: str, beds: int, target_rent: float, sqft: int | None = None,
                         year_built: int | None = None, property_type: HomeType = "unknown",
                         lowest_rent_12mo: float | None = None, effective_date: str | None = None,
                         got_exemption_notice: YesNo | None = None, owner_is_corporate: YesNo | None = None) -> dict:
    """Where a target rent sits among comparable listings, with the AB 1482 legal maximum if a tenant stays."""
    req = _build(PricePositionRequest, zip=zip, beds=beds, target_rent=target_rent, sqft=sqft, year_built=year_built,
                 property_type=property_type, occupied=bool(lowest_rent_12mo and effective_date),
                 lowest_rent_12mo=lowest_rent_12mo, effective_date=effective_date,
                 got_exemption_notice=_tri(got_exemption_notice), owner_is_corporate=_tri(owner_is_corporate))
    return _out(_run(owner.price_position, req),
                link("owner", zip=zip, beds=beds, target=target_rent, sqft=sqft, year=year_built,
                     type=_known(property_type), lowest=lowest_rent_12mo, effective=effective_date,
                     notice=got_exemption_notice, corp=owner_is_corporate))


def owner_reach_tool(zip: str, beds: int, target_rent: float, text: str | None = None) -> dict:
    """Share of comparable renter profiles who would shortlist a listing at this rent."""
    req = _build(OwnerReachRequest, zip=zip, beds=beds, target_rent=target_rent, text=text)
    return _out(_run(owner_reach.owner_reach, req), link("owner_reach", zip=zip, beds=beds, ask=target_rent, text=text))


def search_listings(zip: str | None = None, beds: int | None = None, max_price: float | None = None,
                    property_type: Literal["apartment", "condo", "house"] | None = None,
                    sort: Literal["recent", "price_asc", "price_desc", "biggest_drop"] = "recent",
                    limit: int = 10) -> dict:
    """Current rental listings, newest or cheapest first. Returns at most 25."""
    limit = max(1, min(limit, 25))
    # Called as a plain function, so every parameter is passed (FastAPI's Query defaults only resolve in a request).
    res = _run(tracker.list_listings, zip=zip, beds=beds, type=property_type, max_price=max_price, sort=sort,
               limit=limit, offset=0, ids=None, min_observations=None, source="all", unit_type=None)
    return _out(res, link("find", zip=zip, beds=beds, max=max_price,
                          type={"house": "single_family"}.get(property_type, property_type)))


def find_by_needs(needs: str, limit: int = 5, budget_max_usd: float | None = None,
                  beds_min: int | None = None) -> dict:
    """Rank current listings for a plain-language description (budget, bedrooms, area, must-haves)."""
    req = _build(MatchRequest, text=needs, limit=max(1, min(limit, 10)), budget_max_usd=budget_max_usd,
                 beds_min=beds_min)
    return _out(_run(match.match, req), link("advisor", needs=needs))


def rank_areas(persona: Literal["starter", "wealth"], budget_usd: float, beds: int | None = None) -> dict:
    """Rank ZIPs. starter: best areas for a monthly rent budget. wealth: best areas to build wealth for a home price."""
    req = _build(RankRequest, persona=persona, budget_usd=budget_usd, beds=beds)
    url = (link("find", starter_budget=budget_usd, starter_beds=beds) if persona == "starter"
           else link("buyer", budget=budget_usd, beds=beds))
    return _out(_run(neighborhoods.rank, req), url)


def zip_profile(zip: str) -> dict:
    """Typical rent and home value, forecasts and scores for one ZIP."""
    if not (len(zip) == 5 and zip.isdigit()):
        raise ToolError("zip must be 5 digits")
    return _out(_run(zips.zip_profile, zip, False), f"{BASE_URL}/zip/{zip}")


def prefill_form(form: str, values: dict[str, str | float | int | bool] | None = None) -> dict:
    """Build a link that opens one of RentOrKnot's forms already filled in. It only fills fields; it never submits.
    `form` is one of renter, listing, gouging, owner, owner_reach, buyer, find, advisor; `values` use that form's
    parameter names (an unknown form or name returns the valid ones)."""
    if form not in PREFILL:
        raise ToolError(f"Unknown form {form!r}. Forms: " + "; ".join(
            f"{k} ({', '.join(v['params'])})" for k, v in PREFILL.items()))
    try:
        url = link(form, **(values or {}))
    except ValueError as e:
        raise ToolError(f"{e}. Valid: {', '.join(PREFILL[form]['params'])}") from None
    return _out({"form": form, "label": PREFILL[form]["label"], "params": PREFILL[form]["params"]}, url)
