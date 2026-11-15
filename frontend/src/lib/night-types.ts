// The overnight endpoint types, now taken from the generated contract (scripts/gen-api-types.py).
// Kept as a module so components can import from one place; the aliases below name unions the generator inlines.
import type * as G from "./api.generated";

export type {
  SeriesPoint, ScenarioPath, AreaSummary, AreasResponse, AreaRequestCreate, AreaRequestStatus, GeoFile,
  GeoZipsResponse, TrendSignal, TrendMetrics, ZipTrendsResponse, PriceChange, ListingTrendsResponse, Link,
  GougingRequest, EmergencyInfo, GougingResponse, MatchRequest, ParsedNeeds, MatchResult, MatchResponse,
  OwnerReachRequest, ReachProfile, ReachPoint, ReachChange, OwnerReachResponse,
} from "./api.generated";

export type Scenario = G.ScenarioPath["scenario"];
export type SeriesScenarioResponse = G.SeriesResponse;
export type Tier = G.AreaSummary["tier"];
export type GeoType = G.AreaSummary["geo_type"];
export type AreaRequestState = G.AreaRequestStatus["status"];
export type SignalKind = G.TrendSignal["kind"];
export type GougingVerdict = G.GougingResponse["verdict"];
