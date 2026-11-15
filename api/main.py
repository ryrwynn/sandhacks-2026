"""RentWatch API. Owner: lane D. This skeleton serves /health only until lane D lands."""
from fastapi import FastAPI

from contracts.api_models import HealthResponse

app = FastAPI(title="RentWatch API", version="0.1.0", root_path="/api")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="degraded", database=False)
