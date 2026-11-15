"""API request and response models: the source of /api/openapi.json (docs/PLAN.md "API contract and pages").

Every router in api/routers/ uses these models exactly; the web client is generated from them.
Money is sent as JSON numbers in dollars (rules code works in Decimal and the router converts),
percentages as numbers where 8.2 means 8.2%, and dates as ISO strings.
Generated text fields (summary, explanation, letter) are always optional: null means Gemini
gave nothing usable and the page shows the numbers alone.
"""
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

Verdict = Literal["over_cap", "within_cap", "not_covered", "unclear"]
Persona = Literal["starter", "wealth"]
Metric = Literal["zori", "zhvi"]
Lang = Literal["en", "es", "vi", "tl"]
PropertyType = Literal["apartment", "condo", "single_family", "townhouse", "unknown"]
FairRentLabel = Literal["above_typical_range", "in_range", "below_typical_range"]
EstimateMethod = Literal["model", "zip_bed_median"]

DISCLAIMER_LEGAL = (
    "This is not legal advice. For help with a rent increase, contact the Legal Aid Society of "
    "San Diego (lassd.org, 877-534-2524)."
)
DISCLAIMER_ESTIMATE = "Estimates with ranges from public data, not financial advice or measured results."


# ---------- GET /health ----------
class ModelRunSummary(BaseModel):
    run_id: UUID
    kind: Literal["fair_rent", "forecast"]
    trained_at: datetime
    n_rows: int | None = None
    metrics: dict = Field(default_factory=dict)   # e.g. {"mae_usd": 212.0, "coverage_80": 0.79}


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: bool
    last_scrape_at: datetime | None = None
    row_counts: dict[str, int] = Field(default_factory=dict)   # table or source_key -> rows
    model_runs: list[ModelRunSummary] = Field(default_factory=list)


# ---------- GET /zips ----------
class ZipSummary(BaseModel):
    zip: str
    name: str                                       # 'North Park'
    median_rent_by_beds: dict[str, int | None]      # keys '0' (studio) to '3'; last 30 days of listings
    typical_rent_usd: float | None = None           # latest ZORI
    typical_home_value_usd: float | None = None     # latest ZHVI
    rent_forecast_change_pct: float | None = None   # 12-month forecast change of ZORI
    value_forecast_change_pct: float | None = None  # 12-month forecast change of ZHVI
    listings_30d: int = 0


class ZipsResponse(BaseModel):
    zips: list[ZipSummary]


# ---------- GET /zips/{zip} ----------
class AmenityCounts(BaseModel):
    groceries: int | None = None
    transit_stops: int | None = None
    parks: int | None = None
    food_drink: int | None = None
    gyms: int | None = None
    area_km2: float | None = None


class ZipProfile(BaseModel):
    zip: str
    name: str
    typical_rent_usd: float | None = None
    typical_home_value_usd: float | None = None
    median_rent_by_beds: dict[str, int | None] = Field(default_factory=dict)
    rent_forecast_change_pct: float | None = None
    value_forecast_change_pct: float | None = None
    median_income_usd: float | None = None          # context only, never a score input
    rent_burden_pct: float | None = None            # typical rent / monthly median income; context only
    gross_yield_pct: float | None = None            # 12 x typical rent / typical home value
    amenities: AmenityCounts
    persona_scores: dict[Persona, float | None]     # 0 to 100, default weights, no budget filter
    listings_30d: int = 0


# ---------- GET /zips/{zip}/series?metric= ----------
class SeriesPoint(BaseModel):
    month: date
    value: float
    lo80: float | None = None
    hi80: float | None = None
    kind: Literal["actual", "forecast"]


class SeriesResponse(BaseModel):
    zip: str
    metric: Metric
    points: list[SeriesPoint]
    run_id: UUID | None = None
    backtest_mape: float | None = None      # 12-month holdout error of the model, in %
    naive_mape: float | None = None         # same holdout, "next year equals this month"
    beats_naive: bool | None = None


# ---------- POST /checks ----------
class CheckRequest(BaseModel):
    address: str
    zip: str | None = None
    lowest_rent_12mo: float = Field(gt=0)
    new_rent: float = Field(gt=0)
    effective_date: date
    year_built: int | None = None
    property_type: PropertyType = "unknown"
    got_exemption_notice: bool | None = None   # None = tenant doesn't know
    owner_is_corporate: bool | None = None
    other_exemption: bool = False              # duplex owner on site, dorm, income-restricted
    increases_last_12mo: int = Field(default=0, ge=0)
    is_demo: bool = False


class CheckResponse(BaseModel):
    check_id: UUID
    verdict: Verdict
    cap_pct: float | None = None
    max_legal_rent: float | None = None
    increase_pct: float                         # (new - lowest) / lowest, in %
    overage_monthly: float | None = None
    overage_yearly: float | None = None
    third_increase: bool = False                # flags a third increase within 12 months
    reasons: list[str]
    disclaimer: str = DISCLAIMER_LEGAL


# ---------- POST /checks/{id}/letter?lang= ----------
class LetterResponse(BaseModel):
    check_id: UUID
    lang: Lang
    explanation: str | None = None              # 3 to 5 sentences in `lang`
    letter_en: str | None = None                # English letter; [Tenant name], [Landlord name] placeholders
    figures: list[str] = Field(default_factory=list)   # the figures the text may cite
    disclaimer: str = DISCLAIMER_LEGAL


