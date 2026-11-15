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


class SourceCount(BaseModel):                     # per-source listing counts (morning run)
    source_key: str
    kind: str                                       # 'listing_site' | 'social' | ...
    listings: int
    active: int


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: bool
    last_scrape_at: datetime | None = None
    row_counts: dict[str, int] = Field(default_factory=dict)   # table or source_key -> rows
    model_runs: list[ModelRunSummary] = Field(default_factory=list)
    sources: list[SourceCount] = Field(default_factory=list)


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
    sources: "SourceBreakdown | None" = None        # morning run: active listings by source
    listing_sites_only: bool = False


# ---------- GET /zips/{zip}/series?metric= ----------
class SeriesPoint(BaseModel):
    month: date
    value: float
    lo80: float | None = None
    hi80: float | None = None
    kind: Literal["actual", "forecast"]


Scenario = Literal["baseline", "recession", "growth"]


class ScenarioPath(BaseModel):                  # one macro scenario's forecast (night: scenario_forecasts)
    scenario: Scenario
    model: str                                  # 'sarimax_x' | 'pooled_x' | 'ets'
    points: list[SeriesPoint]                   # forecast months only, kind = 'forecast'
    change_12m_pct: float | None = None         # 12-month change from the latest actual
    backtest_mape: float | None = None
    coverage_80: float | None = None            # held-out share of actuals inside the 80% band
    assumptions: list[str] = Field(default_factory=list)   # e.g. 'Unemployment peaks at 10% (Fed severely adverse)'


class SeriesResponse(BaseModel):
    zip: str
    metric: Metric
    points: list[SeriesPoint]
    run_id: UUID | None = None
    backtest_mape: float | None = None      # 12-month holdout error of the model, in %
    naive_mape: float | None = None         # same holdout, "next year equals this month"
    beats_naive: bool | None = None
    # Overnight additions. Without ?scenario= these stay null/empty and the response is as before.
    # With ?scenario=X, `points` carries actuals plus scenario X's forecast (its cone), and `scenarios`
    # carries every scenario's path so the UI can show them side by side.
    scenario: Scenario | None = None
    scenarios: list[ScenarioPath] = Field(default_factory=list)
    coverage_80: float | None = None


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


# ---------- Tracker endpoints (docs/DESIGN.md) ----------
# Price history comes only from stored price_observations: the source's own history events plus each
# scrape's sightings. Nothing is interpolated or invented; a month with no observation has no point.
ObservationEvent = Literal["history", "seen", "price_change", "removed", "posted"]
MarketRange = Literal["1m", "3m", "6m", "1y", "all"]
ListingSort = Literal["recent", "price_asc", "price_desc", "biggest_drop"]


class SparkPoint(BaseModel):
    month: date                                 # first of the month
    price_usd: float                            # the last observed asking rent in that month


SourceKind = Literal["listing_site", "social"]
UnitType = Literal["entire_unit", "room", "sublet"]
LocationPrecision = Literal["address", "street", "zip", "neighborhood", "city"]
ListingSource = Literal["all", "listing_sites", "facebook"]


class ListingSummary(BaseModel):                # GET /listings items; also the head of GET /listings/{id}
    id: int                                     # listings.listing_id
    address: str | None = None                  # display address, e.g. '2519 El Cajon Blvd'
    unit_label: str | None = None
    neighborhood: str | None = None             # ZIP's neighborhood name, e.g. 'North Park'
    zip: str | None = None
    beds: int | None = None                     # 0 = studio
    baths: float | None = None
    sqft: int | None = None
    property_type: str | None = None
    listing_type: Literal["rent", "sale"] = "rent"
    current_price_usd: float                    # the latest observed price
    first_price_usd: float                      # the first observed price
    first_observed: date
    n_observations: int                         # real observations behind the sparkline
    sparkline: list[SparkPoint]                 # monthly, from real observations only; may be a single point
    fair_rent_label: FairRentLabel | None = None   # null when there aren't enough comparables
    last_seen: datetime
    active: bool                                # seen in the latest scrape; Facebook: posted in the last 21 days
    source_url: str | None = None               # public listing-site page; null for social posts and unknown
    # Morning run: Facebook group listings. Never post text, author names, profile links or photos.
    source_kind: SourceKind = "listing_site"
    source_label: str | None = None             # 'Zillow', 'Facebook group'
    unit_type: UnitType | None = None           # Facebook only; listing-site rows are whole units
    location_precision: LocationPrecision = "address"
    post_url: str | None = None                 # Facebook: the public group post, so a renter can act on it
    group_name: str | None = None               # Facebook: the group's public name
    posted_at: datetime | None = None           # Facebook: the latest post (or repost)
    available_date: date | None = None
    amenities: list[str] = Field(default_factory=list)   # Facebook: pets_allowed, parking, laundry, utilities_included
    unusual_price: bool = False                 # below 40% or above 250% of the ZIP's listing-site median
    trust_weight: float = 1.0                   # Facebook 0.5


