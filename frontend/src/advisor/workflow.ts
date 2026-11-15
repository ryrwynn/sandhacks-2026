// Multi-step workflow: parse needs -> search -> rank -> explain. Each step calls our API; the
// explanation is written from the ranked results only, so every figure in it comes from them.
import { createStep, createWorkflow } from "@mastra/core/workflows";
import { z } from "zod";
import { apiCall } from "./api";

const Needs = z.object({
  budget_max_usd: z.number().nullable().optional(),
  beds_min: z.number().nullable().optional(),
  zips: z.array(z.string()).default([]),
  must_haves: z.array(z.string()).default([]),
}).passthrough();

type Result = { listing: { id: number; address?: string | null; neighborhood?: string | null; beds?: number | null; current_price_usd: number }; score: number; reasons: string[]; unconfirmed: string[] };

const parseNeeds = createStep({
  id: "parse-needs",
  description: "Turn the description into constraints (budget, beds, areas, must-haves).",
  inputSchema: z.object({ text: z.string() }),
  outputSchema: z.object({ text: z.string(), needs: Needs }),
  execute: async ({ inputData }) => {
    const r = await apiCall<{ needs: z.infer<typeof Needs> }>("/match", { method: "POST", body: { text: inputData.text, limit: 1 } });
    return { text: inputData.text, needs: r.needs };
  },
});

const search = createStep({
  id: "search",
  description: "Count current listings that pass the hard filters.",
  inputSchema: z.object({ text: z.string(), needs: Needs }),
  outputSchema: z.object({ text: z.string(), needs: Needs, in_area: z.number() }),
  execute: async ({ inputData }) => {
    const { needs } = inputData;
    const zip = needs.zips[0];
    if (!zip) return { ...inputData, in_area: 0 };
    const r = await apiCall<{ total: number }>("/listings", {
      query: { zip, beds: needs.beds_min ?? undefined, max_price: needs.budget_max_usd ?? undefined, limit: 1 } });
    return { ...inputData, in_area: r.total };
  },
});

const rank = createStep({
  id: "rank",
  description: "Rank the listings against the needs.",
  inputSchema: z.object({ text: z.string(), needs: Needs, in_area: z.number() }),
  outputSchema: z.object({ needs: Needs, results: z.array(z.any()), n_after_filters: z.number(), method: z.string() }),
  execute: async ({ inputData }) => {
    const r = await apiCall<{ results: Result[]; n_after_filters: number; method: string }>(
      "/match", { method: "POST", body: { text: inputData.text, limit: 5 } });
    return { needs: inputData.needs, results: r.results, n_after_filters: r.n_after_filters, method: r.method };
  },
});

const explain = createStep({
  id: "explain",
  description: "Write the answer from the ranked results only.",
  inputSchema: z.object({ needs: Needs, results: z.array(z.any()), n_after_filters: z.number(), method: z.string() }),
  outputSchema: z.object({ answer: z.string(), listing_ids: z.array(z.number()) }),
  execute: async ({ inputData }) => {
    const results = inputData.results as Result[];
    if (!results.length) return { answer: "I found no current listings that pass those filters. Try a higher budget or another area.", listing_ids: [] };
    const lines = results.map((r, i) => {
      const l = r.listing;
      const where = [l.address, l.neighborhood].filter(Boolean).join(", ");
      const un = r.unconfirmed.length ? ` Not stated in the listing: ${r.unconfirmed.join(", ")}.` : "";
      return `${i + 1}. ${where || `Listing ${l.id}`}, $${l.current_price_usd.toLocaleString("en-US")} a month, score ${r.score}. ${r.reasons.join(" ")}${un}`;
    });
    return { answer: `${inputData.n_after_filters} listings pass your filters. Best matches:\n${lines.join("\n")}`, listing_ids: results.map((r) => r.listing.id) };
  },
});

export const findByNeeds = createWorkflow({
  id: "find-by-needs",
  inputSchema: z.object({ text: z.string() }),
  outputSchema: z.object({ answer: z.string(), listing_ids: z.array(z.number()) }),
})
  .then(parseNeeds)
  .then(search)
  .then(rank)
  .then(explain)
  .commit();
