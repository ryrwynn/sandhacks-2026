import type { Filters, Listing, Market } from "./types";
import { AREAS, MOCK_LISTINGS, mockMarket } from "./mock";

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