class ListingsResponse(BaseModel):
    items: list[ListingSummary]
    total: int                                  # matches before limit/offset
    limit: int
    offset: int


class Observation(BaseModel):
    date: date
    event: ObservationEvent
    price_usd: float


class ZipForecastSummary(BaseModel):
    zip: str
    name: str
    metric: Metric = "zori"
    latest_usd: float | None = None
    forecast_12m_usd: float | None = None
    change_pct: float | None = None             # 12-month forecast change
    lo80_usd: float | None = None
    hi80_usd: float | None = None
    backtest_mape: float | None = None
    naive_mape: float | None = None
    beats_naive: bool | None = None             # shown as-is: most series do not beat naive


class ListingDetail(ListingSummary):            # GET /listings/{id}
    observations: list[Observation]             # every stored price observation, oldest first
    year_built: int | None = None
    estimate: FairRentEstimate | None = None    # "what it should rent for"; null when not enough comparables
    percentile: float | None = None             # current price's percentile among same-ZIP, same-bedroom listings
    n_comparables: int = 0
    forecast: ZipForecastSummary | None = None
    disclaimer: str = DISCLAIMER_ESTIMATE


class MarketPoint(BaseModel):
    month: date
    value: float
    basis: Literal["zori", "listings"]          # where this month's number came from
    n_listings: int | None = None               # listings behind a 'listings' month


class MarketForecastPoint(BaseModel):
    month: date
    value: float
    lo80: float
    hi80: float


class SourceStat(BaseModel):
    count: int = 0
    median_usd: float | None = None


class SourceBreakdown(BaseModel):               # active rental listings by where they came from
    listing_sites: SourceStat = Field(default_factory=SourceStat)
    facebook: SourceStat = Field(default_factory=SourceStat)        # whole units; median excludes unusual prices
    facebook_rooms: SourceStat = Field(default_factory=SourceStat)  # rooms and sublets, never in unit medians
    facebook_unusual: int = 0                   # whole units flagged "unusual price" (counted, not in the median)
    facebook_weight: float = 0.5
    listing_sites_only: bool = False            # when true, Facebook rows are left out of counts and medians


class MarketResponse(BaseModel):                # GET /market?zip=&beds=&type=&range=&listing_sites_only=
    zip: str | None = None                      # null = all 12 ZIPs
    beds: int | None = None
    property_type: str | None = None
    range: MarketRange = "1y"
    points: list[MarketPoint]                   # monthly; ZORI for any bedrooms, listing medians by bedroom
                                                # count with a ZORI fallback under 5 listings in a month
    forecast: list[MarketForecastPoint] = Field(default_factory=list)   # next 12 months with the 80% band
    current_value: float | None = None
    change_pct: float | None = None             # current vs the first point in `range`
    change_since: date | None = None
    active_listings: int = 0
    updated_at: datetime | None = None          # last scrape
    backtest_mape: float | None = None
    naive_mape: float | None = None
    beats_naive: bool | None = None
    notes: list[str] = Field(default_factory=list)   # e.g. which months fell back to ZORI and why
    disclaimer: str = DISCLAIMER_ESTIMATE
    sources: SourceBreakdown = Field(default_factory=SourceBreakdown)
    listing_sites_only: bool = False


# ======================================================================================
# Overnight additions (docs/NIGHT.md, Phase 1). One fixture each in contracts/fixtures/.
# ======================================================================================

# ---------- Coverage: GET /areas, POST /areas/requests, GET /areas/requests/{id}, GET /geo/zips ----------
Tier = Literal["core", "county", "index", "on_demand"]
GeoType = Literal["zip", "city"]
AreaRequestState = Literal["queued", "scraping", "loaded", "failed", "over_budget"]


class AreaSummary(BaseModel):
    geo_type: GeoType
    geo_id: str                                 # '92037' or a city slug
    name: str
    county: str | None = None
    tier: Tier
    centroid_lat: float | None = None
    centroid_lng: float | None = None
    has_listings: bool = False                  # core/county/loaded on_demand; index tier is ZORI/ZHVI/ACS only
    typical_rent_usd: float | None = None       # latest ZORI
    typical_home_value_usd: float | None = None # latest ZHVI
    last_scraped_at: datetime | None = None


class AreasResponse(BaseModel):                 # GET /areas?tier=&county=&q=&limit=
    areas: list[AreaSummary]
    total: int
    counts_by_tier: dict[str, int] = Field(default_factory=dict)


class AreaRequestCreate(BaseModel):             # POST /areas/requests
    query: str = Field(min_length=2, max_length=80)   # a California ZIP or city name


