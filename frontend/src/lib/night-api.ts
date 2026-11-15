import { call, post } from "./api";
import type { Metric } from "./contract";
import type * as N from "./night-types";
import seriesScen from "@/mocks/zip_series_scenarios.json";
import areas from "@/mocks/areas.json";
import areaReq from "@/mocks/area_request.json";
import geoZips from "@/mocks/geo_zips.json";
import zipTrends from "@/mocks/zip_trends.json";
import listingTrends from "@/mocks/listing_trends.json";
import gouging from "@/mocks/gouging.json";
import match from "@/mocks/match.json";
import ownerReach from "@/mocks/owner_reach.json";

// Overnight endpoints. Each falls back to its fixture (labeled sample data) when the API is unreachable,
// errors on a GET, or answers 501 (a stub). call() in api.ts handles all three.
const as = <T,>(x: unknown) => x as T;
const q = (p: Record<string, string | number | undefined | null>) => {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(p)) if (v !== undefined && v !== null && v !== "") s.set(k, String(v));
  const t = s.toString();
  return t ? `?${t}` : "";
};

export const getZipSeriesScenarios = (zip: string, metric: Metric, scenario: N.Scenario = "baseline") =>
  call<N.SeriesScenarioResponse>(`/zips/${encodeURIComponent(zip)}/series${q({ metric, scenario })}`, { ...as<N.SeriesScenarioResponse>(seriesScen), zip, metric });

export const getAreas = (p: { tier?: N.Tier; county?: string; q?: string; limit?: number } = {}) =>
  call<N.AreasResponse>(`/areas${q(p)}`, as<N.AreasResponse>(areas));

export const requestArea = (query: string) =>
  call<N.AreaRequestStatus>("/areas/requests", { ...as<N.AreaRequestStatus>(areaReq), query, name: query }, post({ query }));

export const getAreaRequest = (id: string) =>
  call<N.AreaRequestStatus>(`/areas/requests/${encodeURIComponent(id)}`, as<N.AreaRequestStatus>(areaReq));

export const getGeoZips = (bbox: number[]) =>
  call<N.GeoZipsResponse>(`/geo/zips?bbox=${bbox.map((n) => n.toFixed(4)).join(",")}`, { ...as<N.GeoZipsResponse>(geoZips), bbox });

export const getZipTrends = (zip: string) =>
  call<N.ZipTrendsResponse>(`/zips/${encodeURIComponent(zip)}/trends`, { ...as<N.ZipTrendsResponse>(zipTrends), zip });

export const getListingTrends = (id: number) =>
  call<N.ListingTrendsResponse>(`/listings/${id}/trends`, { ...as<N.ListingTrendsResponse>(listingTrends), listing_id: id });

export const postGouging = (req: N.GougingRequest) =>
  call<N.GougingResponse>("/checks/gouging", as<N.GougingResponse>(gouging), post(req));

export const postMatch = (req: N.MatchRequest) =>
  call<N.MatchResponse>("/match", as<N.MatchResponse>(match), post(req));

export const postOwnerReach = (req: N.OwnerReachRequest) =>
  call<N.OwnerReachResponse>("/owner/reach", as<N.OwnerReachResponse>(ownerReach), post(req));
