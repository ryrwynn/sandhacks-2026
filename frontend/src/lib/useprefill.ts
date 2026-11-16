"use client";
import { useSearchParams } from "next/navigation";
import { HOME_TYPES, YES_NO } from "./prefill";

/**
 * Reads the prefill query parameters (lib/prefill.ts, the shared table) for a form's first render.
 * Each reader returns "" when the parameter is missing or not valid, so a form keeps its own default.
 * Forms only fill their fields from these; none of them submits. The page using this needs a Suspense boundary.
 */
export function usePrefill() {
  const q = useSearchParams();
  const get = (k: string) => q.get(k)?.trim() ?? "";
  const match = (k: string, re: RegExp) => { const v = get(k); return re.test(v) ? v : ""; };
  return {
    zip: (k = "zip") => match(k, /^\d{5}$/),
    /** A positive number such as 2350 or 1.5. */
    num: (k: string) => { const v = match(k, /^\d{1,9}(\.\d{1,2})?$/); return v && Number(v) > 0 ? v : ""; },
    /** Zero or more, whole: bedrooms (0 = studio), increases. */
    int: (k: string) => match(k, /^\d{1,4}$/),
    year: (k = "year") => match(k, /^(1[89]|20)\d{2}$/),
    date: (k: string) => match(k, /^\d{4}-\d{2}-\d{2}$/),
    yesNo: (k: string) => { const v = get(k); return (YES_NO as readonly string[]).includes(v) && v !== "unsure" ? v : "";   // "unsure" is the pickers' "I don't know" (empty)
    },
    homeType: (k = "type") => { const v = get(k); return (HOME_TYPES as readonly string[]).includes(v) ? v : ""; },
    text: (k: string, max = 4000) => get(k).slice(0, max),
    /** Bedrooms 0 to 3 as the pickers offer them. */
    beds: (k = "beds") => match(k, /^[0-3]$/),
    has: (k: string) => q.has(k),
  };
}
