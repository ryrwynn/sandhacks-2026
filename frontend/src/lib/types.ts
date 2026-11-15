export type Filters = {
  area: string;
  beds: string;       // "any" | "0" | "1" | "2" | "3"
  type: string;       // "any" | "apartment" | "condo" | "house"
  maxPrice: number;   // 0 = no limit
};

export type MarketPoint = { month: string; median: number };

export type Market = {
  series: MarketPoint[];
  activeListings: number;
  updated: string;
};

export type Listing = {
  id: string;
  address: string;
  area: string;
  beds: number;
  sqft: number;
  type: string;
  rent: number;
  history: number[]; // monthly asking rent, oldest first
  historyStart: string;
  historyEnd: string;
};

export const DEFAULT_FILTERS: Filters = { area: "La Jolla, CA", beds: "1", type: "any", maxPrice: 0 };