# ---------- GET /units/search?address= ----------
class UnitMatch(BaseModel):
    property_id: int
    address_norm: str
    unit_label: str | None = None
    zip: str
    beds: int | None = None
    year_built: int | None = None
    property_type: str | None = None


class UnitSearchResponse(BaseModel):
    query: str
    results: list[UnitMatch]


# ---------- POST /listings/evaluate ----------
class ListingEvalRequest(BaseModel):
    zip: str
    beds: int = Field(ge=0)
    asking_rent: float = Field(gt=0)
    baths: float | None = None
    sqft: int | None = None
    year_built: int | None = None
    property_type: PropertyType = "unknown"
    lat: float | None = None
    lng: float | None = None
    text: str | None = None                     # optional pasted listing; parsed to fill missing facts


class FairRentEstimate(BaseModel):
    low: float                                  # 10th percentile
    expected: float                             # median
    high: float                                 # 90th percentile
    method: EstimateMethod
    mae_usd: float | None = None                # cross-validated median absolute error
    coverage_80: float | None = None            # share of held-out rents inside the 80% range


class ListingEvalResponse(BaseModel):
    estimate: FairRentEstimate
    asking_rent: float
    label: FairRentLabel
    percentile: float | None = None             # asking rent's percentile among comparables, 0 to 100
    n_comparables: int
    parsed_fields: dict | None = None           # what Gemini read from `text`, when given
    disclaimer: str = DISCLAIMER_ESTIMATE


# ---------- POST /neighborhoods/rank ----------
class RankRequest(BaseModel):
    persona: Persona
    budget_usd: float = Field(gt=0)             # monthly rent (starter) or home price (wealth)
    beds: int | None = Field(default=None, ge=0)
    weights: dict[str, float] | None = None     # custom weights (stretch); keys from `weights` in the response


class Contribution(BaseModel):
    feature: str                                # 'rent', 'rent_forecast', 'basics_density', ...
    label: str                                  # 'Low typical rent'
    points: float                               # points this feature added to the score
    value: float | None = None                  # the raw feature value


class RankedZip(BaseModel):
    rank: int
    zip: str
    name: str
    score: float                                # 0 to 100
    price_usd: float | None = None              # typical rent (starter) or home value (wealth)
    top_contributions: list[Contribution]       # the three largest
    summary: str | None = None                  # Gemini "why this ZIP", top 3 ranked only


class RankResponse(BaseModel):
    persona: Persona
    budget_usd: float
    beds: int | None = None
    weights: dict[str, float]
    ranked: list[RankedZip]                     # within budget
    stretch: list[RankedZip]                    # above budget
    disclaimer: str = DISCLAIMER_ESTIMATE


# ---------- POST /owner/price-position ----------
class PricePositionRequest(BaseModel):
    zip: str
    beds: int = Field(ge=0)
    target_rent: float = Field(gt=0)
    baths: float | None = None
    sqft: int | None = None
    year_built: int | None = None
    property_type: PropertyType = "unknown"
    occupied: bool = False                      # a current tenant stays: show the legal maximum
    lowest_rent_12mo: float | None = None
    effective_date: date | None = None
    got_exemption_notice: bool | None = None
    owner_is_corporate: bool | None = None


class PricePoint(BaseModel):
    label: Literal["low", "expected", "high", "target"]
    rent_usd: float
    percentile: float | None = None             # 0 to 100 among comparable active listings
    reach_score: float | None = None            # 0 to 100, higher = more renters likely to consider it


class DaysOnMarket(BaseModel):
    below_expected_median_days: float | None = None
    above_expected_median_days: float | None = None
    n_listings: int


class LegalGuardrail(BaseModel):
    verdict: Verdict
    cap_pct: float | None = None
    max_legal_rent: float | None = None
    reasons: list[str]


class PricePositionResponse(BaseModel):
    estimate: FairRentEstimate
    points: list[PricePoint]
    n_comparables: int
    days_on_market: DaysOnMarket | None = None  # null when the data has no listing/removal events
    legal: LegalGuardrail | None = None         # only when occupied
    disclaimer: str = DISCLAIMER_ESTIMATE


# ---------- POST /owner/listing-analysis ----------
class ListingAnalysisRequest(BaseModel):
    zip: str
    beds: int = Field(ge=0)
    text: str | None = None                     # the owner's listing text, or...
    listing_id: int | None = None               # ...a listing already in the scraped data
    target_rent: float | None = None


class Gap(BaseModel):
    fact: str                                   # 'parking', 'pets', 'laundry', ...
    share_of_comparables: float                 # 0 to 1: how many comparables state it


class ListingAnalysisResponse(BaseModel):
    completeness: float                         # 0 to 100
    readability: float                          # 0 to 100
    reach_score: float                          # completeness x price-position factor, 0 to 100
    stated: dict[str, bool]                     # fact -> whether the listing states it
    gaps: list[Gap]                             # facts most comparables state that this one doesn't
    n_comparables: int
    explanation: str | None = None              # Gemini, 2 to 4 sentences; never a rewritten listing
    disclaimer: str = "A prediction from comparable listings, not measured clicks."
