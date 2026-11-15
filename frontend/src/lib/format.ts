export const usd = (n: number | null | undefined, digits = 0) =>
  n == null ? "n/a" : n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: digits, minimumFractionDigits: digits });

export const pct = (n: number | null | undefined, digits = 1, signed = false) =>
  n == null ? "n/a" : `${signed && n > 0 ? "+" : ""}${n.toFixed(digits)}%`;

export const monthLabel = (iso: string) => {
  const d = new Date(iso + "T00:00:00Z");
  return d.toLocaleDateString("en-US", { month: "short", year: "2-digit", timeZone: "UTC" });
};

// The 12 ZIPs in data/zips.txt.
export const ZIP_OPTIONS: { zip: string; name: string }[] = [
  { zip: "91910", name: "Chula Vista" },
  { zip: "92101", name: "Downtown" },
  { zip: "92103", name: "Hillcrest" },
  { zip: "92104", name: "North Park" },
  { zip: "92105", name: "City Heights" },
  { zip: "92107", name: "Ocean Beach" },
  { zip: "92108", name: "Mission Valley" },
  { zip: "92109", name: "Pacific Beach" },
  { zip: "92111", name: "Linda Vista" },
  { zip: "92117", name: "Clairemont" },
  { zip: "92122", name: "University City" },
  { zip: "92126", name: "Mira Mesa" },
];

// Shading value for a ZIP on the map: typical rent (ZORI), else the 1-bedroom listing median.
export const rentOf = (z: { typical_rent_usd?: number | null; median_rent_by_beds: Record<string, number | null> }) =>
  z.typical_rent_usd ?? z.median_rent_by_beds["1"] ?? null;
