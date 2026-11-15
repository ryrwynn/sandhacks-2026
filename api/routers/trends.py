"""GET /zips/{zip}/trends and GET /listings/{id}/trends (night-forecast). Engine: api/ml/trends.py."""
from fastapi import APIRouter, HTTPException

from api.ml import trends
from api.routers._stub import not_built
from contracts.api_models import ListingTrendsResponse, ZipTrendsResponse

router = APIRouter(tags=["trends"])


@router.get("/zips/{zip}/trends", response_model=ZipTrendsResponse)
def zip_trends(zip: str) -> ZipTrendsResponse:
    try:
        return ZipTrendsResponse(**trends.zip_trends(zip))
    except NotImplementedError:
        raise not_built("ZIP trends")


@router.get("/listings/{listing_id}/trends", response_model=ListingTrendsResponse)
def listing_trends(listing_id: int) -> ListingTrendsResponse:
    try:
        r = trends.listing_trends(listing_id)
    except NotImplementedError:
        raise not_built("Listing trends")
    if r is None:
        raise HTTPException(404, "No such listing")
    return ListingTrendsResponse(**r)
