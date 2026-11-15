"""GET /zips/{zip}/trends and GET /listings/{id}/trends (night-forecast). Engine: api/ml/trends.py."""
from fastapi import APIRouter, HTTPException

from api import db
from api.ml import trends
from contracts.api_models import ListingTrendsResponse, ZipTrendsResponse

router = APIRouter(tags=["trends"])


@router.get("/zips/{zip}/trends", response_model=ZipTrendsResponse)
def zip_trends(zip: str) -> ZipTrendsResponse:
    if zip not in db.ZIP_NAMES:
        raise HTTPException(404, f"{zip} is not one of the ZIPs RentOrKnot covers")
    try:
        return ZipTrendsResponse(**trends.zip_trends(zip))
    except db.DBUnavailable:
        raise HTTPException(503, "Database unavailable")


@router.get("/listings/{listing_id}/trends", response_model=ListingTrendsResponse)
def listing_trends(listing_id: int) -> ListingTrendsResponse:
    try:
        r = trends.listing_trends(listing_id)
    except db.DBUnavailable:
        raise HTTPException(503, "Database unavailable")
    if r is None:
        raise HTTPException(404, "No such listing")
    return ListingTrendsResponse(**r)
