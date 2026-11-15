import logging
import statistics
from decimal import Decimal

from fastapi import APIRouter, HTTPException

from api import db
from api.llm import gemini
from api.ml import listing_analysis
from api.routers._common import estimate, percentile_of, safe
from api.routers.checks import _f, load_caps
from api.routers.listings import make_estimate
from api.rules import ab1482
from contracts.api_models import (DaysOnMarket, Gap, LegalGuardrail, ListingAnalysisRequest,
                                  ListingAnalysisResponse, PricePoint, PricePositionRequest,
                                  PricePositionResponse)

log = logging.getLogger("rentwatch.api")
router = APIRouter(prefix="/owner", tags=["owner"])
MIN_DOM_LISTINGS = 5


def _reach(percentile: float | None) -> float | None:
    """Higher = more renters likely to consider it: the cheaper against comparables, the higher."""
    return None if percentile is None else round(100 - percentile, 1)


def _days_on_market(zip_: str, beds: int, expected: float) -> DaysOnMarket | None:
    rows = safe(db.days_on_market, zip_, beds, default=[])
    if len(rows) < MIN_DOM_LISTINGS:
        return None
    below = [d for p, d in rows if p <= expected]
    above = [d for p, d in rows if p > expected]
    med = lambda xs: round(statistics.median(xs), 1) if len(xs) >= 2 else None  # noqa: E731
    return DaysOnMarket(below_expected_median_days=med(below), above_expected_median_days=med(above),
                        n_listings=len(rows))


@router.post("/price-position", response_model=PricePositionResponse)
def price_position(req: PricePositionRequest) -> PricePositionResponse:
    est, comps, metrics = estimate(req.model_dump())
    if est is None:
        raise HTTPException(503, f"Not enough comparable listings in {req.zip} to estimate a rent yet")
    points = []
    for label, rent in (("low", est["low"]), ("expected", est["expected"]), ("high", est["high"]),
                        ("target", req.target_rent)):
        pct = percentile_of(rent, comps)
        points.append(PricePoint(label=label, rent_usd=round(rent, 2),
                                 percentile=None if pct is None else round(pct, 1), reach_score=_reach(pct)))
    legal = None
    if req.occupied and req.lowest_rent_12mo and req.effective_date:
        inp = ab1482.CheckInput(
            lowest_rent_12mo=Decimal(str(req.lowest_rent_12mo)), new_rent=Decimal(str(req.target_rent)),
            effective_date=req.effective_date, year_built=req.year_built, property_type=req.property_type,
            got_exemption_notice=req.got_exemption_notice, owner_is_corporate=req.owner_is_corporate,
            other_exemption=False, increases_last_12mo=0)
        try:
            r = ab1482.check_increase(inp, load_caps())
            legal = LegalGuardrail(verdict=r.verdict, cap_pct=_f(r.cap_pct), max_legal_rent=_f(r.max_legal_rent),
                                   reasons=r.reasons)
        except NotImplementedError:
            log.warning("check_increase not implemented; legal guardrail omitted")
    return PricePositionResponse(
        estimate=make_estimate(est, metrics), points=points, n_comparables=len(comps),
        days_on_market=_days_on_market(req.zip, req.beds, est["expected"]), legal=legal)


@router.post("/listing-analysis", response_model=ListingAnalysisResponse)
def listing_analysis_endpoint(req: ListingAnalysisRequest) -> ListingAnalysisResponse:
    text = req.text
    if not text and req.listing_id is not None:
        text = safe(db.listing_text, req.listing_id)
    if not text:
        raise HTTPException(422, "Provide the listing text, or a listing_id that has text")
    comp_texts = safe(db.comparable_texts, req.zip, req.beds, default=[])
    price_pct = None
    if req.target_rent:
        rents = safe(db.comparable_rents, req.zip, req.beds, default=[])
        price_pct = percentile_of(req.target_rent, rents)
    try:
        res = listing_analysis.analyze_listing(text, comp_texts, price_pct)
    except NotImplementedError:
        raise HTTPException(503, "Listing analysis is not available yet")
    explanation = None
    if res.get("gaps"):
        try:
            explanation = gemini.explain_gaps(text, res["gaps"])
        except Exception as e:  # optional text: no retry
            log.warning("explain_gaps failed: %s", e)
    return ListingAnalysisResponse(
        completeness=res["completeness"], readability=res["readability"], reach_score=res["reach_score"],
        stated=res["stated"], gaps=[Gap(**g) for g in res["gaps"]], n_comparables=len(comp_texts),
        explanation=explanation)
