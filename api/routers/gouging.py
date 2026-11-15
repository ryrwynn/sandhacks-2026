"""POST /checks/gouging (night-rules): Penal Code 396 check. Engine: api/rules/gouging.py."""
from decimal import Decimal

from fastapi import APIRouter

from api.routers._stub import not_built
from api.rules import gouging
from contracts.api_models import GougingRequest, GougingResponse

router = APIRouter(prefix="/checks", tags=["checks"])


@router.post("/gouging", response_model=GougingResponse)
def check_gouging(req: GougingRequest) -> GougingResponse:
    try:
        r = gouging.check_gouging(
            Decimal(str(req.new_rent)), req.offer_date, zip_=req.zip, county=req.county,
            pre_emergency_rent=None if req.pre_emergency_rent is None else Decimal(str(req.pre_emergency_rent)),
            beds=req.beds)
    except NotImplementedError:
        raise not_built("The gouging check")
    return GougingResponse(**r)
