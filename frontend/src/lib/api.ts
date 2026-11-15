import type * as C from "./api.generated";
import type { Lang, Metric } from "./contract";
import type { ListingDetail, ListingsResponse, ListingSummary, MarketResponse, ListingSort, MarketRange } from "./tracker";
import { MOCK } from "./mockdata";
import { markMock } from "./mockflag";

// ---------------------------------------------------------------------------
// RentOrKnot contract endpoints (docs/PLAN.md "API contract and pages").
// Browser: relative /api/... (Caddy strips the prefix in production; next.config rewrites locally).
// Server: API_INTERNAL_URL read at request time, no /api prefix.
// Live data only: if the API is unreachable or answers with an error, the call throws ApiError and the page
// shows an error state (never sample numbers). NEXT_PUBLIC_USE_MOCKS=true (local UI work only) serves the
// contract fixtures instead, registered with isMock() so pages label them as sample data.
// ---------------------------------------------------------------------------
const FORCE_MOCKS = process.env.NEXT_PUBLIC_USE_MOCKS === "true";
const mocked = new WeakSet<object>();

export function isMock(x: unknown): boolean {
  return typeof x === "object" && x !== null && mocked.has(x);
}

function base(): string {
  if (typeof window !== "undefined") return "/api";
  return process.env.API_INTERNAL_URL || "http://localhost:8000";
}

function serveMock<T extends object>(fixture: T): T {
  // Fresh copy so each result is its own object (and can be tracked in the WeakSet).
  const copy = structuredClone(fixture);
  mocked.add(copy);
  if (typeof window !== "undefined") markMock();
  return copy;
}

/** The API answered with an error (e.g. 422 bad input, 503 not enough data). Never replaced by sample data. */
export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

/** A message a form can show for an error thrown by one of these calls. */
export function errorMessage(e: unknown): string {
  return e instanceof ApiError ? e.message : "Something went wrong. Please try again.";
}

export async function call<T extends object>(path: string, fixture: T, init?: RequestInit): Promise<T> {
  const mock = () => serveMock(fixture);
  if (FORCE_MOCKS) return mock();
  try {
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), 8000);
    const res = await fetch(`${base()}${path}`, {
      ...init,
      cache: "no-store",
      signal: ctl.signal,
      headers: init?.body ? { "Content-Type": "application/json" } : undefined,
    });
    clearTimeout(timer);
    if (!res.ok) {
      const detail = await res.json().then((j) => j?.detail, () => null);
      if (init?.method === "POST") {
        throw new ApiError(typeof detail === "string" ? detail : `Request failed (${res.status}). Please check your entries.`, res.status);
      }
      throw new ApiError(res.status === 404 ? "Not found." : "We couldn't load this data right now. Please try again in a moment.", res.status);
    }
    return (await res.json()) as T;
  } catch (e) {
    if (e instanceof ApiError) throw e;
    // API unreachable or timed out: an error, never sample data.
    throw new ApiError("We couldn't reach our data service. Please try again in a moment.", 0);
  }
}

export const post = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });

export const getHealth = () => call<C.HealthResponse>("/health", MOCK.health);
export const getZips = () => call<C.ZipsResponse>("/zips", MOCK.zips);
export const getZipProfile = (zip: string) =>
  call<C.ZipProfile>(`/zips/${encodeURIComponent(zip)}`, {
    ...MOCK.zipProfile,
    zip,
    name: MOCK.zips.zips.find((z) => z.zip === zip)?.name ?? MOCK.zipProfile.name,
  });
export const getZipSeries = (zip: string, metric: Metric) =>
  call<C.SeriesResponse>(`/zips/${encodeURIComponent(zip)}/series?metric=${metric}`, {
    ...(metric === "zori" ? MOCK.seriesZori : MOCK.seriesZhvi),
    zip,
  });
export const postCheck = (req: C.CheckRequest) => call<C.CheckResponse>("/checks", MOCK.check, post(req));
export const postLetter = (id: string, lang: Lang) =>
  call<C.LetterResponse>(`/checks/${encodeURIComponent(id)}/letter?lang=${lang}`, { ...MOCK.letter, check_id: id, lang }, post({}));
export const searchUnits = (address: string) =>
  call<C.UnitSearchResponse>(`/units/search?address=${encodeURIComponent(address)}`, { ...MOCK.units, query: address });
