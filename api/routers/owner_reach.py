"""POST /owner/reach (night-match)."""
from fastapi import APIRouter

from api.match import reach
from api.routers._stub import not_built
from contracts.api_models import OwnerReachRequest, OwnerReachResponse

router = APIRouter(prefix="/owner", tags=["owner"])


@router.post("/reach", response_model=OwnerReachResponse)
def owner_reach(req: OwnerReachRequest) -> OwnerReachResponse:
    try:
        return reach.owner_reach(req)
    except NotImplementedError:
        raise not_built("Owner reach")
