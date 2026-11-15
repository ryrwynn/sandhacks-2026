export type Filters = {
  zip: string;        // "" = all 12 ZIPs
  beds: string;       // "any" | "0" | "1" | "2" | "3"
  type: string;       // "any" | "apartment" | "condo" | "house"
  maxPrice: number;   // 0 = no limit
};
export const DEFAULT_FILTERS: Filters = { zip: "", beds: "any", type: "any", maxPrice: 0 };
