"""Persona scores per ZIP, 0 to 100 (docs/PLAN.md "Persona scores"). Owner: lane C.

Inputs are prices, forecasts, listings and amenities only; never who lives in a ZIP.
"""
from typing import Literal, TypedDict

Persona = Literal["starter", "wealth"]

STARTER_WEIGHTS = {"rent": 0.40, "rent_forecast": 0.20, "basics_density": 0.25,
                   "other_amenities_density": 0.05, "listings_30d": 0.10}
WEALTH_WEIGHTS = {"value_forecast": 0.35, "gross_yield": 0.30, "value_vs_budget": 0.20,
                  "volatility": 0.15}


class ZipScoreInput(TypedDict, total=False):
    zip: str
    typical_rent: float | None              # for the chosen bedroom count, else ZORI
    rent_forecast_change_pct: float | None
    groceries: float | None
    transit_stops: float | None
    parks: float | None
    food_drink: float | None
    gyms: float | None
    area_km2: float | None
    listings_30d: int | None
    typical_home_value: float | None        # latest ZHVI
    value_forecast_change_pct: float | None
    value_volatility_5y: float | None       # std of monthly % changes over 5 years


def score_zips(rows: list[ZipScoreInput], persona: Persona, budget_usd: float,
               weights: dict[str, float] | None = None) -> dict:
    """Min-max scale each feature across the given ZIPs, flip where lower is better, weight, x100.
    Budget is a hard filter: starter compares typical_rent, wealth compares typical_home_value.
    Returns {"weights": {...}, "ranked": [item, ...], "stretch": [item, ...]} where item is
    {"zip", "score", "price_usd", "top_contributions": [{"feature", "label", "points", "value"}] (3)}.
    ranked and stretch are each sorted by score, highest first."""
    raise NotImplementedError("lane C: score_zips")
