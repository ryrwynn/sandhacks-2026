export type Filters = {
  zip: string;        // "" = all 12 ZIPs
  beds: string;       // "any" | "0" | "1" | "2" | "3"
  type: string;       // "any" | "apartment" | "condo" | "house"
  maxPrice: number;   // 0 = no limit
  source?: "all" | "listing_sites" | "facebook";
  unitType?: "any" | "entire_unit" | "room" | "sublet";
};
export const DEFAULT_FILTERS: Filters = { zip: "", beds: "any", type: "any", maxPrice: 0, source: "all", unitType: "any" };
