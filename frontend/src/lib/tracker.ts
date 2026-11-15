// Tracker endpoint types come from api.generated.ts (regenerate with scripts/gen-api-types.py after any change to
// contracts/api_models.py). Everything below is UI helpers.
import type { FairRentLabel } from "./contract";
import type {
  ListingDetail, ListingsResponse, ListingSummary, MarketForecastPoint, MarketPoint, MarketResponse, Observation,
  SparkPoint, ZipForecastSummary,
} from "./api.generated";

export type {
  ListingDetail, ListingsResponse, ListingSummary, MarketForecastPoint, MarketPoint, MarketResponse, Observation,
  SparkPoint, ZipForecastSummary,
};
export type ObservationEvent = Observation["event"];
export type MarketRange = MarketResponse["range"];
export type ListingSort = "recent" | "price_asc" | "price_desc" | "biggest_drop";

// ---- helpers ----
export const bedsText = (beds: number | null | undefined) => (beds == null ? null : beds === 0 ? "Studio" : `${beds} bed`);

export const FAIR_LABEL: Record<FairRentLabel, string> = {
  in_range: "In typical range",
  above_typical_range: "Above typical range",
  below_typical_range: "Below typical range",
};

/** Change since tracking started, with words so color is never the only signal. */
export function changeOf(now: number, then: number) {
  const diff = now - then;
  const pct = then ? Math.abs(diff / then) * 100 : 0;
  return {
    diff,
    pct,
    dir: diff < 0 ? ("down" as const) : diff > 0 ? ("up" as const) : ("flat" as const),
    arrow: diff < 0 ? "↓" : diff > 0 ? "↑" : "→",
  };
}

export function fmtDate(iso: string | null | undefined, opts: Intl.DateTimeFormatOptions = { month: "short", day: "numeric", year: "numeric" }) {
  if (!iso) return "";
  const d = new Date(iso.length <= 10 ? iso + "T00:00:00Z" : iso);
  return d.toLocaleDateString("en-US", { ...opts, timeZone: "UTC" });
}
export const fmtMonth = (iso: string) => fmtDate(iso, { month: "short", year: "numeric" });

// ---- Facebook group listings (morning run) ----
export const isFacebook = (l: Pick<ListingSummary, "source_kind">) => l.source_kind === "social";
export const FB_BADGE = "Facebook group · lower confidence";
export const UNIT_TYPE_TEXT: Record<NonNullable<ListingSummary["unit_type"]>, string> = {
  entire_unit: "Whole unit", room: "Room", sublet: "Sublet",
};

/** Address for listing sites; for Facebook, a title built from extracted fields ("2-bed apartment in North Park"). */
export function listingTitle(l: ListingSummary): string {
  if (!isFacebook(l)) return [l.address ?? "Address not listed", l.unit_label ? `#${l.unit_label}` : null].filter(Boolean).join(" ");
  const hood = l.neighborhood && l.neighborhood === l.neighborhood.toLowerCase()   // "mira mesa" -> "Mira Mesa"
    ? l.neighborhood.replace(/\b\p{L}/gu, (c) => c.toUpperCase()) : l.neighborhood;
  const where = hood ?? l.zip ?? "San Diego";
  const size = l.beds == null ? null : l.beds === 0 ? "Studio" : `${l.beds}-bed`;
  if (l.unit_type === "room") return `Room in ${where}`;
  if (l.unit_type === "sublet") return `${size ? size + " sublet" : "Sublet"} in ${where}`;
  return `${size ? (l.beds === 0 ? "Studio apartment" : `${size} apartment`) : "Apartment"} in ${where}`;
}

export const AMENITY_TEXT: Record<string, string> = {
  pets_allowed: "Pets allowed", parking: "Parking", laundry: "Laundry", utilities_included: "Utilities included",
};
