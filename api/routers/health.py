from fastapi import APIRouter

from api import db
from contracts.api_models import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Always 200: when the database can't be reached the status is 'degraded'."""
    try:
        db.ping()
        info = db.health_info()
    except Exception:
        return HealthResponse(status="degraded", database=False)
    return HealthResponse(status="ok", database=True, **info)
