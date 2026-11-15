"""POST /match (night-match)."""
from fastapi import APIRouter

from api.match import rank
from api.routers._stub import not_built
from contracts.api_models import MatchRequest, MatchResponse

router = APIRouter(tags=["match"])


@router.post("/match", response_model=MatchResponse)
def match(req: MatchRequest) -> MatchResponse:
    try:
        return rank.match(req)
    except NotImplementedError:
        raise not_built("Needs matching")
