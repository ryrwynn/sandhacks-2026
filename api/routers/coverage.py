"""GET /areas, POST /areas/requests, GET /areas/requests/{id} (night-data). Tables: areas, area_requests."""
from uuid import UUID

from fastapi import APIRouter

from api.routers._stub import not_built
from contracts.api_models import AreaRequestCreate, AreaRequestStatus, AreasResponse, Tier

router = APIRouter(prefix="/areas", tags=["coverage"])


@router.get("", response_model=AreasResponse)
def list_areas(tier: Tier | None = None, county: str | None = None, q: str | None = None,
               limit: int = 200) -> AreasResponse:
    raise not_built("Areas")


@router.post("/requests", response_model=AreaRequestStatus)
def request_area(req: AreaRequestCreate) -> AreaRequestStatus:
    raise not_built("Area requests")


@router.get("/requests/{request_id}", response_model=AreaRequestStatus)
def area_request(request_id: UUID) -> AreaRequestStatus:
    raise not_built("Area requests")
