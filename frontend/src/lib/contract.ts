// Hand-written from contracts/api_models.py. Replaced later by api.generated.ts (from /api/openapi.json).
export type Verdict = "over_cap" | "within_cap" | "not_covered" | "unclear";
export type Persona = "starter" | "wealth";
export type Metric = "zori" | "zhvi";
export type Lang = "en" | "es" | "vi" | "tl";
export type PropertyType = "apartment" | "condo" | "single_family" | "townhouse" | "unknown";
export type FairRentLabel = "above_typical_range" | "in_range" | "below_typical_range";
export type EstimateMethod = "model" | "zip_bed_median";

export const DISCLAIMER_LEGAL =
  "This is not legal advice. For help with a rent increase, contact the Legal Aid Society of San Diego (lassd.org, 877-534-2524).";
export const DISCLAIMER_ESTIMATE = "Estimates with ranges from public data, not financial advice or measured results.";

export interface ModelRunSummary { run_id: string; kind: "fair_rent" | "forecast"; trained_at: string; n_rows?: number | null; metrics: Record<string, number>; }
export interface HealthResponse { status: "ok" | "degraded"; database: boolean; last_scrape_at?: string | null; row_counts: Record<string, number>; model_runs: ModelRunSummary[]; }

export interface ZipSummary {
  zip: string; name: string;
  median_rent_by_beds: Record<string, number | null>;
  typical_rent_usd?: number | null; typical_home_value_usd?: number | null;
  rent_forecast_change_pct?: number | null; value_forecast_change_pct?: number | null;
  listings_30d: number;
}
export interface ZipsResponse { zips: ZipSummary[]; }

export interface AmenityCounts { groceries?: number | null; transit_stops?: number | null; parks?: number | null; food_drink?: number | null; gyms?: number | null; area_km2?: number | null; }
export interface ZipProfile {
  zip: string; name: string;
  typical_rent_usd?: number | null; typical_home_value_usd?: number | null;
  median_rent_by_beds: Record<string, number | null>;
  rent_forecast_change_pct?: number | null; value_forecast_change_pct?: number | null;
  median_income_usd?: number | null; rent_burden_pct?: number | null; gross_yield_pct?: number | null;
  amenities: AmenityCounts;
  persona_scores: Partial<Record<Persona, number | null>>;
  listings_30d: number;
}

export interface SeriesPoint { month: string; value: number; lo80?: number | null; hi80?: number | null; kind: "actual" | "forecast"; }
export interface SeriesResponse {
  zip: string; metric: Metric; points: SeriesPoint[]; run_id?: string | null;
  backtest_mape?: number | null; naive_mape?: number | null; beats_naive?: boolean | null;
}

export interface CheckRequest {
  address: string; zip?: string | null; lowest_rent_12mo: number; new_rent: number; effective_date: string;
  year_built?: number | null; property_type?: PropertyType; got_exemption_notice?: boolean | null;
  owner_is_corporate?: boolean | null; other_exemption?: boolean; increases_last_12mo?: number; is_demo?: boolean;
}
export interface CheckResponse {
  check_id: string; verdict: Verdict; cap_pct?: number | null; max_legal_rent?: number | null;
  increase_pct: number; overage_monthly?: number | null; overage_yearly?: number | null;
  third_increase: boolean; reasons: string[]; disclaimer: string;
}
export interface LetterResponse {
  check_id: string; lang: Lang; explanation?: string | null; letter_en?: string | null; figures: string[]; disclaimer: string;
}

export interface UnitMatch { property_id: number; address_norm: string; unit_label?: string | null; zip: string; beds?: number | null; year_built?: number | null; property_type?: string | null; }
export interface UnitSearchResponse { query: string; results: UnitMatch[]; }

export interface ListingEvalRequest {
  zip: string; beds: number; asking_rent: number; baths?: number | null; sqft?: number | null; year_built?: number | null;
  property_type?: PropertyType; lat?: number | null; lng?: number | null; text?: string | null;
}
export interface FairRentEstimate { low: number; expected: number; high: number; method: EstimateMethod; mae_usd?: number | null; coverage_80?: number | null; }
export interface ListingEvalResponse {
  estimate: FairRentEstimate; asking_rent: number; label: FairRentLabel; percentile?: number | null;
  n_comparables: number; parsed_fields?: Record<string, unknown> | null; disclaimer: string;
}

export interface RankRequest { persona: Persona; budget_usd: number; beds?: number | null; weights?: Record<string, number> | null; }
export interface Contribution { feature: string; label: string; points: number; value?: number | null; }
export interface RankedZip { rank: number; zip: string; name: string; score: number; price_usd?: number | null; top_contributions: Contribution[]; summary?: string | null; }
export interface RankResponse { persona: Persona; budget_usd: number; beds?: number | null; weights: Record<string, number>; ranked: RankedZip[]; stretch: RankedZip[]; disclaimer: string; }

export interface PricePositionRequest {
  zip: string; beds: number; target_rent: number; baths?: number | null; sqft?: number | null; year_built?: number | null;
  property_type?: PropertyType; occupied?: boolean; lowest_rent_12mo?: number | null; effective_date?: string | null;
  got_exemption_notice?: boolean | null; owner_is_corporate?: boolean | null;
}
export interface PricePoint { label: "low" | "expected" | "high" | "target"; rent_usd: number; percentile?: number | null; reach_score?: number | null; }
export interface DaysOnMarket { below_expected_median_days?: number | null; above_expected_median_days?: number | null; n_listings: number; }
export interface LegalGuardrail { verdict: Verdict; cap_pct?: number | null; max_legal_rent?: number | null; reasons: string[]; }
export interface PricePositionResponse {
  estimate: FairRentEstimate; points: PricePoint[]; n_comparables: number;
  days_on_market?: DaysOnMarket | null; legal?: LegalGuardrail | null; disclaimer: string;
}

export interface ListingAnalysisRequest { zip: string; beds: number; text?: string | null; listing_id?: number | null; target_rent?: number | null; }
export interface Gap { fact: string; share_of_comparables: number; }
export interface ListingAnalysisResponse {
  completeness: number; readability: number; reach_score: number; stated: Record<string, boolean>;
  gaps: Gap[]; n_comparables: number; explanation?: string | null; disclaimer: string;
}
