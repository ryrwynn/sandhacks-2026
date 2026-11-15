"""California Penal Code 396 rent-gouging check (night-rules). Sits beside ab1482.py and never replaces it.

Data: api/rules/data/emergencies.yaml (declarations, extensions, counties, source URLs, dates) and the
HUD (Small Area) Fair Market Rents in api/rules/data/. Money in Decimal, rounded down to the cent.
"""
from datetime import date
from decimal import Decimal
from typing import TypedDict


class GougingResult(TypedDict):
    verdict: str                     # 'likely_violation' | 'within_limit' | 'not_covered' | 'unclear'
    county: str | None
    limit_usd: Decimal | None
    increase_pct: Decimal | None
    basis: str                       # 'pre_emergency_plus_10' | 'fmr_160' | 'none'
    fmr_usd: Decimal | None
    fmr_source: str | None
    emergency: dict | None           # keys of contracts.api_models.EmergencyInfo
    reasons: list[str]


def check_gouging(new_rent: Decimal, offer_date: date, *, zip_: str | None = None, county: str | None = None,
                  pre_emergency_rent: Decimal | None = None, beds: int | None = None) -> GougingResult:
    raise NotImplementedError