export const evaluateListing = (req: C.ListingEvalRequest) =>
  call<C.ListingEvalResponse>("/listings/evaluate", { ...MOCK.evaluate, asking_rent: req.asking_rent }, post(req));
export const rankNeighborhoods = (req: C.RankRequest) =>
  call<C.RankResponse>("/neighborhoods/rank", req.persona === "starter" ? MOCK.rankStarter : MOCK.rankWealth, post(req));
export const getPricePosition = (req: C.PricePositionRequest) =>
  call<C.PricePositionResponse>("/owner/price-position", MOCK.pricePos, post(req));
export const getListingAnalysis = (req: C.ListingAnalysisRequest) =>
  call<C.ListingAnalysisResponse>("/owner/listing-analysis", MOCK.analysis, post(req));

// ---------------------------------------------------------------------------
// Tracker endpoints (docs/DESIGN.md). Same fallback rule as above: sample data only when the API is
// unreachable or errors on a GET, and it is labeled. Nothing is invented in the real path.
// ---------------------------------------------------------------------------
export type ListingSourceFilter = "all" | "listing_sites" | "facebook";
export type UnitTypeFilter = "any" | "entire_unit" | "room" | "sublet";
export type ListingQuery = {
  zip?: string; beds?: string; type?: string; maxPrice?: number; sort?: ListingSort; limit?: number; offset?: number; minObservations?: number;
  source?: ListingSourceFilter; unitType?: UnitTypeFilter;
};

function query(params: Record<string, string | number | undefined | null>) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "" && v !== "any") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}

// The API takes the UI's property-type values as they are (apartment | condo | house).

export const getListings = (q: ListingQuery = {}) => {
  const fx = MOCK.listings;
  const items = fx.items.filter(
    (l) =>
      (!q.zip || l.zip === q.zip) &&
      (q.beds === undefined || q.beds === "any" || l.beds === Number(q.beds)) &&
      (!q.maxPrice || l.current_price_usd <= q.maxPrice) &&
      (!q.source || q.source === "all" || (q.source === "facebook") === (l.source_kind === "social")) &&
      (!q.unitType || q.unitType === "any" || (l.unit_type ?? "entire_unit") === q.unitType),
  );
  return call<ListingsResponse>(
    `/listings${query({ zip: q.zip, beds: q.beds, type: q.type, max_price: q.maxPrice, sort: q.sort, limit: q.limit, offset: q.offset, min_observations: q.minObservations, source: q.source === "all" ? undefined : q.source, unit_type: q.unitType })}`,
    { ...fx, items, total: items.length },
  );
};

export const getListingsByIds = (ids: number[]) =>
  ids.length === 0
    ? Promise.resolve<ListingsResponse>({ items: [], total: 0, limit: 0, offset: 0 })
    : call<ListingsResponse>(`/listings${query({ ids: ids.slice(0, 50).join(",") })}`, {
        ...MOCK.listings,
        items: MOCK.listings.items.filter((l) => ids.includes(l.id)),
      });

/** Sample mode only: the detail fixture is one apartment; other ids get their own summary, with observations taken from its sparkline. */
function mockDetail(id: number): ListingDetail {
  const base = MOCK.listingDetail;
  if (base.id === id) return base;
  const s: ListingSummary | undefined = MOCK.listings.items.find((l) => l.id === id);
  if (!s) return { ...base, id };
  return {
    ...base, ...s,
    observations: s.sparkline.map((p) => ({ date: p.month, event: "history" as const, price_usd: p.price_usd })),
    estimate: null, percentile: null, n_comparables: 0, forecast: null,
  };
}
export const getListing = (id: number) => call<ListingDetail>(`/listings/${id}`, mockDetail(id));

export type MarketQuery = { zip?: string; beds?: string; type?: string; range?: MarketRange; listingSitesOnly?: boolean };
export const getMarket = (q: MarketQuery = {}) =>
  call<MarketResponse>(
    `/market${query({ zip: q.zip, beds: q.beds, type: q.type, range: q.range, listing_sites_only: q.listingSitesOnly ? "true" : undefined })}`,
    { ...MOCK.market, zip: q.zip || null, beds: q.beds && q.beds !== "any" ? Number(q.beds) : null, range: q.range ?? "1y" },
  );
