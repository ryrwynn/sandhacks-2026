"""POST /owner/reach (night-match)."""
from fastapi import APIRouter, HTTPException

from api.match import reach
from api.routers._stub import not_built
from contracts.api_models import OwnerReachRequest, OwnerReachResponse

router = APIRouter(prefix="/owner", tags=["owner"])


@router.post("/reach", response_model=OwnerReachResponse)
def owner_reach(req: OwnerReachRequest) -> OwnerReachResponse:
    try:
        r = reach.owner_reach(req)
    except NotImplementedError:
        raise not_built("Owner reach")
    if r.n_comparables < reach.MIN_COMPS:   # a reach figure from no data would be invented
        raise HTTPException(422, f"Only {r.n_comparables} comparable listings in {req.zip} for {req.beds} bedrooms; "
                                 f"reach needs at least {reach.MIN_COMPS}.")
    return r
