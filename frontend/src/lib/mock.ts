import type { Listing, Market } from "./types";

export const AREAS = ["La Jolla, CA", "Pacific Beach, CA", "North Park, CA", "Downtown, CA"];

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const BASE = [2700, 2725, 2715, 2755, 2795, 2815, 2845, 2875, 2895, 2870, 2858, 2850];

export function mockMarket(areaIdx: number, beds: string): Market {
  const bump = areaIdx * -120 + (beds === "any" ? 0 : (Number(beds) - 1) * 650);
  return {
    series: MONTHS.map((month, i) => ({ month, median: BASE[i] + bump })),
    activeListings: 1248 - areaIdx * 130,
    updated: "Dec 31, 2025",
  };
}

const L = (id: string, address: string, area: string, beds: number, sqft: number, type: string, history: number[]): Listing => ({
  id, address, area, beds, sqft, type, rent: history[history.length - 1], history,
  historyStart: "Jul 2025", historyEnd: "Dec 2025",
});

export const MOCK_LISTINGS: Listing[] = [
  L("1", "1000 California St", "La Jolla, CA", 1, 720, "apartment", [3050, 3050, 2995, 2995, 2950, 2950]),
  L("2", "7550 Draper Ave", "La Jolla, CA", 1, 680, "apartment", [2850, 2850, 2800, 2800, 2750, 2750]),
  L("3", "8440 Via Mallorca", "La Jolla, CA", 1, 700, "condo", [2950, 2950, 2900, 2900, 2850, 2850]),
  L("4", "3250 Via Marin", "La Jolla, CA", 1, 760, "apartment", [3200, 3200, 3150, 3150, 3100, 3100]),
  L("5", "8500 Costa Verde", "La Jolla, CA", 1, 740, "apartment", [3095, 3095, 3050, 3050, 2995, 2995]),
  L("6", "8650 Genesee Ave", "La Jolla, CA", 1, 650, "apartment", [2750, 2750, 2700, 2700, 2650, 2650]),
  L("7", "7600 Fay Ave", "La Jolla, CA", 1, 810, "house", [3350, 3350, 3300, 3300, 3250, 3250]),
  L("8", "8889 Caminito Plaza", "La Jolla, CA", 1, 620, "apartment", [2695, 2695, 2650, 2650, 2595, 2595]),
  L("9", "4500 Ocean Blvd", "Pacific Beach, CA", 2, 980, "condo", [3600, 3600, 3550, 3550, 3500, 3495]),
];
