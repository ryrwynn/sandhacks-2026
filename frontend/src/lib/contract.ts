// API types come from api.generated.ts (scripts/gen-api-types.py, from /api/openapi.json).
// This file keeps the names the components import, plus enum aliases and the disclaimers.
import type * as G from "./api.generated";

export type {
  AmenityCounts,
  CheckRequest,
  CheckResponse,
  Contribution,
  DaysOnMarket,
  FairRentEstimate,
  Gap,
  HealthResponse,
  LegalGuardrail,
  LetterResponse,
  ListingAnalysisRequest,
  ListingAnalysisResponse,
  ListingEvalRequest,
  ListingEvalResponse,
  ModelRunSummary,
  PricePoint,
  PricePositionRequest,
  PricePositionResponse,
  RankRequest,
  RankResponse,
  RankedZip,
  SeriesPoint,
  SeriesResponse,
  UnitMatch,
  UnitSearchResponse,
  ZipProfile,
  ZipSummary,
  ZipsResponse,
} from "./api.generated";

export type Verdict = G.CheckResponse["verdict"];
export type Persona = G.RankRequest["persona"];
export type Metric = G.SeriesResponse["metric"];
export type Lang = G.LetterResponse["lang"];
export type PropertyType = NonNullable<G.CheckRequest["property_type"]>;
export type FairRentLabel = G.ListingEvalResponse["label"];
export type EstimateMethod = G.FairRentEstimate["method"];

export const DISCLAIMER_LEGAL =
  "This is not legal advice. For help with a rent increase, contact the Legal Aid Society of San Diego (lassd.org, 877-534-2524).";
export const DISCLAIMER_ESTIMATE = "Estimates with ranges from public data, not financial advice or measured results.";
