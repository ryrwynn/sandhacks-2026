// Hand-written mirror of "Overnight additions" in contracts/api_models.py. Swap for api.generated.ts at merge.
import type { Metric, PropertyType } from "./contract";
import type { ListingSummary } from "./tracker";

export type SeriesPoint = { month: string; value: number; lo80?: number | null; hi80?: number | null; kind: "actual" | "forecast" };
export type Scenario = "baseline" | "recession" | "growth";
export type ScenarioPath = {
  scenario: Scenario; model: string; points: SeriesPoint[]; change_12m_pct?: number | null;
  backtest_mape?: number | null; coverage_80?: number | null; assumptions: string[];
};
export type SeriesScenarioResponse = {
  zip: string; metric: Metric; points: SeriesPoint[]; run_id?: string | null;
  backtest_mape?: number | null; naive_mape?: number | null; beats_naive?: boolean | null;
  scenario?: Scenario | null; scenarios: ScenarioPath[]; coverage_80?: number | null;
};

// Coverage
export type Tier = "core" | "county" | "index" | "on_demand";
export type GeoType = "zip" | "city";
export type AreaRequestState = "queued" | "scraping" | "loaded" | "failed" | "over_budget";
export type AreaSummary = {
  geo_type: GeoType; geo_id: string; name: string; county?: string | null; tier: Tier;
  centroid_lat?: number | null; centroid_lng?: number | null; has_listings: boolean;
  typical_rent_usd?: number | null; typical_home_value_usd?: number | null; last_scraped_at?: string | null;
};
export type AreasResponse = { areas: AreaSummary[]; total: number; counts_by_tier: Record<string, number> };
export type AreaRequestCreate = { query: string };
export type AreaRequestStatus = {
  request_id: string; geo_type: GeoType; geo_id: string; name: string; query: string; status: AreaRequestState;
  est_records?: number | null; est_cost_usd?: number | null; queue_position?: number | null;
  budget_remaining_usd?: number | null; requested_at: string; finished_at?: string | null; message: string; already_covered: boolean;
};
export type GeoFile = { county: string; url: string; n_zips: number };
export type GeoZipsResponse = { bbox: number[]; files: GeoFile[]; zips: string[]; index_url: string };

// Trends
export type SignalKind = "fast_rise" | "fast_fall" | "accelerating" | "decelerating" | "volatile" | "above_zip_trend" | "below_zip_trend" | "relist_jump" | "repeated_cuts";
export type TrendSignal = { kind: SignalKind; label: string; detail?: string | null };
export type TrendMetrics = {
  metric: Metric; as_of: string; latest_usd: number; yoy_pct?: number | null; momentum_3m_pct?: number | null;
  acceleration_pp?: number | null; volatility_pct?: number | null; county_percentile?: number | null;
};
export type ZipTrendsResponse = { zip: string; name: string; rent?: TrendMetrics | null; value?: TrendMetrics | null; signals: TrendSignal[]; disclaimer: string };
export type PriceChange = { date: string; from_usd: number; to_usd: number; change_pct: number; kind: "cut" | "raise" | "relist_jump"; days_since_previous?: number | null };
export type ListingTrendsResponse = {
  listing_id: number; zip?: string | null; first_price_usd: number; current_price_usd: number; total_change_pct: number;
  zip_change_pct?: number | null; vs_zip_pp?: number | null; changes: PriceChange[]; signals: TrendSignal[]; n_observations: number; disclaimer: string;
};

// Gouging
export type GougingVerdict = "likely_violation" | "within_limit" | "not_covered" | "unclear";
export type Link = { label: string; url: string };
export type GougingRequest = {
  zip?: string | null; county?: string | null; new_rent: number; offer_date: string;
  pre_emergency_rent?: number | null; beds?: number | null; is_demo?: boolean;
};
export type EmergencyInfo = { title: string; counties: string[]; declared_on: string; protections_until?: string | null; extensions: string[]; source_url: string };
export type GougingResponse = {
  verdict: GougingVerdict; county?: string | null; limit_usd?: number | null; increase_pct?: number | null;
  basis: "pre_emergency_plus_10" | "fmr_160" | "none"; fmr_usd?: number | null; fmr_source?: string | null;
  emergency?: EmergencyInfo | null; reasons: string[]; links: Link[]; disclaimer: string;
};

// Matching
export type MatchRequest = { text: string; limit?: number; budget_max_usd?: number | null; beds_min?: number | null };
export type ParsedNeeds = {
  budget_min_usd?: number | null; budget_max_usd?: number | null; beds_min?: number | null; beds_max?: number | null;
  zips: string[]; areas: string[]; property_types: PropertyType[]; must_haves: string[]; nice_to_haves: string[];
  commute_anchors: string[]; parsed_by: "gemini" | "rules";
};
export type MatchResult = { listing: ListingSummary; score: number; components: Record<string, number>; reasons: string[]; unconfirmed: string[] };
export type MatchResponse = { needs: ParsedNeeds; results: MatchResult[]; n_candidates: number; n_after_filters: number; method: "embeddings" | "keywords"; disclaimer: string };

// Owner reach
export type OwnerReachRequest = {
  zip: string; beds: number; target_rent: number; listing_id?: number | null; text?: string | null;
  stated?: Record<string, boolean> | null; baths?: number | null; sqft?: number | null;
};
export type ReachProfile = { id: string; label: string; beds: number; max_rent_usd: number; must_haves: string[]; weight: number };
export type ReachPoint = { rent_usd: number; reach_pct: number };
export type ReachChange = {
  kind: "price" | "fact"; label: string; new_rent_usd?: number | null; fact?: string | null;
  reach_before_pct: number; reach_after_pct: number; gain_pts: number;
};
export type OwnerReachResponse = {
  current_reach_pct: number; curve: ReachPoint[]; best_changes: ReachChange[]; profiles: ReachProfile[];
  n_comparables: number; method_note: string; disclaimer: string;
};
