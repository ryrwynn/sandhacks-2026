"""Scenario series (night-forecast). GET /zips/{zip}/series?scenario= is routed in zips.py, which calls
scenario_series() here only when ?scenario= is given, so the default response never changes."""
from fastapi import APIRouter, HTTPException

from api import db
from api.ml import scenarios
from contracts.api_models import SeriesResponse

router = APIRouter(tags=["forecasts"])


def scenario_series(zip_: str, metric: str, scenario: str) -> SeriesResponse:
    try:
        r = scenarios.scenario_series(zip_, metric, scenario)
    except LookupError as e:
        # Sprint: a served ZIP without scenario forecasts yet (new areas before a retrain, or under 60 months of
        # history) gets its actual history and no scenario lines, not a 404. An empty history is an empty series; unserved ZIPs still 404 in zips.py.
        try:
            hist = [h for h in db.series(zip_, metric) if h["kind"] == "actual"]
        except db.DBUnavailable:
            raise HTTPException(503, "Database unavailable")
        r = {"points": [scenarios._pt(h["month"], h["value"], None, None, "actual") for h in hist]}
    except db.DBUnavailable:
        raise HTTPException(503, "Database unavailable")
    return SeriesResponse(zip=zip_, metric=metric, scenario=scenario, **r)
