import logging

from fastapi import APIRouter, HTTPException, Query

from api import db
from api.llm import gemini
from api.routers._common import estimate, label_for, percentile_of, safe
from contracts.api_models import (FairRentEstimate, ListingEvalRequest, ListingEvalResponse, UnitMatch,
                                  UnitSearchResponse)

log = logging.getLogger("rentwatch.api")
router = APIRouter(tags=["listings"])


@router.get("/units/search", response_model=UnitSearchResponse)
def units_search(address: str = Query(min_length=3)) -> UnitSearchResponse:
    rows = safe(db.search_units, address, default=[])
    return UnitSearchResponse(query=address, results=[UnitMatch(**{**r, "zip": r["zip"].strip()}) for r in rows])


def make_estimate(est: dict, metrics: dict) -> FairRentEstimate:
    return FairRentEstimate(low=round(est["low"], 2), expected=round(est["expected"], 2),
                            high=round(est["high"], 2), method=est["method"],
                            mae_usd=metrics.get("mae_usd"), coverage_80=metrics.get("coverage_80"))


@router.post("/listings/evaluate", response_model=ListingEvalResponse)
def evaluate_listing(req: ListingEvalRequest) -> ListingEvalResponse:
    row = req.model_dump()
    parsed = None
    if req.text:
        try:
            fields = gemini.parse_listing(req.text)
        except Exception as e:
            log.warning("parse_listing failed: %s", e)
            fields = None
        if fields is not None:
            parsed = fields.model_dump(exclude_none=True)
            for k in ("baths", "sqft", "year_built"):
                if row.get(k) is None and parsed.get(k) is not None:
                    row[k] = parsed[k]
            if row.get("property_type") == "unknown" and parsed.get("property_type"):
                row["property_type"] = parsed["property_type"]
    est, comps, metrics = estimate(row)
    if est is None:
        raise HTTPException(503, f"Not enough comparable listings in {req.zip} to estimate a rent yet")
    return ListingEvalResponse(
        estimate=make_estimate(est, metrics), asking_rent=req.asking_rent,
        label=label_for(req.asking_rent, est), percentile=percentile_of(req.asking_rent, comps),
        n_comparables=len(comps), parsed_fields=parsed)
