// Tracker endpoint types, mirroring the bottom of contracts/api_models.py (GET /listings, /listings/{id}, /market).
// When api.generated.ts is regenerated from /api/openapi.json these names appear there too; switch the
// imports over and delete this block of types then. Everything below the types is UI helpers.
import type { FairRentEstimate, FairRentLabel } from "./contract";

export type ObservationEvent = "history" | "seen" | "price_change" | "removed" | "posted";
export type MarketRange = "1m" | "3m" | "6m" | "1y" | "all";
export type ListingSort = "recent" | "price_asc" | "price_desc" | "biggest_drop";

export interface SparkPoint { month: string; price_usd: number }

export interface ListingSummary {
  id: number;
  address?: string | null;
  unit_label?: string | null;
  neighborhood?: string | null;
  zip?: string | null;
  beds?: number | null;
  baths?: number | null;
  sqft?: number | null;
  property_type?: string | null;
  listing_type: "rent" | "sale";
  current_price_usd: number;
  first_price_usd: number;
  first_observed: string;
  n_observations: number;
  sparkline: SparkPoint[];
  fair_rent_label?: FairRentLabel | null;
  last_seen: string;
  active: boolean;
  source_url?: string | null;
}

export interface ListingsResponse { items: ListingSummary[]; total: number; limit: number; offset: number }

export interface Observation { date: string; event: ObservationEvent; price_usd: number }

export interface ZipForecastSummary {
  zip: string;
  name: string;
  metric: "zori" | "zhvi";
  latest_usd?: number | null;
  forecast_12m_usd?: number | null;
  change_pct?: number | null;
  lo80_usd?: number | null;
  hi80_usd?: number | null;
  backtest_mape?: number | null;
  naive_mape?: number | null;
  beats_naive?: boolean | null;
}

export interface ListingDetail extends ListingSummary {
  observations: Observation[];
  year_built?: number | null;
  estimate?: FairRentEstimate | null;
  percentile?: number | null;
  n_comparables: number;
  forecast?: ZipForecastSummary | null;
  disclaimer: string;
}

export interface MarketPoint { month: string; value: number; basis: "zori" | "listings"; n_listings?: number | null }
export interface MarketForecastPoint { month: string; value: number; lo80: number; hi80: number }

export interface MarketResponse {
  zip?: string | null;
  beds?: number | null;
  property_type?: string | null;
  range: MarketRange;
  points: MarketPoint[];
  forecast: MarketForecastPoint[];
  current_value?: number | null;
  change_pct?: number | null;
  change_since?: string | null;
  active_listings: number;
  updated_at?: string | null;
  backtest_mape?: number | null;
  naive_mape?: number | null;
  beats_naive?: boolean | null;
  notes: string[];
  disclaimer: string;
}

// ---- helpers ----
export const bedsText = (beds: number | null | undefined) => (beds == null ? null : beds === 0 ? "Studio" : `${beds} bed`);

export const FAIR_LABEL: Record<FairRentLabel, string> = {
  in_range: "In typical range",
  above_typical_range: "Above typical range",
  below_typical_range: "Below typical range",
};

/** Change since tracking started, with words so color is never the only signal. */
export function changeOf(now: number, then: number) {
  const diff = now - then;
  const pct = then ? Math.abs(diff / then) * 100 : 0;
  return {
    diff,
    pct,
    dir: diff < 0 ? ("down" as const) : diff > 0 ? ("up" as const) : ("flat" as const),
    arrow: diff < 0 ? "↓" : diff > 0 ? "↑" : "→",
  };
}

export function fmtDate(iso: string | null | undefined, opts: Intl.DateTimeFormatOptions = { month: "short", day: "numeric", year: "numeric" }) {
  if (!iso) return "";
  const d = new Date(iso.length <= 10 ? iso + "T00:00:00Z" : iso);
  return d.toLocaleDateString("en-US", { ...opts, timeZone: "UTC" });
}
export const fmtMonth = (iso: string) => fmtDate(iso, { month: "short", year: "numeric" });
