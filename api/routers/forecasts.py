"""Scenario series (night-forecast). GET /zips/{zip}/series?scenario= is routed in zips.py, which calls
scenario_series() here only when ?scenario= is given, so the default response never changes."""
from fastapi import APIRouter

from api.ml import scenarios
from api.routers._stub import not_built
from contracts.api_models import SeriesResponse

router = APIRouter(tags=["forecasts"])


def scenario_series(zip_: str, metric: str, scenario: str) -> SeriesResponse:
    try:
        r = scenarios.scenario_series(zip_, metric, scenario)
    except NotImplementedError:
        raise not_built("Scenario forecasts")
    return SeriesResponse(zip=zip_, metric=metric, scenario=scenario, **r)
