// Advisor tools: each one calls our API and returns its JSON. Every figure the advisor states
// must come from one of these results (see scorer.ts). Plain objects fail silently in Mastra: use createTool.
import { createTool } from "@mastra/core/tools";
import { z } from "zod";
import { apiCall } from "./api";

/** Keep tool output small for the model: first N items only. */
const brief = <T,>(items: T[] | undefined, n: number) => (items ?? []).slice(0, n);

export const matchListings = createTool({
  id: "match_listings",
  description:
    "Find and rank current rental listings for a plain-language description (budget, beds, area, must-haves). " +
    "Returns the parsed needs, ranked listings with score, reasons and unconfirmed must-haves. Use this first for any 'find me a place' question.",
  inputSchema: z.object({
    text: z.string().min(3).describe("The renter's description, in their own words"),
    limit: z.number().int().min(1).max(10).default(5),
    budget_max_usd: z.number().optional(),
    beds_min: z.number().int().optional(),
  }),
  execute: async (input, ctx) => {
    const r = await apiCall<{ needs: unknown; results: { listing: Record<string, unknown> }[]; n_after_filters: number; method: string; disclaimer: string }>(
      "/match", { method: "POST", body: input, signal: ctx?.abortSignal });
    return r;
  },
});

export const searchListings = createTool({
  id: "search_listings",
  description: "List current rentals in one ZIP, optionally by bedrooms, property type and maximum price.",
  inputSchema: z.object({
    zip: z.string().regex(/^\d{5}$/),
    beds: z.number().int().min(0).max(10).optional(),
    max_price: z.number().optional(),
    type: z.enum(["apartment", "condo", "house"]).optional(),
    sort: z.enum(["recent", "price_asc", "price_desc", "biggest_drop"]).default("price_asc"),
  }),
  execute: async (input, ctx) => {
    const r = await apiCall<{ items: unknown[]; total: number }>("/listings", { query: { ...input, limit: 8 }, signal: ctx?.abortSignal });
    return { total: r.total, items: brief(r.items, 8) };
  },
});

export const marketSnapshot = createTool({
  id: "market_snapshot",
  description: "Median rent trend and forecast for a ZIP (or all covered ZIPs when zip is omitted), from real observations.",
  inputSchema: z.object({
    zip: z.string().regex(/^\d{5}$/).optional(),
    beds: z.number().int().min(0).max(10).optional(),
    range: z.enum(["1m", "3m", "6m", "1y"]).default("1y"),
  }),
  execute: async (input, ctx) => apiCall("/market", { query: input, signal: ctx?.abortSignal }),
});

export const rentIncreaseCheck = createTool({
  id: "rent_increase_check",
  description:
    "Check a California rent increase against AB 1482 (the state cap). The verdict comes from the rules engine, never from you.",
  inputSchema: z.object({
    address: z.string(),
    zip: z.string().optional(),
    lowest_rent_12mo: z.number().positive(),
    new_rent: z.number().positive(),
    effective_date: z.string().describe("YYYY-MM-DD"),
    year_built: z.number().int().optional(),
    property_type: z.enum(["apartment", "condo", "single_family", "townhouse", "unknown"]).default("unknown"),
  }),
  execute: async (input, ctx) => apiCall("/checks", { method: "POST", body: input, signal: ctx?.abortSignal }),
});

export const gougingCheck = createTool({
  id: "gouging_check",
  description: "Check a price against California's rent-gouging rule (Penal Code 396) during a declared emergency.",
  inputSchema: z.object({
    zip: z.string().optional(),
    county: z.string().optional(),
    new_rent: z.number().positive(),
    offer_date: z.string().describe("YYYY-MM-DD"),
    pre_emergency_rent: z.number().positive().optional(),
    beds: z.number().int().min(0).optional(),
  }),
  execute: async (input, ctx) => apiCall("/checks/gouging", { method: "POST", body: input, signal: ctx?.abortSignal }),
});

export const zipSeries = createTool({
  id: "zip_series",
  description: "Monthly history and forecast cone for one ZIP and metric (zori = rent index, zhvi = home value index).",
  inputSchema: z.object({
    zip: z.string().regex(/^\d{5}$/),
    metric: z.enum(["zori", "zhvi"]).default("zori"),
    scenario: z.enum(["baseline", "recession", "growth"]).optional(),
  }),
  execute: async (input, ctx) => {
    const { zip, ...query } = input;
    return apiCall(`/zips/${zip}/series`, { query, signal: ctx?.abortSignal });
  },
});

export const advisorTools = { matchListings, searchListings, marketSnapshot, rentIncreaseCheck, gougingCheck, zipSeries };
