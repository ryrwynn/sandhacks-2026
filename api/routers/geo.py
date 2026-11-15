"""GET /geo/zips?bbox= (night-data): which county GeoJSON files and ZCTAs a map viewport needs."""
from fastapi import APIRouter

from api.routers._stub import not_built
from contracts.api_models import GeoZipsResponse

router = APIRouter(prefix="/geo", tags=["geo"])


@router.get("/zips", response_model=GeoZipsResponse)
def geo_zips(bbox: str) -> GeoZipsResponse:
    raise not_built("Map geometry")