class AreaRequestStatus(BaseModel):             # POST /areas/requests and GET /areas/requests/{id}
    request_id: UUID
    geo_type: GeoType
    geo_id: str
    name: str
    query: str
    status: AreaRequestState
    est_records: int | None = None
    est_cost_usd: float | None = None
    queue_position: int | None = None           # 1 = next; null once started
    budget_remaining_usd: float | None = None   # today's on-demand budget left
    requested_at: datetime
    finished_at: datetime | None = None
    message: str                                # plain sentence for the UI, e.g. 'Queued: 3rd in line, about $0.45'
    already_covered: bool = False               # the area is already core/county/loaded


class GeoFile(BaseModel):
    county: str                                 # 'San Diego'
    url: str                                    # '/geo/san-diego.geojson' (served by the frontend)
    n_zips: int


class GeoZipsResponse(BaseModel):               # GET /geo/zips?bbox=minLng,minLat,maxLng,maxLat
    bbox: list[float]                           # the bbox echoed back
    files: list[GeoFile]                        # county files the viewport needs
    zips: list[str]                             # ZCTAs that intersect the bbox
    index_url: str = "/geo/index.json"


# ---------- Trends: GET /zips/{zip}/trends, GET /listings/{id}/trends ----------
TREND_DISCLAIMER = "Market signals from public data, not legal findings or financial advice."
SignalKind = Literal["fast_rise", "fast_fall", "accelerating", "decelerating", "volatile",
                     "above_zip_trend", "below_zip_trend", "relist_jump", "repeated_cuts"]


class TrendSignal(BaseModel):
    kind: SignalKind
    label: str                                  # 'Rents rising faster than 90% of San Diego ZIPs'
    detail: str | None = None


class TrendMetrics(BaseModel):
    metric: Metric
    as_of: date
    latest_usd: float
    yoy_pct: float | None = None                # 12-month change
    momentum_3m_pct: float | None = None        # 3-month change, annualized
    acceleration_pp: float | None = None        # change in YoY vs 3 months earlier, percentage points
    volatility_pct: float | None = None         # std of monthly % changes over 24 months
    county_percentile: float | None = None      # YoY's percentile among county ZIPs, 0 to 100


class ZipTrendsResponse(BaseModel):
    zip: str
    name: str
    rent: TrendMetrics | None = None
    value: TrendMetrics | None = None
    signals: list[TrendSignal] = Field(default_factory=list)
    disclaimer: str = TREND_DISCLAIMER


class PriceChange(BaseModel):
    date: date
    from_usd: float
    to_usd: float
    change_pct: float
    kind: Literal["cut", "raise", "relist_jump"]   # relist_jump: back on market at a higher price after removal
    days_since_previous: int | None = None


class ListingTrendsResponse(BaseModel):
    listing_id: int
    zip: str | None = None
    first_price_usd: float
    current_price_usd: float
    total_change_pct: float
    zip_change_pct: float | None = None         # the ZIP's ZORI change over the same dates
    vs_zip_pp: float | None = None              # total_change_pct - zip_change_pct
    changes: list[PriceChange] = Field(default_factory=list)
    signals: list[TrendSignal] = Field(default_factory=list)
    n_observations: int
    disclaimer: str = TREND_DISCLAIMER


# ---------- Gouging: POST /checks/gouging (California Penal Code 396) ----------
GougingVerdict = Literal["likely_violation", "within_limit", "not_covered", "unclear"]


class Link(BaseModel):
    label: str
    url: str


GOUGING_LINKS = [
    Link(label="Legal Aid Society of San Diego", url="https://www.lassd.org/"),
    Link(label="California Attorney General: price gouging", url="https://oag.ca.gov/consumers/pricegougingduringdisasters"),
]
DISCLAIMER_GOUGING = (
    "This is not legal advice. Penal Code 396 applies only during a declared emergency; for help, contact the "
    "Legal Aid Society of San Diego or the California Attorney General."
)


class GougingRequest(BaseModel):
    zip: str | None = None
    county: str | None = None                   # derived from zip when null
    new_rent: float = Field(gt=0)
    offer_date: date                            # when the new price was charged or offered
    pre_emergency_rent: float | None = Field(default=None, gt=0)   # null = not rented or offered before
    beds: int | None = Field(default=None, ge=0)                    # for the HUD FMR rule
    is_demo: bool = False


class EmergencyInfo(BaseModel):
    title: str                                  # 'Los Angeles County wildfires'
    counties: list[str]
    declared_on: date
    protections_until: date | None = None       # after extensions
    extensions: list[date] = Field(default_factory=list)
    source_url: str


