"""AB 1482 rent-cap check (Civil Code 1947.12). Plain Python, no AI. Owner: lane B.

See docs/PLAN.md "Rent-cap detection logic" for the decision order and the required tests.
Decimal only; round down to the cent.
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class RentCap:
    region: str                        # 'san_diego_county'
    period_start: date
    period_end: date                   # inclusive
    cap_pct: Decimal                   # Decimal('8.20') means 8.2%
    source_url: str


@dataclass(frozen=True)
class CheckInput:
    lowest_rent_12mo: Decimal
    new_rent: Decimal
    effective_date: date
    year_built: int | None
    property_type: str                 # 'apartment' | 'condo' | 'single_family' | 'townhouse' | 'unknown'
    got_exemption_notice: bool | None  # None = tenant doesn't know
    owner_is_corporate: bool | None
    other_exemption: bool              # duplex owner on site, dorm, income-restricted
    increases_last_12mo: int


@dataclass(frozen=True)
class CheckResult:
    verdict: str                       # 'over_cap' | 'within_cap' | 'not_covered' | 'unclear'
    cap_pct: Decimal | None
    max_legal_rent: Decimal | None
    overage_monthly: Decimal | None
    reasons: list[str]                 # plain-language lines, shown in the UI and passed to Gemini
    overage_yearly: Decimal | None = None
    increase_pct: Decimal | None = None   # (new - lowest) / lowest x 100, rounded down to 0.1
    third_increase: bool = False          # a third increase within 12 months
    figures: list[str] = field(default_factory=list)  # formatted figures Gemini may cite, e.g. '$2,272.20', '8.2%'


def check_increase(inp: CheckInput, caps: list[RentCap]) -> CheckResult:
    raise NotImplementedError("lane B: api/rules/ab1482.py")
