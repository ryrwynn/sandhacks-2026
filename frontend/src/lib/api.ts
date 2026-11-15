import type { Filters, Listing, Market } from "./types";
import { AREAS, MOCK_LISTINGS, mockMarket } from "./mock";
import type * as C from "./api.generated";
import type { Lang, Metric } from "./contract";
import { MOCK } from "./mockdata";
import { markMock } from "./mockflag";

const USE_API = process.env.NEXT_PUBLIC_USE_API === "true";

function qs(f: Filters) {
  const p = new URLSearchParams({ area: f.area, beds: f.beds, type: f.type, max_price: String(f.maxPrice) });
  return p.toString();
}

// GET /api/market?area=&beds=&type=  -> Market  (medians computed in SQL)
export async function getMarket(f: Filters): Promise<Market> {
  if (USE_API) return (await fetch(`/api/market?${qs(f)}`)).json();
  return mockMarket(Math.max(0, AREAS.indexOf(f.area)), f.beds);
}

// GET /api/listings?area=&beds=&type=&max_price= -> Listing[]  (with price_history)
export async function getListings(f: Filters): Promise<Listing[]> {
  if (USE_API) return (await fetch(`/api/listings?${qs(f)}`)).json();
  return MOCK_LISTINGS.filter(
    (l) =>
      l.area === f.area &&
      (f.beds === "any" || l.beds === Number(f.beds)) &&
      (f.type === "any" || l.type === f.type) &&
      (f.maxPrice === 0 || l.rent <= f.maxPrice)
  );
}

// GET /api/listings?ids=1,2,3
export async function getListingsByIds(ids: string[]): Promise<Listing[]> {
  if (USE_API) return (await fetch(`/api/listings?ids=${ids.join(",")}`)).json();
  return MOCK_LISTINGS.filter((l) => ids.includes(l.id));
}

// ---------------------------------------------------------------------------
// RentWatch contract endpoints (docs/PLAN.md "API contract and pages").
// Browser: relative /api/... (Caddy strips the prefix in production; next.config rewrites locally).
// Server: API_INTERNAL_URL read at request time, no /api prefix.
// If the API is unreachable, or NEXT_PUBLIC_USE_MOCKS=true, the contract fixtures are served and the
// result is registered with isMock() so pages can label it as sample data.
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

async function call<T extends object>(path: string, fixture: T, init?: RequestInit): Promise<T> {
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
      // A POST answer is about the user's own numbers: show the API's error, never sample data.
      if (init?.method === "POST") {
        const detail = await res.json().then((j) => j?.detail, () => null);
        throw new ApiError(typeof detail === "string" ? detail : `Request failed (${res.status}). Please check your entries.`, res.status);
      }
      return mock();
    }
    return (await res.json()) as T;
  } catch (e) {
    if (e instanceof ApiError) throw e;
    return mock();   // API unreachable or timed out: labeled sample data
  }
}

const post = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });

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