class GougingResponse(BaseModel):
    verdict: GougingVerdict
    county: str | None = None
    limit_usd: float | None = None              # the highest price allowed
    increase_pct: float | None = None           # vs pre_emergency_rent
    basis: Literal["pre_emergency_plus_10", "fmr_160", "none"]
    fmr_usd: float | None = None                # HUD (Small Area) FMR used for the 160% rule
    fmr_source: str | None = None               # 'HUD SAFMR FY2026, ZIP 92104, 1 bedroom'
    emergency: EmergencyInfo | None = None
    reasons: list[str]
    links: list[Link] = Field(default_factory=lambda: list(GOUGING_LINKS))
    disclaimer: str = DISCLAIMER_GOUGING


# ---------- Matching: POST /match ----------
class MatchRequest(BaseModel):
    text: str = Field(min_length=3, max_length=2000)   # 'quiet 1BR under $2,400 near UCSD, cat ok, parking'
    limit: int = Field(default=10, ge=1, le=50)
    budget_max_usd: float | None = None         # overrides what the parser read, when the UI has a slider
    beds_min: int | None = None


class ParsedNeeds(BaseModel):
    budget_min_usd: float | None = None
    budget_max_usd: float | None = None
    beds_min: int | None = None
    beds_max: int | None = None
    zips: list[str] = Field(default_factory=list)
    areas: list[str] = Field(default_factory=list)          # names the user gave ('North Park')
    property_types: list[PropertyType] = Field(default_factory=list)
    must_haves: list[str] = Field(default_factory=list)     # 'pets', 'parking', 'laundry', ...
    nice_to_haves: list[str] = Field(default_factory=list)
    commute_anchors: list[str] = Field(default_factory=list)  # 'UCSD', 'Downtown'
    parsed_by: Literal["gemini", "rules"] = "rules"


class MatchResult(BaseModel):
    listing: ListingSummary
    score: float                                # 0 to 100
    components: dict[str, float]                # 'price_fit', 'amenity_fit', 'fair_rent', 'semantic' -> points
    reasons: list[str]                          # why it scored well, plain sentences
    unconfirmed: list[str] = Field(default_factory=list)   # must-haves the listing doesn't state


class MatchResponse(BaseModel):
    needs: ParsedNeeds
    results: list[MatchResult]
    n_candidates: int
    n_after_filters: int
    method: Literal["embeddings", "keywords"]   # keywords when embeddings are unavailable
    disclaimer: str = DISCLAIMER_ESTIMATE


# ---------- Owner reach: POST /owner/reach ----------
class OwnerReachRequest(BaseModel):
    zip: str
    beds: int = Field(ge=0)
    target_rent: float = Field(gt=0)
    listing_id: int | None = None
    text: str | None = None
    stated: dict[str, bool] | None = None       # fact -> stated; parsed from text/listing when null
    baths: float | None = None
    sqft: int | None = None


class ReachProfile(BaseModel):                  # a fixed, documented renter-need profile built from listings
    id: str                                     # 'p2_1br_2400_pets'
    label: str                                  # '1 bedroom, up to $2,400, needs pets allowed'
    beds: int
    max_rent_usd: float
    must_haves: list[str]
    weight: float                               # share of comparable demand this profile stands for, 0 to 1


class ReachPoint(BaseModel):
    rent_usd: float
    reach_pct: float                            # weighted share of profiles that would shortlist it


class ReachChange(BaseModel):
    kind: Literal["price", "fact"]
    label: str                                  # 'Lower the rent to $2,350' / 'State whether pets are allowed'
    new_rent_usd: float | None = None
    fact: str | None = None
    reach_before_pct: float
    reach_after_pct: float
    gain_pts: float


class OwnerReachResponse(BaseModel):
    current_reach_pct: float
    curve: list[ReachPoint]                     # reach at a range of prices around target_rent
    best_changes: list[ReachChange]             # biggest gains first
    profiles: list[ReachProfile]
    n_comparables: int
    method_note: str
    disclaimer: str = "An estimate from comparable listings and fixed renter profiles, not measured demand."


# ---------- Accounts: GET /account/saves, PUT /account/saves ----------
# Called only by the Next.js server (never the browser) with two headers:
#   X-Account-Token: the shared ACCOUNT_API_TOKEN (env); missing or wrong -> 401
#   X-Subject-Hash:  sha256 hex of (AUTH_SECRET + Google subject ID); no email or name ever reaches the API
# With ACCOUNT_API_TOKEN unset the endpoints return 404 (feature off).
class SavedItem(BaseModel):
    listing_id: int
    saved_at: datetime
    price_at_save: float | None = None
    target: float | None = None                 # target-rent alert, dollars


class AccountSavesResponse(BaseModel):
    items: list[SavedItem]


class PutSavesRequest(BaseModel):
    items: list[SavedItem]
    merge: bool = True                          # true: union with stored saves (first sign-in); false: replace


ZipProfile.model_rebuild()   # SourceBreakdown is defined after ZipProfile
